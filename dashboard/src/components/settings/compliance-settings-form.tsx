"use client";

import { useEffect, useState } from "react";
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

export function ComplianceSettingsForm() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [needsMigration, setNeedsMigration] = useState(false);

  const [requireConsent, setRequireConsent] = useState(DEFAULT_ORG_SETTINGS.require_consent);
  const [recordingRetention, setRecordingRetention] = useState(
    DEFAULT_ORG_SETTINGS.recording_retention,
  );

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
        const { data, error: loadError } = await supabase
          .from("organizations")
          .select("settings_json")
          .eq("id", orgId)
          .single();

        if (loadError && isMissingSettingsJsonColumn(loadError.message ?? "")) {
          setNeedsMigration(true);
          return;
        }

        if (loadError) throw loadError;

        const settings = mergeOrgSettings(data.settings_json);
        setRequireConsent(settings.require_consent);
        setRecordingRetention(settings.recording_retention);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : formatSupabaseError(err, "Could not load compliance settings."),
        );
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (needsMigration) {
      setError("Run the database update above before saving compliance settings.");
      return;
    }

    setSaving(true);
    setError("");
    setSaved(false);

    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
      setSaving(false);
      return;
    }

    try {
      const supabase = createClient();
      const orgId = await getOrgId(supabase);

      const { data: existing, error: readError } = await supabase
        .from("organizations")
        .select("settings_json")
        .eq("id", orgId)
        .single();

      if (readError) throw readError;

      const current = mergeOrgSettings(existing.settings_json);
      const settings_json = {
        ...current,
        require_consent: requireConsent,
        recording_retention:
          recordingRetention.trim() || DEFAULT_ORG_SETTINGS.recording_retention,
      };

      const { error: updateError } = await supabase
        .from("organizations")
        .update({ settings_json })
        .eq("id", orgId);

      if (updateError) throw updateError;

      setSaved(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : formatSupabaseError(err, "Could not save compliance settings."),
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <Card>
        <CardHeader title="Compliance" description="DNC, consent, and recording retention" />
        <CardBody>
          <p className="text-sm text-foreground-muted">Loading compliance settings…</p>
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {needsMigration && <SettingsMigrationAlert />}

      <Card>
        <CardHeader title="Compliance" description="DNC, consent, and recording retention" />
        <CardBody className="max-w-md space-y-5">
          <form onSubmit={handleSubmit} className="space-y-5">
            <Field label="Do-not-call list">
              <Button type="button" variant="secondary" disabled={needsMigration}>
                Upload DNC CSV
              </Button>
            </Field>

            <Checkbox
              label="Require consent before outbound dial"
              checked={requireConsent}
              onChange={(e) => {
                setRequireConsent(e.target.checked);
                setSaved(false);
              }}
            />

            <Field label="Call recording retention">
              <Input
                value={recordingRetention}
                onChange={(e) => {
                  setRecordingRetention(e.target.value);
                  setSaved(false);
                }}
                disabled={needsMigration}
              />
            </Field>

            {error && <Alert variant="error">{error}</Alert>}
            {saved && !error && <Alert variant="success">Compliance settings saved.</Alert>}

            <Button type="submit" disabled={saving || needsMigration}>
              {saving ? "Saving…" : saved ? "Saved" : "Save changes"}
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
