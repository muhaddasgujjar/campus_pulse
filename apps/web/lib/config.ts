/**
 * Public runtime config. Only NEXT_PUBLIC_* values belong here: they are inlined into the
 * browser bundle. Never put the Supabase service role key or database URLs in the web app.
 * Each variable must be referenced literally (process.env.NEXT_PUBLIC_X) for Next.js to inline it.
 */

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed.replace(/\/+$/, "") : undefined;
}

export const publicConfig = {
  apiUrl: clean(process.env.NEXT_PUBLIC_API_URL),
  wsUrl: clean(process.env.NEXT_PUBLIC_WS_URL),
  supabaseUrl: clean(process.env.NEXT_PUBLIC_SUPABASE_URL),
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() || undefined,
} as const;
