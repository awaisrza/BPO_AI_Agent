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
    <div className={cn("space-y-3", className)}>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm text-zinc-400">{label}</span>
        <span className="text-sm tabular-nums text-zinc-500">
          {value.toLocaleString()}
          <span className="text-zinc-600"> / {max.toLocaleString()}</span>
          {sublabel && (
            <span className="ml-2 text-xs text-zinc-600">{sublabel}</span>
          )}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full bg-zinc-100 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
