import Link from "next/link";
import { cn } from "@/lib/utils";

const variants = {
  primary:
    "bg-zinc-100 text-zinc-900 hover:bg-white border-transparent shadow-sm",
  secondary:
    "bg-transparent text-zinc-300 hover:bg-white/[0.04] border-surface-border",
  ghost:
    "bg-transparent text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04] border-transparent",
};

const sizes = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-3.5 py-2 text-sm",
};

const baseClass =
  "inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-400 disabled:pointer-events-none disabled:opacity-40";

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  href,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  href?: string;
}) {
  const styles = cn(baseClass, variants[variant], sizes[size], className);

  if (href) {
    return (
      <Link href={href} className={styles}>
        {children}
      </Link>
    );
  }

  return (
    <button className={styles} {...props}>
      {children}
    </button>
  );
}
