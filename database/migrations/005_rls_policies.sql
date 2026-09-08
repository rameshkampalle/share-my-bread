-- Share My Bread / 005_rls_policies.sql
-- Browser clients are not permitted to mutate business tables directly.
-- The FastAPI backend uses the Supabase service role and enforces domain authorization.

begin;

alter table public.profiles enable row level security;
alter table public.groups enable row level security;
alter table public.group_members enable row level security;
alter table public.pickup_points enable row level security;
alter table public.products enable row level security;
alter table public.inventory enable row level security;
alter table public.order_cycles enable row level security;
alter table public.cart_lines enable row level security;
alter table public.line_claims enable row level security;
alter table public.authorizations enable row level security;
alter table public.agent_proposals enable row level security;
alter table public.orders enable row level security;
alter table public.order_lines enable row level security;
alter table public.allocations enable row level security;
alter table public.cash_obligations enable row level security;
alter table public.collection_records enable row level security;
alter table public.fulfilment_events enable row level security;
alter table public.audit_events enable row level security;
alter table public.outbox_events enable row level security;
alter table public.idempotency_records enable row level security;

drop policy if exists profiles_read_self on public.profiles;
create policy profiles_read_self on public.profiles
for select to authenticated using (id = auth.uid());

drop policy if exists products_read_authenticated on public.products;
create policy products_read_authenticated on public.products
for select to authenticated using (active = true);

drop policy if exists inventory_read_authenticated on public.inventory;
create policy inventory_read_authenticated on public.inventory
for select to authenticated using (true);

commit;
