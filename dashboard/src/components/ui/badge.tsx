import { cn } from "@/lib/utils";

const variants = {
  default: "bg-white/[0.06] text-zinc-300",
  success: "bg-emerald-500/10 text-emerald-400",
  warning: "bg-amber-500/10 text-amber-400",
  danger: "bg-red-500/10 text-red-400",
  info: "bg-sky-500/10 text-sky-400",
  live: "bg-emerald-500/10 text-emerald-400",
};

const dots: Partial<Record<keyof typeof variants, string>> = {
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  danger: "bg-red-400",
  info: "bg-sky-400",
  live: "bg-emerald-400",
  default: "bg-zinc-500",
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
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium",
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
