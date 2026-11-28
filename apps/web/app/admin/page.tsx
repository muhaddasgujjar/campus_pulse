import type { Metadata } from "next";

import { LoginForm } from "@/components/admin/LoginForm";
import { BrandMark } from "@/components/brand/BrandMark";
import { institution } from "@/lib/institution";

export const metadata: Metadata = { title: `Staff sign in · ${institution.productName}` };

/**
 * Staff sign in (DESIGN.md 6.2.1, AUTH-1). Staff accounts are created by an admin in Users;
 * there is no self sign-up and no email is sent.
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
          <p className="text-sm text-muted">For {institution.name} staff. Ask an admin for an account.</p>
        </div>
        <LoginForm />
      </section>
    </main>
  );
}
