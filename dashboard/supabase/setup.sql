-- =============================================================================
-- AI FRONTER — ONE-CLICK SETUP
-- Copy this ENTIRE file → Supabase → SQL Editor → Run
-- Safe to run multiple times.
-- =============================================================================

-- 1. Core tables
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

create table if not exists campaigns (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  status text not null default 'paused',
  script_json jsonb not null default '{"label":"Default script","greeting":"Hi","pitch":"Hello","qualifying_questions":[],"transfer_line":"Connecting you now.","not_interested_line":"Goodbye.","transfer_preset":"closers-01"}'::jsonb,
  dials integer not null default 0,
  transfer_rate numeric not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists bots (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  campaign_id uuid references campaigns(id) on delete set null,
  name text not null,
  status text not null default 'offline',
  created_at timestamptz not null default now()
);

-- 2. Helper functions
create or replace function auth_org_id()
returns uuid language sql security definer stable set search_path = public
as $$ select org_id from profiles where id = auth.uid() $$;

create or replace function ensure_user_profile()
returns uuid language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  oid uuid;
  uemail text;
  umeta jsonb;
begin
  if uid is null then raise exception 'Not authenticated'; end if;
  select org_id into oid from profiles where id = uid;
  if oid is not null then return oid; end if;
  select email, raw_user_meta_data into uemail, umeta from auth.users where id = uid;
  insert into organizations (name) values (coalesce(umeta->>'org_name', 'My Call Center')) returning id into oid;
  insert into profiles (id, org_id, email, name, role)
  values (uid, oid, uemail, coalesce(umeta->>'name', split_part(uemail, '@', 1)), 'admin');
  return oid;
end $$;

create or replace function handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare new_org_id uuid;
begin
  insert into organizations (name) values (coalesce(new.raw_user_meta_data->>'org_name', 'My Call Center')) returning id into new_org_id;
  insert into profiles (id, org_id, email, name, role)
  values (new.id, new_org_id, new.email, coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)), 'admin');
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function handle_new_user();

grant execute on function ensure_user_profile() to authenticated;

-- 3. Fix existing users missing profile
do $$
declare u record; new_org_id uuid;
begin
  for u in select id, email, raw_user_meta_data from auth.users where id not in (select id from profiles) loop
    insert into organizations (name) values (coalesce(u.raw_user_meta_data->>'org_name', 'My Call Center')) returning id into new_org_id;
    insert into profiles (id, org_id, email, name, role)
    values (u.id, new_org_id, u.email, coalesce(u.raw_user_meta_data->>'name', split_part(u.email, '@', 1)), 'admin');
  end loop;
end $$;

-- 4. RLS
alter table organizations enable row level security;
alter table profiles enable row level security;
alter table campaigns enable row level security;
alter table bots enable row level security;

drop policy if exists "Users read own profile" on profiles;
create policy "Users read own profile" on profiles for select using (id = auth.uid());

drop policy if exists "Users update own profile" on profiles;
create policy "Users update own profile" on profiles for update using (id = auth.uid());

drop policy if exists "Users read own org" on organizations;
create policy "Users read own org" on organizations for select using (id = auth_org_id());

drop policy if exists "Admins update own org" on organizations;
create policy "Admins update own org" on organizations for update using (id = auth_org_id());

drop policy if exists "org campaigns select" on campaigns;
create policy "org campaigns select" on campaigns for select using (org_id = auth_org_id());

drop policy if exists "org campaigns insert" on campaigns;
create policy "org campaigns insert" on campaigns for insert with check (org_id = auth_org_id());

drop policy if exists "org campaigns update" on campaigns;
create policy "org campaigns update" on campaigns for update using (org_id = auth_org_id());

drop policy if exists "org campaigns delete" on campaigns;
create policy "org campaigns delete" on campaigns for delete using (org_id = auth_org_id());

drop policy if exists "org bots select" on bots;
create policy "org bots select" on bots for select using (org_id = auth_org_id());

drop policy if exists "org bots insert" on bots;
create policy "org bots insert" on bots for insert with check (org_id = auth_org_id());

-- 5. Reload API cache
notify pgrst, 'reload schema';
