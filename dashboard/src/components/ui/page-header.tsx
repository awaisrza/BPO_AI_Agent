export function PageHeader({
  title,
  description,
  action,
  eyebrow,
}: {
  title: React.ReactNode;
  description?: string;
  action?: React.ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="mb-10 flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
      <div className="max-w-2xl">
        {eyebrow && (
          <p className="mb-2 text-sm text-zinc-500">{eyebrow}</p>
        )}
        <h1 className="text-xl font-semibold tracking-tight text-zinc-50">
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-sm leading-relaxed text-zinc-500">
            {description}
          </p>
        )}
      </div>
      {action && (
        <div className="flex shrink-0 items-center gap-2">{action}</div>
      )}
    </div>
  );
}
