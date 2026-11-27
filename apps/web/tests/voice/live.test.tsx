import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatScreen } from "@/components/chat/ChatScreen";
import type { UseChatOptions } from "@/lib/chat/useChat";
import { isEcho, type LiveDeps, type LiveHandlers, LiveSession, type LiveState } from "@/lib/voice/live";
import { Speaker, type SynthLike } from "@/lib/voice/speak";

import { answerEvents, asWebSocket, FakeWebSocket } from "../chat/fakeSocket";
import { FakeRecognition } from "./fakes";

class FakeUtterance {
  voice: SpeechSynthesisVoice | null = null;
  lang = "";
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public text: string) {}
}

class FakeSynth implements SynthLike {
  spoken: FakeUtterance[] = [];
  cancelled = 0;
  constructor(private voices = [{ lang: "en-US", name: "Test English" }]) {}
  speak(u: SpeechSynthesisUtterance) {
    this.spoken.push(u as unknown as FakeUtterance);
  }
  cancel() {
    this.cancelled += 1;
  }
  getVoices() {
    return this.voices as SpeechSynthesisVoice[];
  }
  finishAll() {
    // finish utterances one by one until nothing new is queued
    for (let i = 0; i < 20 && this.spoken.length; i += 1) {
      const before = this.spoken.length;
      this.spoken.at(-1)?.onend?.();
      if (this.spoken.length === before) break;
    }
  }
}

function makeDeps(synth = new FakeSynth()): LiveDeps & { synth: FakeSynth } {
  return {
    Recognition: FakeRecognition,
    speaker: new Speaker(synth, FakeUtterance as unknown as typeof SpeechSynthesisUtterance),
    getUserMedia: null,
    levelMeter: () => null,
    synth,
  };
}

function makeSession(deps: LiveDeps) {
  const states: LiveState[] = [];
  const asked: string[] = [];
  const failed: string[] = [];
  const handlers: LiveHandlers = {
    onState: (s) => states.push(s),
    onHeard: () => undefined,
    onUtterance: (t) => asked.push(t),
    onLevel: () => undefined,
    onFail: (r) => failed.push(r),
  };
  return { session: new LiveSession("en", deps, handlers), states, asked, failed };
}

describe("isEcho", () => {
  it("treats repeated answer words as echo and new words as the student", () => {
    const speaking = "The exam office phone number is 042-37181828.";
    expect(isEcho("exam office phone number", speaking)).toBe(true);
    expect(isEcho("what about the library hours", speaking)).toBe(false);
    expect(isEcho("", speaking)).toBe(true);
  });
});

describe("LiveSession", () => {
  beforeEach(() => {
    FakeRecognition.instances = [];
  });

  it("listens, sends a finished phrase, speaks the answer, then listens again", async () => {
    const deps = makeDeps();
    const { session, states, asked } = makeSession(deps);
    await session.start();
    expect(session.current).toBe("listening");
    FakeRecognition.latest().say(["What are the fees", false]);
    expect(asked).toEqual([]);
    FakeRecognition.latest().say(["What are the fees for BSCS", true]);
    expect(asked).toEqual(["What are the fees for BSCS"]);
    expect(session.current).toBe("thinking");
    session.answer("Rs 1,000 per credit hour.\nSource: Test Page", true);
    expect(session.current).toBe("speaking");
    expect(deps.synth.spoken[0]?.text).toBe("rupees 1,000 per credit hour.");
    deps.synth.finishAll();
    expect(session.current).toBe("listening");
    expect(states).toEqual(["listening", "thinking", "speaking", "listening"]);
  });

  it("stops speaking when the student talks over the answer, but not for echo", async () => {
    const deps = makeDeps();
    const { session, asked } = makeSession(deps);
    await session.start();
    FakeRecognition.latest().say(["exam office number", true]);
    session.answer("The Exam Office phone number is 000-0000000.", true);
    FakeRecognition.latest().say(["exam office phone number", false]); // the speakers' echo
    expect(session.current).toBe("speaking");
    FakeRecognition.latest().say(["no wait what about hostels", true]); // barge-in
    expect(deps.synth.cancelled).toBeGreaterThan(0);
    expect(asked.at(-1)).toBe("no wait what about hostels");
    expect(session.current).toBe("thinking");
  });

  it("can be interrupted by a tap, muted and unmuted", async () => {
    const deps = makeDeps();
    const { session } = makeSession(deps);
    await session.start();
    FakeRecognition.latest().say(["question", true]);
    session.answer("A long answer.", false);
    session.interrupt();
    expect(session.current).toBe("listening");
    session.mute();
    expect(session.current).toBe("muted");
    FakeRecognition.latest().say(["ignored while muted", true]);
    session.unmute();
    expect(session.current).toBe("listening");
    expect(FakeRecognition.instances).toHaveLength(2); // a fresh recognition after unmute
  });

  it("keeps listening when the browser ends a recognition session", async () => {
    const { session } = makeSession(makeDeps());
    await session.start();
    const recognition = FakeRecognition.latest();
    recognition.onend?.();
    expect(recognition.started).toBe(2);
    session.end();
  });

  it("ends with a reason when the microphone is blocked or unsupported", async () => {
    const blocked = makeSession(makeDeps());
    await blocked.session.start();
    FakeRecognition.latest().onerror?.({ error: "not-allowed" });
    expect(blocked.failed).toEqual(["mic"]);
    const unsupported = makeSession({ ...makeDeps(), Recognition: null });
    await unsupported.session.start();
    expect(unsupported.failed).toEqual(["unsupported"]);
  });

  it("goes back to listening when there is no voice for the answer's language", async () => {
    const deps = makeDeps(new FakeSynth([{ lang: "en-US", name: "English only" }]));
    const states: LiveState[] = [];
    const noVoice = vi.fn();
    const session = new LiveSession("ur", deps, {
      onState: (s) => states.push(s),
      onHeard: () => undefined,
      onUtterance: () => undefined,
      onLevel: () => undefined,
      onFail: () => undefined,
      onNoVoice: noVoice,
    });
    await session.start();
    FakeRecognition.latest().say(["فیس کتنی ہے", true]);
    session.answer("فیس Rs 1,000 ہے۔", false);
    expect(noVoice).toHaveBeenCalledWith("ur");
    expect(session.current).toBe("listening");
  });
});

// --- live mode inside the chat -----------------------------------------------------------------

const OPTIONS: UseChatOptions = {
  wsUrl: "ws://api.test",
  apiUrl: "http://api.test",
  socket: { WebSocketImpl: asWebSocket, random: () => 0.5 },
};

function mockConfig() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        institution_slug: "test",
        institution_name: "Test University",
        short_name: "TU",
        disclaimer: "Test disclaimer.",
        starter_questions: [],
      }),
    ),
  );
}

describe("live mode in the chat", () => {
  beforeEach(() => {
    FakeWebSocket.reset();
    FakeRecognition.instances = [];
    window.localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("is disabled where the browser has no speech recognition", async () => {
    mockConfig();
    render(<ChatScreen chatOptions={OPTIONS} liveOptions={{ enabled: false }} />);
    await screen.findByText("Test disclaimer.");
    const button = screen.getByRole("button", { name: "Live mode" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Live mode works in Chrome and Edge");
  });

  it("sends spoken questions as voice turns and speaks the answers", async () => {
    mockConfig();
    const deps = makeDeps();
    render(<ChatScreen chatOptions={OPTIONS} liveOptions={{ enabled: true, deps }} />);
    await screen.findByText("Test disclaimer.");
    act(() => FakeWebSocket.latest().open());
    const ws = FakeWebSocket.latest();
    fireEvent.click(screen.getByRole("button", { name: "Live mode" }));
    expect(screen.getByRole("dialog", { name: "Live mode" })).toBeInTheDocument();
    await act(async () => undefined); // session.start()
    act(() => FakeRecognition.latest().say(["Exam office phone number?", true]));
    expect(ws.sentOfType("user_message")).toEqual([
      expect.objectContaining({ text: "Exam office phone number?", modality: "voice" }),
    ]);
    act(() => {
      ws.emit({ type: "ack", message_id: "q1", conversation_id: "c1" });
      for (const e of answerEvents({ messageId: "a1", conversationId: "c1", text: "Exam Office: phone 000-0000000." })) {
        ws.emit(e);
      }
    });
    expect(deps.synth.spoken[0]?.text).toBe("Exam Office: phone 000-0000000.");
    expect(screen.getByText("Speaking… tap to interrupt")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Interrupt the answer" }));
    expect(screen.getByText("Listening…")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "End live mode" }));
    expect(screen.queryByRole("dialog", { name: "Live mode" })).not.toBeInTheDocument();
    // the live turn is part of the same chat history
    expect(screen.getByText("Exam office phone number?")).toBeInTheDocument();
  });

  it("closes with a note when the microphone is blocked", async () => {
    mockConfig();
    const deps = makeDeps();
    render(<ChatScreen chatOptions={OPTIONS} liveOptions={{ enabled: true, deps }} />);
    await screen.findByText("Test disclaimer.");
    fireEvent.click(screen.getByRole("button", { name: "Live mode" }));
    await act(async () => undefined);
    act(() => FakeRecognition.latest().onerror?.({ error: "not-allowed" }));
    expect(screen.queryByRole("dialog", { name: "Live mode" })).not.toBeInTheDocument();
    expect(screen.getByText(/allow microphone access to talk hands-free/)).toBeInTheDocument();
  });
});
