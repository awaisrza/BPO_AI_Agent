export type OrgSettings = {
  timezone?: string;
  calling_hours?: string;
  enforce_pta_rules?: boolean;
  require_consent?: boolean;
  recording_retention?: string;
};

export const DEFAULT_ORG_SETTINGS: Required<OrgSettings> = {
  timezone: "US Eastern (ET)",
  calling_hours: "9:00 AM – 8:00 PM",
  enforce_pta_rules: true,
  require_consent: true,
  recording_retention: "7 days",
};

export function mergeOrgSettings(raw: unknown): Required<OrgSettings> {
  const parsed = (raw && typeof raw === "object" ? raw : {}) as Partial<OrgSettings>;
  return {
    timezone: parsed.timezone?.trim() || DEFAULT_ORG_SETTINGS.timezone,
    calling_hours: parsed.calling_hours?.trim() || DEFAULT_ORG_SETTINGS.calling_hours,
    enforce_pta_rules: parsed.enforce_pta_rules ?? DEFAULT_ORG_SETTINGS.enforce_pta_rules,
    require_consent: parsed.require_consent ?? DEFAULT_ORG_SETTINGS.require_consent,
    recording_retention:
      parsed.recording_retention?.trim() || DEFAULT_ORG_SETTINGS.recording_retention,
  };
}
