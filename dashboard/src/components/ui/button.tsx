import Link from "next/link";
import { cn } from "@/lib/utils";

const variants = {
  primary:
    "bg-brand text-brand-foreground hover:bg-brand-hover border-transparent shadow-sm",
  secondary:
    "bg-transparent text-foreground-secondary hover:bg-surface-overlay border-surface-border",
  ghost:
    "bg-transparent text-foreground-muted hover:text-foreground-secondary hover:bg-surface-overlay border-transparent",
  danger:
    "bg-transparent text-status-danger hover:bg-status-danger-muted border-transparent",
};

const sizes = {
  sm: "h-8 px-3 text-caption gap-1.5",
  md: "h-9 px-3.5 text-body gap-2",
};

const baseClass =
  "inline-flex items-center justify-center rounded-md border font-medium transition-colors focus-visible:outline-none focus-visible:shadow-focus disabled:pointer-events-none disabled:opacity-40";

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
