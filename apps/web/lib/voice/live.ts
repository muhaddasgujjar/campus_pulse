/**
 * Live mode (VOI-5, DESIGN.md 5.2): hands-free chat on browser speech only. The server sees
 * text, exactly like typed questions, so live mode costs no extra server resources.
 *
 * listening -> (a finished phrase) -> thinking -> (the answer) -> speaking -> listening
 * Barge-in: speech heard while the answer plays stops the playback. Speech that mostly repeats
 * the answer's own words is the speakers' echo, not the student, and is ignored. Tapping the
 * screen always interrupts. The answer itself is still stored in the chat.
 */

import { browserLevelMeter, type RecorderDeps } from "@/lib/voice/recorder";
import { type Speaker, speechLangOf, spokenText } from "@/lib/voice/speak";
import {
  RECOGNITION_LOCALE,
  type RecognitionEvent,
  recognitionCtor,
  type SpeechLang,
  type SpeechRecognitionCtor,
  type SpeechRecognitionLike,
} from "@/lib/voice/support";

export type LiveState = "starting" | "listening" | "thinking" | "speaking" | "muted";
export type LiveEndReason = "mic" | "network" | "unsupported" | "language";

const MAX_NETWORK_RETRIES = 3;
const RESTART_DELAY_MS = 250;

export type LiveHandlers = {
  onState: (state: LiveState) => void;
  /** What the student is saying (interim) or said (final). */
  onHeard: (text: string) => void;
  /** A finished phrase: send it as a voice question. */
  onUtterance: (text: string) => void;
  onLevel: (level: number) => void;
  /** Live mode cannot continue: close and return to the chat with a note. */
  onFail: (reason: LiveEndReason) => void;
  /** The answer could not be spoken (no voice for its language on this device). */
  onNoVoice?: (lang: SpeechLang) => void;
  /** An Urdu answer is read by the Hindi voice (no Urdu voice on this device). */
  onUrduViaHindi?: () => void;
};

export type LiveDeps = {
  Recognition: SpeechRecognitionCtor | null;
  speaker: Speaker | null;
  getUserMedia: RecorderDeps["getUserMedia"] | null;
  levelMeter: RecorderDeps["levelMeter"];
};

export function browserLiveDeps(speaker: Speaker | null): LiveDeps {
  return {
    Recognition: recognitionCtor(),
    speaker,
    getUserMedia:
      typeof navigator !== "undefined" && navigator.mediaDevices?.getUserMedia
        ? (c) => navigator.mediaDevices.getUserMedia(c)
        : null,
    levelMeter: browserLevelMeter,
  };
}

function words(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((w) => w.length > 1);
}

/** True when most heard words appear in what is being spoken (the speakers' echo). */
export function isEcho(heard: string, speaking: string, threshold = 0.6): boolean {
  const heardWords = words(heard);
  if (heardWords.length === 0) return true;
  const spoken = new Set(words(speaking));
  const repeated = heardWords.filter((w) => spoken.has(w)).length;
  return repeated / heardWords.length >= threshold;
}

export class LiveSession {
  private recognition: SpeechRecognitionLike | null = null;
  private meter: ReturnType<LiveDeps["levelMeter"]> = null;
  private stream: MediaStream | null = null;
  private levelTimer: ReturnType<typeof setInterval> | null = null;
  private state: LiveState = "starting";
  private speakingText = "";
  private ended = false;
  private networkErrors = 0;
  private restartTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private lang: SpeechLang,
    private readonly deps: LiveDeps,
    private readonly handlers: LiveHandlers,
  ) {}

  get current(): LiveState {
    return this.state;
  }

  private set(state: LiveState): void {
    this.state = state;
    this.handlers.onState(state);
  }

  async start(): Promise<void> {
    if (!this.deps.Recognition || !this.deps.speaker) {
      this.handlers.onFail("unsupported");
      return;
    }
    if (this.deps.getUserMedia) {
      try {
        this.stream = await this.deps.getUserMedia({ audio: true });
        this.meter = this.deps.levelMeter(this.stream);
        this.levelTimer = setInterval(() => this.handlers.onLevel(this.meter?.read() ?? 0), 100);
      } catch (error) {
        const name = (error as { name?: string })?.name;
        if (name === "NotAllowedError" || name === "SecurityError") {
          this.handlers.onFail("mic");
          return;
        }
        // no level meter: live mode still works with recognition alone
      }
    }
    if (this.ended) return;
    this.listen();
  }

  private listen(): void {
    const Recognition = this.deps.Recognition;
    if (!Recognition || this.ended) return;
    const recognition = new Recognition();
    recognition.lang = RECOGNITION_LOCALE[this.lang];
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      this.networkErrors = 0;
      this.onResult(event);
    };
    recognition.onerror = (event) => {
      switch (event.error) {
        case "not-allowed":
        case "service-not-allowed":
        case "audio-capture":
          this.fail("mic");
          break;
        case "language-not-supported":
          this.fail("language");
          break;
        case "network":
          // Chrome's recognition service drops now and then: retry a few times first.
          this.networkErrors += 1;
          if (this.networkErrors > MAX_NETWORK_RETRIES) this.fail("network");
          break;
        default: // "no-speech", "aborted": keep listening
      }
    };
    recognition.onend = () => {
      // Sessions end after pauses: keep listening until the student ends live mode. A short
      // delay avoids Chrome rejecting a restart while the old session is still closing.
      if (this.ended || this.state === "muted" || this.recognition !== recognition) return;
      const delay = RESTART_DELAY_MS * Math.max(1, this.networkErrors);
      this.restartTimer = setTimeout(() => {
        this.restartTimer = null;
        if (this.ended || this.state === "muted" || this.recognition !== recognition) return;
        try {
          recognition.start();
        } catch {
          this.recognition = null;
          this.listen(); // a fresh session
        }
      }, delay);
    };
    this.recognition = recognition;
    try {
      recognition.start();
    } catch {
      this.fail("unsupported");
      return;
    }
    if (this.state === "starting") this.set("listening");
  }

  private onResult(event: RecognitionEvent): void {
    if (this.ended || this.state === "muted") return;
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const text = (result?.[0]?.transcript ?? "").trim();
      if (!text) continue;
      if (this.state === "speaking") {
        if (isEcho(text, this.speakingText)) continue;
        this.interrupt(); // barge-in: the student is talking over the answer
      }
      this.handlers.onHeard(text);
      if (result?.isFinal && this.state === "listening") {
        this.set("thinking");
        this.handlers.onUtterance(text);
      }
    }
  }

  /** The agent's answer for the last phrase: speak it, then listen again. */
  answer(text: string, hasSources: boolean): void {
    if (this.ended || this.state === "muted") return;
    const lang = speechLangOf(text);
    const spoken = spokenText(text, hasSources, lang);
    this.speakingText = spoken;
    if (lang === "ur" && this.deps.speaker?.voiceFor("ur")?.viaHindi) this.handlers.onUrduViaHindi?.();
    this.set("speaking");
    const started = this.deps.speaker?.play(spoken, lang, {
      onEnd: () => {
        if (!this.ended && this.state === "speaking") this.set("listening");
      },
    });
    if (!started) {
      this.handlers.onNoVoice?.(lang);
      this.set("listening");
    }
  }

  /** The turn failed (rate limit, no connection): back to listening. */
  answerFailed(): void {
    if (!this.ended && this.state === "thinking") this.set("listening");
  }

  /** Tap anywhere, or barge-in: stop speaking and listen. */
  interrupt(): void {
    if (this.state !== "speaking") return;
    this.speakingText = "";
    this.set("listening");
    this.deps.speaker?.stop();
  }

  mute(): void {
    if (this.ended) return;
    this.interrupt();
    this.set("muted");
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.abort();
  }

  unmute(): void {
    if (this.ended || this.state !== "muted") return;
    this.set("listening");
    this.listen();
  }

  setLanguage(lang: SpeechLang): void {
    if (lang === this.lang) return;
    this.lang = lang;
    if (this.state === "muted" || this.ended) return;
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.abort();
    this.listen();
  }

  private fail(reason: LiveEndReason): void {
    if (this.ended) return;
    this.end();
    this.handlers.onFail(reason);
  }

  end(): void {
    if (this.ended) return;
    this.ended = true;
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.abort();
    if (this.state === "speaking") this.deps.speaker?.stop();
    if (this.levelTimer) clearInterval(this.levelTimer);
    if (this.restartTimer) clearTimeout(this.restartTimer);
    this.meter?.close();
    this.stream?.getTracks().forEach((track) => track.stop());
  }
}
