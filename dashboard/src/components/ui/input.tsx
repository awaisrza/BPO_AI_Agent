import { cn } from "@/lib/utils";

const controlClass =
  "w-full rounded-md border border-surface-border bg-surface-overlay text-body text-foreground transition-colors placeholder:text-foreground-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand/30 disabled:cursor-not-allowed disabled:opacity-50";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(controlClass, "h-9 px-3", className)}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        controlClass,
        "resize-y px-3 py-2.5 leading-relaxed",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(controlClass, "h-9 px-3", className)}
      {...props}
    >
      {children}
    </select>
  );
}

export function Field({
  label,
  description,
  children,
  className,
  error,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  error?: string;
}) {
  return (
    <div className={className}>
      <label className="text-body font-medium text-foreground-secondary">{label}</label>
      {description && (
        <p className="mt-0.5 text-caption text-foreground-faint">{description}</p>
      )}
      <div className="mt-2">{children}</div>
      {error && (
        <p className="mt-1.5 text-caption text-status-danger">{error}</p>
      )}
    </div>
  );
}

export function Checkbox({
  label,
  defaultChecked,
  checked,
  onChange,
  className,
}: {
  label: string;
  defaultChecked?: boolean;
  checked?: boolean;
  onChange?: React.ChangeEventHandler<HTMLInputElement>;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 text-body leading-relaxed text-foreground-muted",
        className,
      )}
    >
      <input
        type="checkbox"
        defaultChecked={defaultChecked}
        checked={checked}
        onChange={onChange}
        className="mt-0.5 rounded-sm border-surface-border bg-surface-overlay accent-brand"
      />
      {label}
    </label>
  );
}
