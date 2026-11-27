/**
 * Spoken replies with the browser's speechSynthesis (VOI-2, VOI-4, D18): no server cost.
 * The spoken version leaves out what should not be read aloud (source lines, URLs, markdown)
 * and is spoken sentence by sentence (Chrome cuts long utterances, and progress is per piece).
 */

import { answerParts } from "@/lib/chat/format";
import type { SpeechLang } from "@/lib/voice/support";

const URDU_LETTER = /[؀-ۿ]/g;

/** "ur" when most letters are Urdu script, else "en". */
export function speechLangOf(text: string): SpeechLang {
  const urdu = (text.match(URDU_LETTER) ?? []).length;
  const latin = (text.match(/[A-Za-z]/g) ?? []).length;
  return urdu > latin ? "ur" : "en";
}

/** What "Listen" reads: the answer without its source line, URLs, markdown or symbols. */
export function spokenText(text: string, hasSources: boolean, lang: SpeechLang = speechLangOf(text)): string {
  const { body, passedNotices } = answerParts(text, hasSources);
  let spoken = [body, ...passedNotices].join(" ");
  spoken = spoken
    .split("\n")
    .filter((line) => !/^\s*(Source|ماخذ)\s*:/.test(line))
    .join(". ")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\s+·\s+/g, ", ");
  if (lang === "en") spoken = spoken.replace(/\bRs\.?\s?(?=\d)/g, "rupees ");
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

  /** Speak `text`; returns false when the device has no voice for the language. */
  play(text: string, lang: SpeechLang, handlers: PlayHandlers = {}): boolean {
    const voice = pickVoice(this.synth.getVoices(), lang);
    if (!voice) return false;
    this.stop();
    const token = ++this.token;
    const pieces = sentences(text);
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
    return pickVoice(this.synth.getVoices(), lang) !== null;
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
