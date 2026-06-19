import { cn } from "@/lib/utils";

const variants = {
  default: "bg-surface-overlay text-foreground-secondary border-surface-border",
  success: "bg-status-success-muted text-status-success border-transparent",
  warning: "bg-status-warning-muted text-status-warning border-transparent",
  danger: "bg-status-danger-muted text-status-danger border-transparent",
  info: "bg-status-info-muted text-status-info border-transparent",
  live: "bg-status-success-muted text-status-success border-transparent",
  brand: "bg-brand-muted text-brand border-transparent",
};

const dots: Partial<Record<keyof typeof variants, string>> = {
  success: "bg-status-success",
  warning: "bg-status-warning",
  danger: "bg-status-danger",
  info: "bg-status-info",
  live: "bg-status-success",
  brand: "bg-brand",
  default: "bg-foreground-faint",
};

export function Badge({
  children,
  variant = "default",
  dot = false,
  className,
}: {
  children: React.ReactNode;
  variant?: keyof typeof variants;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-caption font-medium",
        variants[variant],
        className,
      )}
    >
      {dot && (
        <span
          className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dots[variant])}
        />
      )}
      {children}
    </span>
  );
}
