import { Download, FileText } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress-bar";
import { org } from "@/lib/mock-data";

export default function BillingPage() {
  return (
    <>
      <PageHeader
        title="Billing"
        description="Usage tracking and invoices during pilot."
      />

      <div className="mb-8 rounded-xl border border-amber-500/15 bg-amber-500/[0.04] px-5 py-4">
        <p className="text-sm font-medium text-amber-400/90">Free pilot active</p>
        <p className="mt-1 text-sm text-zinc-500">
          {org.botsActive} bots running at $0/month. Billing activates when pilot converts.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="June 2026 usage" />
          <CardBody className="space-y-8">
            <ProgressBar
              value={org.botsActive}
              max={org.botsIncluded}
              label="Bots"
              sublabel="included"
            />
            <ProgressBar
              value={org.minutesUsed}
              max={org.minutesIncluded}
              label="Active minutes"
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Invoice preview"
            action={
              <span className="inline-flex items-center gap-1.5 rounded-md bg-white/[0.06] px-2 py-0.5 text-xs text-zinc-400">
                <FileText className="h-3 w-3" />
                Draft
              </span>
            }
          />
          <CardBody className="space-y-0 px-0 pb-0 pt-0">
            <div className="space-y-0 px-6">
              <InvoiceRow label={`${org.botsActive} bots × $0 (pilot)`} amount="$0.00" />
              <InvoiceRow label="Overage minutes (0 × $13)" amount="$0.00" />
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-surface-border px-6 py-4">
              <span className="font-medium text-zinc-200">Total</span>
              <span className="text-xl font-semibold tabular-nums text-zinc-100">$0.00</span>
            </div>
          </CardBody>
          <CardFooter className="flex gap-2">
            <Button variant="secondary">
              <Download className="h-4 w-4" />
              Download PDF
            </Button>
            <Button variant="ghost">Mark as paid</Button>
          </CardFooter>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Payment methods" description="Local rails during pilot" />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-3">
            <PaymentMethod title="Bank transfer (IBFT)" desc="PKR · Pakistan BPOs" active />
            <PaymentMethod title="Wise" desc="USD · International BPOs" />
            <PaymentMethod title="Safepay" desc="Coming soon · automated PKR" />
          </div>
          <p className="mt-6 text-xs text-zinc-600">
            Paid plan after pilot: ~$18–25/bot/month + overage ~$0.05/min
          </p>
        </CardBody>
      </Card>
    </>
  );
}

function InvoiceRow({ label, amount }: { label: string; amount: string }) {
  return (
    <div className="flex items-center justify-between border-b border-surface-border/60 py-3 text-sm last:border-0">
      <span className="text-zinc-500">{label}</span>
      <span className="tabular-nums text-zinc-400">{amount}</span>
    </div>
  );
}

function PaymentMethod({
  title,
  desc,
  active,
}: {
  title: string;
  desc: string;
  active?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        active
          ? "border-white/15 bg-white/[0.04]"
          : "border-surface-border bg-transparent"
      }`}
    >
      <p className="text-sm font-medium text-zinc-200">{title}</p>
      <p className="mt-1 text-xs text-zinc-600">{desc}</p>
    </div>
  );
}
