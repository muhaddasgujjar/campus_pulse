/**
 * WebSocket /ws/chat protocol (Architectural.md Section 8). Keep in sync with
 * apps/api/app/api/chat_ws.py and apps/api/app/services/chat.py.
 */

export type Stage = "waking" | "searching" | "reading" | "writing" | "queued";

export type Source = {
  title: string;
  office: string | null;
  url: string | null;
  last_verified: string | null; // ISO date
  expired: boolean;
};

export type Office = {
  name: string | null;
  phones: string[];
  email: string | null;
  hours: string | null;
};

export type ErrorCode =
  | "rate_limited"
  | "busy"
  | "provider_down"
  | "internal"
  | "invalid_message"
  | "unavailable";

export type ServerEvent =
  | { type: "ack"; message_id: string; conversation_id: string }
  | { type: "status"; stage: Stage }
  | { type: "sources"; message_id: string; items: Source[] }
  | { type: "token"; message_id: string; text: string }
  | {
      type: "final";
      message_id: string;
      conversation_id: string;
      fallback: boolean;
      cache_hit: boolean;
      office: Office | null;
      replay: boolean;
    }
  | { type: "error"; code: ErrorCode; message: string; retry_after?: number }
  | { type: "pong" };

export type ClientEvent =
  | {
      type: "user_message";
      conversation_id: string | null;
      text: string;
      modality: "text" | "voice";
    }
  | { type: "resume"; conversation_id: string; last_message_id: string | null }
  | { type: "ping" };

const SERVER_TYPES = new Set(["ack", "status", "sources", "token", "final", "error", "pong"]);

/** Parse one frame. Unknown or malformed frames are ignored (null), never thrown. */
export function parseServerEvent(raw: string): ServerEvent | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value === "object" && value !== null && "type" in value) {
      const type = (value as { type: unknown }).type;
      if (typeof type === "string" && SERVER_TYPES.has(type)) return value as ServerEvent;
    }
  } catch {
    // ignore
  }
  return null;
}

/** Message length limit, mirrors CHAT_MAX_MESSAGE_CHARS on the API (SEC-2). */
export const MAX_MESSAGE_CHARS = 1000;
