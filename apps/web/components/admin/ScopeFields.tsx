"use client";

import { useAdmin } from "@/components/admin/AdminShell";
import { Field, Select } from "@/components/admin/ui";

/**
 * Department and office pickers. Staff are limited to their own scope (AUTH-3), so they see
 * only their own department or office; admins can pick any. The server checks again.
 */
export function ScopeFields({
  departmentId,
  officeId,
  onChange,
  idPrefix,
}: {
  departmentId: string | null;
  officeId: string | null;
  onChange: (next: { department_id: string | null; office_id: string | null }) => void;
  idPrefix: string;
}) {
  const { me, lookups } = useAdmin();
  const admin = me.role === "admin";
  const departments = admin ? lookups.departments : lookups.departments.filter((d) => d.id === me.department_id);
  const offices = admin ? lookups.offices : lookups.offices.filter((o) => o.id === me.office_id);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Office" htmlFor={`${idPrefix}-office`}>
        <Select
          id={`${idPrefix}-office`}
          value={officeId ?? ""}
          onChange={(e) => onChange({ department_id: departmentId, office_id: e.target.value || null })}
        >
          <option value="">{admin ? "None" : offices.length ? "None" : "Not your scope"}</option>
          {offices.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Department" htmlFor={`${idPrefix}-department`}>
        <Select
          id={`${idPrefix}-department`}
          value={departmentId ?? ""}
          onChange={(e) => onChange({ department_id: e.target.value || null, office_id: officeId })}
        >
          <option value="">None</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
      </Field>
    </div>
  );
}
