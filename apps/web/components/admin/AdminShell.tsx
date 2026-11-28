"use client";

import {
  ClipboardCheck,
  FileText,
  LayoutDashboard,
  LogOut,
  type LucideIcon,
  MessageCircleQuestion,
  ScrollText,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { BrandMark } from "@/components/brand/BrandMark";
import { Loading } from "@/components/admin/ui";
import { adminApi, ApiError, type Lookups, type Me, type Permission } from "@/lib/admin/api";
import { signOut } from "@/lib/auth";

type AdminSession = {
  me: Me;
  lookups: Lookups;
  can: (permission: Permission) => boolean;
  nameOf: (kind: "department" | "office", id: string | null) => string | null;
};

const SessionContext = createContext<AdminSession | null>(null);

export function useAdmin(): AdminSession {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useAdmin outside AdminShell");
  return session;
}

type NavItem = { href: string; label: string; icon: LucideIcon; permission: Permission };

const NAV: NavItem[] = [
  { href: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard, permission: "edit_content" },
  { href: "/admin/content", label: "Content", icon: FileText, permission: "edit_content" },
  { href: "/admin/approvals", label: "Approvals", icon: ClipboardCheck, permission: "edit_content" },
  { href: "/admin/unanswered", label: "Unanswered", icon: MessageCircleQuestion, permission: "edit_content" },
  { href: "/admin/users", label: "Users", icon: Users, permission: "manage_users" },
  { href: "/admin/audit", label: "Audit", icon: ScrollText, permission: "view_audit" },
  { href: "/admin/settings", label: "Settings", icon: Settings, permission: "edit_settings" },
];

/**
 * Admin layout (DESIGN.md 6.2): left sidebar, top bar with profile, content area.
 * Staff see only what their role may use; the API enforces the same rules (rule 5).
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await adminApi.me();
        if (!me.permissions.includes("edit_content")) {
          if (!cancelled) setError("This account is not a staff account.");
          return;
        }
        const lookups = await adminApi.lookups();
        if (cancelled) return;
        const names = {
          department: new Map(lookups.departments.map((d) => [d.id, d.name])),
          office: new Map(lookups.offices.map((o) => [o.id, o.name])),
        };
        setSession({
          me,
          lookups,
          can: (p) => me.permissions.includes(p),
          nameOf: (kind, id) => (id ? (names[kind].get(id) ?? null) : null),
        });
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
          router.replace("/admin");
          return;
        }
        setError(caught instanceof Error ? caught.message : "Something went wrong.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const leave = useCallback(async () => {
    await signOut();
    router.replace("/admin");
  }, [router]);

  if (error) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
        <p className="text-danger" role="alert">
          {error}
        </p>
        <button type="button" onClick={leave} className="min-h-11 text-accent underline">
          Sign in with another account
        </button>
      </main>
    );
  }
  if (!session) return <Loading label="Checking your sign-in…" />;

  const { me, can, nameOf } = session;
  const scope = nameOf("office", me.office_id) ?? nameOf("department", me.department_id);

  return (
    <SessionContext.Provider value={session}>
      <div className="flex min-h-dvh flex-col md:flex-row">
        <nav
          aria-label="Admin"
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-border bg-surface-1 p-2 md:w-60 md:flex-col md:border-e md:border-b-0 md:p-4"
        >
          <div className="mb-4 hidden items-center gap-2 px-2 md:flex">
            <BrandMark size={32} />
            <span className="font-semibold">Campus Pulse</span>
          </div>
          {NAV.filter((item) => can(item.permission)).map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 shrink-0 items-center gap-3 rounded-(--radius-sm) px-3 text-sm ${
                  active ? "bg-surface-teal font-semibold text-accent" : "text-text hover:bg-surface-2"
                }`}
              >
                <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-end gap-3 border-b border-border px-4 py-2 md:px-8">
            <div className="text-end text-sm">
              <p className="font-medium">{me.full_name ?? me.email}</p>
              <p className="text-xs text-muted">
                {me.role === "admin" ? "Admin" : "Staff"}
                {scope ? ` · ${scope}` : ""}
              </p>
            </div>
            <button
              type="button"
              onClick={leave}
              aria-label="Sign out"
              className="inline-flex size-11 items-center justify-center rounded-(--radius-pill) text-muted hover:bg-surface-2"
            >
              <LogOut size={18} aria-hidden="true" />
            </button>
          </header>
          <main className="flex-1 px-4 py-6 md:px-8">{children}</main>
        </div>
      </div>
    </SessionContext.Provider>
  );
}
