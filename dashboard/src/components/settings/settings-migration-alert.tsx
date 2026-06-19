"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ORG_SETTINGS_MIGRATION_SQL } from "@/lib/org-settings-migration";

export function SettingsMigrationAlert() {
  const [copied, setCopied] = useState(false);

  async function copySql() {
    await navigator.clipboard.writeText(ORG_SETTINGS_MIGRATION_SQL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Alert variant="warning">
      <p className="font-medium text-foreground">Database update required</p>
      <p className="mt-1 text-body">
        Open{" "}
        <a
          href="https://supabase.com/dashboard/project/luisenyyvhjdnyxjygwn/sql/new"
          target="_blank"
          rel="noreferrer"
          className="font-medium text-brand hover:text-brand-hover"
        >
          Supabase → SQL Editor
        </a>
        , paste this, and click <strong>Run</strong>:
      </p>
      <pre className="mt-3 overflow-x-auto rounded-md border border-surface-border bg-surface px-3 py-2 text-caption text-foreground-secondary">
        {ORG_SETTINGS_MIGRATION_SQL}
      </pre>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={copySql}>
          {copied ? "Copied" : "Copy SQL"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => window.location.reload()}
        >
          Refresh after running
        </Button>
      </div>
    </Alert>
  );
}
