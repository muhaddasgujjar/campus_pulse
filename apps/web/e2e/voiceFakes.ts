import type { Page } from "@playwright/test";

/**
 * Headless Chromium has no usable speech engine or microphone. This init script installs:
 * - a fake SpeechRecognition the test drives with window.__say(text, isFinal),
 * - a microphone that returns a real audio stream (an oscillator), so MediaRecorder makes a
 *   genuine WebM file for the server fallback,
 * - a speechSynthesis that records what would be spoken in window.__spoken.
 * `recognition: false` removes SpeechRecognition (browsers like Firefox and Safari).
 */
export async function installVoiceFakes(page: Page, opts: { recognition: boolean }): Promise<void> {
  await page.addInitScript((recognition: boolean) => {
    type Listener = { onresult: ((e: unknown) => void) | null; onend: (() => void) | null };
    const w = window as unknown as Record<string, unknown>;
    const active: Listener[] = [];

    class FakeRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      onresult: ((e: unknown) => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        active.push(this);
      }
      stop() {
        const i = active.indexOf(this);
        if (i >= 0) active.splice(i, 1);
      }
      abort() {
        this.stop();
      }
    }

    if (recognition) {
      w.SpeechRecognition = FakeRecognition;
      w.webkitSpeechRecognition = FakeRecognition;
    } else {
      delete w.SpeechRecognition;
      delete w.webkitSpeechRecognition;
      Object.defineProperty(window, "webkitSpeechRecognition", { value: undefined, configurable: true });
    }

    w.__say = (text: string, isFinal = true) => {
      const result = Object.assign([{ transcript: text }], { isFinal });
      for (const r of [...active]) {
        r.onresult?.({ resultIndex: 0, results: Object.assign([result], { length: 1 }) });
      }
    };

    // A real audio stream: a quiet oscillator through a MediaStreamDestination.
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = 0.05;
      const dest = ctx.createMediaStreamDestination();
      osc.connect(gain).connect(dest);
      osc.start();
      return dest.stream;
    };

    const spoken: string[] = [];
    w.__spoken = spoken;
    const synth = {
      speaking: false,
      getVoices: () => [{ lang: "en-US", name: "Test English", localService: true, default: true, voiceURI: "test" }],
      speak(u: { text: string; onend: (() => void) | null }) {
        spoken.push(u.text);
        setTimeout(() => u.onend?.(), 30);
      },
      cancel() {},
      addEventListener() {},
      removeEventListener() {},
    };
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
    // The real utterance only accepts real voices: use a plain one with the fake engine.
    class FakeUtterance {
      voice: unknown = null;
      lang = "";
      rate = 1;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public text: string) {}
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: FakeUtterance, configurable: true });
  }, opts.recognition);
}
