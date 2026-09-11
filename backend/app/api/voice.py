"""Authenticated voice endpoints: speech is input/output only, never a mutation."""
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from psycopg.rows import dict_row

from app.adapters.elevenlabs import ElevenLabsVoice, VoiceUnavailable
from app.api.cart import connect_database
from app.shared.access import require_shopper
from app.shared.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/voice", tags=["voice"])
MAX_AUDIO_BYTES = 5 * 1024 * 1024
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/mpeg"}
# Per-process protection; use a shared gateway quota when scaling across workers.
_requests: OrderedDict[str, tuple[float, int]] = OrderedDict()


async def voice_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    async with await connect_database() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await require_shopper(cursor, user.id)
    return user


def limit_requests(user_id: str):
    now = time.monotonic()
    started, count = _requests.get(user_id, (now, 0))
    if now - started >= 60:
        started, count = now, 0
    if count >= 10:
        raise HTTPException(status_code=429, detail="Please wait a minute before using voice again.",
                            headers={"Retry-After": "60"})
    _requests[user_id] = (started, count + 1)
    _requests.move_to_end(user_id)
    while len(_requests) > 4096:
        _requests.popitem(last=False)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)

    @field_validator("text")
    @classmethod
    def non_blank(cls, value):
        if not value.strip():
            raise ValueError("Text must not be blank.")
        return value.strip()


@router.get("/status")
async def status(response: Response, user: CurrentUser = Depends(get_current_user)):
    service = ElevenLabsVoice()
    response.headers["Cache-Control"] = "no-store"
    return {"transcription": service.enabled,
            "playback": service.enabled and bool(service.settings.elevenlabs_voice_id),
            "maxAudioBytes": MAX_AUDIO_BYTES, "maxRecordingSeconds": 60}


@router.post("/transcribe")
async def transcribe(request: Request, user: CurrentUser = Depends(voice_user)):
    limit_requests(user.id)
    mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Please record a supported audio format.")
    # Stream into bounded transient memory, not UploadFile's disk-spooled multipart storage.
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Recording is too large. Please record a shorter request.")
        audio.extend(chunk)
    if not audio:
        raise HTTPException(status_code=422, detail="The recording was empty.")
    try:
        text = await ElevenLabsVoice().transcribe(bytes(audio), mime)
    except VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    finally:
        audio.clear()
    return JSONResponse({"transcript": text, "requiresConfirmation": True},
                        headers={"Cache-Control": "no-store"})


@router.post("/speak")
async def speak(payload: SpeechRequest, user: CurrentUser = Depends(voice_user)):
    limit_requests(user.id)
    try:
        audio = await ElevenLabsVoice().speak(payload.text)
    except VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
