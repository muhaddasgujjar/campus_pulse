"use client";

import { Plus, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { Button, Card, Field, Input, Loading, Notice, PageHeader, TextArea } from "@/components/admin/ui";
import { adminApi, type InstitutionSettings } from "@/lib/admin/api";

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

/** Settings (DESIGN.md 6.2.11, ADP-2): institution text, starter questions, contacts. */
export default function SettingsPage() {
  const [form, setForm] = useState<InstitutionSettings | null>(null);
  const [starters, setStarters] = useState("");
  const [allowlist, setAllowlist] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    adminApi
      .settings()
      .then((s) => {
        setForm(s);
        setStarters(s.starter_questions.join("\n"));
        setAllowlist(s.live_fetch_allowlist.join("\n"));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (!form) return error ? <Notice tone="error">{error}</Notice> : <Loading />;

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const saved = await adminApi.saveSettings({
        ...form,
        starter_questions: lines(starters),
        live_fetch_allowlist: lines(allowlist),
        contacts: form.contacts.filter((c) => c.name.trim()),
      });
      setForm(saved);
      setDone(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const contact = (i: number, key: "name" | "phone" | "email", value: string) =>
    setForm({ ...form, contacts: form.contacts.map((c, j) => (j === i ? { ...c, [key]: value || null } : c)) });

  return (
    <>
      <PageHeader title="Settings" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {done ? <Notice tone="success">Saved. The chat uses the new text right away.</Notice> : null}
      <form onSubmit={save} className="flex max-w-3xl flex-col gap-4">
        <Card className="flex flex-col gap-4">
          <h2 className="font-semibold">Institution</h2>
          <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
            <Field label="Name" htmlFor="s-name" required>
              <Input id="s-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </Field>
            <Field label="Short name" htmlFor="s-short">
              <Input id="s-short" value={form.short_name ?? ""} onChange={(e) => setForm({ ...form, short_name: e.target.value || null })} />
            </Field>
          </div>
          <Field label="Disclaimer" htmlFor="s-disclaimer" required hint="Shown under every chat.">
            <TextArea id="s-disclaimer" rows={3} value={form.disclaimer} onChange={(e) => setForm({ ...form, disclaimer: e.target.value })} required />
          </Field>
          <Field label="Office for questions the chat can't answer" htmlFor="s-fallback">
            <Input id="s-fallback" value={form.fallback_office ?? ""} onChange={(e) => setForm({ ...form, fallback_office: e.target.value || null })} />
          </Field>
        </Card>
        <Card className="flex flex-col gap-4">
          <h2 className="font-semibold">Chat</h2>
          <Field label="Starter questions" htmlFor="s-starters" hint="One per line, up to 6.">
            <TextArea id="s-starters" rows={6} value={starters} onChange={(e) => setStarters(e.target.value)} />
          </Field>
          <Field label="Live-fetch sources" htmlFor="s-allow" hint="Allowed website hosts, one per line, e.g. lgu.edu.pk">
            <TextArea id="s-allow" rows={3} value={allowlist} onChange={(e) => setAllowlist(e.target.value)} />
          </Field>
        </Card>
        <Card className="flex flex-col gap-3">
          <h2 className="font-semibold">Contacts</h2>
          {form.contacts.map((c, i) => (
            <div key={i} className="grid items-end gap-2 sm:grid-cols-[1fr_10rem_1fr_auto]">
              <Field label="Name" htmlFor={`c-name-${i}`}>
                <Input id={`c-name-${i}`} value={c.name} onChange={(e) => contact(i, "name", e.target.value)} />
              </Field>
              <Field label="Phone" htmlFor={`c-phone-${i}`}>
                <Input id={`c-phone-${i}`} value={c.phone ?? ""} onChange={(e) => contact(i, "phone", e.target.value)} />
              </Field>
              <Field label="Email" htmlFor={`c-email-${i}`}>
                <Input id={`c-email-${i}`} value={c.email ?? ""} onChange={(e) => contact(i, "email", e.target.value)} />
              </Field>
              <Button tone="ghost" aria-label={`Remove ${c.name || "contact"}`} onClick={() => setForm({ ...form, contacts: form.contacts.filter((_, j) => j !== i) })}>
                <Trash2 size={16} aria-hidden="true" />
              </Button>
            </div>
          ))}
          <div>
            <Button onClick={() => setForm({ ...form, contacts: [...form.contacts, { name: "", phone: null, email: null }] })}>
              <Plus size={16} aria-hidden="true" /> Add contact
            </Button>
          </div>
        </Card>
        <div>
          <Button type="submit" tone="primary" disabled={busy}>
            Save settings
          </Button>
        </div>
      </form>
    </>
  );
}
