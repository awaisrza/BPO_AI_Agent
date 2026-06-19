import { PageBack } from "@/components/ui/page-back";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { AssignBotForm } from "@/components/bots/assign-bot-form";

export default function AssignBotPage() {
  return (
    <>
      <PageBack href="/bots" label="Agents" />

      <PageHeader
        title="Assign agent"
        description="Each agent is one concurrent dialer line linked to a campaign."
      />

      <Card>
        <CardBody>
          <AssignBotForm />
        </CardBody>
      </Card>
    </>
  );
}
