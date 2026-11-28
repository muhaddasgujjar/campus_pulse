/**
 * Admin portal API client (Architectural.md Section 8). Every call carries the signed-in
 * user's token; the server checks the role on every route (rule 5), so hiding a button in the
 * UI is a convenience, not a control.
 */

import { authHeaders } from "@/lib/auth";
import { publicConfig } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Init = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  body?: BodyInit;
  contentType?: string;
  query?: Record<string, string | number | boolean | null | undefined>;
};

function detail(body: unknown, status: number): string {
  const raw = (body as { detail?: unknown } | null)?.detail;
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) {
    return raw
      .map((item: { msg?: string; loc?: unknown[] }) => {
        const field = item.loc?.filter((p) => p !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  if (status === 401) return "Please sign in again.";
  if (status === 403) return "Your role can't do this.";
  return `The server returned ${status}.`;
}

export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const apiUrl = publicConfig.apiUrl;
  if (!apiUrl) throw new ApiError(0, "The app is not connected to the server.");
  const url = new URL(`${apiUrl}${path}`);
  for (const [key, value] of Object.entries(init.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = { ...(await authHeaders()) };
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  } else if (init.contentType) {
    headers["Content-Type"] = init.contentType;
  }
  let response: Response;
  try {
    response = await fetch(url, { method: init.method ?? "GET", headers, body, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Can't reach the server. It may be waking up; try again in a minute.");
  }
  if (response.status === 204) return undefined as T;
  const parsed: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, detail(parsed, response.status));
  return parsed as T;
}

// --- types (mirror the FastAPI response models) -----------------------------------------------

export type Role = "student" | "staff" | "admin";
export type Permission =
  | "chat"
  | "edit_own_profile"
  | "edit_content"
  | "approve_content"
  | "manage_users"
  | "view_audit"
  | "view_metrics"
  | "export"
  | "edit_settings";

export type Me = {
  id: string;
  role: Role;
  is_anonymous: boolean;
  email: string | null;
  full_name: string | null;
  department_id: string | null;
  office_id: string | null;
  program: string | null;
  semester: number | null;
  section: string | null;
  language_pref: "en" | "ur" | null;
  permissions: Permission[];
};

export type Status = "draft" | "pending" | "approved" | "archived";

export type Entry = {
  id: string;
  title: string;
  question: string | null;
  answer: string;
  category: string;
  language: "en" | "ur";
  owner_name: string | null;
  department_id: string | null;
  office_id: string | null;
  status: Status;
  last_verified: string | null;
  expires_at: string | null;
  source_url: string | null;
  version: number;
  rejected_reason: string | null;
  updated_at: string;
  can_edit: boolean;
};

export type EntryInput = {
  title: string;
  question: string | null;
  answer: string;
  category: string;
  language: "en" | "ur";
  owner_name: string | null;
  department_id: string | null;
  office_id: string | null;
  last_verified: string;
  expires_at: string;
  source_url: string | null;
};

export type DocumentRow = {
  id: string;
  title: string;
  category: string;
  owner_name: string | null;
  department_id: string | null;
  office_id: string | null;
  mime: string;
  status: Status;
  last_verified: string | null;
  expires_at: string | null;
  source_url: string | null;
  characters: number;
  updated_at: string;
  can_edit: boolean;
};

export type PdfPreview = { pages: number; characters: number; chunks: number; text_preview: string };

export type Approval = {
  kind: "kb" | "document";
  id: string;
  title: string;
  category: string;
  submitted_at: string;
  current: Record<string, unknown> | null;
  proposed: Record<string, unknown>;
};

export type ReviewItem = {
  kind: "kb" | "document";
  id: string;
  title: string;
  category: string;
  expires_at: string;
  expired: boolean;
  owner_name: string | null;
  can_edit: boolean;
};

export type Unanswered = {
  id: string;
  query: string;
  count: number;
  last_seen: string;
  reason: string | null;
};

export type Named = { id: string; name: string };
export type Lookups = { departments: Named[]; offices: Named[] };

export type StaffUser = {
  id: string;
  email: string | null;
  full_name: string | null;
  role: Role;
  department_id: string | null;
  office_id: string | null;
  is_active: boolean;
  created_at: string;
};

export type AuditRow = {
  id: string;
  created_at: string;
  actor_label: string | null;
  action: string;
  table_name: string;
  row_id: string | null;
  diff: Record<string, unknown>;
};
export type AuditPage = { items: AuditRow[]; actions: string[]; tables: string[] };

export type Counted = { label: string; count: number };
export type Metrics = {
  window_days: number;
  days: { day: string; questions: number; fallbacks: number }[];
  questions_today: number;
  fallback_rate: number | null;
  avg_latency_ms: number | null;
  thumbs_up_rate: number | null;
  thumbs_down: number;
  top_questions: Counted[];
  tool_usage: Counted[];
  open_unanswered: number;
  needs_review: number;
  recent_thumbs_down: { message_id: string; answer: string; comment: string | null; at: string }[];
  usage_today: Record<string, number>;
  database_bytes: number | null;
  database_limit_bytes: number;
};

export type Contact = { name: string; phone: string | null; email: string | null };
export type InstitutionSettings = {
  name: string;
  short_name: string | null;
  disclaimer: string;
  starter_questions: string[];
  fallback_office: string | null;
  contacts: Contact[];
  live_fetch_allowlist: string[];
};

export type TableName = "faculty" | "timetable" | "fees" | "offices" | "key-dates";
export type TableRow = Record<string, unknown> & { id: string; can_edit: boolean; updated_at: string };

export type ImportResult = {
  valid_rows: number;
  errors: string[];
  imported: boolean;
  created: number;
  updated: number;
  unchanged: number;
};

// --- calls -------------------------------------------------------------------------------------

export const adminApi = {
  me: () => api<Me>("/api/me"),
  lookups: () => api<Lookups>("/api/admin/lookups"),

  entries: (query: { status?: Status | ""; q?: string } = {}) =>
    api<Entry[]>("/api/admin/kb", { query }),
  entry: (id: string) => api<Entry>(`/api/admin/kb/${id}`),
  createEntry: (body: EntryInput & { submit: boolean; from_unanswered_id?: string | null }) =>
    api<Entry>("/api/admin/kb", { method: "POST", json: body }),
  updateEntry: (id: string, body: EntryInput) =>
    api<Entry>(`/api/admin/kb/${id}`, { method: "PUT", json: body }),
  submitEntry: (id: string) => api<Entry>(`/api/admin/kb/${id}/submit`, { method: "POST" }),
  archiveEntry: (id: string) => api<Entry>(`/api/admin/kb/${id}/archive`, { method: "POST" }),

  documents: (query: { status?: Status | ""; q?: string } = {}) =>
    api<DocumentRow[]>("/api/admin/documents", { query }),
  previewPdf: (file: Blob) =>
    api<PdfPreview>("/api/admin/documents/preview", {
      method: "POST",
      body: file,
      contentType: "application/pdf",
    }),
  uploadPdf: (
    file: Blob,
    meta: {
      title: string;
      category: string;
      last_verified: string;
      expires_at: string;
      owner_name?: string;
      department_id?: string | null;
      office_id?: string | null;
    },
  ) =>
    api<DocumentRow>("/api/admin/documents", {
      method: "POST",
      body: file,
      contentType: "application/pdf",
      query: meta,
    }),
  submitDocument: (id: string) =>
    api<DocumentRow>(`/api/admin/documents/${id}/submit`, { method: "POST" }),
  archiveDocument: (id: string) =>
    api<DocumentRow>(`/api/admin/documents/${id}/archive`, { method: "POST" }),

  approvals: () => api<Approval[]>("/api/admin/approvals"),
  approve: (kind: Approval["kind"], id: string, comment?: string) =>
    api<{ chunks: number; embedded: boolean }>(`/api/admin/approvals/${kind}/${id}/approve`, {
      method: "POST",
      json: { comment: comment || null },
    }),
  reject: (kind: Approval["kind"], id: string, comment: string) =>
    api(`/api/admin/approvals/${kind}/${id}/reject`, { method: "POST", json: { comment } }),

  review: (mine = false) => api<ReviewItem[]>("/api/admin/review", { query: { mine } }),
  unanswered: (status: "open" | "handled" | "ignored" = "open") =>
    api<Unanswered[]>("/api/admin/unanswered", { query: { status } }),
  resolveUnanswered: (id: string, status: "handled" | "ignored") =>
    api<void>(`/api/admin/unanswered/${id}`, { method: "POST", json: { status } }),

  table: (table: TableName, q?: string) => api<TableRow[]>(`/api/admin/tables/${table}`, { query: { q } }),
  createRow: (table: TableName, body: Record<string, unknown>) =>
    api<TableRow>(`/api/admin/tables/${table}`, { method: "POST", json: body }),
  updateRow: (table: TableName, id: string, body: Record<string, unknown>) =>
    api<TableRow>(`/api/admin/tables/${table}/${id}`, { method: "PUT", json: body }),
  deleteRow: (table: TableName, id: string) =>
    api<void>(`/api/admin/tables/${table}/${id}`, { method: "DELETE" }),
  importCsv: (kind: "timetable" | "faculty", csv: Blob, dryRun: boolean) =>
    api<ImportResult>(`/api/admin/import/${kind}`, {
      method: "POST",
      body: csv,
      contentType: "text/csv",
      query: { dry_run: dryRun },
    }),

  users: () => api<StaffUser[]>("/api/admin/users"),
  createUser: (body: {
    email: string;
    password: string;
    full_name: string;
    role: "staff" | "admin";
    department_id: string | null;
    office_id: string | null;
  }) => api<StaffUser>("/api/admin/users", { method: "POST", json: body }),
  updateUser: (id: string, body: Partial<Pick<StaffUser, "full_name" | "role" | "department_id" | "office_id" | "is_active">>) =>
    api<StaffUser>(`/api/admin/users/${id}`, { method: "PATCH", json: body }),

  audit: (query: { actor?: string; action?: string; table?: string; since?: string; until?: string }) =>
    api<AuditPage>("/api/admin/audit", { query }),
  metrics: (days = 14) => api<Metrics>("/api/admin/metrics", { query: { days } }),
  settings: () => api<InstitutionSettings>("/api/admin/settings"),
  saveSettings: (body: InstitutionSettings) =>
    api<InstitutionSettings>("/api/admin/settings", { method: "PUT", json: body }),
};
