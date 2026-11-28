/** Student account calls (AUTH-4, PRIV-2) and the deadlines card (CHAT-7). */

import { api, type Me } from "@/lib/admin/api";

export type Deadline = {
  id: string;
  title: string;
  date: string;
  kind: string;
  program_scope: string | null;
  office_name: string | null;
  days_left: number;
  last_verified: string | null;
};

export type ProfileInput = {
  program: string | null;
  semester: number | null;
  section: string | null;
  language_pref: "en" | "ur" | null;
};

export const accountApi = {
  me: () => api<Me>("/api/me"),
  saveProfile: (body: ProfileInput) => api<Me>("/api/me/profile", { method: "PUT", json: body }),
  deleteMyData: () => api<{ conversations: number }>("/api/me/data", { method: "DELETE" }),
  deadlines: (program?: string | null) =>
    api<Deadline[]>("/api/deadlines", { query: { program: program || undefined } }),
};
