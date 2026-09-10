import json
import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.api.cart import connect_database
from app.api.journey import CloseCartRequest, close_shared_cart
from app.domain.order_policy import inventory_recovery_target
from app.shared.auth import CurrentUser
from app.shared.auth import get_current_user
from app.shared.access import require_delivery_operator
from app.shared.config import get_settings

router = APIRouter(prefix="/api/operations", tags=["automation"])


class DemoResetRequest(BaseModel):
    confirmation: str


def require_scheduler_secret(value: str | None):
    expected = get_settings().n8n_webhook_secret
    if not expected:
        raise HTTPException(status_code=503, detail="N8N_WEBHOOK_SECRET is not configured.")
    if not value or not secrets.compare_digest(value, expected):
        raise HTTPException(status_code=401, detail="Invalid scheduler secret.")


async def create_due_reminders():
    created = 0
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """select oc.id as cycle_id,oc.cutoff_at,g.name as group_name,p.id as user_id
                       from public.order_cycles oc
                       join public.groups g on g.id=oc.group_id
                       join public.group_members gm on gm.group_id=oc.group_id
                       join public.profiles p on p.id=gm.user_id and p.status='ACTIVE'
                       left join public.authorizations a on a.cycle_id=oc.id and a.user_id=p.id
                       where oc.status='OPEN'
                         and oc.cutoff_at>timezone('utc',now())
                         and oc.cutoff_at<=timezone('utc',now())+interval '24 hours'
                         and a.id is null"""
                )
                for row in await cursor.fetchall():
                    dedupe_key=f"cutoff-reminder:{row['cycle_id']}:{row['user_id']}"
                    await cursor.execute(
                        """insert into public.notifications
                           (user_id,notification_type,title,message,aggregate_id,dedupe_key)
                           values (%s,'CUTOFF_REMINDER','Shared-cart cutoff approaching',%s,%s,%s)
                           on conflict (dedupe_key) do nothing returning id""",
                        [row["user_id"],f"Authorize or decline your items in {row['group_name']} before {row['cutoff_at'].isoformat()}.",row["cycle_id"],dedupe_key],
                    )
                    notification=await cursor.fetchone()
                    if notification:
                        created+=1
                        correlation_id=uuid.uuid4()
                        await cursor.execute(
                            """insert into public.outbox_events
                               (event_type,aggregate_id,correlation_id,payload)
                               values ('CUTOFF_REMINDER_CREATED',%s,%s,%s::jsonb)""",
                            [row["cycle_id"],correlation_id,json.dumps({"notificationId":str(notification["id"]),"userId":str(row["user_id"])})],
                        )
    return created


async def due_cycles():
    async with await connect_database() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """select oc.id,oc.group_id,g.coordinator_id
                   from public.order_cycles oc join public.groups g on g.id=oc.group_id
                   where oc.status='OPEN' and oc.cutoff_at<=timezone('utc',now())
                   order by oc.cutoff_at for update skip locked"""
            )
            return await cursor.fetchall()


@router.post("/tick")
async def automation_tick(x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret")):
    """Called by n8n on a schedule. Safe to retry: reminders dedupe and closed cycles are skipped."""
    require_scheduler_secret(x_webhook_secret)
    reminders = await create_due_reminders()
    closed=[]
    failed=[]
    for cycle in await due_cycles():
        actor=CurrentUser(id=str(cycle["coordinator_id"]),email=None)
        try:
            result=await close_shared_cart(CloseCartRequest(forceBeforeCutoff=False),actor)
            closed.append(str(cycle["id"]))
            if isinstance(result,dict) and result.get("status")=="CLOSED_EMPTY":
                continue
        except HTTPException as exc:
            failed.append({"cycleId":str(cycle["id"]),"status":exc.status_code,"detail":exc.detail})
    return {"remindersCreated":reminders,"cyclesClosed":closed,"failures":failed}


@router.post("/demo-reset")
async def reset_demo_workspace(payload: DemoResetRequest, user: CurrentUser = Depends(get_current_user)):
    """Reset only the caller's non-terminal group journey; completed history is preserved."""
    if payload.confirmation != "RESET DEMO WORKSPACE":
        raise HTTPException(status_code=422,detail="Enter RESET DEMO WORKSPACE exactly to confirm.")
    settings=get_settings()
    if not settings.dev_fulfilment_mode:
        raise HTTPException(status_code=403,detail="Demo reset is disabled outside developer fulfilment mode.")
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_delivery_operator(cursor,user.id)
                await cursor.execute(
                    """select g.id,g.name,pp.id as pickup_point_id from public.groups g
                       join public.group_members gm on gm.group_id=g.id and gm.user_id=%s
                       left join lateral(select id from public.pickup_points where group_id=g.id and active=true order by created_at limit 1) pp on true
                       where g.status='ACTIVE' order by g.updated_at desc limit 1 for update of g""",
                    [user.id],
                )
                group=await cursor.fetchone()
                if not group:
                    raise HTTPException(status_code=404,detail="No active group was found for this administrator.")
                await cursor.execute(
                    """select o.id,o.status from public.orders o join public.order_cycles oc on oc.id=o.cycle_id
                       where oc.group_id=%s and o.status not in ('FULFILLED','CANCELLED') for update of o""",
                    [group["id"]],
                )
                orders=await cursor.fetchall()
                for order in orders:
                    await cursor.execute(
                        """select
                             count(*) filter (where amount_collected>0)::int as cash_collections,
                             (select count(*)::int from public.item_collection_records where order_id=%s) as item_collections
                           from public.cash_obligations where order_id=%s""",
                        [order["id"],order["id"]],
                    )
                    collections=await cursor.fetchone()
                    if collections["cash_collections"] or collections["item_collections"]:
                        raise HTTPException(status_code=409,detail="Reset stopped: an unfinished order has recorded collections and requires an audited support correction.")
                    recovery_target=inventory_recovery_target(order["status"])
                    if recovery_target is None:
                        raise HTTPException(status_code=409,detail=f"Reset cannot safely reconcile order state {order['status']}.")
                    await cursor.execute(
                        "select product_id,sum(quantity)::int as quantity from public.order_lines where order_id=%s group by product_id",
                        [order["id"]],
                    )
                    for stock in await cursor.fetchall():
                        if recovery_target=="RESERVED":
                            await cursor.execute(
                                """update public.inventory set reserved_quantity=greatest(reserved_quantity-%s,0)
                                   where product_id=%s""",
                                [stock["quantity"],stock["product_id"]],
                            )
                        elif recovery_target=="AVAILABLE":
                            await cursor.execute(
                                "update public.inventory set available_quantity=available_quantity+%s where product_id=%s",
                                [stock["quantity"],stock["product_id"]],
                            )
                    await cursor.execute("delete from public.orders where id=%s",[order["id"]])
                await cursor.execute(
                    """delete from public.order_cycles where group_id=%s
                       and status not in ('CLOSED','CANCELLED')""",
                    [group["id"]],
                )
                await cursor.execute(
                    """insert into public.order_cycles (group_id,cutoff_at,pickup_point_id,status,version)
                       values (%s,timezone('utc',now())+interval '7 days',%s,'OPEN',1) returning id,cutoff_at""",
                    [group["id"],group["pickup_point_id"]],
                )
                cycle=await cursor.fetchone()
                correlation_id=uuid.uuid4()
                await cursor.execute(
                    """insert into public.audit_events
                       (correlation_id,actor_id,action,entity_type,entity_id,after_json)
                       values (%s,%s,'DEMO_WORKSPACE_RESET','GROUP',%s,%s::jsonb)""",
                    [correlation_id,user.id,group["id"],json.dumps({"newCycleId":str(cycle["id"]),"removedOrders":len(orders)})],
                )
    return {"groupId":group["id"],"groupName":group["name"],"cycleId":cycle["id"],"cutoffAt":cycle["cutoff_at"],"removedOrders":len(orders)}
