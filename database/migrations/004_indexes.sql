-- Share My Bread / 004_indexes.sql

begin;

create index if not exists products_active_category_idx on public.products (active, category);
create index if not exists products_name_lower_idx on public.products (lower(name));
create index if not exists products_aliases_gin_idx on public.products using gin (aliases);
create index if not exists group_members_user_idx on public.group_members (user_id, group_id);
create index if not exists pickup_points_group_active_idx on public.pickup_points (group_id, active);
create index if not exists cycles_group_status_idx on public.order_cycles (group_id, status);
create index if not exists cycles_cutoff_status_idx on public.order_cycles (cutoff_at, status);
create index if not exists cart_lines_cycle_status_idx on public.cart_lines (cycle_id, status);
create index if not exists authorizations_cycle_idx on public.authorizations (cycle_id, decision);
create index if not exists proposals_cycle_status_idx on public.agent_proposals (cycle_id, status);
create index if not exists orders_status_idx on public.orders (status, updated_at);
create index if not exists allocations_order_user_idx on public.allocations (order_id, user_id);
create index if not exists obligations_order_status_idx on public.cash_obligations (order_id, status);
create index if not exists fulfilment_order_created_idx on public.fulfilment_events (order_id, created_at);
create index if not exists audit_entity_created_idx on public.audit_events (entity_type, entity_id, created_at);
create index if not exists outbox_pending_idx on public.outbox_events (available_at) where status in ('PENDING','FAILED');

commit;
