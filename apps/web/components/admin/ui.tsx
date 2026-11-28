"use client";

import {
  Archive,
  CircleAlert,
  CircleCheck,
  Clock,
  FilePen,
  Inbox,
  X,
} from "lucide-react";
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useEffect,
  useId,
  useRef,
} from "react";

import type { Status } from "@/lib/admin/api";
import { formatDate } from "@/lib/chat/format";

/* Admin portal building blocks (DESIGN.md 6.2). Colors only through tokens. */

type Tone = "primary" | "secondary" | "danger" | "ghost";

const TONE: Record<Tone, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-hover",
  secondary: "border border-border bg-surface-2 text-text hover:border-border-teal",
  danger: "border border-danger text-danger hover:bg-surface-2",
  ghost: "text-accent hover:bg-surface-2",
};

export function Button({
  tone = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-(--radius-sm) px-4 text-sm font-semibold transition-colors duration-(--duration-fast) disabled:cursor-not-allowed disabled:opacity-50 ${TONE[tone]} ${className}`}
    />
  );
}

const CONTROL =
  "min-h-11 w-full rounded-(--radius-sm) border border-border bg-surface-2 px-3 text-sm text-text placeholder:text-muted focus:border-border-teal";

export function Field({
  label,
  hint,
  error,
  required,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  children: ReactNode;
  htmlFor: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
        {required ? <span className="text-muted"> (required)</span> : null}
      </label>
      {children}
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${CONTROL} ${props.className ?? ""}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${CONTROL} py-2 ${props.className ?? ""}`} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${CONTROL} ${props.className ?? ""}`} />;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-(--radius-md) border border-border bg-surface-1 p-5 ${className}`}>
      {children}
    </section>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-bold">{title}</h1>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

const STATUS: Record<Status, { label: string; icon: typeof Clock; className: string }> = {
  draft: { label: "Draft", icon: FilePen, className: "text-muted border-border" },
  pending: { label: "Pending", icon: Clock, className: "text-warning border-warning" },
  approved: { label: "Approved", icon: CircleCheck, className: "text-success border-success" },
  archived: { label: "Archived", icon: Archive, className: "text-muted border-border" },
};

/** Status chip: icon + text, never color alone (DESIGN.md 9). */
export function StatusChip({ status }: { status: Status }) {
  const { label, icon: Icon, className } = STATUS[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-(--radius-pill) border px-2 py-0.5 text-xs font-medium ${className}`}
    >
      <Icon size={12} strokeWidth={2} aria-hidden="true" />
      {label}
    </span>
  );
}

/** Expiry cell: warning color plus an icon and words when expired or close. */
export function Expiry({ iso, today }: { iso: string | null; today: string }) {
  if (!iso) return <span className="text-muted">—</span>;
  const days = Math.round((Date.parse(iso) - Date.parse(today)) / 86_400_000);
  const text = formatDate(iso) ?? iso;
  if (days < 0)
    return (
      <span className="inline-flex items-center gap-1 text-danger">
        <CircleAlert size={14} aria-hidden="true" /> Expired {text}
      </span>
    );
  if (days <= 14)
    return (
      <span className="inline-flex items-center gap-1 text-warning">
        <Clock size={14} aria-hidden="true" /> {text} ({days} days)
      </span>
    );
  return <span>{text}</span>;
}

export function todayIso(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export function Notice({ tone, children }: { tone: "error" | "success" | "info"; children: ReactNode }) {
  const color = tone === "error" ? "text-danger" : tone === "success" ? "text-success" : "text-accent";
  const Icon = tone === "error" ? CircleAlert : tone === "success" ? CircleCheck : Inbox;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`mb-4 flex items-start gap-2 rounded-(--radius-sm) border border-border bg-surface-teal px-3 py-2 text-sm ${color}`}
    >
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-(--radius-md) border border-dashed border-border px-6 py-12 text-center">
      <Inbox size={36} strokeWidth={1.5} className="text-muted" aria-hidden="true" />
      <p className="text-sm text-muted">{text}</p>
      {action}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p role="status" className="py-8 text-center text-sm text-muted">
      {label}
    </p>
  );
}

/** Dense, keyboard-friendly table (48 px rows, hover highlight, no zebra). */
export function Table({ head, children, label }: { head: ReactNode[]; children: ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto rounded-(--radius-md) border border-border">
      <table className="w-full min-w-160 border-collapse text-sm" aria-label={label}>
        <thead className="bg-surface-2 text-start text-xs text-muted uppercase">
          <tr>
            {head.map((cell, i) => (
              <th key={i} scope="col" className="px-3 py-3 text-start font-semibold">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export const ROW = "h-12 border-t border-border hover:bg-surface-2";
export const CELL = "px-3 py-2 align-middle";

/** Modal dialog: Escape and the backdrop close it; focus moves in and back out. */
export function Dialog({
  title,
  onClose,
  children,
  side = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  side?: boolean;
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, [onClose]);
  return (
    <div className={`fixed inset-0 z-40 flex ${side ? "justify-end" : "items-center justify-center p-4"}`}>
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-bg/70"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`sheet-rise relative overflow-y-auto border border-border bg-surface-1 p-5 ${
          side ? "h-full w-full max-w-xl" : "max-h-[90dvh] w-full max-w-lg rounded-(--radius-lg)"
        }`}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-lg font-semibold">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="inline-flex size-11 items-center justify-center rounded-(--radius-pill) text-muted hover:bg-surface-2"
          >
            <X size={20} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Confirm before a destructive action (DESIGN.md 6.2). */
export function Confirm({
  title,
  body,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog title={title} onClose={onCancel}>
      <p className="mb-5 text-sm text-muted">{body}</p>
      <div className="flex justify-end gap-2">
        <Button onClick={onCancel}>Cancel</Button>
        <Button tone="danger" onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
