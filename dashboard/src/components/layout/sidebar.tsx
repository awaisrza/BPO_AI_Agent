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
  PhoneCall,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useOrg } from "@/components/layout/org-provider";

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

function NavSection({ title, items }: { title: string; items: NavItem[] }) {
  const pathname = usePathname();

  return (
    <div className="mb-4">
      <p className="mb-1.5 px-3 text-2xs font-medium uppercase tracking-wider text-foreground-faint">
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
                  ? "bg-brand-muted text-foreground"
                  : "text-foreground-muted hover:bg-surface-overlay hover:text-foreground-secondary",
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-brand" />
              )}
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  active ? "text-brand" : "text-foreground-faint group-hover:text-foreground-muted",
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
    <aside className="hidden h-full w-60 shrink-0 flex-col border-r border-surface-border bg-surface lg:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-surface-border-subtle px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-muted">
          <PhoneCall className="h-4 w-4 text-brand" strokeWidth={1.75} />
        </div>
        <div className="min-w-0">
          <p className="truncate text-body font-semibold text-foreground">AI Fronter</p>
          <p className="text-2xs text-foreground-faint">Call center platform</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4 scrollbar-thin">
        <NavSection title="Operations" items={operationsNav} />
        <NavSection title="Management" items={managementNav} />
        <NavSection title="Configuration" items={configNav} />
      </nav>

      <div className="border-t border-surface-border-subtle p-4">
        <p className="truncate text-body font-medium text-foreground-secondary">{org.name}</p>
        <p className="mt-0.5 text-caption text-foreground-faint">
          {org.plan} plan · {org.botsActive}/{org.botsIncluded} agents
        </p>
        {org.pilot && (
          <span className="mt-2 inline-flex items-center rounded-sm bg-status-warning-muted px-2 py-0.5 text-2xs font-medium text-status-warning">
            Pilot
          </span>
        )}
      </div>
    </aside>
  );
}
