from dataclasses import dataclass

from fastapi import HTTPException
from psycopg.rows import dict_row


@dataclass(frozen=True)
class AccessProfile:
    user_id: str
    display_name: str
    app_role: str

    @property
    def can_shop(self) -> bool:
        return self.app_role in {"MEMBER", "ADMIN"}

    @property
    def can_deliver(self) -> bool:
        return self.app_role == "ADMIN"


async def get_access_profile(cursor, user_id: str) -> AccessProfile:
    await cursor.execute(
        "select id,display_name,app_role,status from public.profiles where id=%s",
        [user_id],
    )
    value = await cursor.fetchone()
    if not value or value["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="This application profile is not active.")
    return AccessProfile(str(value["id"]), value["display_name"], value["app_role"])


async def require_shopper(cursor, user_id: str) -> AccessProfile:
    profile = await get_access_profile(cursor, user_id)
    if not profile.can_shop:
        raise HTTPException(status_code=403, detail="This account cannot create or modify carts.")
    return profile


async def require_delivery_operator(cursor, user_id: str) -> AccessProfile:
    profile = await get_access_profile(cursor, user_id)
    if not profile.can_deliver:
        raise HTTPException(status_code=403, detail="Retail members cannot perform fulfilment actions.")
    return profile
