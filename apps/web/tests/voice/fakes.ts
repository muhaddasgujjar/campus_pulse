/** Fakes for browser voice APIs in jsdom (no microphone, no speech engine). */

import type { RecorderDeps } from "@/lib/voice/recorder";
import type {
  RecognitionErrorEvent,
  RecognitionEvent,
  SpeechRecognitionLike,
} from "@/lib/voice/support";

export class FakeRecognition implements SpeechRecognitionLike {
  static instances: FakeRecognition[] = [];
  lang = "";
  continuous = false;
  interimResults = false;
  started = 0;
  stopped = false;
  onresult: ((event: RecognitionEvent) => void) | null = null;
  onerror: ((event: RecognitionErrorEvent) => void) | null = null;
  onend: (() => void) | null = null;

  constructor() {
    FakeRecognition.instances.push(this);
  }

  static latest(): FakeRecognition {
    const last = FakeRecognition.instances[FakeRecognition.instances.length - 1];
    if (!last) throw new Error("no recognition started");
    return last;
  }

  start(): void {
    this.started += 1;
  }

  stop(): void {
    this.stopped = true;
  }

  abort(): void {
    this.stopped = true;
  }

  /** Emit results: [text, isFinal] pairs for the current session. */
  say(...results: [string, boolean][]): void {
    const list = results.map(([transcript, isFinal]) => {
      const result = { isFinal, length: 1, 0: { transcript } };
      return result;
    });
    this.onresult?.({
      resultIndex: 0,
      results: Object.assign(list, { length: list.length }),
    });
  }
}

export class FakeMediaRecorder {
  static isTypeSupported(type: string): boolean {
    return type === "audio/webm;codecs=opus";
  }
  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: MediaStream, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "";
  }

  start(): void {
    this.state = "recording";
  }

  stop(): void {
    this.state = "inactive";
    this.ondataavailable?.({
      data: new Blob([new Uint8Array([0x1a, 0x45, 0xdf, 0xa3, 1, 2, 3])], { type: this.mimeType }),
    } as BlobEvent);
    this.onstop?.();
  }
}

export function fakeStream(): MediaStream {
  const track = { stop: () => undefined };
  return { getTracks: () => [track] } as unknown as MediaStream;
}

export function fakeDeps(overrides: Partial<RecorderDeps> = {}): RecorderDeps & { clock: { now: number } } {
  const clock = { now: 0 };
  return {
    getUserMedia: async () => fakeStream(),
    MediaRecorder: FakeMediaRecorder as unknown as typeof MediaRecorder,
    Recognition: FakeRecognition,
    levelMeter: () => ({ read: () => 0.5, close: () => undefined }),
    now: () => clock.now,
    clock,
    ...overrides,
  };
}

export function deniedDeps(): RecorderDeps {
  return fakeDeps({
    getUserMedia: async () => {
      throw Object.assign(new Error("denied"), { name: "NotAllowedError" });
    },
  });
}
