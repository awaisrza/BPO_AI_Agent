import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Cable,
  Megaphone,
  Phone,
  PhoneForwarded,
  Timer,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const setupSteps: {
  title: string;
  description: string;
  href: string;
  cta: string;
  icon: LucideIcon;
}[] = [
  {
    title: "Connect your dialer",
    description: "Link ViciDial so agents can start placing calls.",
    href: "/integrations",
    cta: "Open integrations",
    icon: Cable,
  },
  {
    title: "Create a campaign",
    description: "Add your script, qualifying questions, and transfer rules.",
    href: "/campaigns/new",
    cta: "New campaign",
    icon: Megaphone,
  },
  {
    title: "Assign an agent",
    description: "Put an AI agent on the campaign and go live.",
    href: "/bots/assign",
    cta: "Assign agent",
    icon: Bot,
  },
];

export default function OverviewPage() {
  return (
    <div>
      <PageHeader
        title="Overview"
        description="Today's calls, live agents, and transfers — at a glance."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Calls today"
          value="—"
          hint="No calls placed yet"
          icon={Phone}
        />
        <StatCard
          label="Active agents"
          value="—"
          hint="No agents assigned"
          icon={Bot}
        />
        <StatCard
          label="Transfers"
          value="—"
          hint="Warm transfers to closers"
          icon={PhoneForwarded}
        />
        <StatCard
          label="Avg. handle time"
          value="—"
          hint="Per connected call"
          icon={Timer}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Get set up"
            description="Three steps to your first live call."
          />
          <ol className="divide-y divide-surface-border-subtle">
            {setupSteps.map(({ title, description, href, cta, icon: Icon }, i) => (
              <li key={href}>
                <Link
                  href={href}
                  className="group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-surface-overlay/40"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-brand-muted text-brand">
                    <Icon className="h-4 w-4" strokeWidth={1.75} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-body font-medium text-foreground">
                      {i + 1}. {title}
                    </span>
                    <span className="mt-0.5 block text-caption text-foreground-muted">
                      {description}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5 text-caption font-medium text-brand">
                    <span className="hidden sm:inline">{cta}</span>
                    <ArrowRight
                      className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
                      strokeWidth={1.75}
                    />
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </Card>

        <Card>
          <CardHeader
            title="Live activity"
            description="Calls in progress right now."
          />
          <div className="flex flex-col items-center px-5 py-8 text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-md border border-surface-border bg-surface-overlay/60">
              <Users className="h-4 w-4 text-foreground-faint" strokeWidth={1.75} />
            </span>
            <p className="mt-3 text-body font-medium text-foreground-secondary">
              No live calls
            </p>
            <p className="mt-1 max-w-[16rem] text-caption text-foreground-muted">
              Once an agent is dialing, live calls and transfers appear here.
            </p>
            <Button href="/calls" variant="secondary" size="sm" className="mt-4">
              View call log
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
