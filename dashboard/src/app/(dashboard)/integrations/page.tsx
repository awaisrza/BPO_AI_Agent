import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { VicidialIntegrationForm } from "@/components/integrations/vicidial-integration-form";

export default function IntegrationsPage() {
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect ViciDial and external services to your call center."
        eyebrow="Configuration"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <VicidialIntegrationForm />

        <Card>
          <CardHeader
            title="Voice pipeline"
            description="Managed by AI Fronter — no setup required."
            action={<Badge variant="brand">Included</Badge>}
          />
          <CardBody className="space-y-3 text-body text-foreground-muted">
            <p>Speech-to-text, text-to-speech, and conversation AI are provisioned automatically for your agents.</p>
            <ul className="list-inside list-disc space-y-1 text-caption text-foreground-faint">
              <li>Deepgram STT · Fish Audio TTS</li>
              <li>Gemini for off-script questions</li>
              <li>Campaign scripts from your dashboard</li>
            </ul>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
