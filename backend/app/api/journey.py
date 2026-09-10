import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.api.cart import connect_database
from app.domain.order_policy import can_cancel_order, can_close_cycle, can_transition_fulfilment
from app.shared.access import get_access_profile, require_delivery_operator, require_shopper
from app.shared.auth import CurrentUser, get_current_user
from app.shared.config import get_settings

router = APIRouter(prefix="/api/journey", tags=["order journey"])


class FulfilmentRequest(BaseModel):
    status: Literal["PREPARING", "READY_FOR_PICKUP", "FULFILLED", "CANCELLED"]
    orderId: uuid.UUID | None = None
    reason: str | None = None


class CollectCashRequest(BaseModel):
    orderId: uuid.UUID | None = None
    memberId: uuid.UUID | None = None


class CollectItemsRequest(BaseModel):
    orderId: uuid.UUID | None = None
    memberId: uuid.UUID | None = None


class CloseCartRequest(BaseModel):
    forceBeforeCutoff: bool = False


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
    await require_delivery_operator(cursor, user_id)
    if not get_settings().dev_fulfilment_mode:
        raise HTTPException(status_code=403, detail="Demo fulfilment mode is disabled.")


async def require_coordinator_or_admin(cursor, group_id, user_id: str):
    profile = await require_shopper(cursor, user_id)
    await cursor.execute(
        "select member_role from public.group_members where group_id=%s and user_id=%s",
        [group_id,user_id],
    )
    membership=await cursor.fetchone()
    if not can_close_cycle(app_role=profile.app_role,member_role=membership["member_role"] if membership else ""):
        raise HTTPException(status_code=403,detail="Only the coordinator or an administrator can close the shared cart.")
    return profile,membership


async def add_audit(cursor, user_id: str, action: str, entity_type: str, entity_id, after: dict):
    correlation_id = uuid.uuid4()
    await cursor.execute(
        """insert into public.audit_events
        (correlation_id,actor_id,action,entity_type,entity_id,after_json)
        values (%s,%s,%s,%s,%s,%s::jsonb)""",
        [correlation_id, user_id, action, entity_type, entity_id, json.dumps(after, default=str)],
    )
    return correlation_id


async def notify_group(cursor, group_id, notification_type: str, title: str, message: str, aggregate_id):
    """Create one retry-safe in-app notification per active group member."""
    dedupe_prefix=f"{notification_type.lower()}:{aggregate_id}"
    await cursor.execute(
        """insert into public.notifications
           (user_id,notification_type,title,message,aggregate_id,dedupe_key)
           select gm.user_id,%s,%s,%s,%s,%s||':'||gm.user_id::text
           from public.group_members gm join public.profiles p on p.id=gm.user_id
           where gm.group_id=%s and p.status='ACTIVE'
           on conflict (dedupe_key) do nothing""",
        [notification_type,title,message,aggregate_id,dedupe_prefix,group_id],
    )


async def read_journey(connection, user_id: str):
    async with connection.cursor(row_factory=dict_row) as cursor:
        cycle = await current_cycle(cursor, user_id)
        await cursor.execute("select app_role from public.profiles where id=%s", [user_id])
        profile = await cursor.fetchone()
        await cursor.execute(
            """select p.id,p.display_name,gm.member_role,
                      coalesce(a.decision,'PENDING') as decision,a.decided_at
               from public.group_members gm join public.profiles p on p.id=gm.user_id
               left join public.authorizations a on a.cycle_id=%s and a.user_id=p.id
               where gm.group_id=%s
               order by p.display_name""",
            [cycle["id"],cycle["group_id"]],
        )
        member_decisions=await cursor.fetchall()
        await cursor.execute(
            "select member_role from public.group_members where group_id=%s and user_id=%s",
            [cycle["group_id"],user_id],
        )
        membership=await cursor.fetchone()
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
        group_obligations = []
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
                """select co.id,co.user_id,p.display_name,co.amount_due,co.amount_collected,
                          co.status,co.committed_at,co.updated_at,
                          exists(select 1 from public.item_collection_records ic
                                 where ic.order_id=co.order_id and ic.user_id=co.user_id) as items_collected
                   from public.cash_obligations co join public.profiles p on p.id=co.user_id
                   where co.order_id=%s order by p.display_name""",
                [order["id"]],
            )
            group_obligations=await cursor.fetchall()
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
        "group_obligations": group_obligations,
        "pending_commitments": sum(1 for item in group_obligations if item["status"]=="DUE"),
        "pending_collections": sum(1 for item in group_obligations if item["status"]!="COLLECTED"),
        "pending_item_collections": sum(1 for item in group_obligations if not item["items_collected"]),
        "fulfilment_events": fulfilment_events,
        "audit_events": audit_events,
        "is_admin": bool(profile and profile["app_role"] == "ADMIN"),
        "is_coordinator": bool(membership and membership["member_role"]=="COORDINATOR"),
        "member_decisions": member_decisions,
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
                       g.name as group_name,cash.cash_status,cash.amount_due,cash.amount_collected,
                       cash.pending_item_collections,
                       coalesce(lines.items,'[]'::jsonb) as lines
                from public.orders o
                join public.order_cycles oc on oc.id=o.cycle_id
                join public.groups g on g.id=oc.group_id
                join public.group_members gm on gm.group_id=g.id and gm.user_id=%s
                left join lateral (
                  select case when bool_and(status='COLLECTED') then 'COLLECTED'
                              when bool_and(status='COMMITTED') then 'COMMITTED'
                              when bool_or(status='PARTIALLY_COLLECTED') then 'PARTIALLY_COLLECTED'
                              else 'DUE' end as cash_status,
                         sum(amount_due)::numeric(12,2) as amount_due,
                         sum(amount_collected)::numeric(12,2) as amount_collected,
                         count(*) filter (where not exists(
                           select 1 from public.item_collection_records ic
                           where ic.order_id=co.order_id and ic.user_id=co.user_id
                         ))::int as pending_item_collections
                  from public.cash_obligations co where order_id=o.id
                ) cash on true
                left join lateral (
                  select jsonb_agg(jsonb_build_object(
                    'id',ol.id,'name',ol.product_snapshot->>'name','sku',ol.product_snapshot->>'sku',
                    'unit',ol.product_snapshot->>'unit','quantity',ol.quantity,'total',ol.total
                  ) order by ol.id) as items from public.order_lines ol where ol.order_id=o.id
                ) lines on true
                order by o.created_at desc limit 20""",
                [user.id],
            )
            return {"orders": await cursor.fetchall()}


@router.post("/authorize")
async def authorize_cart(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_shopper(cursor,user.id)
                cycle = await current_cycle(cursor, user.id, lock=True)
                if cycle["status"] != "OPEN":
                    raise HTTPException(status_code=409, detail="This cart has already entered checkout.")
                await cursor.execute("select cutoff_at>timezone('utc',now()) as before_cutoff from public.order_cycles where id=%s",[cycle["id"]])
                if not (await cursor.fetchone())["before_cutoff"]:
                    raise HTTPException(status_code=409,detail="The cutoff has passed. The coordinator must close the cart.")
                await cursor.execute(
                    """select cl.id,cl.product_id,cl.quantity,cl.unit_price_snapshot
                    from public.cart_lines cl
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
                correlation_id = await add_audit(cursor, user.id, "CART_AUTHORIZED", "ORDER_CYCLE", cycle["id"], {"snapshotHash": snapshot_hash, "subtotal": str(subtotal)})
                await cursor.execute(
                    """insert into public.outbox_events (event_type,aggregate_id,correlation_id,payload)
                    values ('CART_AUTHORIZED',%s,%s,%s::jsonb)""",
                    [cycle["id"], correlation_id, json.dumps({"userId": user.id, "subtotal": str(subtotal)})],
                )
        return await read_journey(connection, user.id)


@router.post("/decline")
async def decline_cart(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_shopper(cursor,user.id)
                cycle=await current_cycle(cursor,user.id,lock=True)
                if cycle["status"]!="OPEN":
                    raise HTTPException(status_code=409,detail="Decisions are closed for this cycle.")
                await cursor.execute(
                    """insert into public.authorizations (cycle_id,user_id,decision,snapshot_hash)
                       values (%s,%s,'DECLINED','DECLINED')
                       on conflict (cycle_id,user_id) do update set decision='DECLINED',
                       snapshot_hash='DECLINED',decided_at=timezone('utc',now())""",
                    [cycle["id"],user.id],
                )
                await add_audit(cursor,user.id,"CART_DECLINED","ORDER_CYCLE",cycle["id"],{})
        return await read_journey(connection,user.id)


@router.post("/close-cart")
async def close_shared_cart(payload: CloseCartRequest, user: CurrentUser = Depends(get_current_user)):
    """Apply the cutoff boundary and create allocations for authorized members only."""
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                cycle=await current_cycle(cursor,user.id,lock=True)
                profile,_=await require_coordinator_or_admin(cursor,cycle["group_id"],user.id)
                if cycle["status"]!="OPEN":
                    raise HTTPException(status_code=409,detail="This shared cart is already closed.")
                await cursor.execute("select cutoff_at<=timezone('utc',now()) as reached from public.order_cycles where id=%s",[cycle["id"]])
                cutoff_reached=(await cursor.fetchone())["reached"]
                if not cutoff_reached and not (payload.forceBeforeCutoff and profile.app_role=="ADMIN" and get_settings().dev_fulfilment_mode):
                    raise HTTPException(status_code=409,detail="The cutoff has not been reached. Demo admins may explicitly force closure.")

                await cursor.execute(
                    """select cl.id,cl.added_by,cl.product_id,cl.quantity,cl.unit_price_snapshot,
                              p.name,p.sku,p.unit
                       from public.cart_lines cl join public.products p on p.id=cl.product_id
                       join public.authorizations a on a.cycle_id=cl.cycle_id
                         and a.user_id=cl.added_by and a.decision='AUTHORIZED'
                       where cl.cycle_id=%s and cl.status='ACTIVE'
                       order by cl.added_by,cl.id for update of cl""",
                    [cycle["id"]],
                )
                included=await cursor.fetchall()
                if not included:
                    await cursor.execute("update public.order_cycles set status='CLOSED_EMPTY',version=version+1 where id=%s",[cycle["id"]])
                    await cursor.execute("update public.cart_lines set status='ROLLED_FORWARD' where cycle_id=%s and status='ACTIVE'",[cycle["id"]])
                    await add_audit(cursor,user.id,"CYCLE_CLOSED_EMPTY","ORDER_CYCLE",cycle["id"],{})
                    return {"status":"CLOSED_EMPTY","cycleId":cycle["id"]}

                # Revalidate stock for the complete authorized group cart and reserve it atomically.
                await cursor.execute(
                    """select cl.product_id,sum(cl.quantity)::int as quantity
                       from public.cart_lines cl
                       join public.authorizations a on a.cycle_id=cl.cycle_id and a.user_id=cl.added_by and a.decision='AUTHORIZED'
                       where cl.cycle_id=%s and cl.status='ACTIVE' group by cl.product_id""",
                    [cycle["id"]],
                )
                requested=await cursor.fetchall()
                product_ids=[row["product_id"] for row in requested]
                await cursor.execute(
                    "select product_id,available_quantity,reserved_quantity from public.inventory where product_id=any(%s) for update",
                    [product_ids],
                )
                inventory={row["product_id"]:row for row in await cursor.fetchall()}
                reservations=[{**row,**inventory.get(row["product_id"],{})} for row in requested]
                for reservation in reservations:
                    if "available_quantity" not in reservation or reservation["reserved_quantity"]+reservation["quantity"]>reservation["available_quantity"]:
                        raise HTTPException(status_code=409,detail=f"Stock changed for product {reservation['product_id']}. Review the cart before closing.")
                for reservation in reservations:
                    await cursor.execute("update public.inventory set reserved_quantity=reserved_quantity+%s where product_id=%s",[reservation["quantity"],reservation["product_id"]])

                subtotal=sum(line["quantity"]*line["unit_price_snapshot"] for line in included)
                order_number=f"SMB-{str(cycle['id'])[-8:].upper()}"
                await cursor.execute(
                    """insert into public.orders (cycle_id,order_number,status,subtotal)
                       values (%s,%s,'AWAITING_COMMITMENT',%s) returning id""",
                    [cycle["id"],order_number,subtotal],
                )
                order_id=(await cursor.fetchone())["id"]
                member_totals={}
                for line in included:
                    snapshot={"id":str(line["product_id"]),"name":line["name"],"sku":line["sku"],"unit":line["unit"]}
                    total=line["quantity"]*line["unit_price_snapshot"]
                    await cursor.execute(
                        """insert into public.order_lines
                           (order_id,source_line_id,product_id,product_snapshot,quantity,unit_price,total)
                           values (%s,%s,%s,%s::jsonb,%s,%s,%s) returning id""",
                        [order_id,line["id"],line["product_id"],json.dumps(snapshot),line["quantity"],line["unit_price_snapshot"],total],
                    )
                    order_line_id=(await cursor.fetchone())["id"]
                    await cursor.execute(
                        "insert into public.allocations (order_id,user_id,line_id,amount,basis) values (%s,%s,%s,%s,'CLAIMANT_LEVEL')",
                        [order_id,line["added_by"],order_line_id,total],
                    )
                    member_totals[line["added_by"]]=member_totals.get(line["added_by"],0)+total
                for member_id,amount in member_totals.items():
                    await cursor.execute(
                        "insert into public.cash_obligations (order_id,user_id,amount_due,status) values (%s,%s,%s,'DUE')",
                        [order_id,member_id,amount],
                    )

                await cursor.execute(
                    """update public.cart_lines cl set status='ROLLED_FORWARD'
                       where cl.cycle_id=%s and cl.status='ACTIVE' and not exists (
                         select 1 from public.authorizations a where a.cycle_id=cl.cycle_id
                         and a.user_id=cl.added_by and a.decision='AUTHORIZED')""",
                    [cycle["id"]],
                )
                await cursor.execute("update public.order_cycles set status='AWAITING_COMMITMENT',version=version+1 where id=%s",[cycle["id"]])
                correlation_id=await add_audit(cursor,user.id,"CUTOFF_APPLIED","ORDER_CYCLE",cycle["id"],{"orderId":str(order_id),"includedMembers":len(member_totals),"subtotal":str(subtotal)})
                await cursor.execute(
                    """insert into public.outbox_events (event_type,aggregate_id,correlation_id,payload)
                       values ('CASH_COMMITMENTS_REQUESTED',%s,%s,%s::jsonb)""",
                    [order_id,correlation_id,json.dumps({"memberCount":len(member_totals)})],
                )
        return await read_journey(connection,user.id)


@router.post("/commit-cash")
async def commit_cash(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_shopper(cursor,user.id)
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
                await require_coordinator_or_admin(cursor,cycle["group_id"],user.id)
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
                        """select product_id,sum(quantity)::int as quantity from public.order_lines
                           where order_id=%s group by product_id""",
                        [order["id"]],
                    )
                    for stock in await cursor.fetchall():
                        await cursor.execute(
                            """update public.inventory set available_quantity=available_quantity-%s,
                               reserved_quantity=reserved_quantity-%s where product_id=%s
                               and reserved_quantity>=%s and available_quantity>=%s""",
                            [stock["quantity"],stock["quantity"],stock["product_id"],stock["quantity"],stock["quantity"]],
                        )
                        if cursor.rowcount!=1:
                            raise HTTPException(status_code=409,detail=f"Reserved stock is inconsistent for product {stock['product_id']}.")
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
                    await notify_group(cursor,cycle["group_id"],"ORDER_PLACED","Shared order placed",f"Order {order['id']} was accepted by the mock retailer.",order["id"])
        return await read_journey(connection, user.id)


@router.post("/collect-cash")
async def collect_cash(payload: CollectCashRequest | None = None, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_admin(cursor, user.id)
                order_filter = "and o.id=%s" if payload and payload.orderId else ""
                member_filter = "and co.user_id=%s" if payload and payload.memberId else ""
                params = [user.id]
                if payload and payload.orderId: params.append(payload.orderId)
                if payload and payload.memberId: params.append(payload.memberId)
                await cursor.execute(
                    """select co.id,co.status,co.amount_due,co.amount_collected,o.id as order_id
                    from public.cash_obligations co
                    join public.orders o on o.id=co.order_id
                    join public.order_cycles oc on oc.id=o.cycle_id
                    join public.group_members gm on gm.group_id=oc.group_id
                    where gm.user_id=%s and co.status in ('COMMITTED','PARTIALLY_COLLECTED') """ + order_filter + member_filter + """
                    order by o.updated_at desc,co.updated_at limit 1 for update of co""",
                    params,
                )
                obligation = await cursor.fetchone()
                if not obligation:
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
                correlation_id=await add_audit(cursor, user.id, "CASH_COLLECTED", "ORDER", obligation["order_id"], {"amount": str(remaining)})
                await cursor.execute(
                    """insert into public.outbox_events (event_type,aggregate_id,correlation_id,payload)
                       values ('CASH_COLLECTED',%s,%s,%s::jsonb)""",
                    [obligation["order_id"],correlation_id,json.dumps({"amount":str(remaining)})],
                )
        return await read_journey(connection, user.id)


@router.post("/collect-items")
async def collect_items(payload: CollectItemsRequest | None = None, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_admin(cursor,user.id)
                filters=[]
                params=[user.id]
                if payload and payload.orderId:
                    filters.append("o.id=%s")
                    params.append(payload.orderId)
                if payload and payload.memberId:
                    filters.append("co.user_id=%s")
                    params.append(payload.memberId)
                extra=(" and "+" and ".join(filters)) if filters else ""
                await cursor.execute(
                    """select o.id as order_id,co.user_id from public.orders o
                       join public.order_cycles oc on oc.id=o.cycle_id
                       join public.group_members gm on gm.group_id=oc.group_id and gm.user_id=%s
                       join public.cash_obligations co on co.order_id=o.id
                       where o.status='READY_FOR_PICKUP'"""+extra+"""
                         and not exists(select 1 from public.item_collection_records ic
                           where ic.order_id=o.id and ic.user_id=co.user_id)
                       order by o.updated_at desc,co.updated_at limit 1 for update of o""",
                    params,
                )
                collection=await cursor.fetchone()
                if not collection:
                    raise HTTPException(status_code=409,detail="No outstanding item collection was found.")
                await cursor.execute(
                    """insert into public.item_collection_records (order_id,user_id,recorded_by,note)
                       values (%s,%s,%s,'Items collected at pickup')""",
                    [collection["order_id"],collection["user_id"],user.id],
                )
                correlation_id=await add_audit(cursor,user.id,"ITEMS_COLLECTED","ORDER",collection["order_id"],{"memberId":str(collection["user_id"])})
                await cursor.execute(
                    """insert into public.outbox_events (event_type,aggregate_id,correlation_id,payload)
                       values ('ITEMS_COLLECTED',%s,%s,%s::jsonb)""",
                    [collection["order_id"],correlation_id,json.dumps({"memberId":str(collection["user_id"])})],
                )
        return await read_journey(connection,user.id)


@router.post("/fulfilment")
async def update_fulfilment(payload: FulfilmentRequest, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_admin(cursor, user.id)
                if payload.orderId:
                    await cursor.execute(
                        """select o.id,o.status,oc.id as cycle_id,oc.group_id,oc.pickup_point_id
                        from public.orders o join public.order_cycles oc on oc.id=o.cycle_id
                        join public.group_members gm on gm.group_id=oc.group_id
                        where o.id=%s and gm.user_id=%s for update of o""",
                        [payload.orderId, user.id],
                    )
                else:
                    cycle = await current_cycle(cursor, user.id)
                    await cursor.execute(
                        """select o.id,o.status,oc.id as cycle_id,oc.group_id,oc.pickup_point_id
                        from public.orders o join public.order_cycles oc on oc.id=o.cycle_id
                        where o.cycle_id=%s for update of o""",
                        [cycle["id"]],
                    )
                order = await cursor.fetchone()
                if not order or not can_transition_fulfilment(order["status"],payload.status):
                    current = order["status"] if order else "NO_ORDER"
                    raise HTTPException(status_code=409, detail=f"Transition {current} → {payload.status} is not allowed.")
                if payload.status == "CANCELLED":
                    reason=(payload.reason or "").strip()
                    if len(reason)<5:
                        raise HTTPException(status_code=422,detail="A cancellation reason of at least five characters is required.")
                    await cursor.execute(
                        "select count(*) as collected from public.cash_obligations where order_id=%s and amount_collected>0",
                        [order["id"]],
                    )
                    cash_collected=(await cursor.fetchone())["collected"]
                    await cursor.execute("select count(*) as collected from public.item_collection_records where order_id=%s",[order["id"]])
                    items_collected=(await cursor.fetchone())["collected"]
                    if not can_cancel_order(order_status=order["status"],cash_collections=cash_collected,item_collections=items_collected):
                        raise HTTPException(status_code=409,detail="An order with recorded cash or item collection requires a support correction, not cancellation.")
                    await cursor.execute(
                        """select product_id,sum(quantity)::int as quantity from public.order_lines
                           where order_id=%s group by product_id""",
                        [order["id"]],
                    )
                    for stock in await cursor.fetchall():
                        await cursor.execute(
                            "update public.inventory set available_quantity=available_quantity+%s where product_id=%s",
                            [stock["quantity"],stock["product_id"]],
                        )
                    await cursor.execute("update public.cash_obligations set status='CANCELLED' where order_id=%s",[order["id"]])
                    await cursor.execute("update public.order_cycles set status='CANCELLED',version=version+1 where id=%s",[order["cycle_id"]])
                if payload.status == "FULFILLED":
                    await cursor.execute("update public.order_cycles set status='CLOSED',version=version+1 where id=%s",[order["cycle_id"]])
                    await cursor.execute(
                        "select count(*) as pending from public.cash_obligations where order_id=%s and status<>'COLLECTED'",
                        [order["id"]],
                    )
                    if (await cursor.fetchone())["pending"]:
                        raise HTTPException(status_code=409, detail="Record cash collection before fulfilment.")
                    await cursor.execute(
                        """select count(*) as pending from public.cash_obligations co where co.order_id=%s
                           and not exists(select 1 from public.item_collection_records ic
                             where ic.order_id=co.order_id and ic.user_id=co.user_id)""",
                        [order["id"]],
                    )
                    if (await cursor.fetchone())["pending"]:
                        raise HTTPException(status_code=409,detail="Record every member's item collection before fulfilment.")
                await cursor.execute("update public.orders set status=%s,version=version+1 where id=%s", [payload.status, order["id"]])
                await cursor.execute(
                    """insert into public.fulfilment_events (order_id,old_status,new_status,actor_id,source,note)
                    values (%s,%s,%s,%s,'ADMIN_UI',%s)""",
                    [order["id"], order["status"], payload.status, user.id, (payload.reason or "Demo fulfilment control").strip()],
                )
                correlation_id=await add_audit(cursor, user.id, f"ORDER_{payload.status}", "ORDER", order["id"], {"from": order["status"], "to": payload.status, "reason": payload.reason})
                await cursor.execute(
                    """insert into public.outbox_events (event_type,aggregate_id,correlation_id,payload)
                       values (%s,%s,%s,%s::jsonb)""",
                    [f"ORDER_{payload.status}",order["id"],correlation_id,json.dumps({"oldStatus":order["status"],"newStatus":payload.status})],
                )
                notification_messages={
                    "PREPARING":("Order preparation started","The retailer is preparing your shared order."),
                    "READY_FOR_PICKUP":("Order ready for pickup","Your shared order is ready at the configured pickup point."),
                    "FULFILLED":("Order fulfilled","All cash and item-collection obligations are complete."),
                    "CANCELLED":("Order cancelled",f"The shared order was cancelled. Reason: {(payload.reason or '').strip()}"),
                }
                title,message=notification_messages[payload.status]
                await notify_group(cursor,order["group_id"],f"ORDER_{payload.status}",title,message,order["id"])
                if payload.status in ("FULFILLED","CANCELLED"):
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
                        await cursor.execute(
                            """insert into public.cart_lines
                               (cycle_id,added_by,product_id,source_text,quantity,unit_price_snapshot,status)
                               select %s,added_by,product_id,'Rolled forward after cutoff',quantity,unit_price_snapshot,'ACTIVE'
                               from public.cart_lines where cycle_id=%s and status='ROLLED_FORWARD'""",
                            [new_cycle_id,order["cycle_id"]],
                        )
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
