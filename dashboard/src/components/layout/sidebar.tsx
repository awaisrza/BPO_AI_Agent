"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  Cable,
  CreditCard,
  LayoutDashboard,
  Megaphone,
  Phone,
  Settings,
  Users,
  BarChart3,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useOrg } from "@/components/layout/org-provider";
import { ThemeToggle } from "@/components/layout/theme-toggle";

type NavItem = { href: string; label: string; icon: LucideIcon };

const operationsNav: NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/calls", label: "Calls", icon: Phone },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

const managementNav: NavItem[] = [
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/bots", label: "Agents", icon: Bot },
];

const configNav: NavItem[] = [
  { href: "/integrations", label: "Integrations", icon: Cable },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/billing", label: "Billing", icon: CreditCard },
];

function ParasiteMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={className}
      strokeWidth={1.75}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {/* Stylized P built from a call-wave arc */}
      <path d="M7 20V5.5A1.5 1.5 0 0 1 8.5 4H13a5 5 0 0 1 0 10H7" />
      <path d="M16.5 17.5c1.6-1.3 2.5-3.3 2.5-5.5" opacity="0.55" />
    </svg>
  );
}

function NavSection({ title, items }: { title: string; items: NavItem[] }) {
  const pathname = usePathname();

  return (
    <div className="mb-5">
      <p className="mb-1.5 px-3 text-2xs font-medium uppercase tracking-wider text-sidebar-faint">
        {title}
      </p>
      <div className="space-y-0.5">
        {items.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group relative flex items-center gap-2.5 rounded-md px-3 py-2 text-body font-medium transition-colors",
                active
                  ? "bg-sidebar-active text-sidebar-text"
                  : "text-sidebar-muted hover:bg-sidebar-raised hover:text-sidebar-text",
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-sidebar-accent" />
              )}
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  active
                    ? "text-sidebar-accent"
                    : "text-sidebar-faint group-hover:text-sidebar-muted",
                )}
                strokeWidth={1.75}
              />
              {label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export function Sidebar() {
  const org = useOrg();

  return (
    <aside className="hidden h-full w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-sidebar-accent/15 text-sidebar-accent">
          <ParasiteMark className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <p className="truncate font-display text-base font-semibold tracking-tight text-sidebar-text">
            Parasite
          </p>
          <p className="text-2xs text-sidebar-faint">AI fronting for BPOs</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4 scrollbar-thin">
        <NavSection title="Operations" items={operationsNav} />
        <NavSection title="Management" items={managementNav} />
        <NavSection title="Configuration" items={configNav} />
      </nav>

      <div className="border-t border-sidebar-border p-4">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-body font-medium text-sidebar-text">{org.name}</p>
            <p className="mt-0.5 text-caption text-sidebar-faint">
              {org.plan} plan · {org.botsActive}/{org.botsIncluded} agents
            </p>
            {org.pilot && (
              <span className="mt-2 inline-flex items-center rounded-sm bg-sidebar-accent/10 px-2 py-0.5 text-2xs font-medium text-sidebar-accent">
                Pilot
              </span>
            )}
          </div>
          <ThemeToggle variant="sidebar" />
        </div>
      </div>
    </aside>
  );
}
