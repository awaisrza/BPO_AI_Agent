import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export function PageBack({
  href,
  label,
}: {
  href: string;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="mb-4 inline-flex items-center gap-1.5 text-caption font-medium text-foreground-muted transition-colors hover:text-foreground-secondary"
    >
      <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
      {label}
    </Link>
  );
}
