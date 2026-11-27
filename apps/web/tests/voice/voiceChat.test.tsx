import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatScreen } from "@/components/chat/ChatScreen";
import type { RecorderDeps } from "@/lib/voice/recorder";
import type { UseChatOptions } from "@/lib/chat/useChat";

import { answerEvents, asWebSocket, FakeWebSocket } from "../chat/fakeSocket";
import { deniedDeps, fakeDeps, FakeRecognition } from "./fakes";

const OPTIONS: UseChatOptions = {
  wsUrl: "ws://api.test",
  apiUrl: "http://api.test",
  socket: { WebSocketImpl: asWebSocket, random: () => 0.5 },
};

function mockFetch(transcribe: () => Response = () => Response.json({ transcript: "Exam office phone number?" })) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/config")) {
      return Response.json({
        institution_slug: "test",
        institution_name: "Test University",
        short_name: "TU",
        disclaimer: "Test disclaimer.",
        starter_questions: [],
      });
    }
    if (url.includes("/api/voice/transcribe")) return transcribe();
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openChat(deps: RecorderDeps) {
  render(<ChatScreen chatOptions={OPTIONS} voiceOptions={{ enabled: true, deps }} />);
  await screen.findByText("Test disclaimer.");
  act(() => FakeWebSocket.latest().open());
  return FakeWebSocket.latest();
}

async function startRecording() {
  fireEvent.click(screen.getByRole("button", { name: "Record a voice message" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Send voice message" })).toBeEnabled(),
  );
}

describe("voice messages", () => {
  beforeEach(() => {
    FakeWebSocket.reset();
    FakeRecognition.instances = [];
    window.localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the mic only while the input is empty", async () => {
    mockFetch();
    await openChat(fakeDeps());
    const box = screen.getByLabelText("Type a message");
    expect(screen.getByRole("button", { name: "Record a voice message" })).toBeInTheDocument();
    fireEvent.change(box, { target: { value: "hi" } });
    expect(screen.queryByRole("button", { name: "Record a voice message" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  it("sends the live transcript as a voice message and offers Edit and resend", async () => {
    mockFetch();
    const deps = fakeDeps();
    const ws = await openChat(deps);
    await startRecording();
    expect(screen.getByText(/may send audio to your browser's speech service/)).toBeInTheDocument();
    act(() => FakeRecognition.latest().say(["What are the fees for BSCS?", true]));
    expect(screen.getByText("What are the fees for BSCS?")).toBeInTheDocument();
    deps.clock.now = 3400;
    fireEvent.click(screen.getByRole("button", { name: "Send voice message" }));
    await waitFor(() => expect(ws.sentOfType("user_message")).toHaveLength(1));
    expect(ws.sentOfType("user_message")[0]).toMatchObject({
      text: "What are the fees for BSCS?",
      modality: "voice",
    });
    expect(screen.getByText("Voice message · 0:03")).toBeInTheDocument();
    emitAnswer(ws);
    fireEvent.click(screen.getByRole("button", { name: "Edit and resend" }));
    expect(screen.getByLabelText("Type a message")).toHaveValue("What are the fees for BSCS?");
  });

  it("uploads the recording when the browser cannot transcribe", async () => {
    const fetchMock = mockFetch();
    const ws = await openChat(fakeDeps({ Recognition: null }));
    await startRecording();
    expect(screen.getByText("Recording… the transcript appears after sending.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send voice message" }));
    await waitFor(() => expect(ws.sentOfType("user_message")).toHaveLength(1));
    expect(ws.sentOfType("user_message")[0]).toMatchObject({
      text: "Exam office phone number?",
      modality: "voice",
    });
    const upload = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/voice/transcribe"));
    expect(String(upload?.[0])).toContain("lang=en");
    expect(upload?.[1]?.method).toBe("POST");
  });

  it("asks the student to type when the server fallback is not configured", async () => {
    mockFetch(() => new Response("{}", { status: 503 }));
    const ws = await openChat(fakeDeps({ Recognition: null }));
    await startRecording();
    fireEvent.click(screen.getByRole("button", { name: "Send voice message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please type your question.");
    expect(ws.sentOfType("user_message")).toHaveLength(0);
  });

  it("explains how to allow the microphone when access is denied", async () => {
    mockFetch();
    await openChat(deniedDeps());
    fireEvent.click(screen.getByRole("button", { name: "Record a voice message" }));
    expect(await screen.findByRole("dialog", { name: "Allow microphone access" })).toBeInTheDocument();
  });

  it("cancels without sending anything", async () => {
    mockFetch();
    const ws = await openChat(fakeDeps());
    await startRecording();
    act(() => FakeRecognition.latest().say(["never mind", true]));
    fireEvent.click(screen.getByRole("button", { name: "Cancel recording" }));
    expect(screen.getByRole("button", { name: "Record a voice message" })).toBeInTheDocument();
    expect(ws.sentOfType("user_message")).toHaveLength(0);
  });

  it("switches the spoken language and remembers it", async () => {
    mockFetch();
    await openChat(fakeDeps());
    await startRecording();
    fireEvent.click(screen.getByRole("button", { name: "اردو" }));
    await waitFor(() => expect(FakeRecognition.latest().lang).toBe("ur-PK"));
    expect(window.localStorage.getItem("campus-pulse.voice-lang")).toBe("ur");
  });
});

function emitAnswer(ws: FakeWebSocket) {
  act(() => {
    ws.emit({ type: "ack", message_id: "q1", conversation_id: "c1" });
    for (const event of answerEvents({ messageId: "a1", conversationId: "c1", text: "Rs 1,000." })) {
      ws.emit(event);
    }
  });
}
