export const ORG_SETTINGS_MIGRATION_SQL = `alter table organizations
  add column if not exists settings_json jsonb not null default '{}'::jsonb;

notify pgrst, 'reload schema';`;

export function isMissingSettingsJsonColumn(message: string) {
  return message.includes("settings_json") && message.includes("does not exist");
}
