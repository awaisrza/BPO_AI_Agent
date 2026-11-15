"use client";

import { useMemo, useState } from "react";
import { Building2, Scale, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { OrganizationSettingsForm } from "@/components/settings/organization-settings-form";
import { UsersSettingsTable } from "@/components/settings/users-settings-table";
import { ComplianceSettingsForm } from "@/components/settings/compliance-settings-form";

type Section = "organization" | "users" | "compliance";

const SECTIONS: {
  id: Section;
  label: string;
  hint: string;
  icon: typeof Building2;
  dot: string;
}[] = [
  {
    id: "organization",
    label: "Organization",
    hint: "Profile & calling hours",
    icon: Building2,
    dot: "bg-brand",
  },
  {
    id: "users",
    label: "Users",
    hint: "Team access",
    icon: Users,
    dot: "bg-status-info",
  },
  {
    id: "compliance",
    label: "Compliance",
    hint: "DNC · consent · retention",
    icon: Scale,
    dot: "bg-status-warning",
  },
];

export function SettingsPageClient() {
  const [section, setSection] = useState<Section>("organization");
  const active = useMemo(() => SECTIONS.find((s) => s.id === section)!, [section]);

  return (
    <div className="settings-shell relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-surface-raised">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_0%_0%,rgba(59,130,246,0.12),transparent_55%),radial-gradient(ellipse_60%_40%_at_100%_100%,rgba(15,23,42,0.85),transparent_55%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.28] [background-image:linear-gradient(rgba(255,255,255,0.028)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.028)_1px,transparent_1px)] [background-size:40px_40px] [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_85%)]"
      />

      <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-b border-surface-border-subtle bg-surface/75 backdrop-blur-md lg:h-full lg:w-56 lg:border-b-0 lg:border-r">
          <div className="border-b border-surface-border-subtle px-4 py-4">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
              Workspace
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground">Settings</h1>
            <p className="mt-1 text-caption text-foreground-muted">Org · team · rules</p>
          </div>

          <nav className="flex gap-1 overflow-x-auto p-2 scrollbar-thin lg:flex-1 lg:flex-col lg:overflow-y-auto">
            {SECTIONS.map((item) => {
              const Icon = item.icon;
              const selected = section === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSection(item.id)}
                  className={cn(
                    "flex shrink-0 items-center gap-2 rounded-md px-3 py-2.5 text-left transition-colors duration-150 lg:w-full",
                    selected
                      ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
                      : "text-foreground-muted hover:bg-surface-overlay/60 hover:text-foreground-secondary",
                  )}
                >
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", item.dot)} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-caption font-medium">{item.label}</span>
                    <span className="mt-0.5 hidden truncate text-2xs text-foreground-faint lg:block">
                      {item.hint}
                    </span>
                  </span>
                  <Icon className="hidden h-3.5 w-3.5 shrink-0 text-foreground-faint lg:block" />
                </button>
              );
            })}
          </nav>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="border-b border-surface-border-subtle bg-surface-raised/80 px-5 py-4 backdrop-blur-md">
            <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
              {active.hint}
            </p>
            <h2 className="mt-0.5 text-base font-semibold tracking-tight text-foreground">
              {active.label}
            </h2>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <div className="mx-auto w-full max-w-2xl px-5 py-6">
              {section === "organization" && <OrganizationSettingsForm embedded />}
              {section === "users" && <UsersSettingsTable embedded />}
              {section === "compliance" && <ComplianceSettingsForm embedded />}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
