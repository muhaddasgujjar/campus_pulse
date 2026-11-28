"use client";

import { Pencil, UserPlus } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { useAdmin } from "@/components/admin/AdminShell";
import { Button, CELL, Confirm, Dialog, Field, Input, Loading, Notice, PageHeader, ROW, Select, Table } from "@/components/admin/ui";
import { adminApi, type StaffUser } from "@/lib/admin/api";

function InviteDialog({ onClose, onDone }: { onClose: () => void; onDone: (u: StaffUser) => void }) {
  const { lookups } = useAdmin();
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "staff" as "staff" | "admin",
    department_id: "",
    office_id: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(
        await adminApi.createUser({
          ...form,
          department_id: form.department_id || null,
          office_id: form.office_id || null,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Dialog title="Add a staff account" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Full name" htmlFor="u-name" required>
          <Input id="u-name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
        </Field>
        <Field label="Email" htmlFor="u-email" required>
          <Input id="u-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </Field>
        <Field
          label="Temporary password"
          htmlFor="u-password"
          required
          hint="At least 10 characters. Give it to the person yourself; no email is sent."
        >
          <Input id="u-password" type="text" autoComplete="off" minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        </Field>
        <Field label="Role" htmlFor="u-role">
          <Select id="u-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as "staff" | "admin" })}>
            <option value="staff">Staff (edits their office or department)</option>
            <option value="admin">Admin (approves, manages users)</option>
          </Select>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Office" htmlFor="u-office">
            <Select id="u-office" value={form.office_id} onChange={(e) => setForm({ ...form, office_id: e.target.value })}>
              <option value="">None</option>
              {lookups.offices.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Department" htmlFor="u-dept">
            <Select id="u-dept" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
              <option value="">None</option>
              {lookups.departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" tone="primary" disabled={busy}>
            Create account
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function EditDialog({ user, isSelf, onClose, onDone }: { user: StaffUser; isSelf: boolean; onClose: () => void; onDone: (u: StaffUser) => void }) {
  const { lookups } = useAdmin();
  const [form, setForm] = useState({
    full_name: user.full_name ?? "",
    role: user.role === "admin" ? "admin" : "staff",
    department_id: user.department_id ?? "",
    office_id: user.office_id ?? "",
  } as { full_name: string; role: "staff" | "admin"; department_id: string; office_id: string });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(
        await adminApi.updateUser(user.id, {
          full_name: form.full_name.trim(),
          ...(isSelf ? {} : { role: form.role }),
          department_id: form.department_id || null,
          office_id: form.office_id || null,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Edit ${user.email}`} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Full name" htmlFor="e-name" required>
          <Input id="e-name" value={form.full_name} minLength={2} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
        </Field>
        <Field label="Role" htmlFor="e-role" hint={isSelf ? "You can't change your own role." : "Takes effect on their next page load."}>
          <Select id="e-role" value={form.role} disabled={isSelf} onChange={(e) => setForm({ ...form, role: e.target.value as "staff" | "admin" })}>
            <option value="staff">Staff (edits their office or department)</option>
            <option value="admin">Admin (approves, manages users)</option>
          </Select>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Office" htmlFor="e-office">
            <Select id="e-office" value={form.office_id} onChange={(e) => setForm({ ...form, office_id: e.target.value })}>
              <option value="">None</option>
              {lookups.offices.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Department" htmlFor="e-dept">
            <Select id="e-dept" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
              <option value="">None</option>
              {lookups.departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" tone="primary" disabled={busy}>
            Save changes
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/** Users (DESIGN.md 6.2.9, ADM-4): staff and admin accounts, role, scope, active toggle. */
export default function UsersPage() {
  const { me, nameOf } = useAdmin();
  const [rows, setRows] = useState<StaffUser[] | null>(null);
  const [inviting, setInviting] = useState(false);
  const [editing, setEditing] = useState<StaffUser | null>(null);
  const [deactivating, setDeactivating] = useState<StaffUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(() => {
    adminApi
      .users()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function setActive(user: StaffUser, active: boolean) {
    setError(null);
    try {
      await adminApi.updateUser(user.id, { is_active: active });
      setDone(`${user.email} ${active ? "can sign in again" : "can no longer sign in"}.`);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <PageHeader title="Users">
        <Button tone="primary" onClick={() => setInviting(true)}>
          <UserPlus size={16} aria-hidden="true" /> Add staff
        </Button>
      </PageHeader>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {done ? <Notice tone="success">{done}</Notice> : null}
      {rows === null ? (
        <Loading />
      ) : (
        <Table label="Staff accounts" head={["Name", "Email", "Role", "Office or department", "Active", ""]}>
          {rows.map((u) => (
            <tr key={u.id} className={ROW}>
              <td className={CELL}>{u.full_name ?? "—"}</td>
              <td className={CELL}>{u.email}</td>
              <td className={CELL}>{u.role === "admin" ? "Admin" : "Staff"}</td>
              <td className={`${CELL} text-muted`}>{nameOf("office", u.office_id) ?? nameOf("department", u.department_id) ?? "—"}</td>
              <td className={CELL}>
                <label className="inline-flex min-h-11 cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    role="switch"
                    checked={u.is_active}
                    disabled={u.id === me.id}
                    onChange={(e) => (e.target.checked ? void setActive(u, true) : setDeactivating(u))}
                    className="size-5 accent-(--primary)"
                  />
                  <span className="text-sm">{u.is_active ? "Active" : "Inactive"}</span>
                </label>
              </td>
              <td className={CELL}>
                <Button tone="ghost" aria-label={`Edit ${u.email}`} onClick={() => setEditing(u)}>
                  <Pencil size={16} aria-hidden="true" /> Edit
                </Button>
              </td>
            </tr>
          ))}
        </Table>
      )}
      {inviting ? (
        <InviteDialog
          onClose={() => setInviting(false)}
          onDone={(u) => {
            setInviting(false);
            setDone(`Account created for ${u.email}. Share the temporary password with them directly.`);
            load();
          }}
        />
      ) : null}
      {editing ? (
        <EditDialog
          user={editing}
          isSelf={editing.id === me.id}
          onClose={() => setEditing(null)}
          onDone={(u) => {
            setEditing(null);
            setDone(`Saved ${u.email}.`);
            load();
          }}
        />
      ) : null}
      {deactivating ? (
        <Confirm
          title="Deactivate this account?"
          body={`${deactivating.email} will be signed out and can't sign in until reactivated. Their content stays.`}
          confirmLabel="Deactivate"
          onCancel={() => setDeactivating(null)}
          onConfirm={() => {
            const user = deactivating;
            setDeactivating(null);
            void setActive(user, false);
          }}
        />
      ) : null}
    </>
  );
}
