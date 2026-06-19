import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center px-6 py-12 text-center",
        className,
      )}
    >
      {Icon && (
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md border border-surface-border bg-surface-overlay">
          <Icon className="h-4 w-4 text-foreground-faint" strokeWidth={1.75} />
        </div>
      )}
      <p className="text-body font-medium text-foreground-secondary">{title}</p>
      {description && (
        <p className="mt-1 max-w-sm text-caption text-foreground-muted">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
