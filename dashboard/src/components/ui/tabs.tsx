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
    <div className={cn("mb-6 flex gap-1 border-b border-surface-border", className)}>
      {tabs.map((tab) => (
        <button
          key={tab}
          type="button"
          onClick={() => onChange(tab)}
          className={cn(
            "-mb-px border-b-2 px-3 pb-2.5 text-body font-medium transition-colors",
            active === tab
              ? "border-brand text-foreground"
              : "border-transparent text-foreground-muted hover:text-foreground-secondary",
          )}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
