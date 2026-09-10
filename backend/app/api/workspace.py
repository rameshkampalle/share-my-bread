import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.api.cart import connect_database
from app.shared.access import get_access_profile, require_shopper
from app.shared.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["workspace"])


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    joinCode: str = Field(min_length=6, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    pickupLabel: str = Field(default="Community pickup", min_length=2, max_length=120)
    pickupAddress: str = Field(default="Utrecht, Netherlands", min_length=2, max_length=250)
    cutoffAt: datetime


class JoinGroupRequest(BaseModel):
    joinCode: str = Field(min_length=6, max_length=20)


async def workspace_payload(cursor, user_id: str):
    profile = await get_access_profile(cursor, user_id)
    await cursor.execute(
        """select g.id,g.name,g.join_code,gm.member_role,g.coordinator_id,
                  pp.id as pickup_point_id,pp.label as pickup_label,pp.address_text as pickup_address
           from public.group_members gm join public.groups g on g.id=gm.group_id
           left join lateral (
             select id,label,address_text from public.pickup_points
             where group_id=g.id and active=true order by created_at limit 1
           ) pp on true
           where gm.user_id=%s and g.status='ACTIVE' order by gm.joined_at""",
        [user_id],
    )
    groups = await cursor.fetchall()
    for group in groups:
        await cursor.execute(
            """select oc.id,oc.status,oc.cutoff_at,oc.version,oc.created_at,oc.updated_at,
                      count(cl.id) filter (where cl.status='ACTIVE')::int as active_line_count
               from public.order_cycles oc
               left join public.cart_lines cl on cl.cycle_id=oc.id
               where oc.group_id=%s
               group by oc.id
               order by case when oc.status in ('OPEN','REVIEW','AWAITING_COMMITMENT','FINALIZED') then 0 else 1 end,
                        oc.updated_at desc
               limit 1""",
            [group["id"]],
        )
        group["cycle"] = await cursor.fetchone()
        cycle_id = group["cycle"]["id"] if group["cycle"] else None
        await cursor.execute(
            """select p.id,p.display_name,p.app_role,gm.member_role,gm.reliability_state,gm.joined_at,
                      coalesce(a.decision,'PENDING') as decision,a.decided_at
               from public.group_members gm
               join public.profiles p on p.id=gm.user_id
               left join public.authorizations a on a.user_id=gm.user_id and a.cycle_id=%s
               where gm.group_id=%s and p.status='ACTIVE'
               order by case when gm.member_role='COORDINATOR' then 0 else 1 end,p.display_name""",
            [cycle_id, group["id"]],
        )
        group["members"] = await cursor.fetchall()
    return {
        "profile": {
            "id": profile.user_id,
            "display_name": profile.display_name,
            "app_role": profile.app_role,
            "can_shop": profile.can_shop,
            "can_deliver": profile.can_deliver,
        },
        "groups": groups,
    }


@router.get("/workspace/me")
async def get_workspace(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            return await workspace_payload(cursor, user.id)


@router.post("/groups")
async def create_group(payload: CreateGroupRequest, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_shopper(cursor, user.id)
                cutoff=payload.cutoffAt
                if cutoff.tzinfo is None:
                    cutoff=cutoff.replace(tzinfo=timezone.utc)
                if cutoff<=datetime.now(timezone.utc):
                    raise HTTPException(status_code=422,detail="The cutoff must be in the future.")
                await cursor.execute("select 1 from public.group_members where user_id=%s limit 1",[user.id])
                if await cursor.fetchone():
                    raise HTTPException(status_code=409,detail="Leave the current group before creating another MVP workspace.")
                await cursor.execute(
                    """insert into public.groups (name,coordinator_id,join_code,status)
                       values (%s,%s,upper(%s),'ACTIVE') returning id""",
                    [payload.name.strip(), user.id, payload.joinCode.strip()],
                )
                group_id = (await cursor.fetchone())["id"]
                await cursor.execute(
                    """insert into public.group_members (group_id,user_id,member_role)
                       values (%s,%s,'COORDINATOR')""",
                    [group_id, user.id],
                )
                await cursor.execute(
                    """insert into public.pickup_points (group_id,label,address_text,active)
                       values (%s,%s,%s,true) returning id""",
                    [group_id, payload.pickupLabel.strip(), payload.pickupAddress.strip()],
                )
                pickup_id = (await cursor.fetchone())["id"]
                await cursor.execute(
                    """insert into public.order_cycles (group_id,cutoff_at,pickup_point_id,status)
                       values (%s,%s,%s,'OPEN')""",
                    [group_id, cutoff, pickup_id],
                )
                return await workspace_payload(cursor, user.id)


@router.post("/groups/join")
async def join_group(payload: JoinGroupRequest, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_shopper(cursor, user.id)
                await cursor.execute("select 1 from public.group_members where user_id=%s limit 1",[user.id])
                if await cursor.fetchone():
                    raise HTTPException(status_code=409,detail="This MVP account already belongs to a group.")
                await cursor.execute(
                    "select id from public.groups where join_code=upper(%s) and status='ACTIVE'",
                    [payload.joinCode.strip()],
                )
                group = await cursor.fetchone()
                if not group:
                    raise HTTPException(status_code=404, detail="No active group has that join code.")
                await cursor.execute(
                    """insert into public.group_members (group_id,user_id,member_role)
                       values (%s,%s,'MEMBER') on conflict (group_id,user_id) do nothing""",
                    [group["id"], user.id],
                )
                return await workspace_payload(cursor, user.id)
