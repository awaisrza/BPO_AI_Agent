"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";

type SipPayload = {
  domain?: string;
  org_ref?: string;
  template?: string;
  example?: string;
  note?: string;
  bots?: { name: string; agent_user: string; sip_uri: string }[];
};

export function SipIntegrationCard() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<SipPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch("/api/integrations/sip");
        const body = (await res.json()) as SipPayload & { error?: string };
        if (!res.ok) {
          setError(body.error ?? "Could not load SIP settings.");
          return;
        }
        setData(body);
      } catch {
        setError("Could not load SIP settings.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  if (loading) {
    return (
      <Card>
        <CardBody className="flex items-center gap-2 text-body text-foreground-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading SIP URIs…
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="SIP remote agent"
        description="Production path — BPO points ViciDial remote agents here (no server install)."
      />
      <CardBody className="space-y-4">
        {error && <Alert variant="error">{error}</Alert>}
        {data?.note && <p className="text-caption text-foreground-muted">{data.note}</p>}
        {data?.template && (
          <div>
            <p className="text-caption font-medium text-foreground-muted">URI template</p>
            <code className="mt-1 block rounded-md bg-muted px-3 py-2 text-sm">{data.template}</code>
          </div>
        )}
        {data?.example && (
          <div>
            <p className="text-caption font-medium text-foreground-muted">Example</p>
            <code className="mt-1 block break-all rounded-md bg-muted px-3 py-2 text-sm">
              {data.example}
            </code>
          </div>
        )}
        {data?.bots && data.bots.length > 0 && (
          <div className="space-y-2">
            <p className="text-caption font-medium text-foreground-muted">Per-bot URIs</p>
            <ul className="space-y-2 text-sm">
              {data.bots.map((bot) => (
                <li key={bot.agent_user} className="rounded-md border border-border px-3 py-2">
                  <span className="font-medium">{bot.name}</span>
                  <span className="text-foreground-muted"> — agent {bot.agent_user}</span>
                  <code className="mt-1 block break-all text-xs">{bot.sip_uri}</code>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-caption text-foreground-faint">
          Set <code className="text-xs">SIP_EDGE_DOMAIN</code> in dashboard env to your live SIP
          domain. Open firewall UDP 5060 + RTP on your SIP edge VPS.
        </p>
      </CardBody>
    </Card>
  );
}
