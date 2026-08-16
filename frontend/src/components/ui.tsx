import type { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  action,
  children,
}: {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-[var(--color-edge)] bg-[var(--color-panel)] shadow-lg shadow-black/20">
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-[var(--color-edge)] px-5 py-4">
          <div>
            {title && <h2 className="text-sm font-semibold tracking-wide">{title}</h2>}
            {subtitle && (
              <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{subtitle}</p>
            )}
          </div>
          {action}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

const STATUS_STYLES: Record<string, string> = {
  ok: "bg-[var(--color-positive)]/15 text-[var(--color-positive)] border-[var(--color-positive)]/30",
  degraded:
    "bg-[var(--color-caution)]/15 text-[var(--color-caution)] border-[var(--color-caution)]/30",
  error:
    "bg-[var(--color-negative)]/15 text-[var(--color-negative)] border-[var(--color-negative)]/30",
  neutral:
    "bg-[var(--color-panel-raised)] text-[var(--color-ink-muted)] border-[var(--color-edge)]",
};

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: keyof typeof STATUS_STYLES;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${
        STATUS_STYLES[tone] ?? STATUS_STYLES.neutral
      }`}
    >
      {children}
    </span>
  );
}

export function EmptyState({
  title,
  detail,
  hint,
}: {
  title: string;
  detail: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--color-edge)] px-6 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-[var(--color-ink-muted)]">
        {detail}
      </p>
      {hint && (
        <p className="mt-3 font-mono text-[11px] text-[var(--color-accent)]">{hint}</p>
      )}
    </div>
  );
}

export function Field({
  label,
  ...props
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-[var(--color-ink-muted)]">
        {label}
      </span>
      <input
        {...props}
        className="w-full rounded-lg border border-[var(--color-edge)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none transition focus:border-[var(--color-accent)]"
      />
    </label>
  );
}

export function Button({
  children,
  variant = "primary",
  ...props
}: {
  variant?: "primary" | "ghost";
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const styles =
    variant === "primary"
      ? "bg-[var(--color-accent)] text-white hover:brightness-110"
      : "border border-[var(--color-edge)] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]";
  return (
    <button
      {...props}
      className={`rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}
    >
      {children}
    </button>
  );
}
