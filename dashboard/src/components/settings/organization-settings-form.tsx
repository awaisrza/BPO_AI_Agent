"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Field, Input, Checkbox } from "@/components/ui/input";
import { SettingsMigrationAlert } from "@/components/settings/settings-migration-alert";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { formatSupabaseError } from "@/lib/errors";
import { getOrgId } from "@/lib/get-org-id";
import { DEFAULT_ORG_SETTINGS, mergeOrgSettings } from "@/lib/org-settings";
import { isMissingSettingsJsonColumn } from "@/lib/org-settings-migration";

export function OrganizationSettingsForm() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [needsMigration, setNeedsMigration] = useState(false);

  const [companyName, setCompanyName] = useState("");
  const [timezone, setTimezone] = useState(DEFAULT_ORG_SETTINGS.timezone);
  const [callingHours, setCallingHours] = useState(DEFAULT_ORG_SETTINGS.calling_hours);
  const [enforcePta, setEnforcePta] = useState(DEFAULT_ORG_SETTINGS.enforce_pta_rules);

  useEffect(() => {
    async function load() {
      if (!isSupabaseConfigured()) {
        setError(supabaseConfigHelp());
        setLoading(false);
        return;
      }

      try {
        const supabase = createClient();
        const orgId = await getOrgId(supabase);

        const full = await supabase
          .from("organizations")
          .select("name, settings_json")
          .eq("id", orgId)
          .single();

        if (full.error && isMissingSettingsJsonColumn(full.error.message ?? "")) {
          setNeedsMigration(true);
          const nameOnly = await supabase
            .from("organizations")
            .select("name")
            .eq("id", orgId)
            .single();
          if (nameOnly.error) throw nameOnly.error;
          setCompanyName(nameOnly.data.name ?? "");
          return;
        }

        if (full.error) throw full.error;

        const settings = mergeOrgSettings(full.data.settings_json);
        setCompanyName(full.data.name ?? "");
        setTimezone(settings.timezone);
        setCallingHours(settings.calling_hours);
        setEnforcePta(settings.enforce_pta_rules);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : formatSupabaseError(err, "Could not load organization settings."),
        );
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSaved(false);

    const trimmedName = companyName.trim();
    if (!trimmedName) {
      setError("Company name is required.");
      setSaving(false);
      return;
    }

    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
      setSaving(false);
      return;
    }

    try {
      const supabase = createClient();
      const orgId = await getOrgId(supabase);

      if (needsMigration) {
        const { error: updateError } = await supabase
          .from("organizations")
          .update({ name: trimmedName })
          .eq("id", orgId);

        if (updateError) throw updateError;
        setSaved(true);
        router.refresh();
        return;
      }

      const { data: existing, error: readError } = await supabase
        .from("organizations")
        .select("settings_json")
        .eq("id", orgId)
        .single();

      if (readError) throw readError;

      const current = mergeOrgSettings(existing.settings_json);
      const settings_json = {
        ...current,
        timezone: timezone.trim() || DEFAULT_ORG_SETTINGS.timezone,
        calling_hours: callingHours.trim() || DEFAULT_ORG_SETTINGS.calling_hours,
        enforce_pta_rules: enforcePta,
      };

      const { error: updateError } = await supabase
        .from("organizations")
        .update({ name: trimmedName, settings_json })
        .eq("id", orgId);

      if (updateError) {
        if (isMissingSettingsJsonColumn(updateError.message ?? "")) {
          setNeedsMigration(true);
          const { error: nameOnlyError } = await supabase
            .from("organizations")
            .update({ name: trimmedName })
            .eq("id", orgId);
          if (nameOnlyError) throw nameOnlyError;
          setSaved(true);
          setError("Company name saved. Run the database update above to save timezone and calling hours.");
          router.refresh();
          return;
        }
        throw updateError;
      }

      setSaved(true);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : formatSupabaseError(err, "Could not save organization settings."),
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <Card>
        <CardHeader title="Organization" />
        <CardBody>
          <p className="text-sm text-foreground-muted">Loading organization…</p>
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {needsMigration && <SettingsMigrationAlert />}

      <Card>
        <CardHeader title="Organization" />
        <CardBody className="max-w-md space-y-5">
          <form onSubmit={handleSubmit} className="space-y-5">
            <Field label="Company name">
              <Input
                value={companyName}
                onChange={(e) => {
                  setCompanyName(e.target.value);
                  setSaved(false);
                }}
                required
              />
            </Field>

            <Field label="Timezone">
              <Input
                value={timezone}
                onChange={(e) => {
                  setTimezone(e.target.value);
                  setSaved(false);
                }}
                disabled={needsMigration}
              />
            </Field>

            <Field label="Calling hours">
              <Input
                value={callingHours}
                onChange={(e) => {
                  setCallingHours(e.target.value);
                  setSaved(false);
                }}
                disabled={needsMigration}
              />
            </Field>

            <Checkbox
              label="Enforce PTA telemarketing rules (consent and calling hours)"
              checked={enforcePta}
              onChange={(e) => {
                setEnforcePta(e.target.checked);
                setSaved(false);
              }}
              className={needsMigration ? "opacity-50" : undefined}
            />

            {error && (
              <Alert variant={saved ? "warning" : "error"}>{error}</Alert>
            )}
            {saved && !error && (
              <Alert variant="success">Organization settings saved.</Alert>
            )}

            <Button type="submit" className="mt-2" disabled={saving || !companyName.trim()}>
              {saving ? "Saving…" : saved ? "Saved" : "Save changes"}
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
