-- Add the pre-created Supabase Auth users to the multi-user demo.
-- Prerequisite: create and auto-confirm all six email addresses in Authentication > Users.

do $$
declare
  v_group_id constant uuid := '20000000-0000-4000-8000-000000000001';
  v_missing text;
begin
  select string_agg(required.email, ', ' order by required.email)
  into v_missing
  from (values
    ('retail.user1@sharemybread.test'),
    ('retail.user2@sharemybread.test'),
    ('retail.user3@sharemybread.test'),
    ('delivery.user1@sharemybread.test'),
    ('delivery.user2@sharemybread.test'),
    ('admin.support@sharemybread.test')
  ) required(email)
  where not exists (select 1 from auth.users u where lower(u.email)=required.email);

  if v_missing is not null then
    raise exception 'Create and auto-confirm these Auth users first: %', v_missing;
  end if;

  update public.profiles p set
    display_name = case lower(u.email)
      when 'retail.user1@sharemybread.test' then 'Retail User 1'
      when 'retail.user2@sharemybread.test' then 'Retail User 2'
      when 'retail.user3@sharemybread.test' then 'Retail User 3'
      when 'delivery.user1@sharemybread.test' then 'Delivery User 1'
      when 'delivery.user2@sharemybread.test' then 'Delivery User 2'
      when 'admin.support@sharemybread.test' then 'Admin Support'
    end,
    app_role = case when lower(u.email) like 'delivery.%' then 'ADMIN'
                    when lower(u.email)='admin.support@sharemybread.test' then 'ADMIN'
                    else 'MEMBER' end,
    status='ACTIVE', updated_at=timezone('utc',now())
  from auth.users u
  where p.id=u.id and lower(u.email) in (
    'retail.user1@sharemybread.test','retail.user2@sharemybread.test','retail.user3@sharemybread.test',
    'delivery.user1@sharemybread.test','delivery.user2@sharemybread.test','admin.support@sharemybread.test'
  );

  -- All MVP users share the group. Delivery and support accounts use ADMIN.
  insert into public.group_members (group_id,user_id,member_role,reliability_state)
  select v_group_id,u.id,'MEMBER','GOOD'
  from auth.users u
  where lower(u.email) in (
    'retail.user1@sharemybread.test','retail.user2@sharemybread.test',
    'retail.user3@sharemybread.test','delivery.user1@sharemybread.test',
    'delivery.user2@sharemybread.test','admin.support@sharemybread.test'
  )
  on conflict (group_id,user_id) do update
    set member_role='MEMBER',reliability_state='GOOD';
end;
$$;

select u.email,p.display_name,p.app_role,
       coalesce(g.name,'No group') as access_scope
from auth.users u
join public.profiles p on p.id=u.id
left join public.group_members gm on gm.user_id=u.id
left join public.groups g on g.id=gm.group_id
where lower(u.email) in (
  'demo.member@sharemybread.test','retail.user1@sharemybread.test',
  'retail.user2@sharemybread.test','retail.user3@sharemybread.test',
  'delivery.user1@sharemybread.test','delivery.user2@sharemybread.test',
  'admin.support@sharemybread.test'
)
order by p.app_role,u.email;
