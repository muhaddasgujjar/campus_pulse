"use client";

import { Check, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useAdmin } from "@/components/admin/AdminShell";
import { Button, Card, EmptyState, Field, Loading, Notice, PageHeader, TextArea } from "@/components/admin/ui";
import { adminApi, type Approval } from "@/lib/admin/api";
import { formatDate } from "@/lib/chat/format";

const HIDDEN = new Set(["id", "institution_id", "status", "version", "updated_at", "created_at", "owner_id", "rejected_reason"]);

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Side-by-side diff: changed fields are marked with a label, not color alone. */
function Diff({ item }: { item: Approval }) {
  const { nameOf } = useAdmin();
  const keys = [...new Set([...Object.keys(item.current ?? {}), ...Object.keys(item.proposed)])].filter((k) => !HIDDEN.has(k));
  const name = (key: string, value: unknown) =>
    key === "office_id" ? (nameOf("office", value as string) ?? show(value)) : key === "department_id" ? (nameOf("department", value as string) ?? show(value)) : show(value);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-160 border-collapse text-sm">
        <thead className="text-xs text-muted uppercase">
          <tr>
            <th scope="col" className="w-40 px-2 py-2 text-start">Field</th>
            <th scope="col" className="px-2 py-2 text-start">{item.current ? "Current (live)" : "Current"}</th>
            <th scope="col" className="px-2 py-2 text-start">Proposed</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const before = item.current?.[key];
            const after = item.proposed[key];
            const changed = item.current !== null && show(before) !== show(after);
            return (
              <tr key={key} className={`border-t border-border align-top ${changed ? "bg-surface-teal" : ""}`}>
                <th scope="row" className="px-2 py-2 text-start font-medium">
                  {key.replace(/_id$/, "").replaceAll("_", " ")}
                  {changed ? (
                    <>
                      {" "}
                      <span className="ms-1 text-xs font-semibold text-warning">changed</span>
                    </>
                  ) : null}
                </th>
                <td className="px-2 py-2 whitespace-pre-wrap text-muted">{item.current ? name(key, before) : key === "title" ? "New content" : ""}</td>
                <td className="px-2 py-2 whitespace-pre-wrap">{name(key, after)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Approvals (DESIGN.md 6.2.7, DATA-4): admins approve or reject; staff see the queue only. */
export default function ApprovalsPage() {
  const { can } = useAdmin();
  const approver = can("approve_content");
  const [items, setItems] = useState<Approval[] | null>(null);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(() => {
    adminApi
      .approvals()
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function decide(item: Approval, approve: boolean) {
    const comment = (comments[item.id] ?? "").trim();
    if (!approve && !comment) {
      setError("Write a reason so the owner knows what to fix.");
      return;
    }
    setBusy(item.id);
    setError(null);
    setDone(null);
    try {
      if (approve) {
        const result = await adminApi.approve(item.kind, item.id, comment);
        setDone(`"${item.title}" approved and live in the chat (${result.chunks} search chunks).`);
      } else {
        await adminApi.reject(item.kind, item.id, comment);
        setDone(`"${item.title}" returned to its owner.`);
      }
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Approvals" />
      {!approver ? <Notice tone="info">Only an admin can approve. You can see what is waiting.</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {done ? <Notice tone="success">{done}</Notice> : null}
      {items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState text="Nothing is waiting for approval." />
      ) : (
        <div className="flex flex-col gap-4">
          {items.map((item) => (
            <Card key={`${item.kind}-${item.id}`}>
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-lg font-semibold">{item.title}</h2>
                <p className="text-xs text-muted">
                  {item.kind === "kb" ? "Knowledge entry" : "Document"} · {item.category} · submitted {formatDate(item.submitted_at)}
                  {item.current ? " · edit of live content" : " · new"}
                </p>
              </div>
              <Diff item={item} />
              {approver ? (
                <div className="mt-4 flex flex-col gap-3">
                  <Field label="Comment" htmlFor={`c-${item.id}`} hint="Required when rejecting.">
                    <TextArea
                      id={`c-${item.id}`}
                      rows={2}
                      value={comments[item.id] ?? ""}
                      onChange={(e) => setComments({ ...comments, [item.id]: e.target.value })}
                    />
                  </Field>
                  <div className="flex justify-end gap-2">
                    <Button tone="danger" disabled={busy === item.id} onClick={() => void decide(item, false)}>
                      <X size={16} aria-hidden="true" /> Reject
                    </Button>
                    <Button tone="primary" disabled={busy === item.id} onClick={() => void decide(item, true)}>
                      <Check size={16} aria-hidden="true" /> Approve
                    </Button>
                  </div>
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
