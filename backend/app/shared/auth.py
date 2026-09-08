from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException

from app.shared.config import get_settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    settings = get_settings()
    api_key = settings.supabase_publishable_key or settings.supabase_anon_key
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A Supabase access token is required.")
    if not settings.supabase_url or not api_key:
        raise HTTPException(status_code=503, detail="Supabase authentication is not configured.")

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"Authorization": authorization, "apikey": api_key},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="The session is invalid or expired.")
    value = response.json()
    return CurrentUser(id=value["id"], email=value.get("email"))
