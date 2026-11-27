"use client";

import { Building2, CircleAlert, CircleCheck, FileText } from "lucide-react";
import { useState } from "react";

import { Sheet } from "@/components/chat/Sheet";
import { formatDate, verifiedBadge } from "@/lib/chat/format";
import type { Source } from "@/lib/chat/protocol";

/** "Verified by <office> · <date>" or "May be outdated · ..." (CHAT-3). Icon + text, not color only. */
export function VerifiedBadge({ sources }: { sources: Source[] }) {
  const badge = verifiedBadge(sources);
  if (!badge) return null;
  const Icon = badge.kind === "verified" ? CircleCheck : CircleAlert;
  return (
    <p
      className={`flex items-center gap-1.5 text-xs font-medium ${badge.kind === "verified" ? "text-success" : "text-warning"}`}
    >
      <Icon size={14} strokeWidth={1.75} aria-hidden="true" />
      {badge.text}
    </p>
  );
}

/** Source chips; tapping one opens a sheet with title, office, last verified date and link. */
export function SourceChips({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState<Source | null>(null);
  if (sources.length === 0) return null;
  return (
    <>
      <ul className="flex flex-wrap gap-2" aria-label="Sources">
        {sources.map((source) => {
          const Icon = source.office ? Building2 : FileText;
          return (
            <li key={`${source.title}-${source.office ?? ""}`}>
              <button
                type="button"
                onClick={() => setOpen(source)}
                className="inline-flex min-h-8 max-w-64 items-center gap-1.5 rounded-(--radius-pill) bg-surface-2 px-3 py-1 text-xs text-accent hover:bg-surface-teal"
              >
                <Icon size={14} strokeWidth={1.75} aria-hidden="true" className="shrink-0" />
                <span className="truncate">{source.title}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {open && (
        <Sheet title="Source" onClose={() => setOpen(null)}>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted">Title</dt>
            <dd>{open.title}</dd>
            {open.office && (
              <>
                <dt className="text-muted">Office</dt>
                <dd>{open.office}</dd>
              </>
            )}
            <dt className="text-muted">Last verified</dt>
            <dd>
              {formatDate(open.last_verified) ?? "Not stated"}
              {open.expired && <span className="ms-2 text-warning">(may be outdated)</span>}
            </dd>
          </dl>
          {open.url && (
            <a
              href={open.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-flex min-h-11 items-center text-sm text-accent underline"
            >
              Open the source page
            </a>
          )}
        </Sheet>
      )}
    </>
  );
}
