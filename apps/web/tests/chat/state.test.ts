import { describe, expect, it } from "vitest";

import type { ServerEvent } from "@/lib/chat/protocol";
import {
  awaitingAnswer,
  type ChatState,
  chatReducer,
  initialState,
  unacknowledged,
} from "@/lib/chat/state";

const NOW = 1_700_000_000_000;

function run(state: ChatState, ...events: ServerEvent[]): ChatState {
  return events.reduce((s, event) => chatReducer(s, { type: "server", event, now: NOW }), state);
}

function sent(text = "What are the fees?"): ChatState {
  return chatReducer(initialState(), { type: "send", localId: "u1", text, now: NOW });
}

const answer = (id: string, text: string, conversationId = "c1"): ServerEvent[] => [
  { type: "sources", message_id: id, items: [] },
  { type: "token", message_id: id, text },
  {
    type: "final",
    message_id: id,
    conversation_id: conversationId,
    fallback: false,
    cache_hit: false,
    office: null,
    replay: false,
  },
];

describe("chatReducer", () => {
  it("runs one turn: sending -> ack -> status -> answer", () => {
    let state = sent();
    expect(unacknowledged(state)).toHaveLength(1);
    state = run(state, { type: "ack", message_id: "q1", conversation_id: "c1" });
    expect(state.conversationId).toBe("c1");
    expect(state.messages.map((m) => [m.role, m.status])).toEqual([
      ["user", "sent"],
      ["assistant", "streaming"],
    ]);
    expect(awaitingAnswer(state)).toBe(true);
    state = run(state, { type: "status", stage: "searching" });
    expect(state.messages[1]?.stage).toBe("searching");
    state = run(
      state,
      { type: "sources", message_id: "a1", items: [] },
      { type: "token", message_id: "a1", text: "Rs " },
      { type: "token", message_id: "a1", text: "1,000" },
    );
    expect(state.messages[1]?.text).toBe("Rs 1,000");
    state = run(state, answer("a1", "")[2] as ServerEvent);
    expect(state.messages[1]).toMatchObject({ id: "a1", status: "done", stage: null });
    expect(state.lastMessageId).toBe("a1");
    expect(awaitingAnswer(state)).toBe(false);
  });

  it("adds replayed answers (resume) that have no placeholder", () => {
    const state = run(initialState("c1", "a0"), ...answer("a1", "Missed answer"));
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({ role: "assistant", id: "a1", text: "Missed answer" });
    expect(state.lastMessageId).toBe("a1");
  });

  it("marks a refused question as failed and shows the notice", () => {
    const state = run(sent(), {
      type: "error",
      code: "rate_limited",
      message: "You're sending messages fast. Please wait a moment.",
    });
    expect(state.messages[0]?.status).toBe("failed");
    expect(state.notice?.code).toBe("rate_limited");
  });

  it("drops an empty bot placeholder when the turn fails after the ack", () => {
    const acked = run(sent(), { type: "ack", message_id: "q1", conversation_id: "c1" });
    const state = run(acked, { type: "error", code: "internal", message: "Something went wrong." });
    expect(state.messages.map((m) => m.role)).toEqual(["user"]);
  });

  it("keeps questions typed before the history loaded", () => {
    const history = run(initialState(), ...answer("a1", "Old answer")).messages;
    const state = chatReducer(sent("New question"), {
      type: "history",
      messages: history,
      conversationId: "c1",
    });
    expect(state.messages.map((m) => m.text)).toEqual(["Old answer", "New question"]);
    expect(state.lastMessageId).toBe("a1");
  });

  it("records a rating and resets to a new chat", () => {
    let state = run(initialState(), ...answer("a1", "Answer"));
    state = chatReducer(state, { type: "rated", id: "a1", rating: -1 });
    expect(state.messages[0]?.rating).toBe(-1);
    state = chatReducer({ ...state, connection: "online" }, { type: "reset" });
    expect(state).toMatchObject({ messages: [], conversationId: null, connection: "online" });
  });
});
