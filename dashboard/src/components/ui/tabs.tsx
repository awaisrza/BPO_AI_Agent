"use client";

import { cn } from "@/lib/utils";

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: readonly T[];
  active: T;
  onChange: (tab: T) => void;
  className?: string;
}) {
  return (
    <div className={cn("mb-8 flex gap-6 border-b border-surface-border", className)}>
      {tabs.map((tab) => (
        <button
          key={tab}
          type="button"
          onClick={() => onChange(tab)}
          className={cn(
            "-mb-px border-b-2 pb-3 text-sm font-medium transition-colors",
            active === tab
              ? "border-zinc-100 text-zinc-100"
              : "border-transparent text-zinc-500 hover:text-zinc-300",
          )}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
