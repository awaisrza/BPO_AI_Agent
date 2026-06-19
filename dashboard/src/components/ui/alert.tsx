import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

const variants = {
  error: "border-status-danger/30 bg-status-danger-muted text-status-danger",
  warning: "border-status-warning/30 bg-status-warning-muted text-status-warning",
  info: "border-status-info/30 bg-status-info-muted text-status-info",
  success: "border-status-success/30 bg-status-success-muted text-status-success",
};

export function Alert({
  children,
  variant = "error",
  icon: Icon,
  className,
}: {
  children: React.ReactNode;
  variant?: keyof typeof variants;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex gap-3 rounded-md border px-4 py-3 text-body",
        variants[variant],
        className,
      )}
      role="alert"
    >
      {Icon && <Icon className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} />}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
