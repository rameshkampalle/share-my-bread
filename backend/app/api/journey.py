import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.api.cart import connect_database
from app.shared.auth import CurrentUser, get_current_user
from app.shared.config import get_settings

router = APIRouter(prefix="/api/journey", tags=["order journey"])


class FulfilmentRequest(BaseModel):
    status: Literal["PREPARING", "READY_FOR_PICKUP", "FULFILLED", "CANCELLED"]
    orderId: uuid.UUID | None = None


class CollectCashRequest(BaseModel):
    orderId: uuid.UUID | None = None


async def current_cycle(cursor, user_id: str, *, lock: bool = False):
    suffix = "for update of oc" if lock else ""
    await cursor.execute(
        f"""
        select oc.id,oc.group_id,oc.status,oc.cutoff_at,oc.pickup_point_id,g.name as group_name
        from public.order_cycles oc
        join public.groups g on g.id=oc.group_id
        join public.group_members gm on gm.group_id=g.id
        left join public.orders o on o.cycle_id=oc.id
        where gm.user_id=%s
          and oc.status in ('OPEN','REVIEW','AWAITING_COMMITMENT','FINALIZED')
        order by case
          when oc.status in ('REVIEW','AWAITING_COMMITMENT') then 0
          when oc.status='OPEN' then 1
          when oc.status='FINALIZED' and coalesce(o.status,'') not in ('FULFILLED','CANCELLED') then 2
          else 3 end,
          oc.updated_at desc
        limit 1 {suffix}
        """,
        [user_id],
    )
    value = await cursor.fetchone()
    if not value:
        raise HTTPException(status_code=404, detail="No active order cycle was found for this member.")
    return value


async def require_admin(cursor, user_id: str):
    await cursor.execute("select app_role from public.profiles where id=%s", [user_id])
    profile = await cursor.fetchone()
    if not profile or profile["app_role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="This demo fulfilment action requires the ADMIN role.")
    if not get_settings().dev_fulfilment_mode:
        raise HTTPException(status_code=403, detail="Demo fulfilment mode is disabled.")


async def add_audit(cursor, user_id: str, action: str, entity_type: str, entity_id, after: dict):
    correlation_id = uuid.uuid4()
    await cursor.execute(
        """insert into public.audit_events
        (correlation_id,actor_id,action,entity_type,entity_id,after_json)
        values (%s,%s,%s,%s,%s,%s::jsonb)""",
        [correlation_id, user_id, action, entity_type, entity_id, json.dumps(after, default=str)],
    )
    return correlation_id


async def read_journey(connection, user_id: str):
    async with connection.cursor(row_factory=dict_row) as cursor:
        cycle = await current_cycle(cursor, user_id)
        await cursor.execute("select app_role from public.profiles where id=%s", [user_id])
        profile = await cursor.fetchone()
        await cursor.execute(
            """select id,decision,snapshot_hash,decided_at from public.authorizations
            where cycle_id=%s and user_id=%s""",
            [cycle["id"], user_id],
        )
        authorization = await cursor.fetchone()
        await cursor.execute(
            """select id,order_number,status,subtotal,finalized_at,created_at,updated_at
            from public.orders where cycle_id=%s""",
            [cycle["id"]],
        )
        order = await cursor.fetchone()
        order_lines = []
        allocations = []
        obligation = None
        fulfilment_events = []
        audit_events = []
        if order:
            await cursor.execute(
                """select ol.id,ol.product_snapshot,ol.quantity,ol.unit_price,ol.total
                from public.order_lines ol where ol.order_id=%s order by ol.id""",
                [order["id"]],
            )
            order_lines = await cursor.fetchall()
            await cursor.execute(
                """select id,line_id,amount,basis from public.allocations
                where order_id=%s and user_id=%s order by id""",
                [order["id"], user_id],
            )
            allocations = await cursor.fetchall()
            await cursor.execute(
                """select id,amount_due,amount_collected,status,committed_at,updated_at
                from public.cash_obligations where order_id=%s and user_id=%s""",
                [order["id"], user_id],
            )
            obligation = await cursor.fetchone()
            await cursor.execute(
                """select id,old_status,new_status,source,note,created_at
                from public.fulfilment_events where order_id=%s order by created_at,id""",
                [order["id"]],
            )
            fulfilment_events = await cursor.fetchall()
            await cursor.execute(
                """select id,action,entity_type,after_json,created_at
                from public.audit_events
                where entity_id in (%s,%s) order by created_at desc limit 20""",
                [cycle["id"], order["id"]],
            )
            audit_events = await cursor.fetchall()
        else:
            await cursor.execute(
                """select id,action,entity_type,after_json,created_at
                from public.audit_events where entity_id=%s
                order by created_at desc limit 20""",
                [cycle["id"]],
            )
            audit_events = await cursor.fetchall()
    return {
        "cycle": cycle,
        "authorization": authorization,
        "order": order,
        "order_lines": order_lines,
        "allocations": allocations,
        "obligation": obligation,
        "fulfilment_events": fulfilment_events,
        "audit_events": audit_events,
        "is_admin": bool(profile and profile["app_role"] == "ADMIN"),
        "dev_fulfilment_mode": get_settings().dev_fulfilment_mode,
    }


@router.get("/current")
async def get_current_journey(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        return await read_journey(connection, user.id)


@router.get("/history")
async def get_order_history(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """select o.id,o.order_number,o.status,o.subtotal,o.finalized_at,o.created_at,o.updated_at,
                       g.name as group_name,co.status as cash_status,co.amount_due,co.amount_collected,
                       coalesce(jsonb_agg(jsonb_build_object(
                         'id',ol.id,'name',ol.product_snapshot->>'name','sku',ol.product_snapshot->>'sku',
                         'unit',ol.product_snapshot->>'unit','quantity',ol.quantity,'total',ol.total
                       ) order by ol.id) filter (where ol.id is not null),'[]'::jsonb) as lines
                from public.orders o
                join public.order_cycles oc on oc.id=o.cycle_id
                join public.groups g on g.id=oc.group_id
                join public.group_members gm on gm.group_id=g.id and gm.user_id=%s
                left join public.cash_obligations co on co.order_id=o.id and co.user_id=%s
                left join public.order_lines ol on ol.order_id=o.id
                group by o.id,g.name,co.status,co.amount_due,co.amount_collected
                order by o.created_at desc limit 20""",
                [user.id, user.id],
            )
            return {"orders": await cursor.fetchall()}


@router.post("/authorize")
async def authorize_cart(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                cycle = await current_cycle(cursor, user.id, lock=True)
                if cycle["status"] != "OPEN":
                    raise HTTPException(status_code=409, detail="This cart has already entered checkout.")
                await cursor.execute(
                    """select cl.id,cl.product_id,cl.quantity,cl.unit_price_snapshot,p.name,p.sku,p.unit
                    from public.cart_lines cl join public.products p on p.id=cl.product_id
                    where cl.cycle_id=%s and cl.added_by=%s and cl.status='ACTIVE'
                    order by cl.id for update of cl""",
                    [cycle["id"], user.id],
                )
                lines = await cursor.fetchall()
                if not lines:
                    raise HTTPException(status_code=409, detail="Add at least one item before checkout.")
                snapshot = [
                    {"line": str(line["id"]), "product": str(line["product_id"]), "quantity": line["quantity"], "price": str(line["unit_price_snapshot"])}
                    for line in lines
                ]
                snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
                subtotal = sum(line["quantity"] * line["unit_price_snapshot"] for line in lines)
                await cursor.execute(
                    """insert into public.authorizations (cycle_id,user_id,decision,snapshot_hash)
                    values (%s,%s,'AUTHORIZED',%s)
                    on conflict (cycle_id,user_id) do update set decision='AUTHORIZED',
                    snapshot_hash=excluded.snapshot_hash,decided_at=timezone('utc',now())""",
                    [cycle["id"], user.id, snapshot_hash],
                )
                order_number = f"SMB-{str(cycle['id'])[-8:].upper()}"
                await cursor.execute(
                    """insert into public.orders (cycle_id,order_number,status,subtotal)
                    values (%s,%s,'AWAITING_COMMITMENT',%s) returning id""",
                    [cycle["id"], order_number, subtotal],
                )
                order_id = (await cursor.fetchone())["id"]
                for line in lines:
                    product_snapshot = {"id": str(line["product_id"]), "name": line["name"], "sku": line["sku"], "unit": line["unit"]}
                    total = line["quantity"] * line["unit_price_snapshot"]
                    await cursor.execute(
                        """insert into public.order_lines
                        (order_id,source_line_id,product_id,product_snapshot,quantity,unit_price,total)
                        values (%s,%s,%s,%s::jsonb,%s,%s,%s) returning id""",
                        [order_id, line["id"], line["product_id"], json.dumps(product_snapshot), line["quantity"], line["unit_price_snapshot"], total],
                    )
                    order_line_id = (await cursor.fetchone())["id"]
                    await cursor.execute(
                        """insert into public.allocations (order_id,user_id,line_id,amount,basis)
                        values (%s,%s,%s,%s,'CLAIMANT_LEVEL')""",
                        [order_id, user.id, order_line_id, total],
                    )
                await cursor.execute(
                    """insert into public.cash_obligations (order_id,user_id,amount_due,status)
                    values (%s,%s,%s,'DUE')""",
                    [order_id, user.id, subtotal],
                )
                await cursor.execute(
                    "update public.order_cycles set status='AWAITING_COMMITMENT',version=version+1 where id=%s",
                    [cycle["id"]],
                )
                correlation_id = await add_audit(cursor, user.id, "CART_AUTHORIZED", "ORDER_CYCLE", cycle["id"], {"snapshotHash": snapshot_hash, "subtotal": str(subtotal)})
                await cursor.execute(
                    """insert into public.outbox_events (event_type,aggregate_id,correlation_id,payload)
                    values ('CART_AUTHORIZED',%s,%s,%s::jsonb)""",
                    [cycle["id"], correlation_id, json.dumps({"orderId": str(order_id), "subtotal": str(subtotal)})],
                )
        return await read_journey(connection, user.id)


@router.post("/commit-cash")
async def commit_cash(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                cycle = await current_cycle(cursor, user.id, lock=True)
                await cursor.execute(
                    """select co.id,co.status,co.amount_due,o.id as order_id from public.cash_obligations co
                    join public.orders o on o.id=co.order_id where o.cycle_id=%s and co.user_id=%s
                    for update of co""",
                    [cycle["id"], user.id],
                )
                obligation = await cursor.fetchone()
                if not obligation:
                    raise HTTPException(status_code=409, detail="Authorize the cart before committing cash.")
                if obligation["status"] == "DUE":
                    await cursor.execute(
                        "update public.cash_obligations set status='COMMITTED',committed_at=timezone('utc',now()) where id=%s",
                        [obligation["id"]],
                    )
                    await add_audit(cursor, user.id, "CASH_COMMITTED", "ORDER", obligation["order_id"], {"amount": str(obligation["amount_due"])})
                elif obligation["status"] != "COMMITTED":
                    raise HTTPException(status_code=409, detail=f"Cash cannot be committed from {obligation['status']}.")
        return await read_journey(connection, user.id)


@router.post("/finalize")
async def finalize_order(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                cycle = await current_cycle(cursor, user.id, lock=True)
                await cursor.execute("select id,status from public.orders where cycle_id=%s for update", [cycle["id"]])
                order = await cursor.fetchone()
                if not order:
                    raise HTTPException(status_code=409, detail="Authorize the cart before finalizing.")
                if order["status"] == "ORDER_PLACED":
                    pass
                elif order["status"] != "AWAITING_COMMITMENT":
                    raise HTTPException(status_code=409, detail=f"Order cannot be finalized from {order['status']}.")
                else:
                    await cursor.execute(
                        "select count(*) as pending from public.cash_obligations where order_id=%s and status<>'COMMITTED'",
                        [order["id"]],
                    )
                    if (await cursor.fetchone())["pending"]:
                        raise HTTPException(status_code=409, detail="Every member must commit cash before finalization.")
                    now_status = "AWAITING_COMMITMENT"
                    await cursor.execute(
                        "update public.orders set status='ORDER_PLACED',finalized_at=timezone('utc',now()),version=version+1 where id=%s",
                        [order["id"]],
                    )
                    await cursor.execute("update public.order_cycles set status='FINALIZED',version=version+1 where id=%s", [cycle["id"]])
                    await cursor.execute(
                        """insert into public.fulfilment_events (order_id,old_status,new_status,actor_id,source,note)
                        values (%s,%s,'FINALIZED',%s,'SYSTEM','Deterministic allocation and commitment checks passed'),
                               (%s,'FINALIZED','ORDER_PLACED',%s,'MOCK_RETAILER','Mock retailer accepted the order')""",
                        [order["id"], now_status, user.id, order["id"], user.id],
                    )
                    correlation_id = await add_audit(cursor, user.id, "MOCK_ORDER_PLACED", "ORDER", order["id"], {"status": "ORDER_PLACED"})
                    await cursor.execute(
                        """insert into public.outbox_events (event_type,aggregate_id,correlation_id,payload)
                        values ('ORDER_PLACED',%s,%s,%s::jsonb)""",
                        [order["id"], correlation_id, json.dumps({"mode": "mock"})],
                    )
        return await read_journey(connection, user.id)


@router.post("/collect-cash")
async def collect_cash(payload: CollectCashRequest | None = None, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_admin(cursor, user.id)
                order_filter = "and o.id=%s" if payload and payload.orderId else ""
                params = [user.id, user.id, payload.orderId] if payload and payload.orderId else [user.id, user.id]
                await cursor.execute(
                    """select co.id,co.status,co.amount_due,co.amount_collected,o.id as order_id
                    from public.cash_obligations co
                    join public.orders o on o.id=co.order_id
                    join public.order_cycles oc on oc.id=o.cycle_id
                    join public.group_members gm on gm.group_id=oc.group_id
                    where gm.user_id=%s and co.user_id=%s """ + order_filter + """
                    order by o.updated_at desc limit 1 for update of co""",
                    params,
                )
                obligation = await cursor.fetchone()
                if not obligation or obligation["status"] not in ("COMMITTED", "PARTIALLY_COLLECTED"):
                    raise HTTPException(status_code=409, detail="A committed cash obligation is required.")
                remaining = obligation["amount_due"] - obligation["amount_collected"]
                await cursor.execute(
                    """insert into public.collection_records (obligation_id,amount,recorded_by,note)
                    values (%s,%s,%s,'Demo cash collection at pickup')""",
                    [obligation["id"], remaining, user.id],
                )
                await cursor.execute(
                    "update public.cash_obligations set amount_collected=amount_due,status='COLLECTED' where id=%s",
                    [obligation["id"]],
                )
                await add_audit(cursor, user.id, "CASH_COLLECTED", "ORDER", obligation["order_id"], {"amount": str(remaining)})
        return await read_journey(connection, user.id)


@router.post("/fulfilment")
async def update_fulfilment(payload: FulfilmentRequest, user: CurrentUser = Depends(get_current_user)):
    transitions = {
        "ORDER_PLACED": {"PREPARING", "CANCELLED"},
        "PREPARING": {"READY_FOR_PICKUP", "CANCELLED"},
        "READY_FOR_PICKUP": {"FULFILLED", "CANCELLED"},
    }
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_admin(cursor, user.id)
                if payload.orderId:
                    await cursor.execute(
                        """select o.id,o.status,oc.group_id,oc.pickup_point_id
                        from public.orders o join public.order_cycles oc on oc.id=o.cycle_id
                        join public.group_members gm on gm.group_id=oc.group_id
                        where o.id=%s and gm.user_id=%s for update of o""",
                        [payload.orderId, user.id],
                    )
                else:
                    cycle = await current_cycle(cursor, user.id)
                    await cursor.execute(
                        """select o.id,o.status,oc.group_id,oc.pickup_point_id
                        from public.orders o join public.order_cycles oc on oc.id=o.cycle_id
                        where o.cycle_id=%s for update of o""",
                        [cycle["id"]],
                    )
                order = await cursor.fetchone()
                if not order or payload.status not in transitions.get(order["status"], set()):
                    current = order["status"] if order else "NO_ORDER"
                    raise HTTPException(status_code=409, detail=f"Transition {current} → {payload.status} is not allowed.")
                if payload.status == "FULFILLED":
                    await cursor.execute(
                        "select count(*) as pending from public.cash_obligations where order_id=%s and status<>'COLLECTED'",
                        [order["id"]],
                    )
                    if (await cursor.fetchone())["pending"]:
                        raise HTTPException(status_code=409, detail="Record cash collection before fulfilment.")
                await cursor.execute("update public.orders set status=%s,version=version+1 where id=%s", [payload.status, order["id"]])
                await cursor.execute(
                    """insert into public.fulfilment_events (order_id,old_status,new_status,actor_id,source,note)
                    values (%s,%s,%s,%s,'ADMIN_UI','Demo fulfilment control')""",
                    [order["id"], order["status"], payload.status, user.id],
                )
                await add_audit(cursor, user.id, f"ORDER_{payload.status}", "ORDER", order["id"], {"from": order["status"], "to": payload.status})
                if payload.status == "FULFILLED":
                    await cursor.execute(
                        "select id from public.order_cycles where group_id=%s and status='OPEN' limit 1",
                        [order["group_id"]],
                    )
                    if not await cursor.fetchone():
                        await cursor.execute(
                            """insert into public.order_cycles
                            (group_id,cutoff_at,pickup_point_id,status,version)
                            values (%s,timezone('utc',now())+interval '7 days',%s,'OPEN',1)
                            returning id""",
                            [order["group_id"], order["pickup_point_id"]],
                        )
                        new_cycle_id = (await cursor.fetchone())["id"]
                        await add_audit(cursor, user.id, "NEW_ORDER_CYCLE_CREATED", "ORDER_CYCLE", new_cycle_id, {"previousOrderId": str(order["id"])})
        return await read_journey(connection, user.id)


@router.post("/rollover")
async def rollover_completed_order(user: CurrentUser = Depends(get_current_user)):
    """Idempotently repair a fulfilled demo created before automatic rollover existed."""
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_admin(cursor, user.id)
                cycle = await current_cycle(cursor, user.id, lock=True)
                if cycle["status"] == "OPEN":
                    return await read_journey(connection, user.id)
                await cursor.execute("select id,status from public.orders where cycle_id=%s for update", [cycle["id"]])
                order = await cursor.fetchone()
                if not order or order["status"] != "FULFILLED":
                    raise HTTPException(status_code=409, detail="Only a fulfilled order can roll over to a new cart.")
                await cursor.execute(
                    """insert into public.order_cycles
                    (group_id,cutoff_at,pickup_point_id,status,version)
                    values (%s,timezone('utc',now())+interval '7 days',%s,'OPEN',1)
                    returning id""",
                    [cycle["group_id"], cycle["pickup_point_id"]],
                )
                new_cycle_id = (await cursor.fetchone())["id"]
                await add_audit(cursor, user.id, "NEW_ORDER_CYCLE_CREATED", "ORDER_CYCLE", new_cycle_id, {"previousOrderId": str(order["id"]), "reason": "automatic-rollover"})
        return await read_journey(connection, user.id)
