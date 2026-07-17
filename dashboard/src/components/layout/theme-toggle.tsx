"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

export function ThemeToggle({
  className,
  showLabel = true,
}: {
  className?: string;
  showLabel?: boolean;
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

  return (
    <button
      type="button"
      onClick={toggle}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
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
