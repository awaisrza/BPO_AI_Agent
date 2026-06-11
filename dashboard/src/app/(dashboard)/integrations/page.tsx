import { CheckCircle2 } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select } from "@/components/ui/input";

export default function IntegrationsPage() {
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect ViciDial and your voice agent pipeline."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="ViciDial"
            description="Dialer, dispositions, warm transfer"
            action={
              <Badge variant="success" className="gap-1.5">
                <CheckCircle2 className="h-3 w-3" />
                Connected
              </Badge>
            }
          />
          <CardBody className="space-y-5">
            <Field label="Server URL">
              <Input defaultValue="https://vicidial.abccall.com" readOnly />
            </Field>
            <Field label="AGI script path">
              <Input defaultValue="/var/lib/asterisk/agi-bin/ai_fronter.agi" readOnly />
            </Field>
            <Field label="API user">
              <Input defaultValue="api_fronter" readOnly />
            </Field>
            <Field label="API password">
              <Input type="password" defaultValue="••••••••••••" />
            </Field>
            <Field label="Campaign mapping">
              <Select className="w-full">
                <option>MED_AEP_2026 → Medicare AEP</option>
                <option>SOLAR_Q1 → Solar Q1</option>
              </Select>
            </Field>
            <div className="flex gap-2 pt-1">
              <Button variant="secondary">Test connection</Button>
              <Button>Save</Button>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Voice agent (RunPod)"
            description="GPU pipeline — STT + TTS"
            action={
              <Badge variant="success" className="gap-1.5">
                <CheckCircle2 className="h-3 w-3" />
                Online
              </Badge>
            }
          />
          <CardBody className="space-y-5">
            <Field label="GPU endpoint">
              <Input defaultValue="https://api.runpod.ai/v2/xxxxx" readOnly />
            </Field>
            <Field label="Schedule">
              <Input defaultValue="8h/day · US Eastern calling window" readOnly />
            </Field>
            <Field label="STT model">
              <Input defaultValue="faster-whisper distil-small" readOnly />
            </Field>
            <Field label="TTS engine">
              <Input defaultValue="Piper + cached script audio" readOnly />
            </Field>
            <div className="flex gap-2 pt-1">
              <Button variant="secondary">Test pipeline</Button>
              <Button>Save</Button>
            </div>
          </CardBody>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Webhooks" description="Send call events to external systems" />
        <CardBody className="space-y-5">
          <Field label="Webhook URL">
            <Input defaultValue="https://hooks.abccall.com/ai-fronter" />
          </Field>
          <div>
            <p className="mb-3 text-sm font-medium text-zinc-400">Events</p>
            <div className="flex flex-wrap gap-2">
              {["call.started", "call.ended", "disposition.created", "transfer.completed"].map((e) => (
                <label
                  key={e}
                  className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-overlay/40 px-3 py-2 text-xs text-zinc-400"
                >
                  <input type="checkbox" defaultChecked className="rounded accent-zinc-100" />
                  <code className="text-zinc-300">{e}</code>
                </label>
              ))}
            </div>
          </div>
        </CardBody>
      </Card>
    </>
  );
}
