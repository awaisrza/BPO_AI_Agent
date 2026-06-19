-- Run AFTER bootstrap-login.sql if login still fails
-- Shows whether your auth user has a profile + organization

select
  u.email,
  p.id as profile_id,
  p.org_id,
  o.name as company,
  case
    when p.id is null then 'MISSING PROFILE — re-run bootstrap-login.sql'
    when o.id is null then 'BROKEN PROFILE — re-run bootstrap-login.sql'
    else 'OK'
  end as status
from auth.users u
left join profiles p on p.id = u.id
left join organizations o on o.id = p.org_id
order by u.created_at desc;
