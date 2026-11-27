/**
 * Browser voice support (D18): Web Speech API recognition, MediaRecorder, speechSynthesis.
 * Everything here is feature-detected: unsupported browsers keep typing (and the server
 * fallback transcription when it is configured).
 */

export type SpeechLang = "en" | "ur";

/** Recognition locales. Pakistan English is not offered by every engine, so en-US. */
export const RECOGNITION_LOCALE: Record<SpeechLang, string> = { en: "en-US", ur: "ur-PK" };

// --- minimal Web Speech API types (Chrome and Edge ship it as webkitSpeechRecognition) ---------

export type RecognitionAlternative = { transcript: string };
export type RecognitionResult = { isFinal: boolean; length: number; [index: number]: RecognitionAlternative };
export type RecognitionEvent = {
  resultIndex: number;
  results: { length: number; [index: number]: RecognitionResult };
};
export type RecognitionErrorEvent = { error: string };

export interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

type VoiceWindow = Window & {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
};

export function recognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as VoiceWindow;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function canRecord(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof window.MediaRecorder !== "undefined"
  );
}

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** The first container this browser can record that the API accepts. */
export function pickMimeType(isTypeSupported: (type: string) => boolean): string {
  for (const type of ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"]) {
    try {
      if (isTypeSupported(type)) return type;
    } catch {
      // some browsers throw for unknown types
    }
  }
  return "";
}

// --- the student's spoken language (until profiles arrive in M5) ------------------------------

const LANG_KEY = "campus-pulse.voice-lang";

export function loadSpeechLang(): SpeechLang {
  try {
    return window.localStorage.getItem(LANG_KEY) === "ur" ? "ur" : "en";
  } catch {
    return "en";
  }
}

export function saveSpeechLang(lang: SpeechLang): void {
  try {
    window.localStorage.setItem(LANG_KEY, lang);
  } catch {
    // ignore
  }
}

/** "0:07" */
export function formatDuration(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
