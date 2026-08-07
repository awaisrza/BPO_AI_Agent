"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, Menu } from "lucide-react";
import { UserMenu } from "@/components/layout/user-menu";
import { cn } from "@/lib/utils";

const mobileNav = [
  { href: "/", label: "Overview" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/bots", label: "Agents" },
  { href: "/calls", label: "Calls" },
];

const pageTitles: Record<string, string> = {
  "/": "Overview",
  "/campaigns": "Campaigns",
  "/campaigns/new": "New campaign",
  "/bots": "Agent fleet",
  "/bots/assign": "Assign agent",
  "/leads": "Leads",
  "/calls": "Calls",
  "/analytics": "Analytics",
  "/integrations": "Integrations",
  "/settings": "Settings",
  "/billing": "Billing",
};

function resolveTitle(pathname: string): string {
  if (pageTitles[pathname]) return pageTitles[pathname];
  if (pathname.startsWith("/campaigns/")) return "Campaign editor";
  return "Dashboard";
}

export function TopBar({ title }: { title?: string }) {
  const pathname = usePathname();
  const pageTitle = title ?? resolveTitle(pathname);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-surface-border bg-surface px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <details className="relative lg:hidden">
          <summary className="flex cursor-pointer list-none items-center rounded-md p-2 text-foreground-muted hover:bg-surface-overlay hover:text-foreground-secondary">
            <Menu className="h-4 w-4" strokeWidth={1.75} />
            <span className="sr-only">Open navigation</span>
          </summary>
          <div className="absolute left-0 top-full z-50 mt-1 w-48 rounded-md border border-surface-border bg-surface-raised py-1 shadow-sm">
            {mobileNav.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "block px-3 py-2 text-body",
                  pathname === href || (href !== "/" && pathname.startsWith(href))
                    ? "bg-brand-muted text-foreground"
                    : "text-foreground-muted hover:bg-surface-overlay",
                )}
              >
                {label}
              </Link>
            ))}
          </div>
        </details>
        <p className="truncate text-body font-medium text-foreground">{pageTitle}</p>
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          className="rounded-md p-2 text-foreground-faint transition-colors hover:bg-surface-overlay hover:text-foreground-muted"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" strokeWidth={1.75} />
        </button>
        <UserMenu />
      </div>
    </header>
  );
}
