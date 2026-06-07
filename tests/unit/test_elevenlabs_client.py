"""Step 3: ElevenLabsClient wraps the three endpoints used by both tools."""
from __future__ import annotations

import pytest
import responses

from hamlet_ai.core.elevenlabs import (
    CLONE_URL,
    LIST_VOICES_URL,
    TTS_URL,
    VOICE_DETAIL_URL,
    AuthError,
    BadAudioError,
    BadResponseError,
    ElevenLabsClient,
    ElevenLabsError,
    RateLimitError,
    write_audio_atomic,
)


@pytest.fixture
def client() -> ElevenLabsClient:
    # No-op sleep so retry backoff doesn't slow the suite.
    return ElevenLabsClient(api_key="test-key", sleep_fn=lambda _: None)


def test_client_requires_api_key():
    with pytest.raises(ValueError):
        ElevenLabsClient(api_key="")


@responses.activate
def test_clone_voice_posts_multipart_and_returns_voice_id(tmp_path, client):
    audio = tmp_path / "vol.mp3"
    audio.write_bytes(b"FAKE_AUDIO")
    responses.add(
        responses.POST,
        CLONE_URL,
        json={"voice_id": "abc123"},
        status=200,
    )
    voice_id = client.clone_voice(str(audio), "vol.mp3")
    assert voice_id == "abc123"
    call = responses.calls[0].request
    assert call.headers["xi-api-key"] == "test-key"


@responses.activate
def test_clone_voice_raises_on_non_200(tmp_path, client):
    audio = tmp_path / "vol.mp3"
    audio.write_bytes(b"FAKE_AUDIO")
    responses.add(responses.POST, CLONE_URL, json={"error": "bad audio"}, status=422)
    with pytest.raises(ElevenLabsError) as exc:
        client.clone_voice(str(audio), "vol.mp3")
    assert exc.value.status_code == 422


@responses.activate
def test_clone_voice_raises_when_voice_id_missing(tmp_path, client):
    audio = tmp_path / "vol.mp3"
    audio.write_bytes(b"FAKE_AUDIO")
    responses.add(responses.POST, CLONE_URL, json={}, status=200)
    with pytest.raises(ElevenLabsError):
        client.clone_voice(str(audio), "vol.mp3")


@responses.activate
def test_get_voice_status_returns_status_code(client):
    voice_id = "abc"
    responses.add(
        responses.GET,
        VOICE_DETAIL_URL.format(voice_id=voice_id),
        json={"voice_id": voice_id},
        status=200,
    )
    assert client.get_voice_status(voice_id) == 200


@responses.activate
def test_get_voice_status_404_during_polling(client):
    voice_id = "abc"
    responses.add(
        responses.GET,
        VOICE_DETAIL_URL.format(voice_id=voice_id),
        json={"detail": "not found"},
        status=404,
    )
    assert client.get_voice_status(voice_id) == 404


@responses.activate
def test_synthesize_returns_audio_bytes(client):
    voice_id = "abc"
    body = b"\x00\x01FAKE_MP3"
    responses.add(
        responses.POST,
        TTS_URL.format(voice_id=voice_id),
        body=body,
        status=200,
        content_type="audio/mpeg",
    )
    audio = client.synthesize(
        voice_id=voice_id,
        text="Hello",
        model_id="eleven_v3",
        voice_settings={"stability": 0.5},
    )
    assert audio == body


@responses.activate
def test_synthesize_raises_on_non_200(client):
    voice_id = "abc"
    responses.add(
        responses.POST,
        TTS_URL.format(voice_id=voice_id),
        json={"detail": "rate limit"},
        status=429,
    )
    with pytest.raises(ElevenLabsError) as exc:
        client.synthesize(voice_id, "Hello", "eleven_v3", {"stability": 0.5})
    assert exc.value.status_code == 429


@responses.activate
def test_list_voices_returns_voices_array(client):
    responses.add(
        responses.GET,
        LIST_VOICES_URL,
        json={"voices": [{"voice_id": "v1", "name": "A"}, {"voice_id": "v2", "name": "B"}]},
        status=200,
    )
    voices = client.list_voices()
    assert [v["voice_id"] for v in voices] == ["v1", "v2"]


@responses.activate
def test_list_voices_raises_on_error(client):
    responses.add(responses.GET, LIST_VOICES_URL, json={"detail": "auth"}, status=401)
    with pytest.raises(ElevenLabsError) as exc:
        client.list_voices()
    assert exc.value.status_code == 401


@responses.activate
def test_delete_voice_returns_true_on_success(client):
    voice_id = "abc"
    responses.add(
        responses.DELETE,
        VOICE_DETAIL_URL.format(voice_id=voice_id),
        json={"status": "ok"},
        status=200,
    )
    assert client.delete_voice(voice_id) is True


@responses.activate
def test_delete_voice_raises_on_error(client):
    voice_id = "abc"
    responses.add(
        responses.DELETE,
        VOICE_DETAIL_URL.format(voice_id=voice_id),
        json={"detail": "not found"},
        status=404,
    )
    with pytest.raises(ElevenLabsError):
        client.delete_voice(voice_id)


# ---------- Step 7: hardening ---------------------------------------------

@responses.activate
def test_specific_exception_classes_by_status(tmp_path, client):
    audio = tmp_path / "vol.mp3"
    audio.write_bytes(b"A")
    responses.add(responses.POST, CLONE_URL, json={"e": "bad"}, status=422)
    with pytest.raises(BadAudioError):
        client.clone_voice(str(audio), "vol.mp3")

    responses.add(responses.GET, LIST_VOICES_URL, json={"e": "auth"}, status=401)
    with pytest.raises(AuthError):
        client.list_voices()


@responses.activate
def test_retries_then_succeeds_on_500_then_200(client):
    voice_id = "abc"
    url = TTS_URL.format(voice_id=voice_id)
    responses.add(responses.POST, url, json={"e": "boom"}, status=500)
    responses.add(responses.POST, url, body=b"AUDIO", status=200, content_type="audio/mpeg")
    audio = client.synthesize(voice_id, "Hi", "eleven_v3", {"stability": 0.5})
    assert audio == b"AUDIO"
    assert len(responses.calls) == 2  # retried once


@responses.activate
def test_rate_limit_raises_after_retries(client):
    voice_id = "abc"
    url = TTS_URL.format(voice_id=voice_id)
    responses.add(responses.POST, url, json={"e": "slow down"}, status=429)
    with pytest.raises(RateLimitError):
        client.synthesize(voice_id, "Hi", "eleven_v3", {"stability": 0.5})
    # initial try + 3 retries == 4 calls
    assert len(responses.calls) == 4


@responses.activate
def test_4xx_not_retried(tmp_path, client):
    audio = tmp_path / "vol.mp3"
    audio.write_bytes(b"A")
    responses.add(responses.POST, CLONE_URL, json={"e": "bad"}, status=422)
    with pytest.raises(BadAudioError):
        client.clone_voice(str(audio), "vol.mp3")
    assert len(responses.calls) == 1  # no retry on 422


@responses.activate
def test_list_voices_bad_schema_raises_bad_response(client):
    responses.add(responses.GET, LIST_VOICES_URL, json={"nope": []}, status=200)
    with pytest.raises(BadResponseError):
        client.list_voices()


def test_logging_redacts_api_key():
    logs: list[str] = []
    c = ElevenLabsClient(api_key="sk_supersecretkey1234567890", log_fn=logs.append)
    c._log("using key sk_supersecretkey1234567890 for voice v1")
    assert logs
    assert "sk_supersecretkey1234567890" not in logs[0]
    assert "<REDACTED>" in logs[0]


def test_write_audio_atomic_writes_and_cleans_tmp(tmp_path):
    out = tmp_path / "line.mp3"
    write_audio_atomic(out, b"\x00MP3")
    assert out.read_bytes() == b"\x00MP3"
    assert not list(tmp_path.glob(".*.tmp"))
