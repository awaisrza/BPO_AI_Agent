"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bot,
  Cable,
  ChevronLeft,
  ChevronRight,
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

type NavItem = { href: string; label: string; icon: LucideIcon };

const COLLAPSE_KEY = "sidebar.collapsed";

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

function NavSection({
  title,
  items,
  collapsed,
}: {
  title: string;
  items: NavItem[];
  collapsed: boolean;
}) {
  const pathname = usePathname();

  return (
    <div className={cn(collapsed ? "mb-2" : "mb-3")}>
      {!collapsed && (
        <p className="mb-1 px-2.5 text-2xs font-semibold uppercase tracking-[0.14em] text-foreground-faint">
          {title}
        </p>
      )}
      {collapsed && (
        <div className="mx-auto mb-1.5 h-px w-6 bg-surface-border-subtle" aria-hidden />
      )}
      <div className="space-y-0.5">
        {items.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={cn(
                "group relative flex items-center rounded-md text-caption font-medium transition-[background-color,color,box-shadow] duration-150",
                collapsed ? "justify-center px-2 py-2.5" : "gap-2.5 px-2.5 py-2",
                active
                  ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
                  : "text-foreground-muted hover:bg-surface-overlay/70 hover:text-foreground-secondary",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  active ? "text-brand" : "text-foreground-faint group-hover:text-foreground-muted",
                )}
                strokeWidth={1.75}
              />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export function Sidebar() {
  const org = useOrg();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <aside
      className={cn(
        "relative hidden h-full shrink-0 flex-col border-r border-surface-border bg-surface-raised/80 backdrop-blur-md transition-[width] duration-200 ease-out lg:flex",
        collapsed ? "w-[4.25rem]" : "w-56",
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_40%_at_0%_0%,rgba(59,130,246,0.1),transparent_55%)]"
      />

      <div
        className={cn(
          "relative flex h-14 shrink-0 items-center border-b border-surface-border-subtle",
          collapsed ? "justify-center px-2" : "gap-2 px-3",
        )}
      >
        <Image
          src="/parasite-mark.png"
          alt="Parasite"
          width={40}
          height={40}
          className="h-10 w-10 shrink-0 object-contain object-center"
          priority
        />
        {!collapsed && (
          <p className="min-w-0 flex-1 truncate text-[15px] font-semibold leading-none tracking-tight text-foreground">
            Parasite
          </p>
        )}
      </div>

      <nav
        className={cn(
          "relative min-h-0 flex-1 overflow-y-auto py-3 scrollbar-thin",
          collapsed ? "px-1.5" : "px-2",
        )}
      >
        <NavSection title="Operations" items={operationsNav} collapsed={collapsed} />
        <NavSection title="Management" items={managementNav} collapsed={collapsed} />
        <NavSection title="Configuration" items={configNav} collapsed={collapsed} />
      </nav>

      <div
        className={cn(
          "relative shrink-0 border-t border-surface-border-subtle",
          collapsed ? "p-1.5" : "p-2.5",
        )}
      >
        <button
          type="button"
          onClick={toggleCollapsed}
          className={cn(
            "mb-2 flex w-full items-center rounded-md border border-surface-border-subtle bg-surface-overlay/50 text-foreground-faint transition-colors hover:bg-surface-overlay hover:text-foreground-secondary",
            collapsed ? "justify-center px-2 py-2" : "justify-between gap-2 px-2.5 py-2",
          )}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {!collapsed && <span className="text-2xs font-medium">Collapse</span>}
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
          ) : (
            <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
          )}
        </button>

        <div
          className={cn(
            "rounded-md border border-surface-border-subtle bg-surface-overlay/40",
            collapsed ? "px-1.5 py-2 text-center" : "px-2.5 py-2",
          )}
          title={collapsed ? `${org.name} · ${org.botsActive}/${org.botsIncluded} agents` : undefined}
        >
          {collapsed ? (
            <p className="text-2xs font-semibold tabular-nums text-foreground">
              {org.botsActive}
              <span className="text-foreground-faint">/{org.botsIncluded}</span>
            </p>
          ) : (
            <>
              <p className="truncate text-caption font-medium text-foreground-secondary">
                {org.name}
              </p>
              <p className="mt-0.5 text-2xs tabular-nums text-foreground-faint">
                {org.botsActive}/{org.botsIncluded} agents
              </p>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface">
                <div
                  className="h-full rounded-full bg-brand transition-all"
                  style={{
                    width: `${Math.min(100, Math.round((org.botsActive / Math.max(org.botsIncluded, 1)) * 100))}%`,
                  }}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
