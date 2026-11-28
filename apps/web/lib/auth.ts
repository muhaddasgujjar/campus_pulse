/**
 * Sign-in for staff, admins and students (AUTH-1, AUTH-2, AUTH-4).
 *
 * - With NEXT_PUBLIC_SUPABASE_URL and the anon key set, Supabase Auth runs in the browser:
 *   staff use email and password (accounts made by an admin), students use anonymous sign-in.
 *   The API verifies the Supabase access token and reads the role from `profiles`.
 * - On a laptop with no Supabase project (`make api-local`, DEV_AUTH), the API signs a local
 *   token at POST /api/auth/dev-login. That route does not exist in dev or prod.
 *
 * The token only says who someone is. What they may do is decided by the server on every call.
 */

import { publicConfig } from "@/lib/config";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const DEV_TOKEN_KEY = "campus-pulse.dev-token";

function readDevToken(): string | null {
  try {
    return window.localStorage.getItem(DEV_TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeDevToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(DEV_TOKEN_KEY, token);
    else window.localStorage.removeItem(DEV_TOKEN_KEY);
  } catch {
    // storage blocked: the user signs in again next time
  }
}

/** The current access token, or null when nobody is signed in. */
export async function getAccessToken(): Promise<string | null> {
  const supabase = getSupabaseBrowserClient();
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }
  return readDevToken();
}

export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function devLogin(email: string | null): Promise<string | null> {
  const apiUrl = publicConfig.apiUrl;
  if (!apiUrl) return "The app is not connected to the server.";
  try {
    const response = await fetch(`${apiUrl}/api/auth/dev-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (response.status === 404) return "Sign-in is not set up on this server.";
    if (!response.ok) return "Email or password is wrong, or the account is inactive.";
    const body = (await response.json()) as { access_token: string };
    writeDevToken(body.access_token);
    return null;
  } catch {
    return "Can't reach the server. Check your connection and try again.";
  }
}

/** Staff and admin sign-in. Returns an error message, or null on success. */
export async function signInStaff(email: string, password: string): Promise<string | null> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return devLogin(email.trim());
  const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
  return error ? "Email or password is wrong, or the account is inactive." : null;
}

/** A student account without email (Supabase anonymous sign-in). Keeps an existing session. */
export async function signInStudent(): Promise<string | null> {
  if (await getAccessToken()) return null;
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return devLogin(null);
  const { error } = await supabase.auth.signInAnonymously();
  return error ? "Couldn't create your profile right now. Please try again." : null;
}

export async function signOut(): Promise<void> {
  writeDevToken(null);
  const supabase = getSupabaseBrowserClient();
  if (supabase) await supabase.auth.signOut();
}
