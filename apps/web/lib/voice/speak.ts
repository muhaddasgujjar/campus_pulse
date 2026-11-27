/**
 * Spoken replies with the browser's speechSynthesis (VOI-2, VOI-4, D18): no server cost.
 * The spoken version leaves out what should not be read aloud (source lines, URLs, markdown)
 * and is spoken sentence by sentence (Chrome cuts long utterances, and progress is per piece).
 */

import { answerParts } from "@/lib/chat/format";
import type { SpeechLang } from "@/lib/voice/support";
import { urduToDevanagari } from "@/lib/voice/urdu";

const URDU_LETTER = /[\u0600-\u06FF]/g;

/**
 * "ur" when a good share of the letters are Urdu script. Urdu answers often carry English
 * names (BSCS, LGU website, FY), so a simple majority would misread them as English.
 */
export function speechLangOf(text: string): SpeechLang {
  const urdu = (text.match(URDU_LETTER) ?? []).length;
  const latin = (text.match(/[A-Za-z]/g) ?? []).length;
  return urdu > 0 && urdu >= 0.3 * (urdu + latin) ? "ur" : "en";
}

/** What "Listen" reads: the answer without its source line, URLs, markdown or symbols. */
export function spokenText(text: string, hasSources: boolean, lang: SpeechLang = speechLangOf(text)): string {
  const { body, passedNotices } = answerParts(text, hasSources);
  let spoken = [body, ...passedNotices]
    .join("\n")
    .split("\n")
    .filter((line) => !/^\s*\(?\s*(Source|ماخذ)\s*:/.test(line))
    .map((line) => line.replace(/^\s*[-•]\s+/, "").trim())
    .filter(Boolean)
    .join(". ")
    // source notes in brackets inside a line: "(ماخذ: Fee Structure, ...)"
    .replace(/\(\s*(Source|ماخذ)\s*:[^)]*\)/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s+·\s+/g, ", ");
  spoken =
    lang === "en"
      ? spoken.replace(/\bRs\.?\s?(?=\d)/g, "rupees ")
      : spoken.replace(/\bRs\.?\s?(\d[\d,]*)/g, "$1 روپے");
  return spoken.replace(/\.\s*\./g, ".").replace(/\s{2,}/g, " ").trim();
}

/** Sentences of at most ~220 characters (Urdu full stop ۔ and question mark ؟ included). */
export function sentences(text: string, maxChars = 220): string[] {
  const parts = text.match(/[^.!?۔؟]+[.!?۔؟]*/g) ?? [];
  const out: string[] = [];
  for (const raw of parts) {
    const part = raw.trim();
    if (!part) continue;
    if (part.length <= maxChars) {
      out.push(part);
      continue;
    }
    let rest = part;
    while (rest.length > maxChars) {
      const cut = rest.lastIndexOf(" ", maxChars);
      const at = cut > 0 ? cut : maxChars;
      out.push(rest.slice(0, at).trim());
      rest = rest.slice(at).trim();
    }
    if (rest) out.push(rest);
  }
  return out;
}

export type VoiceLike = { lang: string; name: string; localService?: boolean };

/** A voice for the language, preferring Pakistan, then any of that language. */
export function pickVoice<V extends VoiceLike>(voices: readonly V[], lang: SpeechLang): V | null {
  const tag = (v: V) => v.lang.replace("_", "-").toLowerCase();
  const preferred = lang === "ur" ? ["ur-pk", "ur-in"] : ["en-pk", "en-in", "en-gb", "en-us"];
  for (const want of preferred) {
    const match = voices.find((v) => tag(v) === want);
    if (match) return match;
  }
  return voices.find((v) => tag(v).startsWith(lang)) ?? null;
}

// --- one speaker per page ----------------------------------------------------------------------

export type SynthLike = {
  speak(utterance: SpeechSynthesisUtterance): void;
  cancel(): void;
  getVoices(): SpeechSynthesisVoice[];
};

export type VoiceChoice = { voice: SpeechSynthesisVoice; viaHindi: boolean };

export type PlayHandlers = {
  onProgress?: (fraction: number) => void;
  onEnd?: () => void;
};

export class Speaker {
  private token = 0;
  private endCurrent: (() => void) | null = null;

  constructor(
    private readonly synth: SynthLike,
    private readonly Utterance: typeof SpeechSynthesisUtterance,
  ) {}

  /**
   * How `lang` would be spoken on this device: its own voice, or (Urdu only) the Hindi voice
   * reading a Devanagari version (Chrome on Windows has no Urdu voice), or null.
   */
  voiceFor(lang: SpeechLang): VoiceChoice | null {
    const voices = this.synth.getVoices();
    const own = pickVoice(voices, lang);
    if (own) return { voice: own, viaHindi: false };
    if (lang === "ur") {
      const hindi = voices.find((v) => v.lang.replace("_", "-").toLowerCase().startsWith("hi"));
      if (hindi) return { voice: hindi, viaHindi: true };
    }
    return null;
  }

  /** Speak `text`; returns false when the device has no voice for the language. */
  play(text: string, lang: SpeechLang, handlers: PlayHandlers = {}): boolean {
    const choice = this.voiceFor(lang);
    if (!choice) return false;
    const { voice, viaHindi } = choice;
    this.stop();
    const token = ++this.token;
    const pieces = sentences(text).map((piece) => (viaHindi ? urduToDevanagari(piece) : piece));
    const total = pieces.reduce((sum, p) => sum + p.length, 0) || 1;
    let done = 0;
    this.endCurrent = () => handlers.onEnd?.();
    const next = (index: number) => {
      if (token !== this.token) return;
      const piece = pieces[index];
      if (piece === undefined) {
        this.endCurrent = null;
        handlers.onProgress?.(1);
        handlers.onEnd?.();
        return;
      }
      const utterance = new this.Utterance(piece);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.rate = 1;
      utterance.onend = () => {
        done += piece.length;
        handlers.onProgress?.(done / total);
        next(index + 1);
      };
      utterance.onerror = () => {
        if (token !== this.token) return;
        this.endCurrent = null;
        handlers.onEnd?.();
      };
      this.synth.speak(utterance);
    };
    handlers.onProgress?.(0);
    next(0);
    return true;
  }

  /** Stop playback (barge-in, another Listen, leaving the page). */
  stop(): void {
    this.token += 1;
    const end = this.endCurrent;
    this.endCurrent = null;
    this.synth.cancel();
    end?.();
  }

  hasVoice(lang: SpeechLang): boolean {
    return this.voiceFor(lang) !== null;
  }
}

let shared: Speaker | null = null;

export function getSpeaker(): Speaker | null {
  if (shared) return shared;
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  shared = new Speaker(window.speechSynthesis, window.SpeechSynthesisUtterance);
  return shared;
}

/** For tests: use a fake synthesizer. */
export function setSpeaker(speaker: Speaker | null): void {
  shared = speaker;
}

/** Subscribe to voice list changes (Chrome loads voices asynchronously). */
export function subscribeVoices(callback: () => void): () => void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return () => undefined;
  window.speechSynthesis.addEventListener?.("voiceschanged", callback);
  return () => window.speechSynthesis.removeEventListener?.("voiceschanged", callback);
}
