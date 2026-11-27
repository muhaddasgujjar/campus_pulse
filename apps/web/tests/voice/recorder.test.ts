import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MicPermissionError, VoiceRecorder } from "@/lib/voice/recorder";
import { formatDuration, pickMimeType } from "@/lib/voice/support";

import { deniedDeps, fakeDeps, FakeRecognition } from "./fakes";

describe("VoiceRecorder", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeRecognition.instances = [];
  });
  afterEach(() => vi.useRealTimers());

  it("records audio and builds the live transcript in the chosen language", async () => {
    const deps = fakeDeps();
    const updates: string[] = [];
    const recorder = new VoiceRecorder("ur", (u) => updates.push(u.transcript), () => undefined, deps);
    await recorder.start();
    const recognition = FakeRecognition.latest();
    expect(recognition).toMatchObject({ lang: "ur-PK", continuous: true, interimResults: true });
    recognition.say(["فیس کتنی", false]);
    expect(updates.at(-1)).toBe("فیس کتنی");
    recognition.say(["فیس کتنی ہے", true]);
    deps.clock.now = 4200;
    const result = await recorder.stop();
    expect(result).toMatchObject({ transcript: "فیس کتنی ہے", recognized: true, seconds: 4.2 });
    expect(result.blob?.type).toBe("audio/webm;codecs=opus");
    expect(recognition.stopped).toBe(true);
  });

  it("keeps earlier words when the browser restarts recognition after a pause", async () => {
    const recorder = new VoiceRecorder("en", () => undefined, () => undefined, fakeDeps());
    await recorder.start();
    const recognition = FakeRecognition.latest();
    recognition.say(["What are the fees", true]);
    recognition.onend?.(); // Chrome ends the session after silence
    expect(recognition.started).toBe(2);
    recognition.say(["for BSCS", true]); // the new session reports only its own results
    expect((await recorder.stop()).transcript).toBe("What are the fees for BSCS");
  });

  it("stops at the 60 second limit", async () => {
    const deps = fakeDeps();
    const onLimit = vi.fn();
    const recorder = new VoiceRecorder("en", () => undefined, onLimit, deps);
    await recorder.start();
    deps.clock.now = 59_000;
    vi.advanceTimersByTime(100);
    expect(onLimit).not.toHaveBeenCalled();
    deps.clock.now = 60_000;
    vi.advanceTimersByTime(100);
    expect(onLimit).toHaveBeenCalled();
    expect((await recorder.stop()).seconds).toBe(60);
  });

  it("marks the transcript as not live when recognition fails (server fallback)", async () => {
    const recorder = new VoiceRecorder("en", () => undefined, () => undefined, fakeDeps());
    await recorder.start();
    FakeRecognition.latest().onerror?.({ error: "network" });
    const result = await recorder.stop();
    expect(result.recognized).toBe(false);
    expect(result.blob).not.toBeNull();
  });

  it("works without recognition (audio only)", async () => {
    const recorder = new VoiceRecorder("en", () => undefined, () => undefined, fakeDeps({ Recognition: null }));
    expect(recorder.hasLiveTranscript).toBe(false);
    await recorder.start();
    const result = await recorder.stop();
    expect(result).toMatchObject({ transcript: "", recognized: false });
    expect(result.blob).not.toBeNull();
  });

  it("reports a denied microphone", async () => {
    const recorder = new VoiceRecorder("en", () => undefined, () => undefined, deniedDeps());
    await expect(recorder.start()).rejects.toBeInstanceOf(MicPermissionError);
  });
});

describe("voice helpers", () => {
  it("formats durations and picks a recordable type", () => {
    expect(formatDuration(7.9)).toBe("0:07");
    expect(formatDuration(60)).toBe("1:00");
    expect(pickMimeType((t) => t === "audio/mp4")).toBe("audio/mp4");
    expect(pickMimeType(() => false)).toBe("");
  });
});
