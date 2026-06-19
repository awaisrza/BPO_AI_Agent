// Keep in sync with dashboard/supabase/bootstrap-login.sql
export const PROFILE_SETUP_SQL = `-- Complete login bootstrap — run once in Supabase SQL Editor

create table if not exists organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan text not null default 'pilot',
  vicidial_url text,
  vicidial_user text,
  vicidial_pass text,
  transfer_preset text default 'CLOSER',
  bots_included integer default 10,
  minutes_included integer default 35000,
  settings_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  org_id uuid not null references organizations(id) on delete cascade,
  email text not null,
  name text,
  role text not null default 'admin',
  created_at timestamptz not null default now()
);

alter table organizations
  add column if not exists settings_json jsonb not null default '{}'::jsonb;

create or replace function auth_org_id()
returns uuid language sql security definer stable set search_path = public
as $$ select org_id from profiles where id = auth.uid() $$;

create or replace function ensure_user_profile()
returns uuid language plpgsql security definer set search_path = public as $$
declare uid uuid := auth.uid(); oid uuid; uemail text; uname jsonb;
begin
  if uid is null then raise exception 'Not authenticated'; end if;
  select org_id into oid from profiles where id = uid;
  if oid is not null then
    if exists (select 1 from organizations where id = oid) then return oid; end if;
    delete from profiles where id = uid;
    oid := null;
  end if;
  select email, raw_user_meta_data into uemail, uname from auth.users where id = uid;
  insert into organizations (name) values (coalesce(uname->>'org_name', 'My Call Center')) returning id into oid;
  insert into profiles (id, org_id, email, name, role)
  values (uid, oid, uemail, coalesce(uname->>'name', split_part(uemail, '@', 1)), 'admin');
  return oid;
end $$;

grant execute on function ensure_user_profile() to authenticated;

do $$ declare u record; new_org_id uuid; begin
  for u in select id, email, raw_user_meta_data from auth.users
    where id not in (select id from profiles) loop
    insert into organizations (name) values (coalesce(u.raw_user_meta_data->>'org_name', 'My Call Center')) returning id into new_org_id;
    insert into profiles (id, org_id, email, name, role) values (u.id, new_org_id, u.email, coalesce(u.raw_user_meta_data->>'name', split_part(u.email, '@', 1)), 'admin');
  end loop;
end $$;

alter table organizations enable row level security;
alter table profiles enable row level security;
drop policy if exists "Users read own profile" on profiles;
create policy "Users read own profile" on profiles for select using (id = auth.uid());
drop policy if exists "Users update own profile" on profiles;
create policy "Users update own profile" on profiles for update using (id = auth.uid());
drop policy if exists "Users read own org" on organizations;
create policy "Users read own org" on organizations for select using (id = auth_org_id());
drop policy if exists "Admins update own org" on organizations;
create policy "Admins update own org" on organizations for update using (id = auth_org_id());

notify pgrst, 'reload schema';`;
