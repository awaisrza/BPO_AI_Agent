import { cn } from "@/lib/utils";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-lg border border-surface-border bg-surface-overlay px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 transition-colors focus:border-white/20 focus:outline-none focus:ring-1 focus:ring-white/10",
        className,
      )}
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
        "w-full resize-y rounded-lg border border-surface-border bg-surface-overlay px-4 py-3 text-sm leading-relaxed text-zinc-200 placeholder:text-zinc-600 transition-colors focus:border-white/20 focus:outline-none focus:ring-1 focus:ring-white/10",
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
      className={cn(
        "rounded-lg border border-surface-border bg-surface-overlay px-3 py-2 text-sm text-zinc-200 transition-colors focus:border-white/20 focus:outline-none focus:ring-1 focus:ring-white/10",
        className,
      )}
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
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="text-sm font-medium text-zinc-400">{label}</label>
      {description && (
        <p className="mt-0.5 text-xs text-zinc-600">{description}</p>
      )}
      <div className="mt-2">{children}</div>
    </div>
  );
}

export function Checkbox({
  label,
  defaultChecked,
  className,
}: {
  label: string;
  defaultChecked?: boolean;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 text-sm leading-relaxed text-zinc-400",
        className,
      )}
    >
      <input
        type="checkbox"
        defaultChecked={defaultChecked}
        className="mt-0.5 rounded border-surface-border bg-surface-overlay accent-zinc-100"
      />
      {label}
    </label>
  );
}
