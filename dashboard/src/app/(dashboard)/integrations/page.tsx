import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { VicidialIntegrationForm } from "@/components/integrations/vicidial-integration-form";
import { SipIntegrationCard } from "@/components/integrations/sip-integration-card";

export default function IntegrationsPage() {
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect ViciDial and SIP for outbound AI fronter calls."
        eyebrow="Configuration"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <VicidialIntegrationForm />
        <SipIntegrationCard />

        <Card className="lg:col-span-2">
          <CardHeader
            title="Voice pipeline"
            description="GPU stack uses shared Whisper + Chatterbox when a campaign is running."
            action={<Badge variant="brand">Included</Badge>}
          />
          <CardBody className="space-y-3 text-body text-foreground-muted">
            <p>
              Inference pool, fleet workers, and conversation AI run on your GPU host. Managed
              Deepgram + Fish mode remains available for non-GPU pilots.
            </p>
            <ul className="list-inside list-disc space-y-1 text-caption text-foreground-faint">
              <li>Whisper STT · Chatterbox TTS (pooled on GPU)</li>
              <li>Gemini for off-script questions</li>
              <li>Campaign scripts from your dashboard</li>
            </ul>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
