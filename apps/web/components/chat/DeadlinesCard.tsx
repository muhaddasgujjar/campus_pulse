"use client";

import { CalendarClock } from "lucide-react";
import { useEffect, useState } from "react";

import { accountApi, type Deadline } from "@/lib/account";
import { formatDate } from "@/lib/chat/format";

function left(days: number): string {
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

/**
 * Upcoming deadlines (CHAT-7) from staff-verified key dates. Shown on the welcome screen;
 * filtered by the student's program when they saved one. Hidden when nothing is coming up.
 */
export function DeadlinesCard({ program, onAsk }: { program: string | null; onAsk: (q: string) => void }) {
  const [items, setItems] = useState<Deadline[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    accountApi
      .deadlines(program)
      .then((rows) => !cancelled && setItems(rows))
      .catch(() => !cancelled && setItems([]));
    return () => {
      cancelled = true;
    };
  }, [program]);

  if (!items || items.length === 0) return null;
  return (
    <section
      aria-labelledby="deadlines-title"
      className="w-full max-w-md rounded-(--radius-md) border border-border-teal bg-surface-teal p-4 text-start"
    >
      <h2 id="deadlines-title" className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <CalendarClock size={16} strokeWidth={1.75} className="text-accent" aria-hidden="true" />
        Upcoming deadlines{program ? ` for ${program}` : ""}
      </h2>
      <ul className="flex flex-col divide-y divide-border">
        {items.map((d) => (
          <li key={d.id}>
            <button
              type="button"
              onClick={() => onAsk(`Tell me about: ${d.title}`)}
              className="flex min-h-11 w-full items-center justify-between gap-3 py-2 text-start text-sm hover:text-accent"
            >
              <span className="min-w-0">
                <span className="block truncate">{d.title}</span>
                {d.office_name ? <span className="text-xs text-muted">{d.office_name}</span> : null}
              </span>
              <span className={`shrink-0 text-end text-xs ${d.days_left <= 3 ? "text-warning" : "text-muted"}`}>
                {formatDate(d.date)}
                <span className="block">{left(d.days_left)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
