"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

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
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="rounded-md p-2 text-foreground-faint transition-colors hover:bg-surface-overlay hover:text-foreground-muted"
    >
      {/* Render both and swap via CSS so SSR markup never mismatches */}
      <Sun className="hidden h-4 w-4 dark:block" strokeWidth={1.75} />
      <Moon className="h-4 w-4 dark:hidden" strokeWidth={1.75} />
    </button>
  );
}
