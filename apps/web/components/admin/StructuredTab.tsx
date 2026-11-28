"use client";

import { FileSpreadsheet, Plus, Search } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { useAdmin } from "@/components/admin/AdminShell";
import {
  Button,
  CELL,
  Confirm,
  Dialog,
  EmptyState,
  Field,
  Input,
  Loading,
  Notice,
  ROW,
  Select,
  Table,
  TextArea,
  todayIso,
} from "@/components/admin/ui";
import { adminApi, type ImportResult, type TableRow } from "@/lib/admin/api";
import { cellText, columnLabel, type FieldSpec, type TableSpec, toBody, toValues } from "@/lib/admin/tables";

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: FieldSpec;
  value: string;
  onChange: (v: string) => void;
}) {
  const { me, lookups } = useAdmin();
  const id = `f-${field.name}`;
  let control;
  if (field.kind === "textarea") {
    control = <TextArea id={id} rows={3} value={value} onChange={(e) => onChange(e.target.value)} />;
  } else if (field.kind === "select" || field.kind === "department") {
    const options =
      field.kind === "department"
        ? lookups.departments
            .filter((d) => me.role === "admin" || d.id === me.department_id)
            .map((d) => ({ value: d.id, label: d.name }))
        : (field.options ?? []);
    control = (
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} required={field.required}>
        {!field.required ? <option value="">None</option> : <option value="" disabled>Choose…</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    );
  } else {
    const type = field.kind === "list" ? "text" : field.kind;
    control = (
      <Input
        id={id}
        type={type}
        step={field.kind === "number" ? "any" : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={field.required}
      />
    );
  }
  return (
    <Field label={field.label} htmlFor={id} required={field.required} hint={field.hint}>
      {control}
    </Field>
  );
}

function RowDialog({
  spec,
  row,
  onClose,
  onSaved,
}: {
  spec: TableSpec;
  row: TableRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial = toValues(spec, row);
    if (!row) initial.last_verified = todayIso();
    return initial;
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = toBody(spec, values);
      if (row) await adminApi.updateRow(spec.name, row.id, body);
      else await adminApi.createRow(spec.name, body);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Dialog title={row ? `Edit ${spec.singular}` : `Add ${spec.singular}`} onClose={onClose} side>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {spec.fields.map((field) => (
          <FieldInput
            key={field.name}
            field={field}
            value={values[field.name] ?? ""}
            onChange={(v) => setValues((current) => ({ ...current, [field.name]: v }))}
          />
        ))}
        {error ? <Notice tone="error">{error}</Notice> : null}
        <p className="text-xs text-muted">Changes reach the chat at once and are recorded in the audit log.</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" tone="primary" disabled={busy}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/** Timetable or faculty CSV import (DESIGN.md 6.2.6): validate every row first, then confirm. */
function ImportDialog({ kind, onClose, onDone }: { kind: "timetable" | "faculty"; onClose: () => void; onDone: (r: ImportResult) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function validate(picked: File | undefined) {
    setCheck(null);
    setError(null);
    if (!picked) return;
    setFile(picked);
    setBusy(true);
    try {
      setCheck(await adminApi.importCsv(kind, picked, true));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!file) return;
    setBusy(true);
    try {
      onDone(await adminApi.importCsv(kind, file, false));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Import ${kind} CSV`} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <label className="flex cursor-pointer flex-col items-center gap-2 rounded-(--radius-md) border-2 border-dashed border-border px-4 py-6 text-center text-sm">
          <FileSpreadsheet size={28} className="text-accent" aria-hidden="true" />
          {file ? file.name : "Choose a CSV file (UTF-8)"}
          <span className="text-xs text-muted">Use the same columns as seed/lgu/{kind}.csv</span>
          <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => void validate(e.target.files?.[0])} />
        </label>
        {busy && !check ? <Loading label="Checking every row…" /> : null}
        {check ? (
          check.errors.length ? (
            <div role="alert">
              <p className="mb-2 text-sm font-semibold text-danger">
                {check.errors.length} problem{check.errors.length === 1 ? "" : "s"} found. Nothing was imported. Fix the file and choose it again.
              </p>
              <ul className="max-h-60 overflow-y-auto rounded-(--radius-sm) border border-danger bg-surface-2 p-3 text-xs">
                {check.errors.map((e) => (
                  <li key={e} className="py-0.5">
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Notice tone="success">All {check.valid_rows} rows are valid.</Notice>
          )
        ) : null}
        {error ? <Notice tone="error">{error}</Notice> : null}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button tone="primary" disabled={!check || check.errors.length > 0 || busy} onClick={() => void confirm()}>
            Import {check?.valid_rows ?? ""} rows
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export function StructuredTab({ spec }: { spec: TableSpec }) {
  const { me } = useAdmin();
  const [rows, setRows] = useState<TableRow[] | null>(null);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<TableRow | "new" | null>(null);
  const [deleting, setDeleting] = useState<TableRow | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  // Timetable rows belong to a department (AUTH-3); faculty imports are admin only.
  const canImport =
    me.role === "admin" || (spec.name === "timetable" && me.department_id !== null);

  const load = useCallback(() => {
    adminApi
      .table(spec.name, q)
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [spec.name, q]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <div className="relative min-w-60 flex-1">
          <Search size={16} className="absolute start-3 top-3.5 text-muted" aria-hidden="true" />
          <Input aria-label={`Search ${spec.label}`} placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} className="ps-9" />
        </div>
        {canImport ? (
          <Button onClick={() => setImporting(true)}>
            <FileSpreadsheet size={16} aria-hidden="true" /> Import CSV
          </Button>
        ) : null}
        <Button tone="primary" onClick={() => setEditing("new")}>
          <Plus size={16} aria-hidden="true" /> Add {spec.singular}
        </Button>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {done ? <Notice tone="success">{done}</Notice> : null}
      {rows === null ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState text={q ? "Nothing matches this search." : `No ${spec.label.toLowerCase()} yet. Add the first one.`} />
      ) : (
        <Table label={spec.label} head={[...spec.columns.map((c) => columnLabel(spec, c)), ""]}>
          {rows.map((row) => (
            <tr key={row.id} className={ROW}>
              {spec.columns.map((c) => (
                <td key={c} className={CELL}>
                  {cellText(c, row[c])}
                </td>
              ))}
              <td className={`${CELL} text-end whitespace-nowrap`}>
                {row.can_edit ? (
                  <>
                    <Button tone="ghost" onClick={() => setEditing(row)}>
                      Edit
                    </Button>
                    <Button tone="ghost" onClick={() => setDeleting(row)}>
                      Delete
                    </Button>
                  </>
                ) : (
                  <span className="text-xs text-muted">View only</span>
                )}
              </td>
            </tr>
          ))}
        </Table>
      )}
      {editing ? (
        <RowDialog
          spec={spec}
          row={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setDone("Saved.");
            load();
          }}
        />
      ) : null}
      {deleting ? (
        <Confirm
          title={`Delete this ${spec.singular}?`}
          body="The chat stops using it at once. The audit log keeps a copy."
          confirmLabel="Delete"
          onCancel={() => setDeleting(null)}
          onConfirm={() => {
            const row = deleting;
            setDeleting(null);
            adminApi
              .deleteRow(spec.name, row.id)
              .then(() => {
                setDone("Deleted.");
                load();
              })
              .catch((e: Error) => setError(e.message));
          }}
        />
      ) : null}
      {importing && (spec.name === "timetable" || spec.name === "faculty") ? (
        <ImportDialog
          kind={spec.name}
          onClose={() => setImporting(false)}
          onDone={(r) => {
            setImporting(false);
            setDone(`Imported: ${r.created} new, ${r.updated} updated, ${r.unchanged} unchanged.`);
            load();
          }}
        />
      ) : null}
    </>
  );
}
