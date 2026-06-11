import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { AssignBotForm } from "@/components/bots/assign-bot-form";

export default function AssignBotPage() {
  return (
    <>
      <Link
        href="/bots"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-zinc-600 transition-colors hover:text-zinc-400"
      >
        <ArrowLeft className="h-4 w-4" />
        Bots
      </Link>

      <PageHeader
        title="Assign bot to campaign"
        description="Each bot is one concurrent dialer line linked to a campaign."
      />

      <Card>
        <CardBody>
          <AssignBotForm />
        </CardBody>
      </Card>
    </>
  );
}
