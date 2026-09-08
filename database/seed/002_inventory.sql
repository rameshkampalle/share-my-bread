-- Share My Bread / reproducible inventory

insert into public.inventory (product_id, available_quantity, reserved_quantity)
select id,
  case sku
    when 'DAIRY-004' then 0
    when 'BAKERY-003' then 3
    when 'VEG-003' then 4
    when 'PULSE-004' then 0
    when 'SNACK-002' then 2
    else 20
  end as available_quantity,
  0 as reserved_quantity
from public.products
where active = true
on conflict (product_id) do update set
  available_quantity = excluded.available_quantity,
  reserved_quantity = excluded.reserved_quantity,
  updated_at = timezone('utc', now());
