"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Field, Input } from "@/components/ui/input";
import { isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { normalizeVicidialUrl } from "@/lib/vicidial/connection";

export function VicidialIntegrationForm() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saved, setSaved] = useState(false);

  const [serverUrl, setServerUrl] = useState("");
  const [apiUser, setApiUser] = useState("");
  const [apiPassword, setApiPassword] = useState("");
  const [passwordSet, setPasswordSet] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [testMessage, setTestMessage] = useState("");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    async function load() {
      if (!isSupabaseConfigured()) {
        setError(supabaseConfigHelp());
        setLoading(false);
        return;
      }

      try {
        const res = await fetch("/api/vicidial/settings");
        const data = (await res.json()) as {
          vicidial_url?: string;
          vicidial_user?: string;
          password_set?: boolean;
          configured?: boolean;
          error?: string;
          warning?: string;
        };

        if (!res.ok) {
          setError(data.error ?? "Could not load ViciDial settings.");
          return;
        }

        if (data.warning) {
          setError(data.warning);
        }

        setServerUrl(data.vicidial_url ?? "");
        setApiUser(data.vicidial_user ?? "");
        setPasswordSet(Boolean(data.password_set));
        setConnected(Boolean(data.configured));
      } catch {
        setError("Could not load ViciDial settings.");
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  async function handleSave() {
    setSaving(true);
    setError("");
    setSuccess("");
    setTestMessage("");
    setSaved(false);

    const url = normalizeVicidialUrl(serverUrl);
    const user = apiUser.trim();

    if (!url || !user) {
      setError("Server URL and API user are required.");
      setSaving(false);
      return;
    }

    if (!apiPassword.trim() && !passwordSet) {
      setError("API password is required the first time you connect.");
      setSaving(false);
      return;
    }

    if (!isSupabaseConfigured()) {
      setError(supabaseConfigHelp());
      setSaving(false);
      return;
    }

    try {
      const res = await fetch("/api/vicidial/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vicidial_url: url,
          vicidial_user: user,
          vicidial_pass: apiPassword.trim() || undefined,
        }),
      });

      const data = (await res.json()) as { ok?: boolean; error?: string };
      if (!res.ok) {
        throw new Error(data.error ?? "Could not save ViciDial settings.");
      }

      if (apiPassword.trim()) {
        setApiPassword("");
      }

      setSaved(true);
      setConnected(true);
      setPasswordSet(true);
      setSuccess("ViciDial settings saved. Run a connection test to verify.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save ViciDial settings.");
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setError("");
    setSuccess("");
    setTestMessage("");

    try {
      const res = await fetch("/api/vicidial/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vicidial_url: serverUrl,
          vicidial_user: apiUser,
          vicidial_pass: apiPassword.trim() || undefined,
        }),
      });

      const data = (await res.json()) as {
        ok?: boolean;
        message?: string;
        error?: string;
      };

      if (!res.ok) {
        setConnected(false);
        setError(data.error ?? "Connection test failed.");
        return;
      }

      setConnected(true);
      setTestMessage(data.message ?? "Connected to ViciDial.");
    } catch {
      setConnected(false);
      setError("Could not reach the connection test service.");
    } finally {
      setTesting(false);
    }
  }

  if (loading) {
    return (
      <Card>
        <CardBody className="flex items-center gap-2 text-body text-foreground-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading ViciDial settings…
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="ViciDial"
        description="Connect your dialer for closers, warm transfer, and dispositions."
        action={
          connected ? (
            <Badge variant="success" className="gap-1.5">
              <CheckCircle2 className="h-3 w-3" />
              Configured
            </Badge>
          ) : (
            <Badge variant="warning">Not connected</Badge>
          )
        }
      />
      <CardBody className="space-y-4">
        <Field
          label="Server URL"
          description="Server root only — not the admin login page. Example: http://178.238.231.150"
        >
          <Input
            value={serverUrl}
            onChange={(e) => {
              setServerUrl(e.target.value);
              setSaved(false);
            }}
            placeholder="http://178.238.231.150"
          />
        </Field>

        <Field
          label="API user"
          description="ViciDial API login created by your dialer admin (not a closer login)."
        >
          <Input
            value={apiUser}
            onChange={(e) => {
              setApiUser(e.target.value);
              setSaved(false);
            }}
            placeholder="api_fronter"
          />
        </Field>

        <Field
          label="API password"
          description={
            passwordSet
              ? "Leave blank to keep the saved password, or enter a new one to replace it."
              : "Password for the API user above."
          }
        >
          <Input
            type="password"
            value={apiPassword}
            onChange={(e) => {
              setApiPassword(e.target.value);
              setSaved(false);
            }}
            placeholder={passwordSet ? "••••••••••••" : "Enter API password"}
            autoComplete="new-password"
          />
        </Field>

        <p className="text-caption text-foreground-faint">
          AGI script and campaign mapping are configured on your dialer server during onboarding.
        </p>

        {error && <Alert variant="error">{error}</Alert>}
        {success && <Alert variant="success">{success}</Alert>}
        {testMessage && <Alert variant="success">{testMessage}</Alert>}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            type="button"
            variant="secondary"
            onClick={() => void handleTest()}
            disabled={testing || saving}
          >
            {testing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Testing…
              </>
            ) : (
              "Test connection"
            )}
          </Button>
          <Button type="button" onClick={() => void handleSave()} disabled={saving || testing}>
            {saving ? "Saving…" : saved ? "Saved" : "Save"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
