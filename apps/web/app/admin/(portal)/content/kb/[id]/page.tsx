"use client";

import { ArrowLeft, BadgeCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, use, useEffect, useState } from "react";

import { useAdmin } from "@/components/admin/AdminShell";
import { ScopeFields } from "@/components/admin/ScopeFields";
import { Button, Card, Field, Input, Loading, Notice, PageHeader, Select, StatusChip, TextArea, todayIso } from "@/components/admin/ui";
import { adminApi, type Entry, type EntryInput } from "@/lib/admin/api";
import { formatDate } from "@/lib/chat/format";

const CATEGORIES = ["admission", "fees", "exams", "scholarships", "timetable", "faculty", "policies", "transport", "hostel", "general"];

function inAYear(iso: string): string {
  const d = new Date(iso);
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
}

function blank(me: { department_id: string | null; office_id: string | null }): EntryInput {
  const today = todayIso();
  return {
    title: "",
    question: null,
    answer: "",
    category: "general",
    language: "en",
    owner_name: null,
    department_id: me.department_id,
    office_id: me.office_id,
    last_verified: today,
    expires_at: inAYear(today),
    source_url: null,
  };
}

function fromEntry(e: Entry): EntryInput {
  return {
    title: e.title,
    question: e.question,
    answer: e.answer,
    category: e.category,
    language: e.language,
    owner_name: e.owner_name,
    department_id: e.department_id,
    office_id: e.office_id,
    last_verified: e.last_verified ?? todayIso(),
    expires_at: e.expires_at ?? inAYear(todayIso()),
    source_url: e.source_url,
  };
}

/** Entry editor (DESIGN.md 6.2.4): fields on the left, how the bot will cite it on the right. */
export default function EntryEditorPage(props: PageProps<"/admin/content/kb/[id]">) {
  const { id } = use(props.params);
  const query = use(props.searchParams);
  const question = typeof query.q === "string" ? query.q : null;
  const fromUnanswered = typeof query.from === "string" ? query.from : null;
  const isNew = id === "new";
  const router = useRouter();
  const { me, nameOf } = useAdmin();
  const [entry, setEntry] = useState<Entry | null>(null);
  const [form, setForm] = useState<EntryInput | null>(() =>
    isNew ? { ...blank(me), question, title: question?.slice(0, 120) ?? "" } : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isNew) return;
    adminApi
      .entry(id)
      .then((e) => {
        setEntry(e);
        setForm(fromEntry(e));
      })
      .catch((e: Error) => setError(e.message));
  }, [id, isNew]);

  if (error && !form) return <Notice tone="error">{error}</Notice>;
  if (!form) return <Loading />;

  const readOnly = entry !== null && (!entry.can_edit || entry.status === "archived");
  const set = (patch: Partial<EntryInput>) => setForm({ ...form, ...patch });
  const owner = form.owner_name || nameOf("office", form.office_id) || nameOf("department", form.department_id) || "LGU";

  async function save(submit: boolean, event?: FormEvent) {
    event?.preventDefault();
    if (!form) return;
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      if (isNew) {
        const created = await adminApi.createEntry({ ...form, submit, from_unanswered_id: fromUnanswered });
        router.replace(`/admin/content/kb/${created.id}`);
        return;
      }
      let updated = await adminApi.updateEntry(id, form);
      if (submit && updated.status === "draft") updated = await adminApi.submitEntry(id);
      setEntry(updated);
      setForm(fromEntry(updated));
      setSaved(updated.status === "pending" ? "Saved and sent for approval." : "Draft saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Link href="/admin/content" className="mb-3 inline-flex min-h-11 items-center gap-2 text-sm text-accent">
        <ArrowLeft size={16} aria-hidden="true" /> Content
      </Link>
      <PageHeader title={isNew ? "New knowledge entry" : "Edit entry"}>
        {entry ? <StatusChip status={entry.status} /> : null}
      </PageHeader>
      {entry?.status === "approved" && !readOnly ? (
        <Notice tone="info">This entry is live. Saving a change sends it back for approval; the chat stops using it until an admin approves the new version.</Notice>
      ) : null}
      {entry?.rejected_reason ? <Notice tone="error">Returned by an admin: {entry.rejected_reason}</Notice> : null}
      {readOnly ? <Notice tone="info">You can view this entry but not edit it (it belongs to another office or is archived).</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {saved ? <Notice tone="success">{saved}</Notice> : null}
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <form onSubmit={(e) => save(false, e)} className="flex flex-col gap-4">
          <fieldset disabled={readOnly || busy} className="flex flex-col gap-4">
            <Field label="Title" htmlFor="title" required>
              <Input id="title" value={form.title} onChange={(e) => set({ title: e.target.value })} maxLength={200} required />
            </Field>
            <Field label="Question students ask" htmlFor="question" hint="Optional. Helps the search match student wording.">
              <Input id="question" value={form.question ?? ""} onChange={(e) => set({ question: e.target.value || null })} />
            </Field>
            <Field label="Answer" htmlFor="answer" required hint="Lead with the answer. Include amounts with Rs and the fiscal year.">
              <TextArea id="answer" rows={8} value={form.answer} onChange={(e) => set({ answer: e.target.value })} required />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Category" htmlFor="category" required>
                <Select id="category" value={form.category} onChange={(e) => set({ category: e.target.value })}>
                  {[...new Set([...CATEGORIES, form.category])].map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Language" htmlFor="language">
                <Select id="language" value={form.language} onChange={(e) => set({ language: e.target.value as "en" | "ur" })}>
                  <option value="en">English</option>
                  <option value="ur">Urdu</option>
                </Select>
              </Field>
            </div>
            <ScopeFields
              idPrefix="entry"
              departmentId={form.department_id}
              officeId={form.office_id}
              onChange={(scope) => set(scope)}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Last verified" htmlFor="verified" required>
                <Input id="verified" type="date" value={form.last_verified} onChange={(e) => set({ last_verified: e.target.value })} required />
              </Field>
              <Field label="Expires" htmlFor="expires" required hint="When someone must check it again.">
                <Input id="expires" type="date" value={form.expires_at} onChange={(e) => set({ expires_at: e.target.value })} required />
              </Field>
            </div>
            <Field label="Owner name" htmlFor="owner" hint="Shown in the source line, e.g. Admission Office">
              <Input id="owner" value={form.owner_name ?? ""} onChange={(e) => set({ owner_name: e.target.value || null })} />
            </Field>
            <Field label="Source link" htmlFor="source">
              <Input id="source" type="url" value={form.source_url ?? ""} onChange={(e) => set({ source_url: e.target.value || null })} />
            </Field>
          </fieldset>
          {!readOnly ? (
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={busy}>
                Save draft
              </Button>
              <Button tone="primary" disabled={busy} onClick={() => void save(true)}>
                Submit for approval
              </Button>
            </div>
          ) : null}
        </form>
        <aside aria-label="Preview" className="lg:sticky lg:top-4 lg:self-start">
          <p className="mb-2 text-xs text-muted uppercase">How the chat will show it</p>
          <Card className="flex flex-col gap-3">
            {form.question ? <p className="ms-auto max-w-[85%] rounded-(--radius-md) bg-user-bubble px-3 py-2 text-sm text-on-user-bubble">{form.question}</p> : null}
            <div className="rounded-(--radius-md) bg-surface-2 px-3 py-2 text-sm whitespace-pre-wrap" dir="auto">
              {form.answer || <span className="text-muted">The answer appears here.</span>}
            </div>
            <p className="flex items-center gap-1 text-xs text-muted">
              <BadgeCheck size={14} className="text-success" aria-hidden="true" />
              Source: {form.title || "Untitled"} · {owner} · verified {formatDate(form.last_verified) ?? "—"}
            </p>
          </Card>
        </aside>
      </div>
    </>
  );
}
