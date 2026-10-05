import type { Metadata } from "next";

import { BrandMark } from "@/components/brand/BrandMark";
import { institution } from "@/lib/institution";

export const metadata: Metadata = { title: `Staff sign in · ${institution.productName}` };

/**
 * Admin login shell (DESIGN.md 6.2.1). M1 placeholder: fields are disabled.
 * Supabase Auth sign-in and server-side RBAC arrive in M5 (AUTH-2, AUTH-3).
 */
export default function AdminLoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <section
        aria-labelledby="admin-title"
        className="flex w-full max-w-sm flex-col gap-6 rounded-(--radius-lg) border border-border bg-surface-1 p-8"
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <BrandMark size={56} />
          <h1 id="admin-title" className="text-2xl font-bold">
            Staff sign in
          </h1>
          <p className="text-sm text-muted">Staff sign-in arrives in milestone M5.</p>
        </div>
        <form className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              disabled
              className="min-h-11 rounded-(--radius-sm) border border-border bg-surface-2 px-3 text-text disabled:opacity-70"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              disabled
              className="min-h-11 rounded-(--radius-sm) border border-border bg-surface-2 px-3 text-text disabled:opacity-70"
            />
          </div>
          <button
            type="submit"
            disabled
            className="min-h-11 rounded-(--radius-sm) bg-primary font-semibold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            Sign in
          </button>
        </form>
      </section>
    </main>
  );
}
