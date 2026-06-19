-- AI Fronter — run this in Supabase SQL Editor (in order, once per project).

-- =============================================================================
-- 1. Organizations & profiles (auth)
-- =============================================================================

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
  role text not null default 'admin' check (role in ('admin', 'manager', 'supervisor')),
  created_at timestamptz not null default now()
);

create or replace function auth_org_id()
returns uuid
language sql
security definer
stable
set search_path = public
as $$
  select org_id from profiles where id = auth.uid()
$$;

-- Creates org + profile for users who signed up before the signup trigger existed.
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
  umeta jsonb;
  orgname text;
begin
  if uid is null then
    raise exception 'Not authenticated';
  end if;

  select org_id into oid from profiles where id = uid;
  if oid is not null then
    return oid;
  end if;

  select email, raw_user_meta_data into uemail, umeta
  from auth.users where id = uid;

  orgname := coalesce(umeta->>'org_name', 'My Call Center');

  insert into organizations (name) values (orgname) returning id into oid;

  insert into profiles (id, org_id, email, name, role)
  values (
    uid,
    oid,
    uemail,
    coalesce(umeta->>'name', split_part(uemail, '@', 1)),
    'admin'
  );

  return oid;
end;
$$;

grant execute on function ensure_user_profile() to authenticated;

create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  new_org_id uuid;
begin
  insert into organizations (name)
  values (coalesce(new.raw_user_meta_data->>'org_name', 'My Call Center'))
  returning id into new_org_id;

  insert into profiles (id, org_id, email, name, role)
  values (
    new.id,
    new_org_id,
    new.email,
    coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)),
    'admin'
  );

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

alter table organizations enable row level security;
alter table profiles enable row level security;

create policy "Users read own profile"
  on profiles for select using (id = auth.uid());

create policy "Users update own profile"
  on profiles for update using (id = auth.uid());

create policy "Users read own org"
  on organizations for select using (id = auth_org_id());

create policy "Admins update own org"
  on organizations for update using (id = auth_org_id());

-- =============================================================================
-- 2. Campaigns, bots, calls, contacts, usage
-- =============================================================================

create table if not exists campaigns (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  status text not null default 'paused' check (status in ('running', 'paused')),
  script_json jsonb not null default jsonb_build_object(
    'label', 'Default script',
    'greeting', 'Hi, this is Alex calling on a recorded line. How are you today?',
    'pitch', 'Great — I will be quick. We help homeowners cut their electricity bill with no upfront cost. Do you currently own your home?',
    'qualifying_questions', jsonb_build_array(
      'Do you own your home?',
      'Is your average monthly electric bill over 100 dollars?'
    ),
    'transfer_line', 'Perfect — let me connect you with a specialist right now, one moment.',
    'not_interested_line', 'No problem at all, thanks for your time. Have a great day!',
    'transfer_preset', 'closers-01'
  ),
  voice_id text,
  vicidial_campaign_id text,
  dials integer not null default 0,
  connect_rate numeric not null default 0,
  transfer_rate numeric not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists bots (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  campaign_id uuid references campaigns(id) on delete set null,
  name text not null,
  status text not null default 'offline'
    check (status in ('live', 'idle', 'dialing', 'ringing', 'offline')),
  vicidial_agent_user text,
  calls_today integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists contacts (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  campaign_id uuid references campaigns(id) on delete set null,
  phone text not null,
  name text,
  status text not null default 'new',
  last_attempt_at timestamptz,
  outcome text,
  created_at timestamptz not null default now()
);

create table if not exists calls (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  campaign_id uuid references campaigns(id) on delete set null,
  bot_id uuid references bots(id) on delete set null,
  phone text,
  duration_sec integer not null default 0,
  outcome text,
  disposition text,
  transferred boolean not null default false,
  transcript_json jsonb not null default '[]'::jsonb,
  sentiment text,
  created_at timestamptz not null default now()
);

create table if not exists usage_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  bot_id uuid references bots(id) on delete set null,
  call_id uuid references calls(id) on delete set null,
  minutes numeric not null,
  created_at timestamptz not null default now()
);

-- =============================================================================
-- 3. RLS policies
-- =============================================================================

alter table campaigns enable row level security;
alter table bots enable row level security;
alter table contacts enable row level security;
alter table calls enable row level security;
alter table usage_events enable row level security;

create policy "org campaigns select" on campaigns for select using (org_id = auth_org_id());
create policy "org campaigns insert" on campaigns for insert with check (org_id = auth_org_id());
create policy "org campaigns update" on campaigns for update using (org_id = auth_org_id());
create policy "org campaigns delete" on campaigns for delete using (org_id = auth_org_id());

create policy "org bots select" on bots for select using (org_id = auth_org_id());
create policy "org bots insert" on bots for insert with check (org_id = auth_org_id());
create policy "org bots update" on bots for update using (org_id = auth_org_id());
create policy "org bots delete" on bots for delete using (org_id = auth_org_id());

create policy "org contacts select" on contacts for select using (org_id = auth_org_id());
create policy "org contacts insert" on contacts for insert with check (org_id = auth_org_id());
create policy "org contacts update" on contacts for update using (org_id = auth_org_id());
create policy "org contacts delete" on contacts for delete using (org_id = auth_org_id());

create policy "org calls select" on calls for select using (org_id = auth_org_id());
create policy "org calls insert" on calls for insert with check (org_id = auth_org_id());

create policy "org usage select" on usage_events for select using (org_id = auth_org_id());
create policy "org usage insert" on usage_events for insert with check (org_id = auth_org_id());
