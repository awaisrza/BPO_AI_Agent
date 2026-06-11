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
import { cn } from "@/lib/utils";
import { org } from "@/lib/mock-data";

const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/bots", label: "Bots", icon: Bot },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/calls", label: "Calls", icon: Phone },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/integrations", label: "Integrations", icon: Cable },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/billing", label: "Billing", icon: CreditCard },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-[220px] shrink-0 flex-col border-r border-surface-border bg-surface">
      <div className="flex h-14 items-center gap-3 px-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white/[0.08]">
          <Phone className="h-3.5 w-3.5 text-zinc-200" strokeWidth={2} />
        </div>
        <div>
          <p className="text-sm font-medium text-zinc-100">AI Fronter</p>
          <p className="text-2xs text-zinc-600">Voice platform</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 pt-2">
        {nav.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                active
                  ? "bg-white/[0.06] text-zinc-100"
                  : "text-zinc-500 hover:bg-white/[0.03] hover:text-zinc-300",
              )}
            >
              <Icon className="h-4 w-4 shrink-0 opacity-70" strokeWidth={1.75} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-surface-border p-4">
        <p className="truncate text-sm font-medium text-zinc-300">{org.name}</p>
        <p className="mt-1 text-xs text-zinc-600">
          {org.plan} · {org.botsActive}/{org.botsIncluded} bots
        </p>
        {org.pilot && (
          <span className="mt-3 inline-flex items-center rounded-md bg-amber-500/10 px-2 py-0.5 text-2xs font-medium text-amber-400/90">
            Free pilot
          </span>
        )}
      </div>
    </aside>
  );
}
