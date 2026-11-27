"use client";

import { SendHorizontal, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { TRANSCRIBE_ERRORS, transcribeOnServer } from "@/lib/voice/api";
import {
  MAX_RECORDING_SECONDS,
  MicPermissionError,
  type RecorderDeps,
  VoiceRecorder,
} from "@/lib/voice/recorder";
import { formatDuration, recognitionCtor, type SpeechLang } from "@/lib/voice/support";

const BARS = 28;

export type VoiceBarProps = {
  lang: SpeechLang;
  onLangChange: (lang: SpeechLang) => void;
  onDone: (transcript: string, seconds: number) => void;
  onCancel: () => void;
  onError: (message: string) => void;
  onPermissionDenied: () => void;
  deps?: RecorderDeps;
  apiUrl?: string;
};

/**
 * Recording bar (DESIGN.md 5.1): red dot, timer, live waveform, live transcript, cancel, send.
 * 60 seconds at most. Without browser recognition the audio goes to the server fallback.
 */
export function VoiceRecorderBar({
  lang,
  onLangChange,
  onDone,
  onCancel,
  onError,
  onPermissionDenied,
  deps,
  apiUrl,
}: VoiceBarProps) {
  const [phase, setPhase] = useState<"starting" | "recording" | "transcribing">("starting");
  const [transcript, setTranscript] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0));
  const recorder = useRef<VoiceRecorder | null>(null);
  const finishing = useRef(false);
  // Live transcript only where the browser has speech recognition.
  const [live] = useState(() => (deps ? deps.Recognition : recognitionCtor()) !== null);

  const finish = useCallback(async () => {
    const current = recorder.current;
    if (!current || finishing.current) return;
    finishing.current = true;
    const result = await current.stop();
    recorder.current = null;
    if (result.recognized && result.transcript) {
      onDone(result.transcript, result.seconds);
      return;
    }
    if (!result.blob) {
      onError("We couldn't hear anything. Please try again or type.");
      return;
    }
    setPhase("transcribing");
    const server = await transcribeOnServer(result.blob, lang, apiUrl);
    if (!server.ok) onError(TRANSCRIBE_ERRORS[server.reason]);
    else if (!server.transcript.trim()) onError("We couldn't hear anything. Please try again or type.");
    else onDone(server.transcript, result.seconds);
  }, [apiUrl, lang, onDone, onError]);

  useEffect(() => {
    finishing.current = false;
    const instance = new VoiceRecorder(
      lang,
      (update) => {
        setTranscript(update.transcript);
        setSeconds(update.seconds);
        setLevels((prev) => [...prev.slice(1), update.level]);
      },
      () => void finish(),
      deps,
    );
    recorder.current = instance;
    instance
      .start()
      .then(() => setPhase("recording"))
      .catch((error: unknown) => {
        recorder.current = null;
        if (error instanceof MicPermissionError) onPermissionDenied();
        else onError("The microphone could not be started. Please type your question.");
      });
    return () => {
      if (recorder.current === instance) instance.cancel();
    };
    // Restart only when the language changes (a new recognition session is needed).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

  const cancel = () => {
    recorder.current?.cancel();
    recorder.current = null;
    onCancel();
  };

  return (
    <div className="flex flex-col gap-2" aria-label="Recording a voice message">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={cancel}
          aria-label="Cancel recording"
          disabled={phase === "transcribing"}
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-(--radius-pill) text-muted hover:bg-surface-2 disabled:opacity-50"
        >
          <Trash2 size={20} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <div className="flex min-h-11 flex-1 items-center gap-3 rounded-(--radius-lg) border border-border bg-surface-2 px-4">
          <span aria-hidden="true" className="recording-dot size-2.5 shrink-0 rounded-(--radius-pill) bg-danger" />
          <span className="text-sm tabular-nums" aria-live="off">
            {formatDuration(seconds)} / {formatDuration(MAX_RECORDING_SECONDS)}
          </span>
          <span aria-hidden="true" className="flex h-6 flex-1 items-center gap-0.5 overflow-hidden">
            {levels.map((level, index) => (
              <span
                key={index}
                className="w-0.5 shrink-0 rounded-(--radius-pill) bg-accent"
                style={{ height: `${Math.max(8, Math.round(level * 100))}%` }}
              />
            ))}
          </span>
        </div>
        <button
          type="button"
          onClick={() => void finish()}
          aria-label="Send voice message"
          disabled={phase !== "recording"}
          className="mic-active inline-flex size-11 shrink-0 items-center justify-center rounded-(--radius-pill) bg-primary text-on-primary hover:bg-primary-hover disabled:opacity-50"
        >
          <SendHorizontal size={20} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
      <div className="flex items-start gap-3">
        <p dir="auto" className="min-h-5 flex-1 text-sm text-muted" aria-live="polite">
          {phase === "transcribing"
            ? "Transcribing…"
            : transcript || (live ? "Listening…" : "Recording… the transcript appears after sending.")}
        </p>
        <div role="group" aria-label="Spoken language" className="flex shrink-0 overflow-hidden rounded-(--radius-pill) border border-border text-xs">
          {(["en", "ur"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={lang === option}
              disabled={phase === "transcribing"}
              onClick={() => lang !== option && onLangChange(option)}
              className={`min-h-8 px-3 ${lang === option ? "bg-surface-teal text-accent" : "text-muted"}`}
            >
              {option === "en" ? "EN" : "اردو"}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-muted">
        Speech recognition may send audio to your browser&apos;s speech service. Recordings are not
        stored.
      </p>
    </div>
  );
}
