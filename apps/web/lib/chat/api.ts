/** Chat REST calls (Architectural.md Section 8): config, history, feedback. */

import { publicConfig } from "@/lib/config";
import type { Source } from "@/lib/chat/protocol";
import type { ChatMessage } from "@/lib/chat/state";

export type PublicConfig = {
  institution_slug: string;
  institution_name: string | null;
  short_name: string | null;
  disclaimer: string;
  starter_questions: string[];
};

type MessageOut = {
  id: string;
  role: "user" | "assistant";
  modality: "text" | "voice";
  content: string;
  sources: Source[];
  created_at: string;
};

export type FeedbackReason = "wrong" | "outdated" | "not_helpful";

export const FEEDBACK_REASONS: { value: FeedbackReason; label: string }[] = [
  { value: "wrong", label: "The answer is wrong" },
  { value: "outdated", label: "The information is outdated" },
  { value: "not_helpful", label: "It did not answer my question" },
];

function base(apiUrl: string | undefined): string {
  if (!apiUrl) throw new Error("NEXT_PUBLIC_API_URL is not set");
  return apiUrl;
}

export async function fetchConfig(apiUrl = publicConfig.apiUrl): Promise<PublicConfig | null> {
  try {
    const response = await fetch(`${base(apiUrl)}/api/config`, { cache: "no-store" });
    return response.ok ? ((await response.json()) as PublicConfig) : null;
  } catch {
    return null;
  }
}

/** The stored conversation, or null when it is gone (404) or the API cannot be reached. */
export async function fetchHistory(
  conversationId: string,
  apiUrl = publicConfig.apiUrl,
): Promise<ChatMessage[] | null> {
  try {
    const response = await fetch(
      `${base(apiUrl)}/api/conversations/${encodeURIComponent(conversationId)}/messages`,
      { cache: "no-store" },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as MessageOut[];
    return rows.map((row) => ({
      localId: `h-${row.id}`,
      id: row.id,
      role: row.role,
      modality: row.modality,
      seconds: null,
      text: row.content,
      sources: row.sources,
      createdAt: Date.parse(row.created_at),
      status: row.role === "user" ? "sent" : "done",
      stage: null,
      fallback: false,
      office: null,
      rating: null,
    }));
  } catch {
    return null;
  }
}

export async function sendFeedback(
  body: { message_id: string; rating: 1 | -1; reason?: FeedbackReason; comment?: string },
  apiUrl = publicConfig.apiUrl,
): Promise<boolean> {
  try {
    const response = await fetch(`${base(apiUrl)}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return response.ok;
  } catch {
    return false;
  }
}
