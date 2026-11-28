import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/config", () => ({
  publicConfig: { apiUrl: "http://api.test", wsUrl: undefined, supabaseUrl: undefined, supabaseAnonKey: undefined },
}));

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  usePathname: () => "/admin/dashboard",
}));

import { AdminShell } from "@/components/admin/AdminShell";
import { api, ApiError, type Me } from "@/lib/admin/api";
import { cellText, TABLE_SPECS, toBody, toValues } from "@/lib/admin/tables";
import { getAccessToken, signInStaff, signOut } from "@/lib/auth";

function me(role: Me["role"]): Me {
  const permissions: Me["permissions"] =
    role === "admin"
      ? ["chat", "edit_own_profile", "edit_content", "approve_content", "manage_users", "view_audit", "view_metrics", "export", "edit_settings"]
      : role === "staff"
        ? ["chat", "edit_own_profile", "edit_content"]
        : ["chat", "edit_own_profile"];
  return {
    id: "u1",
    role,
    is_anonymous: false,
    email: `${role}@test.edu`,
    full_name: role,
    department_id: null,
    office_id: "o1",
    program: null,
    semester: null,
    section: null,
    language_pref: null,
    permissions,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function serve(routes: Record<string, () => Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = new URL(String(input));
    const handler = routes[url.pathname];
    return handler ? handler() : json({ detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  window.localStorage.clear();
  replace.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("auth on a laptop (DEV_AUTH)", () => {
  it("signs staff in through dev-login and sends the token on every call", async () => {
    const fetchMock = serve({
      "/api/auth/dev-login": () => json({ access_token: "tok-1", token_type: "bearer" }),
      "/api/me": () => json(me("staff")),
    });
    expect(await signInStaff("staff@local.test", "")).toBeNull();
    expect(await getAccessToken()).toBe("tok-1");
    await api("/api/me");
    const init = fetchMock.mock.calls.at(-1)?.[1] ?? {};
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-1");
    await signOut();
    expect(await getAccessToken()).toBeNull();
  });

  it("explains a wrong account without saying which part was wrong", async () => {
    serve({ "/api/auth/dev-login": () => json({ detail: "unknown or inactive account" }, 401) });
    expect(await signInStaff("nobody@x.y", "")).toMatch(/wrong, or the account is inactive/);
  });
});

describe("api errors", () => {
  it("turns FastAPI validation errors into one readable line", async () => {
    serve({
      "/api/admin/kb": () =>
        json({ detail: [{ loc: ["body", "expires_at"], msg: "must be after last_verified" }] }, 422),
    });
    await expect(api("/api/admin/kb")).rejects.toEqual(new ApiError(422, "expires_at: must be after last_verified"));
  });
});

describe("admin shell", () => {
  it("shows staff only the screens their role may use", async () => {
    window.localStorage.setItem("campus-pulse.dev-token", "tok");
    serve({ "/api/me": () => json(me("staff")), "/api/admin/lookups": () => json({ departments: [], offices: [{ id: "o1", name: "Exam Office" }] }) });
    render(<AdminShell>content</AdminShell>);
    expect(await screen.findByRole("link", { name: "Content" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Approvals" })).toBeInTheDocument();
    for (const hidden of ["Users", "Audit", "Settings"]) {
      expect(screen.queryByRole("link", { name: hidden })).not.toBeInTheDocument();
    }
    expect(screen.getByText("Staff · Exam Office")).toBeInTheDocument();
  });

  it("shows admins every screen", async () => {
    serve({ "/api/me": () => json(me("admin")), "/api/admin/lookups": () => json({ departments: [], offices: [] }) });
    render(<AdminShell>content</AdminShell>);
    for (const name of ["Dashboard", "Content", "Approvals", "Unanswered", "Users", "Audit", "Settings"]) {
      expect(await screen.findByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("sends a signed-out visitor to the sign-in page", async () => {
    serve({ "/api/me": () => json({ detail: "sign in required" }, 401) });
    render(<AdminShell>secret</AdminShell>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin"));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("refuses a student account", async () => {
    serve({ "/api/me": () => json(me("student")) });
    render(<AdminShell>secret</AdminShell>);
    expect(await screen.findByRole("alert")).toHaveTextContent("not a staff account");
  });
});

describe("structured table forms", () => {
  it("round-trips a timetable row between the API and the form", () => {
    const spec = TABLE_SPECS.timetable;
    const row = {
      program: "BSCS", semester: 3, section: "B", department_id: null, day: 2,
      start_time: "09:00:00", end_time: "10:30:00", course_code: "CS-201", course_name: "Data Structures",
      faculty_name: null, room: "C-12", effective_from: null, effective_to: null,
      last_verified: "2026-11-01", source_name: "Department timetable",
    };
    const values = toValues(spec, row);
    expect(values.start_time).toBe("09:00");
    expect(values.day).toBe("2");
    const body = toBody(spec, values);
    expect(body).toMatchObject({ semester: 3, day: 2, faculty_name: null, start_time: "09:00" });
  });

  it("splits list fields on commas and shows days by name", () => {
    const spec = TABLE_SPECS.offices;
    const body = toBody(spec, { ...toValues(spec, null), name: "Exam Office", phones: "042-1, 042-2 ,", last_verified: "2026-11-01", source_name: "x" });
    expect(body.phones).toEqual(["042-1", "042-2"]);
    expect(cellText("day", 1)).toBe("Monday");
    expect(cellText("phones", [])).toBe("—");
    expect(cellText("email", null)).toBe("—");
  });
});
