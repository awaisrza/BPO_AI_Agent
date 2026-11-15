"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, Menu } from "lucide-react";
import { UserMenu } from "@/components/layout/user-menu";
import { cn } from "@/lib/utils";

const mobileNav = [
  { href: "/", label: "Overview" },
  { href: "/calls", label: "Calls" },
  { href: "/leads", label: "Leads" },
  { href: "/analytics", label: "Analytics" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/bots", label: "Agents" },
  { href: "/integrations", label: "Integrations" },
  { href: "/settings", label: "Settings" },
  { href: "/billing", label: "Billing" },
];

const pageMeta: Record<string, { title: string; section: string }> = {
  "/": { title: "Overview", section: "Operations" },
  "/campaigns": { title: "Campaigns", section: "Management" },
  "/campaigns/new": { title: "New campaign", section: "Management" },
  "/bots": { title: "Agents", section: "Management" },
  "/bots/assign": { title: "Assign agent", section: "Management" },
  "/leads": { title: "Leads", section: "Operations" },
  "/calls": { title: "Calls", section: "Operations" },
  "/analytics": { title: "Analytics", section: "Operations" },
  "/integrations": { title: "Integrations", section: "Configuration" },
  "/settings": { title: "Settings", section: "Configuration" },
  "/billing": { title: "Billing", section: "Configuration" },
};

function resolveMeta(pathname: string): { title: string; section: string } {
  if (pageMeta[pathname]) return pageMeta[pathname];
  if (pathname.startsWith("/campaigns/")) {
    return { title: "Campaign editor", section: "Management" };
  }
  return { title: "Dashboard", section: "Workspace" };
}

export function TopBar({ title }: { title?: string }) {
  const pathname = usePathname();
  const meta = resolveMeta(pathname);
  const pageTitle = title ?? meta.title;

  return (
    <header className="relative flex h-14 shrink-0 items-center justify-between gap-4 border-b border-surface-border-subtle bg-surface-raised px-3 sm:px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_120%_at_100%_0%,rgba(59,130,246,0.06),transparent_55%)]"
      />

      <div className="relative flex min-w-0 items-center gap-2.5">
        <details className="relative lg:hidden">
          <summary className="flex cursor-pointer list-none items-center rounded-md border border-surface-border-subtle bg-surface-overlay/50 p-2 text-foreground-muted transition-colors hover:bg-surface-overlay hover:text-foreground-secondary">
            <Menu className="h-4 w-4" strokeWidth={1.75} />
            <span className="sr-only">Open navigation</span>
          </summary>
          <div className="absolute left-0 top-full z-50 mt-1.5 w-52 overflow-hidden rounded-md border border-surface-border bg-surface-raised py-1 shadow-sm">
            {mobileNav.map(({ href, label }) => {
              const active =
                href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "block px-3 py-2 text-caption font-medium transition-colors",
                    active
                      ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
                      : "text-foreground-muted hover:bg-surface-overlay/70 hover:text-foreground-secondary",
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </div>
        </details>

        <div className="min-w-0">
          <p className="truncate text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
            {meta.section}
          </p>
          <p className="truncate text-body font-semibold tracking-tight text-foreground">
            {pageTitle}
          </p>
        </div>
      </div>

      <div className="relative flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          className="rounded-md border border-transparent p-2 text-foreground-faint transition-colors hover:border-surface-border-subtle hover:bg-surface-overlay hover:text-foreground-secondary"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" strokeWidth={1.75} />
        </button>
        <UserMenu />
      </div>
    </header>
  );
}
