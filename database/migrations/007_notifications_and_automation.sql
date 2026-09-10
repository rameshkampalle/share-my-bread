-- In-app notifications and scheduler idempotency for the multi-user MVP.
-- Run once after 006_multi_user_roles.sql.

begin;

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  notification_type text not null,
  title text not null,
  message text not null,
  aggregate_id uuid,
  dedupe_key text not null unique,
  read_at timestamptz,
  created_at timestamptz not null default timezone('utc',now())
);

create index if not exists notifications_user_created_idx
  on public.notifications (user_id,created_at desc);
create index if not exists notifications_user_unread_idx
  on public.notifications (user_id,created_at desc) where read_at is null;

alter table public.notifications enable row level security;

commit;
