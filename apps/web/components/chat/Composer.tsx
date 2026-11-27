"use client";

import { CircleAlert, Mic, SendHorizontal } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { Sheet } from "@/components/chat/Sheet";
import { VoiceRecorderBar } from "@/components/chat/VoiceRecorderBar";
import { MAX_MESSAGE_CHARS } from "@/lib/chat/protocol";
import type { RecorderDeps } from "@/lib/voice/recorder";
import { canRecord, loadSpeechLang, saveSpeechLang, type SpeechLang } from "@/lib/voice/support";

const noSubscribe = () => () => undefined;

export type VoiceOptions = {
  /** Overrides browser detection (tests). */
  enabled?: boolean;
  deps?: RecorderDeps;
  apiUrl?: string;
};

type ComposerProps = {
  onSend: (text: string) => void;
  onSendVoice: (transcript: string, seconds: number) => void;
  disabled: boolean;
  disclaimer: string;
  /** "Edit and resend": puts a transcript back into the input. */
  editRequest?: { text: string; nonce: number } | null;
  voice?: VoiceOptions;
};

/**
 * Composer (DESIGN.md Section 4): grows to 5 lines, Enter sends, Shift+Enter adds a line.
 * Mic button when empty (voice messages, VOI-1), send button when there is text.
 */
export function Composer({
  onSend,
  onSendVoice,
  disabled,
  disclaimer,
  editRequest,
  voice,
}: ComposerProps) {
  const [text, setText] = useState("");
  const [recording, setRecording] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [permissionHelp, setPermissionHelp] = useState(false);
  const [lang, setLang] = useState<SpeechLang>(() =>
    typeof window === "undefined" ? "en" : loadSpeechLang(),
  );
  // Browser capabilities are only known on the client; the server snapshot says "no", so the
  // first render matches the prerendered page.
  const detected = useSyncExternalStore(noSubscribe, canRecord, () => false);
  const voiceSupported = voice?.enabled ?? detected;
  const [seenEdit, setSeenEdit] = useState<number | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const trimmed = text.trim();
  const canSend = !disabled && trimmed.length > 0 && trimmed.length <= MAX_MESSAGE_CHARS;

  // "Edit and resend": adopt the transcript once per request (state adjusted during render).
  if (editRequest && editRequest.nonce !== seenEdit) {
    setSeenEdit(editRequest.nonce);
    setText(editRequest.text);
  }
  useEffect(() => {
    if (editRequest) input.current?.focus();
  }, [editRequest]);

  const grow = (element: HTMLTextAreaElement) => {
    element.style.height = "auto";
    const line = parseFloat(getComputedStyle(element).lineHeight) || 24;
    element.style.height = `${Math.min(element.scrollHeight, line * 5 + 20)}px`;
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!canSend) return;
    onSend(trimmed);
    setText("");
    if (input.current) {
      input.current.style.height = "auto";
      input.current.focus();
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  };

  const showMic = voiceSupported && trimmed.length === 0;

  return (
    <footer className="sticky bottom-0 border-t border-border bg-bg px-4 pt-3 pb-4">
      {recording ? (
        <VoiceRecorderBar
          lang={lang}
          onLangChange={(next) => {
            setLang(next);
            saveSpeechLang(next);
          }}
          onDone={(transcript, seconds) => {
            setRecording(false);
            onSendVoice(transcript, seconds);
          }}
          onCancel={() => setRecording(false)}
          onError={(message) => {
            setRecording(false);
            setVoiceError(message);
          }}
          onPermissionDenied={() => {
            setRecording(false);
            setPermissionHelp(true);
          }}
          deps={voice?.deps}
          apiUrl={voice?.apiUrl}
        />
      ) : (
        <form className="flex items-end gap-2" aria-label="Message composer" onSubmit={submit}>
          <label htmlFor="composer" className="sr-only">
            Type a message
          </label>
          <textarea
            id="composer"
            ref={input}
            rows={1}
            value={text}
            disabled={disabled}
            maxLength={MAX_MESSAGE_CHARS}
            placeholder="Type a message…"
            dir="auto"
            onChange={(event) => {
              setText(event.target.value);
              grow(event.target);
            }}
            onKeyDown={onKeyDown}
            className="min-h-11 flex-1 resize-none rounded-(--radius-lg) border border-border bg-surface-2 px-4 py-2.5 text-base leading-6 text-text placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-70"
          />
          {showMic ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                setVoiceError(null);
                setRecording(true);
              }}
              aria-label="Record a voice message"
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-(--radius-pill) border border-accent text-accent hover:bg-surface-teal disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Mic size={20} strokeWidth={1.75} aria-hidden="true" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canSend}
              aria-label="Send"
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-(--radius-pill) bg-primary text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              <SendHorizontal size={20} strokeWidth={1.75} aria-hidden="true" />
            </button>
          )}
        </form>
      )}
      {voiceError && (
        <p role="alert" className="mt-2 flex items-start gap-2 text-sm text-warning">
          <CircleAlert size={16} strokeWidth={1.75} aria-hidden="true" className="mt-0.5 shrink-0" />
          <span className="flex-1">{voiceError}</span>
          <button type="button" onClick={() => setVoiceError(null)} className="text-accent underline">
            Dismiss
          </button>
        </p>
      )}
      {text.length > MAX_MESSAGE_CHARS * 0.9 && (
        <p className="mt-1 text-xs text-muted">
          {text.length} / {MAX_MESSAGE_CHARS}
        </p>
      )}
      <p className="mt-2 text-xs text-muted">{disclaimer}</p>
      {permissionHelp && (
        <Sheet title="Allow microphone access" onClose={() => setPermissionHelp(false)}>
          <div className="flex flex-col gap-3 text-sm">
            <p>Allow microphone access to send voice messages.</p>
            <ol className="list-decimal ps-5 text-muted">
              <li>Tap the lock or settings icon next to the address bar.</li>
              <li>Set Microphone to Allow.</li>
              <li>Come back and tap the microphone again.</li>
            </ol>
            <p className="text-muted">You can always type your question instead.</p>
          </div>
        </Sheet>
      )}
    </footer>
  );
}
