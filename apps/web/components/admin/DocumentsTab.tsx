"use client";

import { FileUp, Upload } from "lucide-react";
import { type DragEvent, type FormEvent, useCallback, useEffect, useState } from "react";

import { useAdmin } from "@/components/admin/AdminShell";
import { ScopeFields } from "@/components/admin/ScopeFields";
import {
  Button,
  CELL,
  Confirm,
  Dialog,
  EmptyState,
  Expiry,
  Field,
  Input,
  Loading,
  Notice,
  ROW,
  StatusChip,
  Table,
  todayIso,
} from "@/components/admin/ui";
import { adminApi, type DocumentRow, type PdfPreview } from "@/lib/admin/api";

const MAX_MB = 10;

/** Document upload (DESIGN.md 6.2.5): drop a text PDF, see the extracted text, add metadata. */
function UploadDialog({ onClose, onDone }: { onClose: () => void; onDone: (title: string) => void }) {
  const { me } = useAdmin();
  const today = todayIso();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PdfPreview | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("policies");
  const [verified, setVerified] = useState(today);
  const [expires, setExpires] = useState(`${Number(today.slice(0, 4)) + 1}${today.slice(4)}`);
  const [scope, setScope] = useState({ department_id: me.department_id, office_id: me.office_id });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);

  async function choose(picked: File | undefined) {
    setError(null);
    setPreview(null);
    if (!picked) return;
    if (picked.type !== "application/pdf") return setError("Choose a PDF file.");
    if (picked.size > MAX_MB * 1024 * 1024) return setError(`The PDF is larger than ${MAX_MB} MB.`);
    setFile(picked);
    setTitle((t) => t || picked.name.replace(/\.pdf$/i, ""));
    setBusy(true);
    try {
      setPreview(await adminApi.previewPdf(picked));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const doc = await adminApi.uploadPdf(file, {
        title,
        category,
        last_verified: verified,
        expires_at: expires,
        department_id: scope.department_id,
        office_id: scope.office_id,
      });
      onDone(doc.title);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    void choose(event.dataTransfer.files[0]);
  };

  return (
    <Dialog title="Upload a PDF" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={drop}
          className={`flex cursor-pointer flex-col items-center gap-2 rounded-(--radius-md) border-2 border-dashed px-4 py-8 text-center text-sm ${
            over ? "border-primary bg-surface-teal" : "border-border"
          }`}
        >
          <FileUp size={28} className="text-accent" aria-hidden="true" />
          {file ? file.name : "Drop a PDF here or choose a file"}
          <span className="text-xs text-muted">Text PDFs only, up to {MAX_MB} MB. Scanned images can&apos;t be read.</span>
          <input type="file" accept="application/pdf" className="sr-only" onChange={(e) => void choose(e.target.files?.[0])} />
        </label>
        {preview ? (
          <div className="rounded-(--radius-sm) border border-border bg-surface-2 p-3 text-xs">
            <p className="mb-2 font-semibold">
              {preview.pages} pages · {preview.characters.toLocaleString()} characters · {preview.chunks} chunks for search
            </p>
            <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap text-muted">{preview.text_preview}</pre>
          </div>
        ) : null}
        <Field label="Title" htmlFor="doc-title" required>
          <Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3} />
        </Field>
        <Field label="Category" htmlFor="doc-category" required>
          <Input id="doc-category" value={category} onChange={(e) => setCategory(e.target.value)} required />
        </Field>
        <ScopeFields idPrefix="doc" departmentId={scope.department_id} officeId={scope.office_id} onChange={setScope} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Last verified" htmlFor="doc-verified" required>
            <Input id="doc-verified" type="date" value={verified} onChange={(e) => setVerified(e.target.value)} />
          </Field>
          <Field label="Expires" htmlFor="doc-expires" required>
            <Input id="doc-expires" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <p className="text-xs text-muted">The document waits for an admin&apos;s approval before the chat uses it.</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" tone="primary" disabled={!preview || busy}>
            <Upload size={16} aria-hidden="true" /> Upload
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function DocumentsTab() {
  const { nameOf } = useAdmin();
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [archiving, setArchiving] = useState<DocumentRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const today = todayIso();

  const load = useCallback(() => {
    adminApi
      .documents()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function act(run: () => Promise<unknown>, message: string) {
    setError(null);
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
      <div className="mb-4 flex justify-end">
        <Button tone="primary" onClick={() => setUploading(true)}>
          <Upload size={16} aria-hidden="true" /> Upload PDF
        </Button>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {done ? <Notice tone="success">{done}</Notice> : null}
      {rows === null ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState text="No documents yet. Upload the first one." />
      ) : (
        <Table label="Documents" head={["Title", "Category", "Owner", "Status", "Expires", ""]}>
          {rows.map((d) => (
            <tr key={d.id} className={ROW}>
              <td className={CELL}>
                <p className="font-medium">{d.title}</p>
                <p className="text-xs text-muted">{d.characters.toLocaleString()} characters</p>
              </td>
              <td className={CELL}>{d.category}</td>
              <td className={`${CELL} text-muted`}>
                {nameOf("office", d.office_id) ?? nameOf("department", d.department_id) ?? d.owner_name ?? "—"}
              </td>
              <td className={CELL}>
                <StatusChip status={d.status} />
              </td>
              <td className={CELL}>
                <Expiry iso={d.expires_at} today={today} />
              </td>
              <td className={`${CELL} text-end whitespace-nowrap`}>
                {d.can_edit && d.status === "draft" ? (
                  <Button tone="ghost" onClick={() => act(() => adminApi.submitDocument(d.id), `"${d.title}" sent for approval.`)}>
                    Submit
                  </Button>
                ) : null}
                {d.can_edit && d.status !== "archived" ? (
                  <Button tone="ghost" onClick={() => setArchiving(d)}>
                    Archive
                  </Button>
                ) : null}
              </td>
            </tr>
          ))}
        </Table>
      )}
      {uploading ? (
        <UploadDialog
          onClose={() => setUploading(false)}
          onDone={(title) => {
            setUploading(false);
            setDone(`"${title}" uploaded and waiting for approval.`);
            load();
          }}
        />
      ) : null}
      {archiving ? (
        <Confirm
          title="Archive this document?"
          body={`"${archiving.title}" will stop being used by the chat.`}
          confirmLabel="Archive"
          onCancel={() => setArchiving(null)}
          onConfirm={() => {
            const doc = archiving;
            setArchiving(null);
            void act(() => adminApi.archiveDocument(doc.id), `"${doc.title}" archived.`);
          }}
        />
      ) : null}
    </>
  );
}
