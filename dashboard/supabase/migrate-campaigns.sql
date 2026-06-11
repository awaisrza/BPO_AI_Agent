-- Fix campaigns table — run in Supabase SQL Editor.
-- Safe to run multiple times.

-- 1. Ensure script_json exists (script name is stored inside as "label")
alter table campaigns add column if not exists script_json jsonb not null default jsonb_build_object(
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
);

alter table campaigns add column if not exists status text not null default 'paused';
alter table campaigns add column if not exists dials integer not null default 0;
alter table campaigns add column if not exists connect_rate numeric not null default 0;
alter table campaigns add column if not exists transfer_rate numeric not null default 0;

-- 2. Optional: add script_label if you want it later (app no longer requires it)
alter table campaigns add column if not exists script_label text;

-- 3. Force Supabase API to reload schema cache
notify pgrst, 'reload schema';
