-- Optional: ensure ViciDial mapping columns exist (safe to re-run).

alter table campaigns add column if not exists vicidial_campaign_id text;
alter table bots add column if not exists vicidial_agent_user text;
