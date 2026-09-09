-- Multi-user MVP invariants. Delivery operators use the existing ADMIN role.
-- Safe to run once after 001-005.

begin;

alter table public.order_cycles drop constraint if exists order_cycles_status_check;
alter table public.order_cycles add constraint order_cycles_status_check
  check (status in ('DRAFT','OPEN','REVIEW','AWAITING_COMMITMENT','FINALIZED','CANCELLED','CLOSED_EMPTY','CLOSED'));

-- A group may have only one cart that members can actively change/authorize.
create unique index if not exists one_working_cycle_per_group_idx
  on public.order_cycles (group_id)
  where status in ('DRAFT','OPEN','REVIEW','AWAITING_COMMITMENT');

create table if not exists public.item_collection_records (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  user_id uuid not null references public.profiles(id),
  recorded_by uuid not null references public.profiles(id),
  note text,
  collected_at timestamptz not null default timezone('utc',now()),
  unique (order_id,user_id)
);

alter table public.item_collection_records enable row level security;

commit;
