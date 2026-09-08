-- Share My Bread / 003_order_audit_schema.sql

begin;

create table if not exists public.orders (
  id uuid primary key default gen_random_uuid(),
  cycle_id uuid not null unique references public.order_cycles(id),
  order_number text not null unique,
  status text not null check (status in ('AWAITING_COMMITMENT','FINALIZED','ORDER_PLACED','PREPARING','READY_FOR_PICKUP','PARTIALLY_COLLECTED','FULFILLED','CANCELLED')),
  subtotal numeric(12,2) not null check (subtotal >= 0),
  version integer not null default 1 check (version > 0),
  finalized_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.order_lines (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  source_line_id uuid references public.cart_lines(id),
  product_id uuid references public.products(id),
  product_snapshot jsonb not null,
  quantity integer not null check (quantity > 0),
  unit_price numeric(10,2) not null check (unit_price >= 0),
  total numeric(12,2) not null check (total >= 0)
);

create table if not exists public.allocations (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  user_id uuid not null references public.profiles(id),
  line_id uuid references public.order_lines(id) on delete cascade,
  amount numeric(12,2) not null check (amount >= 0),
  basis text not null check (basis in ('CLAIMANT_LEVEL','EQUAL_ORDER','FEE','DISCOUNT','TAX'))
);

create table if not exists public.cash_obligations (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  user_id uuid not null references public.profiles(id),
  amount_due numeric(12,2) not null check (amount_due >= 0),
  amount_collected numeric(12,2) not null default 0 check (amount_collected >= 0),
  status text not null default 'DUE' check (status in ('DUE','COMMITTED','PARTIALLY_COLLECTED','COLLECTED','WAIVED','CANCELLED')),
  committed_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (order_id, user_id),
  check (amount_collected <= amount_due)
);

create table if not exists public.collection_records (
  id uuid primary key default gen_random_uuid(),
  obligation_id uuid not null references public.cash_obligations(id) on delete cascade,
  amount numeric(12,2) not null check (amount > 0),
  recorded_by uuid not null references public.profiles(id),
  note text,
  recorded_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.fulfilment_events (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  old_status text,
  new_status text not null,
  actor_id uuid references public.profiles(id),
  source text not null check (source in ('ADMIN_UI','SYSTEM','MOCK_RETAILER')),
  note text,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.audit_events (
  id uuid primary key default gen_random_uuid(),
  correlation_id uuid not null,
  actor_id uuid references public.profiles(id),
  action text not null,
  entity_type text not null,
  entity_id uuid,
  before_json jsonb,
  after_json jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.outbox_events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,
  aggregate_id uuid not null,
  correlation_id uuid not null,
  payload jsonb not null,
  status text not null default 'PENDING' check (status in ('PENDING','PROCESSING','PUBLISHED','FAILED')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.idempotency_records (
  actor_id uuid not null references public.profiles(id),
  idempotency_key text not null,
  command_name text not null,
  response_status integer not null,
  response_body jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (actor_id, idempotency_key)
);

drop trigger if exists orders_set_updated_at on public.orders;
create trigger orders_set_updated_at before update on public.orders
for each row execute function public.set_updated_at();

drop trigger if exists obligations_set_updated_at on public.cash_obligations;
create trigger obligations_set_updated_at before update on public.cash_obligations
for each row execute function public.set_updated_at();

commit;
