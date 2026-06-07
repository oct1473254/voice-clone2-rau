"""Shared ElevenLabs HTTP client used by both the voice-clone and script-gen tools.

The client intentionally takes only the parameters it needs (api_key, optional
session) so callers can inject a mocked ``requests.Session`` in tests. No module-
level configuration; nothing is imported at module load except the standard
library and ``requests``.
"""
from __future__ import annotations

from typing import Any

import requests


CLONE_URL = "https://api.elevenlabs.io/v1/voices/add"
VOICE_DETAIL_URL = "https://api.elevenlabs.io/v1/voices/{voice_id}"
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
LIST_VOICES_URL = "https://api.elevenlabs.io/v1/voices"


class ElevenLabsError(RuntimeError):
    """Raised when the ElevenLabs API returns a non-success status."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"ElevenLabs API error {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class ElevenLabsClient:
    def __init__(self, api_key: str, session: requests.Session | None = None):
        if not api_key:
            raise ValueError("ElevenLabsClient requires a non-empty api_key.")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _headers(self, accept_audio: bool = False) -> dict[str, str]:
        headers = {"xi-api-key": self.api_key}
        if accept_audio:
            headers["Accept"] = "audio/mpeg"
        return headers

    def clone_voice(
        self,
        audio_path: str,
        audio_filename: str,
        name: str = "AudienceClone",
        description: str = "Live audience voice clone",
        content_type: str = "audio/mpeg",
    ) -> str:
        with open(audio_path, "rb") as fh:
            files = {"files": (audio_filename, fh, content_type)}
            data = {"name": name, "description": description}
            response = self.session.post(
                CLONE_URL, headers=self._headers(), files=files, data=data
            )
        if response.status_code != 200:
            raise ElevenLabsError(response.status_code, response.text)
        voice_id = response.json().get("voice_id")
        if not voice_id:
            raise ElevenLabsError(response.status_code, "missing voice_id in response")
        return voice_id

    def get_voice_status(self, voice_id: str) -> int:
        response = self.session.get(
            VOICE_DETAIL_URL.format(voice_id=voice_id),
            headers=self._headers(),
        )
        return response.status_code

    def synthesize(
        self,
        voice_id: str,
        text: str,
        model_id: str,
        voice_settings: dict[str, Any],
    ) -> bytes:
        response = self.session.post(
            TTS_URL.format(voice_id=voice_id),
            headers={**self._headers(accept_audio=True), "Content-Type": "application/json"},
            json={"text": text, "model_id": model_id, "voice_settings": voice_settings},
        )
        if response.status_code != 200:
            raise ElevenLabsError(response.status_code, response.text)
        return response.content

    def list_voices(self) -> list[dict[str, Any]]:
        response = self.session.get(LIST_VOICES_URL, headers=self._headers())
        if response.status_code != 200:
            raise ElevenLabsError(response.status_code, response.text)
        payload = response.json()
        return payload.get("voices", [])

    def delete_voice(self, voice_id: str) -> bool:
        response = self.session.delete(
            VOICE_DETAIL_URL.format(voice_id=voice_id),
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise ElevenLabsError(response.status_code, response.text)
        return True
