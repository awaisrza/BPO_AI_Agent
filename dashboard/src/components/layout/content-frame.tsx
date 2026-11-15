"use client";

import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const FULL_BLEED = new Set([
  "/leads",
  "/calls",
  "/bots",
  "/integrations",
  "/settings",
  "/campaigns",
]);

function isFullBleed(pathname: string) {
  if (FULL_BLEED.has(pathname)) return true;
  // Campaign editor / new campaign
  if (pathname.startsWith("/campaigns/")) return true;
  return false;
}

export function ContentFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const fullBleed = isFullBleed(pathname);

  return (
    <main
      className={cn(
        "flex min-h-0 flex-1 flex-col",
        fullBleed ? "overflow-hidden" : "overflow-y-auto scrollbar-thin",
      )}
    >
      <div
        className={cn(
          "flex min-h-0 w-full flex-1 flex-col",
          !fullBleed && "mx-auto max-w-content px-4 py-6 sm:px-6 lg:px-8 lg:py-8",
        )}
      >
        {children}
      </div>
    </main>
  );
}
