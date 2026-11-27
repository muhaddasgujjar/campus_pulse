"use client";

import { MessageSquare, Mic, MicOff, PhoneOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { BrandMark } from "@/components/brand/BrandMark";
import type { ChatMessage, Notice } from "@/lib/chat/state";
import { browserLiveDeps, type LiveDeps, type LiveEndReason, LiveSession, type LiveState } from "@/lib/voice/live";
import { getSpeaker } from "@/lib/voice/speak";
import { loadSpeechLang, saveSpeechLang, type SpeechLang } from "@/lib/voice/support";

const STATE_TEXT: Record<LiveState, string> = {
  starting: "Starting…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking… tap to interrupt",
  muted: "Muted",
};

export const LIVE_END_NOTES: Record<LiveEndReason, string> = {
  mic: "Live mode stopped: allow microphone access to talk hands-free.",
  network: "Live mode stopped: speech recognition lost its connection. You can keep typing.",
  unsupported: "Live mode works in Chrome and Edge.",
  language:
    "Speech recognition for this language isn't available in this browser. Try Chrome or Edge with an internet connection.",
};

type LiveOverlayProps = {
  messages: ChatMessage[];
  notice: Notice;
  onAsk: (text: string) => void;
  onClose: (note?: string) => void;
  deps?: LiveDeps;
};

/**
 * Hands-free live mode (VOI-5, DESIGN.md 5.2). Questions go through the same chat as typed
 * ones (modality voice); answers are spoken with the browser's voice and shown as captions.
 */
export function LiveOverlay({ messages, notice, onAsk, onClose, deps }: LiveOverlayProps) {
  const [state, setState] = useState<LiveState>("starting");
  const [heard, setHeard] = useState("");
  const [level, setLevel] = useState(0);
  const [lang, setLang] = useState<SpeechLang>(() => loadSpeechLang());
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const session = useRef<LiveSession | null>(null);
  // Answers that existed before live mode opened are never spoken or captioned.
  const [earlier] = useState(
    () => new Set(messages.filter((m) => m.role === "assistant").map((m) => m.localId)),
  );
  const spokenIds = useRef(new Set(earlier));
  const lastNotice = useRef(notice);

  const latestAnswer = [...messages].reverse().find((m) => m.role === "assistant");

  useEffect(() => {
    const live = new LiveSession(lang, deps ?? browserLiveDeps(getSpeaker()), {
      onState: setState,
      onHeard: setHeard,
      onUtterance: (text) => {
        setVoiceNote(null);
        onAsk(text);
      },
      onLevel: setLevel,
      onFail: (reason) => onClose(LIVE_END_NOTES[reason]),
      onUrduViaHindi: () =>
        setVoiceNote("No Urdu voice on this device: Urdu answers are read with the Hindi voice."),
      onNoVoice: (spokenLang) =>
        setVoiceNote(
          spokenLang === "ur"
            ? "Voice playback isn't available in Urdu on this device."
            : "Voice playback isn't available on this device.",
        ),
    });
    session.current = live;
    void live.start();
    return () => live.end();
    // One session for the lifetime of the overlay; language changes go through setLanguage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Speak each new finished answer once.
  useEffect(() => {
    const live = session.current;
    if (!live || !latestAnswer || latestAnswer.status !== "done") return;
    if (spokenIds.current.has(latestAnswer.localId)) return;
    spokenIds.current.add(latestAnswer.localId);
    live.answer(latestAnswer.text, latestAnswer.sources.length > 0);
  }, [latestAnswer]);

  // A refused or failed turn (rate limit, no connection): listen again.
  useEffect(() => {
    if (notice && notice !== lastNotice.current) session.current?.answerFailed();
    lastNotice.current = notice;
  }, [notice]);

  const answerCaption =
    latestAnswer && latestAnswer.status === "done" && !earlier.has(latestAnswer.localId)
      ? latestAnswer.text.split("\n")[0]
      : "";

  const scale = 1 + Math.min(level, 1) * 0.6;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Live mode"
      className="fixed inset-0 z-50 flex flex-col bg-bg"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <p className="text-sm text-muted" aria-live="polite">
          {STATE_TEXT[state]}
        </p>
        <div role="group" aria-label="Spoken language" className="flex overflow-hidden rounded-(--radius-pill) border border-border text-xs">
          {(["en", "ur"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={lang === option}
              onClick={() => {
                setLang(option);
                saveSpeechLang(option);
                session.current?.setLanguage(option);
              }}
              className={`min-h-8 px-3 ${lang === option ? "bg-surface-teal text-accent" : "text-muted"}`}
            >
              {option === "en" ? "EN" : "اردو"}
            </button>
          ))}
        </div>
      </div>

      <div className="relative flex flex-1 flex-col items-center justify-center gap-8 px-6">
        {state === "speaking" && (
          <button
            type="button"
            aria-label="Interrupt the answer"
            onClick={() => session.current?.interrupt()}
            className="absolute inset-0 z-10 cursor-pointer"
          />
        )}
        <span className={`live-rings live-${state}`} style={{ ["--live-scale" as string]: scale }}>
          <span className="live-ring" />
          <span className="live-ring" />
          <span className="live-ring" />
          <span className="live-dot" />
          <BrandMark size={96} glow />
        </span>
        <span className="flex w-full max-w-xl flex-col gap-2 text-center" aria-live="polite">
          <span dir="auto" className="line-clamp-2 min-h-6 text-muted">
            {heard ? `You: ${heard}` : "Ask anything about the university."}
          </span>
          <span dir="auto" className="line-clamp-2 min-h-6 text-lg">
            {answerCaption}
          </span>
          {voiceNote && <span className="text-sm text-warning">{voiceNote}</span>}
        </span>
      </div>

      <div className="flex items-center justify-center gap-6 px-4 pt-2 pb-8">
        <button
          type="button"
          onClick={() => (state === "muted" ? session.current?.unmute() : session.current?.mute())}
          aria-label={state === "muted" ? "Unmute" : "Mute"}
          aria-pressed={state === "muted"}
          className="inline-flex size-14 items-center justify-center rounded-(--radius-pill) border border-border text-text hover:bg-surface-2"
        >
          {state === "muted" ? (
            <MicOff size={24} strokeWidth={1.75} aria-hidden="true" />
          ) : (
            <Mic size={24} strokeWidth={1.75} aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          onClick={() => onClose()}
          aria-label="End live mode"
          className="inline-flex size-16 items-center justify-center rounded-(--radius-pill) bg-danger text-on-primary hover:opacity-90"
        >
          <PhoneOff size={26} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => onClose()}
          aria-label="Switch to text"
          className="inline-flex size-14 items-center justify-center rounded-(--radius-pill) border border-border text-text hover:bg-surface-2"
        >
          <MessageSquare size={24} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
