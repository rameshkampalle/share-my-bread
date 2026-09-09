import json
import uuid
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.shared.auth import CurrentUser, get_current_user
from app.shared.access import require_shopper
from app.domain.order_policy import can_edit_line
from app.shared.config import get_settings

router = APIRouter(prefix="/api/cart", tags=["cart"])


class ProposalItem(BaseModel):
    productId: uuid.UUID
    quantity: int = Field(ge=1, le=99)


class CartProposal(BaseModel):
    action: Literal["ADD_ITEMS"]
    items: list[ProposalItem] = Field(min_length=1, max_length=20)


class ConfirmRequest(BaseModel):
    cycleId: uuid.UUID
    correlationId: uuid.UUID
    sourceText: str = Field(min_length=1, max_length=500)
    proposal: CartProposal


class AddItemRequest(BaseModel):
    productId: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateItemRequest(BaseModel):
    quantity: int = Field(ge=1, le=99)


def database_url() -> str:
    value = get_settings().database_url
    if not value:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured.")
    return value


async def connect_database():
    return await psycopg.AsyncConnection.connect(
        database_url(),
        connect_timeout=10,
        options="-c statement_timeout=15000 -c lock_timeout=5000",
    )


async def read_cart(connection, user_id: str, cycle_id: str | None = None):
    cycle_filter = "and oc.id = %s" if cycle_id else ""
    params = [user_id, cycle_id] if cycle_id else [user_id]
    query = f"""
        select oc.id as cycle_id, oc.group_id, oc.cutoff_at, g.name as group_name
        from public.order_cycles oc
        join public.groups g on g.id = oc.group_id
        join public.group_members gm on gm.group_id = g.id
        left join public.orders o on o.cycle_id=oc.id
        where gm.user_id = %s
          and oc.status in ('OPEN','REVIEW','AWAITING_COMMITMENT','FINALIZED')
          {cycle_filter}
        order by case
          when oc.status in ('REVIEW','AWAITING_COMMITMENT') then 0
          when oc.status='OPEN' then 1
          when oc.status='FINALIZED' and coalesce(o.status,'') not in ('FULFILLED','CANCELLED') then 2
          else 3 end,
          oc.updated_at desc
        limit 1
    """
    async with connection.cursor(row_factory=dict_row) as cursor:
        profile = await require_shopper(cursor, user_id)
        await cursor.execute(query, params)
        cycle = await cursor.fetchone()
        if not cycle:
            raise HTTPException(status_code=404, detail="No open order cycle was found for this member.")
        await cursor.execute(
            """
            select cl.id, cl.product_id, p.name, p.sku, p.unit, cl.quantity,
                   cl.unit_price_snapshot as unit_price,
                   (cl.quantity * cl.unit_price_snapshot)::numeric(12,2) as line_total,
                   cl.added_by as contributor_id, pr.display_name as contributor_name,
                   (cl.added_by=%s or %s='ADMIN' or gm.member_role='COORDINATOR') as editable
            from public.cart_lines cl
            join public.products p on p.id = cl.product_id
            join public.profiles pr on pr.id=cl.added_by
            join public.group_members gm on gm.group_id=%s and gm.user_id=%s
            where cl.cycle_id = %s and cl.status = 'ACTIVE'
            order by pr.display_name,cl.created_at
            """,
            [user_id,profile.app_role,cycle["group_id"],user_id,cycle["cycle_id"]],
        )
        lines = await cursor.fetchall()
        await cursor.execute(
            """select coalesce(sum(quantity*unit_price_snapshot),0)::numeric(12,2) as subtotal
               from public.cart_lines where cycle_id=%s and added_by=%s and status='ACTIVE'""",
            [cycle["cycle_id"],user_id],
        )
        member_subtotal=(await cursor.fetchone())["subtotal"]
    subtotal = sum(line["line_total"] for line in lines)
    return {**cycle, "lines": lines, "subtotal": subtotal, "member_subtotal": member_subtotal,
            "currency": "EUR", "viewer_role": profile.app_role}


@router.get("/current")
async def get_current_cart(user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        return await read_cart(connection, user.id)


async def require_open_cycle(cursor, user_id: str):
    await require_shopper(cursor, user_id)
    await cursor.execute(
        """
        select oc.id from public.order_cycles oc
        join public.group_members gm on gm.group_id=oc.group_id
        where gm.user_id=%s and oc.status='OPEN' and oc.cutoff_at>timezone('utc',now())
        order by oc.cutoff_at limit 1 for update of oc
        """,
        [user_id],
    )
    cycle = await cursor.fetchone()
    if not cycle:
        raise HTTPException(status_code=409, detail="The cart is locked because checkout has started.")
    return cycle["id"]


@router.post("/items")
async def add_item(payload: AddItemRequest, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                cycle_id = await require_open_cycle(cursor, user.id)
                await cursor.execute(
                    """
                    select p.id,p.price,(i.available_quantity-i.reserved_quantity) as free
                    from public.products p join public.inventory i on i.product_id=p.id
                    where p.id=%s and p.active=true for update of i
                    """,
                    [payload.productId],
                )
                product = await cursor.fetchone()
                if not product:
                    raise HTTPException(status_code=409, detail="The requested product quantity is unavailable.")
                await cursor.execute(
                    """select coalesce(sum(quantity),0) as in_cart from public.cart_lines
                       where cycle_id=%s and product_id=%s and status='ACTIVE'""",
                    [cycle_id,payload.productId],
                )
                if (await cursor.fetchone())["in_cart"] + payload.quantity > product["free"]:
                    raise HTTPException(status_code=409, detail="The requested product quantity is unavailable.")
                await cursor.execute(
                    """
                    select id,quantity from public.cart_lines
                    where cycle_id=%s and added_by=%s and product_id=%s and status='ACTIVE'
                    order by created_at limit 1 for update
                    """,
                    [cycle_id,user.id,payload.productId],
                )
                line = await cursor.fetchone()
                if line:
                    await cursor.execute("update public.cart_lines set quantity=quantity+%s where id=%s", [payload.quantity,line["id"]])
                else:
                    await cursor.execute(
                        """insert into public.cart_lines
                        (cycle_id,added_by,product_id,source_text,quantity,unit_price_snapshot,status)
                        values (%s,%s,%s,'Manual catalogue add',%s,%s,'ACTIVE')""",
                        [cycle_id,user.id,payload.productId,payload.quantity,product["price"]],
                    )
                await cursor.execute("delete from public.authorizations where cycle_id=%s and user_id=%s",[cycle_id,user.id])
        return await read_cart(connection,user.id,str(cycle_id))


@router.patch("/items/{line_id}")
async def update_item(line_id: uuid.UUID, payload: UpdateItemRequest, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                profile=await require_shopper(cursor,user.id)
                await cursor.execute(
                    """select cl.id,cl.cycle_id,cl.product_id,cl.added_by,
                              (i.available_quantity-i.reserved_quantity) as free,gm.member_role
                    from public.cart_lines cl join public.order_cycles oc on oc.id=cl.cycle_id
                    join public.inventory i on i.product_id=cl.product_id
                    join public.group_members gm on gm.group_id=oc.group_id and gm.user_id=%s
                    where cl.id=%s and cl.status='ACTIVE' and oc.status='OPEN'
                      and oc.cutoff_at>timezone('utc',now())
                    for update of cl,i""",
                    [user.id,line_id],
                )
                line=await cursor.fetchone()
                if not line or not can_edit_line(app_role=profile.app_role,member_role=line["member_role"],actor_id=user.id,owner_id=str(line["added_by"])):
                    raise HTTPException(status_code=404,detail="Editable cart line not found.")
                await cursor.execute(
                    """select coalesce(sum(quantity),0) as other_quantity from public.cart_lines
                       where cycle_id=%s and product_id=%s and status='ACTIVE' and id<>%s""",
                    [line["cycle_id"],line["product_id"],line_id],
                )
                if (await cursor.fetchone())["other_quantity"] + payload.quantity > line["free"]:
                    raise HTTPException(status_code=409,detail="The requested quantity exceeds available stock.")
                await cursor.execute("update public.cart_lines set quantity=%s where id=%s",[payload.quantity,line_id])
                await cursor.execute("delete from public.authorizations where cycle_id=%s and user_id=%s",[line["cycle_id"],line["added_by"]])
        return await read_cart(connection,user.id,str(line["cycle_id"]))


@router.delete("/items/{line_id}")
async def remove_item(line_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)):
    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                profile=await require_shopper(cursor,user.id)
                await cursor.execute(
                    """select cl.id,cl.cycle_id,cl.added_by,gm.member_role from public.cart_lines cl
                       join public.order_cycles oc on oc.id=cl.cycle_id
                       join public.group_members gm on gm.group_id=oc.group_id and gm.user_id=%s
                       where cl.id=%s and cl.status='ACTIVE' and oc.status='OPEN'
                         and oc.cutoff_at>timezone('utc',now()) for update of cl""",
                    [user.id,line_id],
                )
                line=await cursor.fetchone()
                if not line or not can_edit_line(app_role=profile.app_role,member_role=line["member_role"],actor_id=user.id,owner_id=str(line["added_by"])):
                    raise HTTPException(status_code=404,detail="Editable cart line not found.")
                await cursor.execute("update public.cart_lines set status='REMOVED' where id=%s",[line_id])
                await cursor.execute("delete from public.authorizations where cycle_id=%s and user_id=%s",[line["cycle_id"],line["added_by"]])
        return await read_cart(connection,user.id,str(line["cycle_id"]))


@router.post("/confirm")
async def confirm_proposal(
    payload: ConfirmRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key or len(idempotency_key) > 120:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required.")
    if len({item.productId for item in payload.proposal.items}) != len(payload.proposal.items):
        raise HTTPException(status_code=400, detail="A product may appear only once per proposal.")

    async with await connect_database() as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await require_shopper(cursor,user.id)
                await cursor.execute(
                    "select response_body from public.idempotency_records where actor_id=%s and idempotency_key=%s",
                    [user.id, idempotency_key],
                )
                previous = await cursor.fetchone()
                if previous:
                    return previous["response_body"]

                await cursor.execute(
                    """
                    select oc.id from public.order_cycles oc
                    join public.group_members gm on gm.group_id=oc.group_id
                    where oc.id=%s and oc.status='OPEN' and gm.user_id=%s
                      and oc.cutoff_at>timezone('utc',now())
                    for update of oc
                    """,
                    [payload.cycleId, user.id],
                )
                if not await cursor.fetchone():
                    raise HTTPException(status_code=403, detail="The order cycle is not open for this member.")

                ids = [item.productId for item in payload.proposal.items]
                await cursor.execute(
                    """
                    select p.id, p.price, i.available_quantity, i.reserved_quantity
                    from public.products p join public.inventory i on i.product_id=p.id
                    where p.id = any(%s) and p.active=true for update of i
                    """,
                    [ids],
                )
                products = {row["id"]: row for row in await cursor.fetchall()}
                if len(products) != len(ids):
                    raise HTTPException(status_code=409, detail="One or more products are unavailable.")

                for item in payload.proposal.items:
                    product = products[item.productId]
                    free = product["available_quantity"] - product["reserved_quantity"]
                    await cursor.execute(
                        """select coalesce(sum(quantity),0) as in_cart from public.cart_lines
                           where cycle_id=%s and product_id=%s and status='ACTIVE'""",
                        [payload.cycleId,item.productId],
                    )
                    if (await cursor.fetchone())["in_cart"] + item.quantity > free:
                        raise HTTPException(status_code=409, detail=f"Insufficient stock for product {item.productId}.")
                    await cursor.execute(
                        """
                        select id from public.cart_lines
                        where cycle_id=%s and added_by=%s and product_id=%s and status='ACTIVE'
                        order by created_at limit 1 for update
                        """,
                        [payload.cycleId, user.id, item.productId],
                    )
                    existing = await cursor.fetchone()
                    if existing:
                        await cursor.execute(
                            "update public.cart_lines set quantity=quantity+%s, updated_at=timezone('utc',now()) where id=%s",
                            [item.quantity, existing["id"]],
                        )
                    else:
                        await cursor.execute(
                            """
                            insert into public.cart_lines
                              (cycle_id,added_by,product_id,source_text,quantity,unit_price_snapshot,status)
                            values (%s,%s,%s,%s,%s,%s,'ACTIVE')
                            """,
                            [payload.cycleId, user.id, item.productId, payload.sourceText, item.quantity, product["price"]],
                        )

                await cursor.execute("delete from public.authorizations where cycle_id=%s and user_id=%s",[payload.cycleId,user.id])

                await cursor.execute(
                    """
                    insert into public.agent_proposals
                      (correlation_id,idempotency_key,cycle_id,user_id,action,payload,status,decided_at)
                    values (%s,%s,%s,%s,'ADD_ITEM',%s::jsonb,'ACCEPTED',timezone('utc',now()))
                    """,
                    [payload.correlationId, idempotency_key, payload.cycleId, user.id, json.dumps(payload.proposal.model_dump(mode="json"))],
                )
                cart = await read_cart(connection, user.id, str(payload.cycleId))
                result = {"status": "CONFIRMED", "correlationId": payload.correlationId, "cart": cart}
                serializable = json.loads(json.dumps(result, default=str))
                await cursor.execute(
                    """
                    insert into public.idempotency_records
                      (actor_id,idempotency_key,command_name,response_status,response_body)
                    values (%s,%s,'CONFIRM_CART_PROPOSAL',200,%s::jsonb)
                    """,
                    [user.id, idempotency_key, json.dumps(serializable)],
                )
                await cursor.execute(
                    """
                    insert into public.audit_events
                      (correlation_id,actor_id,action,entity_type,entity_id,after_json)
                    values (%s,%s,'CART_PROPOSAL_CONFIRMED','ORDER_CYCLE',%s,%s::jsonb)
                    """,
                    [payload.correlationId, user.id, payload.cycleId, json.dumps(payload.proposal.model_dump(mode="json"))],
                )
                return serializable
