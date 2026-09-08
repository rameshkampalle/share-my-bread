import json
import uuid
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.shared.auth import CurrentUser, get_current_user
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


def database_url() -> str:
    value = get_settings().database_url
    if not value:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured.")
    return value


async def read_cart(connection, user_id: str, cycle_id: str | None = None):
    cycle_filter = "and oc.id = %s" if cycle_id else ""
    params = [user_id, cycle_id] if cycle_id else [user_id]
    query = f"""
        select oc.id as cycle_id, oc.cutoff_at, g.name as group_name
        from public.order_cycles oc
        join public.groups g on g.id = oc.group_id
        join public.group_members gm on gm.group_id = g.id
        where gm.user_id = %s and oc.status = 'OPEN' {cycle_filter}
        order by oc.cutoff_at limit 1
    """
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        cycle = await cursor.fetchone()
        if not cycle:
            raise HTTPException(status_code=404, detail="No open order cycle was found for this member.")
        await cursor.execute(
            """
            select cl.id, cl.product_id, p.name, p.sku, p.unit, cl.quantity,
                   cl.unit_price_snapshot as unit_price,
                   (cl.quantity * cl.unit_price_snapshot)::numeric(12,2) as line_total
            from public.cart_lines cl
            join public.products p on p.id = cl.product_id
            where cl.cycle_id = %s and cl.added_by = %s and cl.status = 'ACTIVE'
            order by cl.created_at
            """,
            [cycle["cycle_id"], user_id],
        )
        lines = await cursor.fetchall()
    subtotal = sum(float(line["line_total"]) for line in lines)
    return {**cycle, "lines": lines, "subtotal": round(subtotal, 2), "currency": "EUR"}


@router.get("/current")
async def get_current_cart(user: CurrentUser = Depends(get_current_user)):
    async with await psycopg.AsyncConnection.connect(database_url()) as connection:
        return await read_cart(connection, user.id)


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

    async with await psycopg.AsyncConnection.connect(database_url()) as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
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
                    if item.quantity > free:
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
