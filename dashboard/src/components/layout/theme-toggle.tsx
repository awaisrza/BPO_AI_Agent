"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

export function ThemeToggle({
  className,
  showLabel = true,
  variant = "default",
}: {
  className?: string;
  showLabel?: boolean;
  /** Icon-only control for the sidebar footer corner */
  variant?: "default" | "sidebar";
}) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
    setDark(next);
  }

  const label = dark ? "Switch to light mode" : "Switch to dark mode";

  if (variant === "sidebar") {
    return (
      <button
        type="button"
        onClick={toggle}
        title={label}
        aria-label={label}
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-sidebar-border bg-sidebar-raised text-sidebar-accent transition-colors hover:bg-sidebar-active",
          className,
        )}
      >
        {dark ? (
          <Sun className="h-3.5 w-3.5" strokeWidth={1.75} />
        ) : (
          <Moon className="h-3.5 w-3.5" strokeWidth={1.75} />
        )}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={label}
      aria-label={label}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md border border-surface-border bg-surface-raised px-2.5 py-1.5 text-caption font-medium text-foreground-secondary shadow-sm transition-colors hover:bg-surface-overlay hover:text-foreground",
        className,
      )}
    >
      {dark ? (
        <Sun className="h-3.5 w-3.5 shrink-0 text-brand" strokeWidth={1.75} />
      ) : (
        <Moon className="h-3.5 w-3.5 shrink-0 text-brand" strokeWidth={1.75} />
      )}
      {showLabel && <span>{dark ? "Light" : "Dark"}</span>}
    </button>
  );
}
