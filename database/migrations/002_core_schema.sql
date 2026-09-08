-- Share My Bread / 002_core_schema.sql

begin;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default 'Member',
  app_role text not null default 'MEMBER' check (app_role in ('MEMBER','ADMIN')),
  memory_consent boolean not null default false,
  status text not null default 'ACTIVE' check (status in ('ACTIVE','SUSPENDED')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.groups (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 2 and 120),
  coordinator_id uuid not null references public.profiles(id),
  join_code text not null unique check (char_length(join_code) between 6 and 20),
  status text not null default 'ACTIVE' check (status in ('ACTIVE','CLOSED')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.group_members (
  group_id uuid not null references public.groups(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  member_role text not null default 'MEMBER' check (member_role in ('MEMBER','COORDINATOR')),
  reliability_state text not null default 'GOOD' check (reliability_state in ('GOOD','REVIEW','BLOCKED')),
  joined_at timestamptz not null default timezone('utc', now()),
  primary key (group_id, user_id)
);

create table if not exists public.pickup_points (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references public.groups(id) on delete cascade,
  label text not null,
  address_text text not null,
  latitude numeric(9,6),
  longitude numeric(9,6),
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  sku text not null unique,
  name text not null,
  description text not null default '',
  category text not null,
  brand text,
  unit text not null,
  price numeric(10,2) not null check (price >= 0),
  currency char(3) not null default 'EUR',
  aliases text[] not null default '{}',
  dietary_tags text[] not null default '{}',
  image_url text,
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.inventory (
  product_id uuid primary key references public.products(id) on delete cascade,
  available_quantity integer not null default 0 check (available_quantity >= 0),
  reserved_quantity integer not null default 0 check (reserved_quantity >= 0),
  updated_at timestamptz not null default timezone('utc', now()),
  check (reserved_quantity <= available_quantity)
);

create table if not exists public.order_cycles (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references public.groups(id) on delete cascade,
  cutoff_at timestamptz not null,
  pickup_point_id uuid references public.pickup_points(id),
  status text not null default 'DRAFT' check (status in ('DRAFT','OPEN','REVIEW','AWAITING_COMMITMENT','FINALIZED','CANCELLED','CLOSED_EMPTY')),
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.cart_lines (
  id uuid primary key default gen_random_uuid(),
  cycle_id uuid not null references public.order_cycles(id) on delete cascade,
  added_by uuid not null references public.profiles(id),
  product_id uuid not null references public.products(id),
  source_text text,
  quantity integer not null check (quantity > 0),
  unit_price_snapshot numeric(10,2) not null check (unit_price_snapshot >= 0),
  status text not null default 'ACTIVE' check (status in ('ACTIVE','MERGED','REMOVED','ROLLED_FORWARD')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.line_claims (
  id uuid primary key default gen_random_uuid(),
  cart_line_id uuid not null references public.cart_lines(id) on delete cascade,
  user_id uuid not null references public.profiles(id),
  quantity integer not null check (quantity > 0),
  decision text not null default 'PENDING' check (decision in ('PENDING','CLAIMED','DECLINED')),
  decided_at timestamptz,
  unique (cart_line_id, user_id)
);

create table if not exists public.authorizations (
  id uuid primary key default gen_random_uuid(),
  cycle_id uuid not null references public.order_cycles(id) on delete cascade,
  user_id uuid not null references public.profiles(id),
  decision text not null check (decision in ('AUTHORIZED','DECLINED')),
  snapshot_hash text not null,
  decided_at timestamptz not null default timezone('utc', now()),
  unique (cycle_id, user_id)
);

create table if not exists public.agent_proposals (
  id uuid primary key default gen_random_uuid(),
  correlation_id uuid not null,
  idempotency_key text not null,
  cycle_id uuid not null references public.order_cycles(id) on delete cascade,
  user_id uuid not null references public.profiles(id),
  action text not null check (action in ('ADD_ITEM','MERGE_ITEMS','SUBSTITUTE_ITEM')),
  payload jsonb not null,
  status text not null default 'PENDING' check (status in ('PENDING','ACCEPTED','REJECTED','EXPIRED')),
  expires_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  decided_at timestamptz,
  unique (user_id, idempotency_key)
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1), 'Member'))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

drop trigger if exists products_set_updated_at on public.products;
create trigger products_set_updated_at before update on public.products
for each row execute function public.set_updated_at();

drop trigger if exists inventory_set_updated_at on public.inventory;
create trigger inventory_set_updated_at before update on public.inventory
for each row execute function public.set_updated_at();

drop trigger if exists cycles_set_updated_at on public.order_cycles;
create trigger cycles_set_updated_at before update on public.order_cycles
for each row execute function public.set_updated_at();

drop trigger if exists cart_lines_set_updated_at on public.cart_lines;
create trigger cart_lines_set_updated_at before update on public.cart_lines
for each row execute function public.set_updated_at();

commit;
