"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { adminApi } from "@/lib/admin/api";
import { getAccessToken, signInStaff } from "@/lib/auth";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const CONTROL =
  "min-h-11 rounded-(--radius-sm) border border-border bg-surface-2 px-3 text-text focus:border-border-teal";

/** Staff sign in (DESIGN.md 6.2.1): email and password, error text inline. */
export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const local = getSupabaseBrowserClient() === null;

  // Already signed in as staff: go straight to the portal.
  useEffect(() => {
    void getAccessToken().then(async (token) => {
      if (!token) return;
      const me = await adminApi.me().catch(() => null);
      if (me?.permissions.includes("edit_content")) router.replace("/admin/dashboard");
    });
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const problem = await signInStaff(email, password);
    if (problem) {
      setError(problem);
      setBusy(false);
      return;
    }
    const me = await adminApi.me().catch(() => null);
    if (!me?.permissions.includes("edit_content")) {
      setError("This account is not a staff account.");
      setBusy(false);
      return;
    }
    router.replace("/admin/dashboard");
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
      <div className="flex flex-col gap-1">
        <label htmlFor="email" className="text-sm font-medium">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "login-error" : undefined}
          className={CONTROL}
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
          required={!local}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={CONTROL}
        />
        {local ? (
          <p className="text-xs text-muted">
            Local mode: any password works. Try admin@local.test or staff@local.test.
          </p>
        ) : null}
      </div>
      {error ? (
        <p id="login-error" role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={busy || !email}
        className="min-h-11 rounded-(--radius-sm) bg-primary font-semibold text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
