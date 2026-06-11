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
        "rounded-xl border border-surface-border bg-surface-raised p-5",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-zinc-500">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-zinc-600" aria-hidden />}
      </div>
      <p className="mt-3 text-2xl font-semibold tracking-tightest text-zinc-50">
        {value}
      </p>
      {hint && (
        <p
          className={cn(
            "mt-1.5 text-xs",
            trend === "up" && "text-emerald-400/90",
            trend === "down" && "text-red-400/90",
            (!trend || trend === "neutral") && "text-zinc-500",
          )}
        >
          {hint}
        </p>
      )}
    </div>
  );
}
