"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAdmin } from "@/components/admin/AdminShell";
import {
  Button,
  CELL,
  Confirm,
  EmptyState,
  Expiry,
  Input,
  Loading,
  Notice,
  ROW,
  Select,
  StatusChip,
  Table,
  todayIso,
} from "@/components/admin/ui";
import { adminApi, type Entry, type Status } from "@/lib/admin/api";

/** Knowledge entries: filters, status chips, expiry warnings, submit and archive. */
export function KnowledgeTab() {
  const { nameOf } = useAdmin();
  const [rows, setRows] = useState<Entry[] | null>(null);
  const [status, setStatus] = useState<Status | "">("");
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [archiving, setArchiving] = useState<Entry | null>(null);
  const today = todayIso();

  const load = useCallback(() => {
    adminApi
      .entries({ status, q })
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [status, q]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  async function act(run: () => Promise<unknown>, message: string) {
    setError(null);
    setDone(null);
    try {
      await run();
      setDone(message);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <div className="relative min-w-60 flex-1">
          <Search size={16} className="absolute start-3 top-3.5 text-muted" aria-hidden="true" />
          <Input aria-label="Search entries" placeholder="Search title or answer" value={q} onChange={(e) => setQ(e.target.value)} className="ps-9" />
        </div>
        <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value as Status | "")} className="w-40">
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="archived">Archived</option>
        </Select>
        <Link href="/admin/content/kb/new" className="inline-flex min-h-11 items-center gap-2 rounded-(--radius-sm) bg-primary px-4 text-sm font-semibold text-on-primary hover:bg-primary-hover">
          <Plus size={16} aria-hidden="true" /> New entry
        </Link>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {done ? <Notice tone="success">{done}</Notice> : null}
      {rows === null ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState
          text={q || status ? "No entries match these filters." : "No entries yet. Add the first one."}
        />
      ) : (
        <Table label="Knowledge entries" head={["Title", "Category", "Owner", "Status", "Expires", ""]}>
          {rows.map((e) => (
            <tr key={e.id} className={ROW}>
              <td className={CELL}>
                <Link href={`/admin/content/kb/${e.id}`} className="font-medium hover:text-accent">
                  {e.title}
                </Link>
                {e.rejected_reason ? <p className="text-xs text-danger">Returned: {e.rejected_reason}</p> : null}
              </td>
              <td className={CELL}>{e.category}</td>
              <td className={`${CELL} text-muted`}>
                {nameOf("office", e.office_id) ?? nameOf("department", e.department_id) ?? e.owner_name ?? "—"}
              </td>
              <td className={CELL}>
                <StatusChip status={e.status} />
              </td>
              <td className={CELL}>
                <Expiry iso={e.expires_at} today={today} />
              </td>
              <td className={`${CELL} text-end whitespace-nowrap`}>
                {e.can_edit && e.status === "draft" ? (
                  <Button tone="ghost" onClick={() => act(() => adminApi.submitEntry(e.id), `"${e.title}" sent for approval.`)}>
                    Submit
                  </Button>
                ) : null}
                {e.can_edit && e.status !== "archived" ? (
                  <Button tone="ghost" onClick={() => setArchiving(e)}>
                    Archive
                  </Button>
                ) : null}
              </td>
            </tr>
          ))}
        </Table>
      )}
      {archiving ? (
        <Confirm
          title="Archive this entry?"
          body={`"${archiving.title}" will stop being used by the chat. The history is kept.`}
          confirmLabel="Archive"
          onCancel={() => setArchiving(null)}
          onConfirm={() => {
            const entry = archiving;
            setArchiving(null);
            void act(() => adminApi.archiveEntry(entry.id), `"${entry.title}" archived.`);
          }}
        />
      ) : null}
    </>
  );
}
