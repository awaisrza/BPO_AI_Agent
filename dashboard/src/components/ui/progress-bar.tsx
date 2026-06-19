import { cn } from "@/lib/utils";

export function ProgressBar({
  value,
  max,
  label,
  sublabel,
  className,
}: {
  value: number;
  max: number;
  label: string;
  sublabel?: string;
  className?: string;
}) {
  const pct = Math.min(100, Math.round((value / max) * 100));

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-body text-foreground-secondary">{label}</span>
        <span className="text-caption tabular-nums text-foreground-muted">
          {value.toLocaleString()}
          <span className="text-foreground-faint"> / {max.toLocaleString()}</span>
          {sublabel && (
            <span className="ml-2 text-foreground-faint">{sublabel}</span>
          )}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-sm bg-surface-overlay">
        <div
          className="h-full rounded-sm bg-brand transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
