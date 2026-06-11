import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowLeft, Mic, Play, Save } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { CampaignEditorTitle } from "@/components/campaigns/campaign-editor-title";

export default async function CampaignEditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Link
        href="/campaigns"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-zinc-600 transition-colors hover:text-zinc-400"
      >
        <ArrowLeft className="h-4 w-4" />
        Campaigns
      </Link>

      <PageHeader
        title={<CampaignEditorTitle id={id} />}
        description="Configure what the bot says, qualifying questions, and transfer rules."
        action={
          <>
            <Button variant="secondary">
              <Play className="h-4 w-4" />
              Test bot
            </Button>
            <Button>
              <Save className="h-4 w-4" />
              Save
            </Button>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="Opening script"
              description="Played when a human answers"
              action={<Badge variant="success">Cached audio</Badge>}
            />
            <CardBody>
              <Textarea
                className="min-h-[100px]"
                defaultValue="Hi, this is Sarah calling about your Medicare benefits review. Do you have a moment?"
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Qualifying questions" />
            <CardBody className="space-y-2">
              {[
                "Are you 65 or older?",
                "Do you have Medicare Part A?",
                "Interested in speaking with a licensed specialist?",
              ].map((q) => (
                <div
                  key={q}
                  className="flex items-center gap-3 rounded-lg border border-surface-border bg-surface-overlay/40 px-4 py-3"
                >
                  <input type="checkbox" defaultChecked className="rounded accent-zinc-100" />
                  <span className="text-sm text-zinc-300">{q}</span>
                </div>
              ))}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Objection handling" description="Gemini replies when off-script" />
            <CardBody className="space-y-4 text-sm">
              <div className="flex gap-3">
                <span className="shrink-0 text-zinc-500">Not interested</span>
                <span className="text-zinc-400">Polite close, disposition NI</span>
              </div>
              <div className="flex gap-3">
                <span className="shrink-0 text-zinc-500">Who is this?</span>
                <span className="text-zinc-400">Explain purpose, continue script</span>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Transfer rule" />
            <CardBody>
              <p className="rounded-lg bg-emerald-500/[0.06] px-4 py-3 text-sm text-emerald-400/90">
                IF qualified AND interested → Warm transfer to{" "}
                <span className="font-mono text-emerald-300">closers-01</span>
              </p>
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Settings" />
            <CardBody className="space-y-5">
              <SettingRow label="Voice" value="Sarah · US English" icon={Mic} />
              <SettingRow label="ViciDial ID" value="MED_AEP_2026" mono />
              <SettingRow label="Bots assigned" value="8 bots" />
              <SettingRow label="Transfer queue" value="closers-01" mono />
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}

function SettingRow({
  label,
  value,
  mono,
  icon: Icon,
}: {
  label: string;
  value: string;
  mono?: boolean;
  icon?: LucideIcon;
}) {
  return (
    <div>
      <p className="text-xs text-zinc-600">{label}</p>
      <p className={`mt-1.5 flex items-center gap-2 text-sm text-zinc-200 ${mono ? "font-mono" : ""}`}>
        {Icon && <Icon className="h-3.5 w-3.5 text-zinc-600" />}
        {value}
      </p>
    </div>
  );
}
