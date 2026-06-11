-- Run in Supabase SQL Editor if campaign create fails with permission / profile errors.
-- Safe to run multiple times.

do $$
declare
  u record;
  new_org_id uuid;
begin
  for u in
    select id, email, raw_user_meta_data
    from auth.users
    where id not in (select id from profiles)
  loop
    insert into organizations (name)
    values (coalesce(u.raw_user_meta_data->>'org_name', 'My Call Center'))
    returning id into new_org_id;

    insert into profiles (id, org_id, email, name, role)
    values (
      u.id,
      new_org_id,
      u.email,
      coalesce(u.raw_user_meta_data->>'name', split_part(u.email, '@', 1)),
      'admin'
    );
  end loop;
end $$;

-- Also add the auto-fix function for future signups (if not already in schema.sql)
create or replace function ensure_user_profile()
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  uid uuid := auth.uid();
  oid uuid;
  uemail text;
  uname jsonb;
  orgname text;
begin
  if uid is null then
    raise exception 'Not authenticated';
  end if;

  select org_id into oid from profiles where id = uid;
  if oid is not null then
    return oid;
  end if;

  select email, raw_user_meta_data into uemail, uname
  from auth.users where id = uid;

  orgname := coalesce(uname->>'org_name', 'My Call Center');

  insert into organizations (name) values (orgname) returning id into oid;

  insert into profiles (id, org_id, email, name, role)
  values (
    uid,
    oid,
    uemail,
    coalesce(uname->>'name', split_part(uemail, '@', 1)),
    'admin'
  );

  return oid;
end;
$$;

grant execute on function ensure_user_profile() to authenticated;
