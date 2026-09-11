"""ElevenLabs boundary. No cart access, persistence, or provider-body logging."""
import httpx

from app.shared.config import get_settings


class VoiceUnavailable(RuntimeError):
    pass


class ElevenLabsVoice:
    base_url = "https://api.elevenlabs.io/v1"

    def __init__(self):
        self.settings = get_settings()
        self.enabled = self.settings.elevenlabs_enabled and bool(self.settings.elevenlabs_api_key)

    def headers(self):
        if not self.enabled:
            raise VoiceUnavailable("Voice is unavailable. Please use text.")
        return {"xi-api-key": self.settings.elevenlabs_api_key}

    async def request(self, path, *, max_bytes, **kwargs):
        headers = self.headers()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as client:
                # Never silently re-enable provider retention when zero-retention is rejected.
                async with client.stream("POST", f"{self.base_url}/{path}", headers=headers,
                                         params={"enable_logging": "false"}, **kwargs) as response:
                    if response.status_code >= 400:
                        raise VoiceUnavailable("Voice service could not process the request. Please use text.")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > max_bytes:
                            raise VoiceUnavailable("Voice response was too large. Please try a shorter request.")
                        chunks.extend(chunk)
                    return bytes(chunks), response.headers.get("content-type", "")
        except httpx.HTTPError:
            raise VoiceUnavailable("Voice service is temporarily unavailable. Please use text.") from None

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        import json
        content, _ = await self.request(
            "speech-to-text", max_bytes=256_000,
            files={"file": ("request.audio", audio, mime_type)},
            data={"model_id": self.settings.elevenlabs_stt_model_id,
                  "tag_audio_events": "false", "diarize": "false"},
        )
        try:
            result = json.loads(content)
            text = result.get("text") if isinstance(result, dict) else None
            if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                raise ValueError()
            return text.strip()
        except (ValueError, UnicodeDecodeError):
            raise VoiceUnavailable("No usable transcript was returned. Please try again or type your request.") from None

    async def speak(self, text: str) -> bytes:
        if not self.settings.elevenlabs_voice_id:
            raise VoiceUnavailable("Spoken playback is unavailable. Please read the text.")
        content, mime = await self.request(
            f"text-to-speech/{self.settings.elevenlabs_voice_id}", max_bytes=2_000_000,
            json={"text": text, "model_id": self.settings.elevenlabs_tts_model_id,
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        )
        if not mime.startswith("audio/") or not content:
            raise VoiceUnavailable("No playable audio was returned. Please read the text.")
        return content
