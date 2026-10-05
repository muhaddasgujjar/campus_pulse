import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { publicConfig } from "@/lib/config";

/**
 * Supabase browser client, used for **Auth only** (D16): anonymous sign-in for students and
 * email/password for staff (M5). All data goes through the FastAPI service, never through
 * Supabase tables (RLS denies everything to the anon key).
 *
 * Returns null when NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set, so
 * the app runs locally and in CI without any Supabase project.
 */
let client: SupabaseClient | null | undefined;

export function getSupabaseBrowserClient(): SupabaseClient | null {
  if (client !== undefined) return client;
  const { supabaseUrl, supabaseAnonKey } = publicConfig;
  client =
    supabaseUrl && supabaseAnonKey
      ? createClient(supabaseUrl, supabaseAnonKey, {
          auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
        })
      : null;
  return client;
}
