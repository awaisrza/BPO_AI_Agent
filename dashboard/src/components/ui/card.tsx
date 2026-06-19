import { cn } from "@/lib/utils";

export function Card({
  children,
  className,
  padding = "default",
}: {
  children: React.ReactNode;
  className?: string;
  padding?: "none" | "default" | "compact";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-surface-border bg-surface-raised",
        padding === "compact" && "p-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-surface-border-subtle px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0">
        <h3 className="text-body font-medium text-foreground">{title}</h3>
        {description && (
          <p className="mt-1 text-caption text-foreground-muted">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("px-5 py-4", className)}>{children}</div>;
}

export function CardFooter({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "border-t border-surface-border-subtle px-5 py-3",
        className,
      )}
    >
      {children}
    </div>
  );
}
