"""Shared ElevenLabs HTTP client used by both the voice-clone and script-gen tools.

Hardened (Step 7) with:
  * per-call timeouts (configurable);
  * exponential-backoff retries for 429 + 5xx (and 408), never for other 4xx;
  * specific exception classes (auth / bad-audio / quota / rate-limit / timeout);
  * redacted logging (never logs the key or audio bytes — only status codes,
    voice_ids, and timing);
  * response schema validation (bad shapes raise ``BadResponseError``);
  * an atomic audio-write helper.

The client takes only what it needs (api_key, optional session) so tests can
inject a mocked ``requests.Session`` or use the ``responses`` library.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import requests


CLONE_URL = "https://api.elevenlabs.io/v1/voices/add"
VOICE_DETAIL_URL = "https://api.elevenlabs.io/v1/voices/{voice_id}"
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
LIST_VOICES_URL = "https://api.elevenlabs.io/v1/voices"

# Statuses worth retrying: rate limit, request timeout, and transient 5xx.
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}


class ElevenLabsError(RuntimeError):
    """Base error for any non-success ElevenLabs interaction."""

    def __init__(self, status_code: int | None, body: str):
        super().__init__(f"ElevenLabs API error {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class AuthError(ElevenLabsError):
    """401 — invalid or missing API key."""


class BadAudioError(ElevenLabsError):
    """422 — the uploaded audio was rejected."""


class QuotaError(ElevenLabsError):
    """402/403 — out of quota / forbidden."""


class RateLimitError(ElevenLabsError):
    """429 — rate limited (after retries are exhausted)."""


class Timeout(ElevenLabsError):
    """408 or a client-side request timeout."""


class BadResponseError(ElevenLabsError):
    """A 200 response whose body didn't match the expected schema."""


def _map_status(status_code: int, body: str) -> ElevenLabsError:
    if status_code == 401:
        return AuthError(status_code, body)
    if status_code == 422:
        return BadAudioError(status_code, body)
    if status_code in (402, 403):
        return QuotaError(status_code, body)
    if status_code == 429:
        return RateLimitError(status_code, body)
    if status_code == 408:
        return Timeout(status_code, body)
    return ElevenLabsError(status_code, body)


def write_audio_atomic(path: Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` atomically (tmp + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return path


class ElevenLabsClient:
    def __init__(
        self,
        api_key: str,
        session: requests.Session | None = None,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        log_fn: Callable[[str], None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        backoff_base: float = 0.5,
    ):
        if not api_key:
            raise ValueError("ElevenLabsClient requires a non-empty api_key.")
        self.api_key = api_key
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.log_fn = log_fn
        self.sleep_fn = sleep_fn
        self.backoff_base = backoff_base

    # ---- internals --------------------------------------------------------

    def _headers(self, accept_audio: bool = False) -> dict[str, str]:
        headers = {"xi-api-key": self.api_key}
        if accept_audio:
            headers["Accept"] = "audio/mpeg"
        return headers

    def _log(self, msg: str) -> None:
        if self.log_fn is None:
            return
        from hamlet_ai.redaction import redact

        self.log_fn(redact(msg, secrets=[self.api_key]))

    def _backoff(self, attempt: int) -> float:
        return self.backoff_base * (2 ** attempt)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Perform a request with retries; raise a mapped error on failure."""
        response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            start = time.monotonic()
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.Timeout:
                self._log(f"{method} timed out (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    self.sleep_fn(self._backoff(attempt))
                    continue
                raise Timeout(None, "request timed out")
            except requests.RequestException as e:
                self._log(f"{method} connection error (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    self.sleep_fn(self._backoff(attempt))
                    continue
                raise ElevenLabsError(None, str(e))

            elapsed = time.monotonic() - start
            if response.status_code == 200:
                self._log(f"{method} 200 in {elapsed:.2f}s")
                return response
            if response.status_code in RETRY_STATUSES and attempt < self.max_retries:
                self._log(f"{method} {response.status_code}; retrying (attempt {attempt + 1})")
                self.sleep_fn(self._backoff(attempt))
                continue
            self._log(f"{method} {response.status_code} (no retry)")
            raise _map_status(response.status_code, response.text)

        # Retries exhausted on a retryable status.
        assert response is not None
        raise _map_status(response.status_code, response.text)

    # ---- public API -------------------------------------------------------

    def clone_voice(
        self,
        audio_path: str,
        audio_filename: str,
        name: str = "AudienceClone",
        description: str = "Live audience voice clone",
        content_type: str = "audio/mpeg",
    ) -> str:
        # Read bytes once so retries can re-send the same payload.
        with open(audio_path, "rb") as fh:
            audio_bytes = fh.read()
        files = {"files": (audio_filename, audio_bytes, content_type)}
        data = {"name": name, "description": description}
        response = self._request(
            "POST", CLONE_URL, headers=self._headers(), files=files, data=data
        )
        try:
            payload = response.json()
        except ValueError as e:
            raise BadResponseError(200, f"clone response was not JSON: {e}") from e
        voice_id = payload.get("voice_id") if isinstance(payload, dict) else None
        if not voice_id:
            raise BadResponseError(200, "missing voice_id in clone response")
        self._log(f"clone ok voice_id={voice_id}")
        return voice_id

    def get_voice_status(self, voice_id: str) -> int:
        """Poll a voice's readiness. Returns the raw status code (404 == not ready).

        Runs inside ``wait_for_voice``'s live poll loop, so a transient network
        blip must not abort the show. We retry connection errors, timeouts, and
        transient server statuses (429/5xx) with backoff. 200 (ready) and 404
        (not ready yet) are the meaningful polling signals and are returned
        immediately without retry.
        """
        url = VOICE_DETAIL_URL.format(voice_id=voice_id)
        response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url, headers=self._headers(), timeout=self.timeout
                )
            except requests.Timeout:
                self._log(f"GET status timed out (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    self.sleep_fn(self._backoff(attempt))
                    continue
                raise Timeout(None, "voice status request timed out")
            except requests.RequestException as e:
                self._log(f"GET status connection error (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    self.sleep_fn(self._backoff(attempt))
                    continue
                raise ElevenLabsError(None, str(e))

            if response.status_code in RETRY_STATUSES and attempt < self.max_retries:
                self._log(
                    f"GET status {response.status_code}; retrying (attempt {attempt + 1})"
                )
                self.sleep_fn(self._backoff(attempt))
                continue
            return response.status_code

        assert response is not None
        return response.status_code

    def synthesize(
        self,
        voice_id: str,
        text: str,
        model_id: str,
        voice_settings: dict[str, Any],
    ) -> bytes:
        response = self._request(
            "POST",
            TTS_URL.format(voice_id=voice_id),
            headers={**self._headers(accept_audio=True), "Content-Type": "application/json"},
            json={"text": text, "model_id": model_id, "voice_settings": voice_settings},
        )
        return response.content

    def list_voices(self) -> list[dict[str, Any]]:
        response = self._request("GET", LIST_VOICES_URL, headers=self._headers())
        try:
            payload = response.json()
        except ValueError as e:
            raise BadResponseError(200, f"list_voices response was not JSON: {e}") from e
        if not isinstance(payload, dict) or "voices" not in payload:
            raise BadResponseError(200, "list_voices response missing 'voices' array")
        return payload.get("voices", [])

    def delete_voice(self, voice_id: str) -> bool:
        self._request(
            "DELETE",
            VOICE_DETAIL_URL.format(voice_id=voice_id),
            headers=self._headers(),
        )
        self._log(f"deleted voice_id={voice_id}")
        return True
