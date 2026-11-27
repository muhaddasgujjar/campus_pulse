"use client";

import { Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { getSpeaker, speechLangOf, spokenText, subscribeVoices } from "@/lib/voice/speak";

/**
 * "Listen" (VOI-2): plays the spoken version with the browser's voice, with a progress bar.
 * Hidden when the device has no voice for the answer's language (DESIGN.md 8).
 */
export function ListenButton({ text, hasSources }: { text: string; hasSources: boolean }) {
  const lang = speechLangOf(text);
  const available = useSyncExternalStore(
    subscribeVoices,
    () => getSpeaker()?.hasVoice(lang) ?? false,
    () => false,
  );
  const [progress, setProgress] = useState<number | null>(null);
  const playingRef = useRef(false);

  // Leaving the chat stops our own playback (only on unmount).
  useEffect(
    () => () => {
      if (playingRef.current) getSpeaker()?.stop();
    },
    [],
  );

  if (!available) return null;
  const playing = progress !== null;

  const toggle = () => {
    const speaker = getSpeaker();
    if (!speaker) return;
    if (playing) {
      speaker.stop();
      return;
    }
    playingRef.current = true;
    const started = speaker.play(spokenText(text, hasSources, lang), lang, {
      onProgress: (fraction) => setProgress(fraction),
      onEnd: () => {
        playingRef.current = false;
        setProgress(null);
      },
    });
    if (!started) playingRef.current = false;
  };

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={toggle}
        aria-pressed={playing}
        className="inline-flex min-h-11 items-center gap-1.5 rounded-(--radius-pill) px-3 text-sm text-accent hover:bg-surface-2"
      >
        {playing ? (
          <Square size={16} strokeWidth={1.75} aria-hidden="true" />
        ) : (
          <Volume2 size={18} strokeWidth={1.75} aria-hidden="true" />
        )}
        {playing ? "Stop" : "Listen"}
      </button>
      {playing && (
        <span
          role="progressbar"
          aria-label="Playback"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round((progress ?? 0) * 100)}
          className="h-1 w-16 overflow-hidden rounded-(--radius-pill) bg-surface-2"
        >
          <span
            className="block h-full bg-accent transition-[width] duration-(--duration-base)"
            style={{ width: `${Math.round((progress ?? 0) * 100)}%` }}
          />
        </span>
      )}
    </span>
  );
}
