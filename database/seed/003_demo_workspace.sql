-- Single-user demo workspace. Safe to rerun.
-- Prerequisite: create and auto-confirm demo.member@sharemybread.test in Supabase Auth.

do $$
declare
  v_user_id uuid;
  v_group_id constant uuid := '20000000-0000-4000-8000-000000000001';
  v_pickup_id constant uuid := '30000000-0000-4000-8000-000000000001';
  v_cycle_id constant uuid := '40000000-0000-4000-8000-000000000001';
begin
  select id into v_user_id from auth.users
  where lower(email)='demo.member@sharemybread.test' limit 1;
  if v_user_id is null then
    raise exception 'Create demo.member@sharemybread.test in Authentication > Users first.';
  end if;

  insert into public.profiles (id,display_name,app_role,status)
  values (v_user_id,'Demo Member','ADMIN','ACTIVE')
  on conflict (id) do update set display_name='Demo Member',app_role='ADMIN',status='ACTIVE',updated_at=timezone('utc',now());

  insert into public.groups (id,name,coordinator_id,join_code,status)
  values (v_group_id,'Share My Bread Demo Group',v_user_id,'SMBDEMO2026','ACTIVE')
  on conflict (id) do update set coordinator_id=v_user_id,status='ACTIVE',updated_at=timezone('utc',now());

  insert into public.group_members (group_id,user_id,member_role,reliability_state)
  values (v_group_id,v_user_id,'COORDINATOR','GOOD')
  on conflict (group_id,user_id) do update set member_role='COORDINATOR',reliability_state='GOOD';

  insert into public.pickup_points (id,group_id,label,address_text,latitude,longitude,active)
  values (v_pickup_id,v_group_id,'Demo Community Pickup','Utrecht, Netherlands',52.090737,5.121420,true)
  on conflict (id) do update set label=excluded.label,address_text=excluded.address_text,active=true;

  -- Reset only the deterministic demo checkout so the 12-step journey can be replayed.
  delete from public.audit_events where entity_id=v_cycle_id
    or entity_id in (select id from public.orders where cycle_id=v_cycle_id);
  delete from public.outbox_events where aggregate_id=v_cycle_id
    or aggregate_id in (select id from public.orders where cycle_id=v_cycle_id);
  delete from public.orders where cycle_id=v_cycle_id;
  delete from public.authorizations where cycle_id=v_cycle_id;

  insert into public.order_cycles (id,group_id,cutoff_at,pickup_point_id,status,version)
  values (v_cycle_id,v_group_id,timezone('utc',now())+interval '7 days',v_pickup_id,'OPEN',1)
  on conflict (id) do update set cutoff_at=excluded.cutoff_at,pickup_point_id=excluded.pickup_point_id,
    status='OPEN',updated_at=timezone('utc',now());
end;
$$;

select p.id as user_id,g.id as group_id,oc.id as cycle_id,oc.status
from auth.users u join public.profiles p on p.id=u.id
join public.groups g on g.coordinator_id=p.id join public.order_cycles oc on oc.group_id=g.id
where lower(u.email)='demo.member@sharemybread.test'
and g.id='20000000-0000-4000-8000-000000000001';
