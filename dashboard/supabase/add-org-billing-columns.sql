-- Optional: billing/plan columns referenced by the dashboard.
-- Run in Supabase SQL Editor if bots usage or plan limits fail to load.

alter table organizations add column if not exists bots_included integer default 10;
alter table organizations add column if not exists minutes_included integer default 35000;
