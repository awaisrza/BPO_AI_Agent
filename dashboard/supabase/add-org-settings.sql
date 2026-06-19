-- Add organization settings storage (safe to run multiple times).
alter table organizations
  add column if not exists settings_json jsonb not null default '{}'::jsonb;

notify pgrst, 'reload schema';
