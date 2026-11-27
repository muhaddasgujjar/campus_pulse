/** Server fallback transcription (VOI-1): only for browsers without speech recognition. */

import { publicConfig } from "@/lib/config";
import type { SpeechLang } from "@/lib/voice/support";

export type TranscribeResult =
  | { ok: true; transcript: string }
  | { ok: false; reason: "not_configured" | "busy" | "too_large" | "failed" };

/** Uploads the recording (raw body, its own Content-Type). The server never stores it. */
export async function transcribeOnServer(
  audio: Blob,
  lang: SpeechLang,
  apiUrl = publicConfig.apiUrl,
): Promise<TranscribeResult> {
  if (!apiUrl) return { ok: false, reason: "not_configured" };
  try {
    const response = await fetch(`${apiUrl}/api/voice/transcribe?lang=${lang}`, {
      method: "POST",
      headers: { "Content-Type": audio.type || "audio/webm" },
      body: audio,
    });
    if (response.ok) {
      const body = (await response.json()) as { transcript?: unknown };
      return { ok: true, transcript: typeof body.transcript === "string" ? body.transcript : "" };
    }
    if (response.status === 503) return { ok: false, reason: "not_configured" };
    if (response.status === 429) return { ok: false, reason: "busy" };
    if (response.status === 413) return { ok: false, reason: "too_large" };
    return { ok: false, reason: "failed" };
  } catch {
    return { ok: false, reason: "failed" };
  }
}

export const TRANSCRIBE_ERRORS: Record<Exclude<TranscribeResult, { ok: true }>["reason"], string> = {
  not_configured: "Voice messages need Chrome or Edge on this device. Please type your question.",
  busy: "Lots of students are asking right now. Please try again in a minute, or type.",
  too_large: "That recording is too long. Please keep voice messages under a minute.",
  failed: "We couldn't transcribe that recording. Please try again or type.",
};
