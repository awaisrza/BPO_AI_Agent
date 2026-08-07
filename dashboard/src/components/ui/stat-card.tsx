import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  trend,
  className,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  trend?: "up" | "down" | "neutral";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-surface-border bg-surface-raised p-4",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="data-label">{label}</p>
        {Icon && (
          <Icon className="h-3.5 w-3.5 text-foreground-faint" strokeWidth={1.75} aria-hidden />
        )}
      </div>
      <p className="metric-value mt-2">{value}</p>
      {hint && (
        <p
          className={cn(
            "mt-1 text-caption",
            trend === "up" && "text-status-success",
            trend === "down" && "text-status-danger",
            (!trend || trend === "neutral") && "text-foreground-faint",
          )}
        >
          {hint}
        </p>
      )}
    </div>
  );
}
