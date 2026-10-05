import { publicConfig } from "@/lib/config";

/**
 * Wake the API on Render's free plan (it sleeps after 15 minutes idle, COST-6).
 * Fire and forget: calls GET /healthz once, ignores the result and every error.
 * The "waking up" UI state and WebSocket retry with backoff arrive in M3.
 */
export function wakeApi(apiUrl: string | undefined = publicConfig.apiUrl): void {
  if (!apiUrl || typeof fetch !== "function") return;
  void fetch(`${apiUrl}/healthz`, { method: "GET", cache: "no-store", keepalive: true }).catch(
    () => undefined,
  );
}
