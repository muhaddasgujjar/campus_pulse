"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, CELL, Dialog, EmptyState, Field, Input, Loading, Notice, PageHeader, ROW, Select, Table } from "@/components/admin/ui";
import { adminApi, type AuditPage, type AuditRow } from "@/lib/admin/api";

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Audit log (DESIGN.md 6.2.10, ADM-2): every write, filterable, with the JSON diff. */
export default function AuditLogPage() {
  const [filters, setFilters] = useState({ actor: "", action: "", table: "", since: "", until: "" });
  const [page, setPage] = useState<AuditPage | null>(null);
  const [open, setOpen] = useState<AuditRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    adminApi
      .audit(filters)
      .then(setPage)
      .catch((e: Error) => setError(e.message));
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => setFilters({ ...filters, [key]: e.target.value });

  return (
    <>
      <PageHeader title="Audit log" />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label="Actor" htmlFor="a-actor">
          <Input id="a-actor" placeholder="email or cli" value={filters.actor} onChange={set("actor")} />
        </Field>
        <Field label="Action" htmlFor="a-action">
          <Select id="a-action" value={filters.action} onChange={set("action")}>
            <option value="">Any</option>
            {page?.actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Table" htmlFor="a-table">
          <Select id="a-table" value={filters.table} onChange={set("table")}>
            <option value="">Any</option>
            {page?.tables.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="From" htmlFor="a-since">
          <Input id="a-since" type="date" value={filters.since} onChange={set("since")} />
        </Field>
        <Field label="To" htmlFor="a-until">
          <Input id="a-until" type="date" value={filters.until} onChange={set("until")} />
        </Field>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {page === null ? (
        <Loading />
      ) : page.items.length === 0 ? (
        <EmptyState text="No actions match these filters." />
      ) : (
        <Table label="Audit log" head={["When", "Actor", "Action", "Table", ""]}>
          {page.items.map((row) => (
            <tr key={row.id} className={ROW}>
              <td className={`${CELL} whitespace-nowrap`}>{when(row.created_at)}</td>
              <td className={CELL}>{row.actor_label ?? "—"}</td>
              <td className={CELL}>{row.action}</td>
              <td className={CELL}>{row.table_name}</td>
              <td className={`${CELL} text-end`}>
                <Button tone="ghost" onClick={() => setOpen(row)}>
                  Details
                </Button>
              </td>
            </tr>
          ))}
        </Table>
      )}
      {open ? (
        <Dialog title={`${open.action} · ${open.table_name}`} onClose={() => setOpen(null)} side>
          <dl className="mb-4 grid grid-cols-[6rem_1fr] gap-2 text-sm">
            <dt className="text-muted">When</dt>
            <dd>{when(open.created_at)}</dd>
            <dt className="text-muted">Actor</dt>
            <dd>{open.actor_label}</dd>
            <dt className="text-muted">Row</dt>
            <dd className="break-all">{open.row_id ?? "—"}</dd>
          </dl>
          <pre className="overflow-x-auto rounded-(--radius-sm) bg-surface-2 p-3 text-xs">{JSON.stringify(open.diff, null, 2)}</pre>
        </Dialog>
      ) : null}
    </>
  );
}
