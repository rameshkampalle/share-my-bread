select count(*) as active_products from public.products where active;

select p.sku, p.name, p.category, p.price, i.available_quantity, i.reserved_quantity
from public.products p
join public.inventory i on i.product_id = p.id
order by p.category, p.name;

select table_name, is_insertable_into
from information_schema.tables
where table_schema = 'public'
order by table_name;

select extname, extversion
from pg_extension
where extname = 'pgcrypto';
