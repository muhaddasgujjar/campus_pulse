/**
 * Structured tables in the admin portal (DATA-1): which fields each form shows and which
 * columns each list shows. Mirrors app/services/admin_tables.py; the server validates again.
 */

import type { TableName } from "@/lib/admin/api";

export type FieldKind = "text" | "textarea" | "number" | "date" | "time" | "list" | "select" | "department";

export type FieldSpec = {
  name: string;
  label: string;
  kind: FieldKind;
  required?: boolean;
  options?: { value: string; label: string }[];
  hint?: string;
  /** Value a new row's form starts with. */
  default?: string;
};

export type TableSpec = {
  name: TableName;
  label: string;
  singular: string;
  columns: string[];
  fields: FieldSpec[];
};

const verified: FieldSpec[] = [
  { name: "last_verified", label: "Last verified", kind: "date", required: true },
  {
    name: "source_name",
    label: "Source",
    kind: "text",
    required: true,
    hint: "Where this came from, e.g. Exam Office notice, 3 Nov 2026",
  },
];

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const TABLE_SPECS: Record<TableName, TableSpec> = {
  faculty: {
    name: "faculty",
    label: "Faculty",
    singular: "faculty member",
    columns: ["name", "designation", "email", "office_room", "status", "last_verified"],
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "designation", label: "Designation", kind: "text" },
      { name: "department_id", label: "Department", kind: "department" },
      { name: "email", label: "Email", kind: "text" },
      { name: "office_room", label: "Office room", kind: "text" },
      { name: "courses", label: "Courses", kind: "list", hint: "Comma separated" },
      {
        name: "status",
        label: "Status",
        kind: "select",
        required: true,
        default: "active",
        options: [
          { value: "active", label: "Active" },
          { value: "on_leave", label: "On leave" },
          { value: "left", label: "Left" },
        ],
      },
      ...verified,
    ],
  },
  timetable: {
    name: "timetable",
    label: "Timetable",
    singular: "class",
    columns: ["program", "semester", "section", "day", "start_time", "end_time", "course_name", "room"],
    fields: [
      { name: "program", label: "Program", kind: "text", required: true },
      { name: "semester", label: "Semester", kind: "number", required: true },
      { name: "section", label: "Section", kind: "text" },
      { name: "department_id", label: "Department", kind: "department" },
      {
        name: "day",
        label: "Day",
        kind: "select",
        required: true,
        options: DAYS.map((d, i) => ({ value: String(i + 1), label: d })),
      },
      { name: "start_time", label: "Starts", kind: "time", required: true },
      { name: "end_time", label: "Ends", kind: "time", required: true },
      { name: "course_code", label: "Course code", kind: "text" },
      { name: "course_name", label: "Course name", kind: "text", required: true },
      { name: "faculty_name", label: "Teacher", kind: "text" },
      { name: "room", label: "Room", kind: "text" },
      { name: "effective_from", label: "Effective from", kind: "date" },
      { name: "effective_to", label: "Effective to", kind: "date" },
      ...verified,
    ],
  },
  fees: {
    name: "fees",
    label: "Fees",
    singular: "fee row",
    columns: ["program_group", "level", "fiscal_year", "admission_fee", "tuition_per_credit_hour", "last_verified"],
    fields: [
      { name: "program_group", label: "Program group", kind: "text", required: true },
      { name: "level", label: "Level", kind: "text" },
      { name: "fiscal_year", label: "Fiscal year", kind: "text", required: true, hint: "e.g. 2026-27" },
      { name: "admission_fee", label: "Admission fee (Rs)", kind: "number" },
      { name: "tuition_per_credit_hour", label: "Tuition per credit hour (Rs)", kind: "number" },
      { name: "misc_per_semester", label: "Other charges per semester (Rs)", kind: "number" },
      { name: "credit_hours_sem1", label: "Credit hours, semester 1", kind: "number" },
      { name: "notes", label: "Notes", kind: "textarea" },
      ...verified,
    ],
  },
  offices: {
    name: "offices",
    label: "Offices",
    singular: "office",
    columns: ["name", "phones", "email", "hours", "last_verified"],
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "phones", label: "Phones", kind: "list", hint: "Comma separated" },
      { name: "email", label: "Email", kind: "text" },
      { name: "hours", label: "Hours", kind: "text" },
      { name: "location", label: "Location", kind: "text" },
      { name: "topics", label: "Topics", kind: "list", hint: "Words students use, comma separated" },
      ...verified,
    ],
  },
  "key-dates": {
    name: "key-dates",
    label: "Key dates",
    singular: "key date",
    columns: ["title", "date", "kind", "program_scope", "office_name"],
    fields: [
      { name: "title", label: "Title", kind: "text", required: true },
      { name: "date", label: "Date", kind: "date", required: true },
      {
        name: "kind",
        label: "Kind",
        kind: "select",
        required: true,
        options: ["admission", "fee", "scholarship", "exam", "semester", "holiday", "other"].map((k) => ({
          value: k,
          label: k[0].toUpperCase() + k.slice(1),
        })),
      },
      { name: "program_scope", label: "Programs", kind: "text", hint: "Empty = every program" },
      { name: "office_name", label: "Office to confirm with", kind: "text" },
      ...verified,
    ],
  },
};

export const DAY_NAMES = DAYS;

/** Form values (strings) -> request body. Empty optional fields are sent as null. */
export function toBody(spec: TableSpec, values: Record<string, string>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const field of spec.fields) {
    const raw = (values[field.name] ?? "").trim();
    if (field.kind === "list") {
      body[field.name] = raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : [];
    } else if (field.kind === "number" || (field.kind === "select" && field.name === "day")) {
      body[field.name] = raw === "" ? null : Number(raw);
    } else {
      body[field.name] = raw === "" ? null : raw;
    }
  }
  return body;
}

/** A row from the API -> form values (strings). */
export function toValues(spec: TableSpec, row: Record<string, unknown> | null): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of spec.fields) {
    const value = row?.[field.name];
    if (Array.isArray(value)) values[field.name] = value.join(", ");
    else if (field.kind === "time" && typeof value === "string") values[field.name] = value.slice(0, 5);
    else if (value === null || value === undefined) values[field.name] = row ? "" : (field.default ?? "");
    else values[field.name] = String(value);
  }
  return values;
}

/** One cell of a list table, as text. */
export function cellText(column: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (column === "day" && typeof value === "number") return DAYS[value - 1] ?? String(value);
  if ((column === "start_time" || column === "end_time") && typeof value === "string") return value.slice(0, 5);
  return String(value);
}

export function columnLabel(spec: TableSpec, column: string): string {
  return spec.fields.find((f) => f.name === column)?.label ?? column;
}
