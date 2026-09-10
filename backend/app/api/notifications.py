import uuid

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from app.api.cart import connect_database
from app.shared.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """select id,notification_type,title,message,aggregate_id,read_at,created_at
                   from public.notifications where user_id=%s
                   order by created_at desc limit 30""",
                [user.id],
            )
            items = await cursor.fetchall()
    return {"unread": sum(1 for item in items if item["read_at"] is None), "items": items}


@router.post("/{notification_id}/read")
async def mark_notification_read(notification_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """update public.notifications set read_at=coalesce(read_at,timezone('utc',now()))
                       where id=%s and user_id=%s returning id,read_at""",
                    [notification_id, user.id],
                )
                item = await cursor.fetchone()
                if not item:
                    raise HTTPException(status_code=404, detail="Notification not found.")
    return item


@router.post("/read-all")
async def mark_all_notifications_read(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """update public.notifications set read_at=timezone('utc',now())
                       where user_id=%s and read_at is null""",
                    [user.id],
                )
                updated = cursor.rowcount
    return {"updated": updated}
