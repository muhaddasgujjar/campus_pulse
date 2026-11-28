"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Sheet } from "@/components/chat/Sheet";
import { accountApi, type ProfileInput } from "@/lib/account";
import { getAccessToken, signInStudent, signOut } from "@/lib/auth";

const CONTROL =
  "min-h-11 w-full rounded-(--radius-sm) border border-border bg-surface-2 px-3 text-sm text-text focus:border-border-teal";

const EMPTY: ProfileInput = { program: null, semester: null, section: null, language_pref: null };

/**
 * Student profile (AUTH-4): program, semester and section. Today the program filters the
 * deadlines card; the chat does not read the profile yet. No email or name is asked for. "Delete my data" (PRIV-2) removes the student's chats
 * and profile details.
 */
export function ProfileSheet({
  onClose,
  onSaved,
  onDeleted,
}: {
  onClose: () => void;
  onSaved: (profile: ProfileInput, token: string | null) => void;
  onDeleted: () => void;
}) {
  const [form, setForm] = useState<ProfileInput>(EMPTY);
  const [hasAccount, setHasAccount] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getAccessToken().then(async (token) => {
      if (!token) return;
      const me = await accountApi.me().catch(() => null);
      if (!me) return;
      setHasAccount(true);
      setForm({ program: me.program, semester: me.semester, section: me.section, language_pref: me.language_pref });
    });
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const problem = await signInStudent();
    if (problem) {
      setMessage({ tone: "error", text: problem });
      setBusy(false);
      return;
    }
    try {
      await accountApi.saveProfile(form);
      setHasAccount(true);
      onSaved(form, await getAccessToken());
      setMessage({ tone: "ok", text: "Saved. Deadlines now show your program first." });
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function erase() {
    setBusy(true);
    try {
      await accountApi.deleteMyData();
      await signOut();
      onDeleted();
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <Sheet title="Your profile" onClose={onClose}>
      {confirming ? (
        <div className="flex flex-col gap-4">
          <p className="text-sm">
            This deletes your chats and profile details from Campus Pulse. It can&apos;t be undone.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setConfirming(false)} className="min-h-11 rounded-(--radius-sm) border border-border px-4 text-sm">
              Cancel
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void erase()}
              className="min-h-11 rounded-(--radius-sm) border border-danger px-4 text-sm font-semibold text-danger disabled:opacity-50"
            >
              Delete my data
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={save} className="flex flex-col gap-4">
          <p className="text-sm text-muted">Optional. Used to show deadlines for your program. No name or email needed.</p>
          <div className="grid grid-cols-3 gap-3">
            <label className="col-span-3 flex flex-col gap-1 text-sm sm:col-span-1">
              Program
              <input className={CONTROL} placeholder="BSCS" maxLength={40} value={form.program ?? ""} onChange={(e) => setForm({ ...form, program: e.target.value || null })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Semester
              <select className={CONTROL} value={form.semester ?? ""} onChange={(e) => setForm({ ...form, semester: e.target.value ? Number(e.target.value) : null })}>
                <option value="">—</option>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Section
              <input className={CONTROL} placeholder="A" maxLength={10} value={form.section ?? ""} onChange={(e) => setForm({ ...form, section: e.target.value || null })} />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            Language
            <select className={CONTROL} value={form.language_pref ?? ""} onChange={(e) => setForm({ ...form, language_pref: (e.target.value || null) as ProfileInput["language_pref"] })}>
              <option value="">Same as my question</option>
              <option value="en">English</option>
              <option value="ur">اردو (Urdu)</option>
            </select>
          </label>
          {message ? (
            <p role={message.tone === "error" ? "alert" : "status"} className={`text-sm ${message.tone === "error" ? "text-danger" : "text-success"}`}>
              {message.text}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center justify-between gap-2">
            {hasAccount ? (
              <button type="button" onClick={() => setConfirming(true)} className="min-h-11 text-sm text-danger underline">
                Delete my data
              </button>
            ) : (
              <span />
            )}
            <button
              type="submit"
              disabled={busy}
              className="min-h-11 rounded-(--radius-sm) bg-primary px-5 text-sm font-semibold text-on-primary hover:bg-primary-hover disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </form>
      )}
    </Sheet>
  );
}
