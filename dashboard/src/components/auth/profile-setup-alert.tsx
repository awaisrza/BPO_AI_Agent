"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PROFILE_SETUP_SQL } from "@/lib/profile-setup-sql";

export function ProfileSetupAlert() {
  const [copied, setCopied] = useState(false);

  async function copySql() {
    await navigator.clipboard.writeText(PROFILE_SETUP_SQL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Alert variant="warning">
      <p className="font-medium text-foreground">One-time database fix required</p>
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
        , paste this, click <strong>Run</strong>, and wait for <strong>Success</strong>:
      </p>
      <pre className="mt-3 max-h-64 overflow-auto rounded-md border border-surface-border bg-surface px-3 py-2 text-caption text-foreground-secondary">
        {PROFILE_SETUP_SQL}
      </pre>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={copySql}>
          {copied ? "Copied" : "Copy SQL"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => window.location.assign("/")}
        >
          Continue after running SQL
        </Button>
      </div>
    </Alert>
  );
}
