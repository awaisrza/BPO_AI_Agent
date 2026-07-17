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
  /** "sidebar" styles for the dark pine sidebar panel */
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

  return (
    <button
      type="button"
      onClick={toggle}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className={cn(
        "inline-flex w-full items-center justify-center gap-1.5 rounded-md border px-2.5 py-1.5 text-caption font-medium shadow-sm transition-colors",
        variant === "sidebar"
          ? "border-sidebar-border bg-sidebar-raised text-sidebar-text hover:bg-sidebar-active"
          : "border-surface-border bg-surface-raised text-foreground-secondary hover:bg-surface-overlay hover:text-foreground",
        className,
      )}
    >
      {dark ? (
        <Sun
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            variant === "sidebar" ? "text-sidebar-accent" : "text-brand",
          )}
          strokeWidth={1.75}
        />
      ) : (
        <Moon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            variant === "sidebar" ? "text-sidebar-accent" : "text-brand",
          )}
          strokeWidth={1.75}
        />
      )}
      {showLabel && <span>{dark ? "Light mode" : "Dark mode"}</span>}
    </button>
  );
}
