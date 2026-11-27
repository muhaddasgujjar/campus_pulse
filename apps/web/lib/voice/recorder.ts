/**
 * Voice message recorder (VOI-1, DESIGN.md 5.1): MediaRecorder for the audio plus, where the
 * browser has it, live speech recognition for the transcript. Audio stays in memory: it is
 * only uploaded when the browser cannot transcribe it itself, and it is never stored.
 *
 * Browser APIs are injected (RecorderDeps) so the logic is testable without a microphone.
 */

import {
  RECOGNITION_LOCALE,
  type RecognitionEvent,
  recognitionCtor,
  type SpeechLang,
  type SpeechRecognitionCtor,
  type SpeechRecognitionLike,
  pickMimeType,
} from "@/lib/voice/support";

export const MAX_RECORDING_SECONDS = 60;

export class MicPermissionError extends Error {
  constructor() {
    super("microphone permission denied");
    this.name = "MicPermissionError";
  }
}

export type RecorderDeps = {
  getUserMedia: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  MediaRecorder: typeof MediaRecorder | null;
  Recognition: SpeechRecognitionCtor | null;
  /** Returns a function that reads the current input level (0..1), or null. */
  levelMeter: (stream: MediaStream) => { read: () => number; close: () => void } | null;
  now: () => number;
};

export type RecorderUpdate = {
  transcript: string; // final + interim text so far
  level: number; // 0..1, for the waveform
  seconds: number;
};

export type RecordingResult = {
  transcript: string;
  blob: Blob | null;
  mimeType: string;
  seconds: number;
  /** Recognition ran in the browser without failing (the transcript is live). */
  recognized: boolean;
};

export function browserLevelMeter(stream: MediaStream) {
  const Ctx =
    typeof window !== "undefined"
      ? (window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
      : undefined;
  if (!Ctx) return null;
  try {
    const ctx = new Ctx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.fftSize);
    return {
      read: () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) sum += ((v - 128) / 128) ** 2;
        return Math.min(1, Math.sqrt(sum / data.length) * 4);
      },
      close: () => void ctx.close().catch(() => undefined),
    };
  } catch {
    return null;
  }
}

export function browserRecorderDeps(): RecorderDeps {
  return {
    getUserMedia: (c) => navigator.mediaDevices.getUserMedia(c),
    MediaRecorder: typeof MediaRecorder !== "undefined" ? MediaRecorder : null,
    Recognition: recognitionCtor(),
    levelMeter: browserLevelMeter,
    now: () => Date.now(),
  };
}

/** Joins recognition results: every final result, then the current interim one. */
export function transcriptOf(event: RecognitionEvent): { final: string; interim: string } {
  let final = "";
  let interim = "";
  for (let i = 0; i < event.results.length; i += 1) {
    const result = event.results[i];
    const text = result?.[0]?.transcript ?? "";
    if (result?.isFinal) final += text;
    else interim += text;
  }
  return { final: final.trim(), interim: interim.trim() };
}

export class VoiceRecorder {
  private stream: MediaStream | null = null;
  private media: MediaRecorder | null = null;
  private recognition: SpeechRecognitionLike | null = null;
  private meter: ReturnType<RecorderDeps["levelMeter"]> = null;
  private chunks: Blob[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private startedAt = 0;
  private finalText = "";
  private sessionBase = ""; // finals from earlier recognition sessions (after a restart)
  private interimText = "";
  private recognitionFailed = false;
  private active = false;
  private mimeType = "";

  constructor(
    private readonly lang: SpeechLang,
    private readonly onUpdate: (update: RecorderUpdate) => void,
    private readonly onLimit: () => void,
    private readonly deps: RecorderDeps = browserRecorderDeps(),
    private readonly maxSeconds = MAX_RECORDING_SECONDS,
  ) {}

  get hasLiveTranscript(): boolean {
    return this.deps.Recognition !== null;
  }

  async start(): Promise<void> {
    try {
      this.stream = await this.deps.getUserMedia({ audio: true });
    } catch (error) {
      const name = (error as { name?: string })?.name;
      if (name === "NotAllowedError" || name === "SecurityError") throw new MicPermissionError();
      throw error;
    }
    this.active = true;
    this.startedAt = this.deps.now();
    const Recorder = this.deps.MediaRecorder;
    if (Recorder) {
      this.mimeType = pickMimeType((t) => Recorder.isTypeSupported(t));
      this.media = new Recorder(this.stream, this.mimeType ? { mimeType: this.mimeType } : undefined);
      this.mimeType = this.media.mimeType || this.mimeType;
      this.media.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) this.chunks.push(event.data);
      };
      this.media.start(250);
    }
    this.startRecognition();
    this.meter = this.deps.levelMeter(this.stream);
    this.timer = setInterval(() => this.tick(), 100);
  }

  private startRecognition(): void {
    const Recognition = this.deps.Recognition;
    if (!Recognition || this.recognitionFailed) return;
    const recognition = new Recognition();
    recognition.lang = RECOGNITION_LOCALE[this.lang];
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      const { final, interim } = transcriptOf(event);
      // A restarted session reports only its own results: keep earlier finals.
      this.interimText = interim;
      if (final) this.finalText = this.joinFinal(final);
      this.emit();
    };
    recognition.onerror = (event) => {
      if (event.error !== "no-speech" && event.error !== "aborted") this.recognitionFailed = true;
    };
    recognition.onend = () => {
      // Chrome ends a session after a pause: keep listening while recording.
      if (this.active && !this.recognitionFailed && this.recognition === recognition) {
        this.sessionBase = this.finalText;
        try {
          recognition.start();
        } catch {
          this.recognitionFailed = true;
        }
      }
    };
    this.recognition = recognition;
    this.sessionBase = "";
    try {
      recognition.start();
    } catch {
      this.recognitionFailed = true;
    }
  }

  private joinFinal(sessionFinal: string): string {
    return [this.sessionBase, sessionFinal].filter(Boolean).join(" ");
  }

  private seconds(): number {
    return (this.deps.now() - this.startedAt) / 1000;
  }

  private emit(level = 0): void {
    const transcript = [this.finalText, this.interimText].filter(Boolean).join(" ");
    this.onUpdate({ transcript, level, seconds: this.seconds() });
  }

  private tick(): void {
    if (!this.active) return;
    this.emit(this.meter?.read() ?? 0);
    if (this.seconds() >= this.maxSeconds) this.onLimit();
  }

  private release(): void {
    this.active = false;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    const recognition = this.recognition;
    this.recognition = null;
    try {
      recognition?.stop();
    } catch {
      // already stopped
    }
    this.meter?.close();
    this.meter = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  /** Stop and return the transcript and (in memory) the audio. */
  async stop(): Promise<RecordingResult> {
    const seconds = Math.min(this.seconds(), this.maxSeconds);
    const media = this.media;
    const stopped =
      media && media.state !== "inactive"
        ? new Promise<void>((resolve) => {
            media.onstop = () => resolve();
            media.stop();
          })
        : Promise.resolve();
    this.release();
    await stopped;
    const transcript = [this.finalText, this.interimText].filter(Boolean).join(" ").trim();
    const blob = this.chunks.length ? new Blob(this.chunks, { type: this.mimeType || "audio/webm" }) : null;
    this.chunks = [];
    return {
      transcript,
      blob,
      mimeType: this.mimeType || "audio/webm",
      seconds,
      recognized: this.deps.Recognition !== null && !this.recognitionFailed,
    };
  }

  /** Stop and throw everything away. */
  cancel(): void {
    if (this.media && this.media.state !== "inactive") this.media.stop();
    this.release();
    this.chunks = [];
  }
}
