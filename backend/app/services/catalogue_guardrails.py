"""Vector hits select IDs only. Product facts come from the relational catalogue."""
import json

from psycopg.rows import dict_row

from app.api.cart import connect_database
from app.services.guardrails import GuardrailUnavailable


async def read_products(product_ids):
    async with await connect_database() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """select p.id, p.name, p.unit, p.category, p.price, p.currency,
                          greatest(i.available_quantity-i.reserved_quantity,0) as available
                   from public.products p join public.inventory i on i.product_id=p.id
                   where p.active=true and p.id=any(%s::uuid[])""", [product_ids])
            return await cursor.fetchall()


async def checked_catalogue(product_ids, checker):
    if not product_ids:
        return {'results': [], 'source': 'database', 'count': 0}
    try:
        ids = list(dict.fromkeys(str(value) for value in product_ids))
        rows = await read_products(ids)
        by_id = {str(row['id']): row for row in rows}
        products = [
            {'productId': value, 'name': by_id[value]['name'], 'unit': by_id[value]['unit'],
             'category': by_id[value]['category'], 'price': str(by_id[value]['price']),
             'currency': by_id[value]['currency'], 'availableQuantity': by_id[value]['available']}
            for value in ids if value in by_id
        ]
        if products:
            text = json.dumps(products, ensure_ascii=False)
            if len(text) > 16000:
                raise GuardrailUnavailable()
            checked = await checker.check('retrieval', text)
            # Rewriting structured identifiers/prices could corrupt catalogue facts.
            if checked['status'] != 'passed' or checked['text'] != text:
                raise GuardrailUnavailable()
        return {'results': products, 'source': 'database', 'count': len(products)}
    except Exception:
        raise GuardrailUnavailable() from None
