/**
 * Chat state as a pure reducer (easy to test, no React or sockets here).
 * One turn: send (user bubble "sending") -> ack ("sent", bot placeholder) -> status* ->
 * sources -> token* -> final. `resume` replays answers as sources/token/final without an ack.
 */

import type { ErrorCode, Office, ServerEvent, Source, Stage } from "@/lib/chat/protocol";

export type Connection = "connecting" | "waking" | "online" | "reconnecting" | "offline";

export type ChatMessage = {
  localId: string;
  id: string | null;
  role: "user" | "assistant";
  text: string;
  sources: Source[];
  createdAt: number;
  status: "sending" | "sent" | "failed" | "streaming" | "done";
  stage: Stage | null;
  fallback: boolean;
  office: Office | null;
  rating: 1 | -1 | null;
};

export type Notice = { code: ErrorCode | "offline"; message: string } | null;

export type ChatState = {
  conversationId: string | null;
  lastMessageId: string | null;
  messages: ChatMessage[];
  connection: Connection;
  notice: Notice;
};

export type ChatAction =
  | { type: "send"; localId: string; text: string; now: number }
  | { type: "server"; event: ServerEvent; now: number }
  | { type: "connection"; connection: Connection }
  | { type: "history"; messages: ChatMessage[]; conversationId: string }
  | { type: "rated"; id: string; rating: 1 | -1 }
  | { type: "dismissNotice" }
  | { type: "reset" };

export function initialState(
  conversationId: string | null = null,
  lastMessageId: string | null = null,
): ChatState {
  return { conversationId, lastMessageId, messages: [], connection: "connecting", notice: null };
}

let counter = 0;
export function localId(prefix = "m"): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter}`;
}

function blank(role: ChatMessage["role"], now: number, patch: Partial<ChatMessage>): ChatMessage {
  return {
    localId: localId(role === "user" ? "u" : "a"),
    id: null,
    role,
    text: "",
    sources: [],
    createdAt: now,
    status: role === "user" ? "sending" : "streaming",
    stage: null,
    fallback: false,
    office: null,
    rating: null,
    ...patch,
  };
}

function update(
  messages: ChatMessage[],
  index: number,
  patch: Partial<ChatMessage>,
): ChatMessage[] {
  return messages.map((m, i) => (i === index ? { ...m, ...patch } : m));
}

/** The bot message an answer event belongs to: by id, else the open placeholder. */
function answerIndex(messages: ChatMessage[], messageId: string): number {
  const byId = messages.findIndex((m) => m.role === "assistant" && m.id === messageId);
  if (byId !== -1) return byId;
  return messages.findIndex((m) => m.role === "assistant" && m.status === "streaming" && !m.id);
}

/** Questions sent but not acknowledged: resent after a reconnect. */
export function unacknowledged(state: ChatState): ChatMessage[] {
  return state.messages.filter((m) => m.role === "user" && m.status === "sending");
}

/** A turn is in flight: acknowledged, answer not finished. */
export function awaitingAnswer(state: ChatState): boolean {
  return state.messages.some((m) => m.role === "assistant" && m.status === "streaming");
}

function onServer(state: ChatState, event: ServerEvent, now: number): ChatState {
  const messages = state.messages;
  switch (event.type) {
    case "ack": {
      const index = messages.findIndex((m) => m.role === "user" && m.status === "sending");
      const acked = index === -1 ? messages : update(messages, index, { id: event.message_id, status: "sent" });
      return {
        ...state,
        conversationId: event.conversation_id,
        messages: [...acked, blank("assistant", now, {})],
        notice: null,
      };
    }
    case "status": {
      const index = messages.findIndex((m) => m.role === "assistant" && m.status === "streaming");
      return index === -1 ? state : { ...state, messages: update(messages, index, { stage: event.stage }) };
    }
    case "sources": {
      const index = answerIndex(messages, event.message_id);
      if (index === -1) {
        // a replayed answer (resume): no placeholder exists
        const replayed = blank("assistant", now, { id: event.message_id, sources: event.items });
        return { ...state, messages: [...messages, replayed] };
      }
      return {
        ...state,
        messages: update(messages, index, { id: event.message_id, sources: event.items }),
      };
    }
    case "token": {
      const index = answerIndex(messages, event.message_id);
      if (index === -1) return state;
      const current = messages[index];
      return {
        ...state,
        messages: update(messages, index, { id: event.message_id, text: (current?.text ?? "") + event.text }),
      };
    }
    case "final": {
      const index = answerIndex(messages, event.message_id);
      if (index === -1) return state;
      return {
        ...state,
        conversationId: event.conversation_id,
        lastMessageId: event.message_id,
        messages: update(messages, index, {
          id: event.message_id,
          status: "done",
          stage: null,
          fallback: event.fallback,
          office: event.office,
        }),
      };
    }
    case "error": {
      // The question was refused or the turn failed: mark it, drop the bot placeholder.
      let next = messages.filter((m) => !(m.role === "assistant" && m.status === "streaming" && !m.text));
      const index = next.findIndex((m) => m.role === "user" && m.status === "sending");
      if (index !== -1) next = update(next, index, { status: "failed" });
      return { ...state, messages: next, notice: { code: event.code, message: event.message } };
    }
    case "pong":
      return state;
  }
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "send":
      return {
        ...state,
        notice: null,
        messages: [
          ...state.messages,
          blank("user", action.now, { localId: action.localId, text: action.text }),
        ],
      };
    case "server":
      return onServer(state, action.event, action.now);
    case "connection":
      return { ...state, connection: action.connection };
    case "history": {
      // Keep anything typed before the history arrived (it is newer).
      const pending = state.messages.filter((m) => !m.id);
      const last = [...action.messages].reverse().find((m) => m.role === "assistant" && m.id);
      return {
        ...state,
        conversationId: action.conversationId,
        lastMessageId: last?.id ?? state.lastMessageId,
        messages: [...action.messages, ...pending],
      };
    }
    case "rated":
      return {
        ...state,
        messages: state.messages.map((m) => (m.id === action.id ? { ...m, rating: action.rating } : m)),
      };
    case "dismissNotice":
      return { ...state, notice: null };
    case "reset":
      return { ...initialState(), connection: state.connection };
  }
}
