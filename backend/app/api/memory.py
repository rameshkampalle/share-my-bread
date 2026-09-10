import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.cart import connect_database
from app.services.memory import Mem0Memory, MemoryUnavailable
from app.shared.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/memory", tags=["memory"])


class ConsentRequest(BaseModel):
    enabled: bool


class PreferenceRequest(BaseModel):
    preference: str = Field(min_length=3, max_length=240)


async def consent_for(user_id: str) -> bool:
    async with await connect_database() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("select memory_consent from public.profiles where id=%s", [user_id])
            row = await cursor.fetchone()
    return bool(row and row[0])


@router.get("")
async def memory_status(user: CurrentUser = Depends(get_current_user)):
    consent = await consent_for(user.id)
    service = Mem0Memory()
    memories, error = [], None
    if consent and service.enabled:
        try:
            memories = await service.list(user.id)
        except MemoryUnavailable as exc:
            error = str(exc)
    return {"consent": consent, "configured": service.enabled, "memories": memories, "error": error}


@router.post("/consent")
async def set_consent(payload: ConsentRequest, user: CurrentUser = Depends(get_current_user)):
    service = Mem0Memory()
    if payload.enabled and not service.enabled:
        raise HTTPException(status_code=503, detail="Preference memory is not configured.")
    if not payload.enabled and await consent_for(user.id) and service.enabled:
        try:
            await service.delete_all(user.id)
        except MemoryUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Memory could not be erased; consent was not changed. {exc}")
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "update public.profiles set memory_consent=%s,updated_at=timezone('utc',now()) where id=%s",
                    [payload.enabled, user.id],
                )
    return {"consent": payload.enabled, "configured": service.enabled, "memories": []}


@router.post("/preferences", status_code=202)
async def add_preference(payload: PreferenceRequest, user: CurrentUser = Depends(get_current_user)):
    if not await consent_for(user.id):
        raise HTTPException(status_code=403, detail="Enable preference memory before saving a preference.")
    try:
        result = await Mem0Memory().add(user.id, payload.preference.strip())
    except MemoryUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"accepted": True, "eventId": result.get("event_id"), "status": result.get("status")}


@router.delete("/preferences/{memory_id}", status_code=204)
async def delete_preference(memory_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)):
    if not await consent_for(user.id):
        raise HTTPException(status_code=403, detail="Preference memory is disabled.")
    try:
        await Mem0Memory().delete(user.id, str(memory_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Memory not found.")
    except MemoryUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(status_code=204)


@router.get("/context")
async def memory_context(query: str = "grocery preferences", user: CurrentUser = Depends(get_current_user)):
    if len(query) > 500 or not await consent_for(user.id):
        return {"memories": []}
    service = Mem0Memory()
    if not service.enabled:
        return {"memories": []}
    try:
        items = await service.search(user.id, query)
    except MemoryUnavailable:
        return {"memories": []}
    return {"memories": [str(item.get("memory", ""))[:240] for item in items if item.get("memory")][:5]}
