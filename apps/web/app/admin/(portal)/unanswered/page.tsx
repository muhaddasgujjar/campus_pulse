"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, CELL, EmptyState, Loading, Notice, PageHeader, ROW, Select, Table } from "@/components/admin/ui";
import { adminApi, type Unanswered } from "@/lib/admin/api";
import { formatDate } from "@/lib/chat/format";

type View = "open" | "handled" | "ignored";

/** Unanswered questions (DESIGN.md 6.2.8, DATA-7): turn gaps into new entries. */
export default function UnansweredPage() {
  const [view, setView] = useState<View>("open");
  const [rows, setRows] = useState<Unanswered[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    adminApi
      .unanswered(view)
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [view]);
  useEffect(load, [load]);

  async function resolve(row: Unanswered, status: "handled" | "ignored") {
    try {
      await adminApi.resolveUnanswered(row.id, status);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <PageHeader title="Unanswered questions">
        <Select aria-label="Show" value={view} onChange={(e) => setView(e.target.value as View)} className="w-40">
          <option value="open">Open</option>
          <option value="handled">Handled</option>
          <option value="ignored">Ignored</option>
        </Select>
      </PageHeader>
      <p className="mb-4 text-sm text-muted">
        Questions the chat could not answer from verified data. Personal details were removed before saving.
      </p>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {rows === null ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState text={view === "open" ? "No open questions. The chat answered everything." : "Nothing here."} />
      ) : (
        <Table label="Unanswered questions" head={["Question", "Times asked", "Last seen", ""]}>
          {rows.map((row) => (
            <tr key={row.id} className={ROW}>
              <td className={CELL} dir="auto">
                {row.query}
                {row.reason ? <p className="text-xs text-muted">{row.reason}</p> : null}
              </td>
              <td className={`${CELL} tabular-nums`}>{row.count}</td>
              <td className={CELL}>{formatDate(row.last_seen)}</td>
              <td className={`${CELL} text-end whitespace-nowrap`}>
                {view === "open" ? (
                  <>
                    <Link
                      href={`/admin/content/kb/new?from=${row.id}&q=${encodeURIComponent(row.query)}`}
                      className="inline-flex min-h-11 items-center px-3 text-sm font-semibold text-accent"
                    >
                      Create entry
                    </Link>
                    <Button tone="ghost" onClick={() => void resolve(row, "handled")}>
                      Mark handled
                    </Button>
                    <Button tone="ghost" onClick={() => void resolve(row, "ignored")}>
                      Ignore
                    </Button>
                  </>
                ) : null}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
