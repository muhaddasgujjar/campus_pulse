import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatScreen } from "@/components/chat/ChatScreen";
import type { UseChatOptions } from "@/lib/chat/useChat";

import { answerEvents, asWebSocket, FakeWebSocket } from "./fakeSocket";

// Stable options object: the hook reconnects when it changes.
const OPTIONS: UseChatOptions = {
  wsUrl: "ws://api.test",
  apiUrl: "http://api.test",
  socket: { WebSocketImpl: asWebSocket, random: () => 0.5 },
};

const CONFIG = {
  institution_slug: "test",
  institution_name: "Test University",
  short_name: "TU",
  disclaimer: "Test disclaimer: confirm with the office.",
  starter_questions: ["What are the fees?", "Exam office phone?"],
};

const FEE_SOURCE = {
  title: "Test Fee Page",
  office: "Test Office",
  url: null,
  last_verified: "2026-10-05",
  expired: false,
};

function mockFetch(routes: Record<string, unknown> = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/config")) return Response.json(CONFIG);
    if (url.endsWith("/api/feedback") && init?.method === "POST") {
      return new Response(null, { status: 204 });
    }
    for (const [path, body] of Object.entries(routes)) {
      if (url.endsWith(path)) return Response.json(body);
    }
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openChat() {
  render(<ChatScreen chatOptions={OPTIONS} />);
  await screen.findByRole("list", { name: "Starter questions" });
  act(() => FakeWebSocket.latest().open());
  return FakeWebSocket.latest();
}

function emit(ws: FakeWebSocket, ...events: object[]) {
  act(() => {
    for (const event of events) ws.emit(event);
  });
}

describe("ChatScreen", () => {
  beforeEach(() => {
    FakeWebSocket.reset();
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the greeting, starter questions and the disclaimer from /api/config", async () => {
    mockFetch();
    await openChat();
    expect(screen.getByText(/Ask me anything about LGU/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "What are the fees?" })).toBeInTheDocument();
    expect(screen.getByText("Test disclaimer: confirm with the office.")).toBeInTheDocument();
    expect(screen.getByText("Online")).toBeInTheDocument();
  });

  it("sends a question and renders the streamed answer with badge and source chip", async () => {
    mockFetch();
    const ws = await openChat();
    fireEvent.click(screen.getByRole("button", { name: "What are the fees?" }));
    expect(ws.sentOfType("user_message")).toEqual([
      { type: "user_message", conversation_id: null, text: "What are the fees?", modality: "text" },
    ]);
    emit(ws, { type: "ack", message_id: "q1", conversation_id: "c1" });
    emit(ws, { type: "status", stage: "searching" });
    expect(screen.getByText("Searching university records…")).toBeInTheDocument();
    emit(
      ws,
      ...answerEvents({
        messageId: "a1",
        conversationId: "c1",
        text: "Tuition is Rs 1,000 per credit hour.\nSource: Test Fee Page · last verified Mon, 5 Oct 2026",
        sources: [FEE_SOURCE],
      }),
    );
    expect(screen.getByText("Tuition is Rs 1,000 per credit hour.")).toBeInTheDocument();
    expect(screen.queryByText(/^Source: /)).not.toBeInTheDocument();
    expect(screen.getByText("Verified by Test Office · 5 Oct 2026")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Test Fee Page" }));
    const sheet = screen.getByRole("dialog", { name: "Source" });
    expect(within(sheet).getByText("Test Office")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem("campus-pulse.chat") ?? "{}")).toEqual({
      conversationId: "c1",
      lastMessageId: "a1",
    });
  });

  it("waits for the first ack before sending a second question (one conversation)", async () => {
    mockFetch();
    const ws = await openChat();
    const box = screen.getByLabelText("Type a message");
    fireEvent.change(box, { target: { value: "First?" } });
    fireEvent.keyDown(box, { key: "Enter" });
    fireEvent.change(box, { target: { value: "Second?" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(ws.sentOfType("user_message")).toHaveLength(1);
    emit(ws, { type: "ack", message_id: "q1", conversation_id: "c1" });
    const sent = ws.sentOfType("user_message");
    expect(sent).toHaveLength(2);
    expect(sent[1]).toMatchObject({ text: "Second?", conversation_id: "c1" });
  });

  it("shows the fallback card with tap-to-call phone and email", async () => {
    mockFetch();
    const ws = await openChat();
    fireEvent.click(screen.getByRole("button", { name: "Exam office phone?" }));
    emit(ws, { type: "ack", message_id: "q1", conversation_id: "c1" });
    emit(
      ws,
      ...answerEvents({
        messageId: "a1",
        conversationId: "c1",
        text: "I don't have verified information on this.",
        fallback: true,
        office: { name: "Test Office", phones: ["000-0000000"], email: "test@example.edu", hours: null },
      }),
    );
    expect(screen.getByText("I don't have verified information on this.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Call 000-0000000" })).toHaveAttribute(
      "href",
      "tel:0000000000",
    );
    expect(screen.getByRole("link", { name: "Email test@example.edu" })).toHaveAttribute(
      "href",
      "mailto:test@example.edu",
    );
  });

  it("sends thumbs-down feedback with a reason", async () => {
    const fetchMock = mockFetch();
    const ws = await openChat();
    fireEvent.click(screen.getByRole("button", { name: "What are the fees?" }));
    emit(ws, { type: "ack", message_id: "q1", conversation_id: "c1" });
    emit(ws, ...answerEvents({ messageId: "a1", conversationId: "c1", text: "Rs 1,000." }));
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" }));
    fireEvent.click(screen.getByLabelText("The information is outdated"));
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for the feedback");
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/feedback"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      message_id: "a1",
      rating: -1,
      reason: "outdated",
    });
    expect(screen.getByRole("button", { name: "Not helpful" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the rate-limit notice and lets the student retry", async () => {
    mockFetch();
    const ws = await openChat();
    fireEvent.click(screen.getByRole("button", { name: "What are the fees?" }));
    emit(ws, {
      type: "error",
      code: "rate_limited",
      message: "You're sending messages fast. Please wait a moment.",
      retry_after: 600,
    });
    expect(screen.getByRole("alert")).toHaveTextContent("You're sending messages fast.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(ws.sentOfType("user_message")).toHaveLength(2);
  });

  it("restores the history after a reload and resumes after a reconnect", async () => {
    window.localStorage.setItem(
      "campus-pulse.chat",
      JSON.stringify({ conversationId: "c1", lastMessageId: "a1" }),
    );
    mockFetch({
      "/api/conversations/c1/messages": [
        { id: "q1", role: "user", modality: "text", content: "Old question", sources: [], created_at: "2026-10-05T09:00:00Z" },
        { id: "a1", role: "assistant", modality: "text", content: "Old answer", sources: [], created_at: "2026-10-05T09:00:01Z" },
      ],
    });
    render(<ChatScreen chatOptions={OPTIONS} />);
    expect(await screen.findByText("Old answer")).toBeInTheDocument();
    const first = FakeWebSocket.latest();
    act(() => first.open());
    expect(first.sentOfType("resume")).toEqual([]); // first open: history came over REST
    vi.useFakeTimers();
    try {
      act(() => first.drop());
      expect(screen.getByText("Connection lost. Reconnecting…")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(1000));
      const second = FakeWebSocket.latest();
      act(() => second.open());
      expect(second.sentOfType("resume")).toEqual([
        { type: "resume", conversation_id: "c1", last_message_id: "a1" },
      ]);
      emit(second, ...answerEvents({ messageId: "a2", conversationId: "c1", text: "Missed answer" }));
    } finally {
      vi.useRealTimers();
    }
    await waitFor(() => expect(screen.getByText("Missed answer")).toBeInTheDocument());
  });
});
