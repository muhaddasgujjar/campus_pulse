"use client";

import { SendHorizontal } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";

import { MAX_MESSAGE_CHARS } from "@/lib/chat/protocol";

type ComposerProps = {
  onSend: (text: string) => void;
  disabled: boolean;
  disclaimer: string;
};

/**
 * Composer (DESIGN.md Section 4): grows to 5 lines, Enter sends, Shift+Enter adds a line.
 * The mic button arrives with voice messages in M4.
 */
export function Composer({ onSend, disabled, disclaimer }: ComposerProps) {
  const [text, setText] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const trimmed = text.trim();
  const canSend = !disabled && trimmed.length > 0 && trimmed.length <= MAX_MESSAGE_CHARS;

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

  return (
    <footer className="sticky bottom-0 border-t border-border bg-bg px-4 pt-3 pb-4">
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
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Send"
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-(--radius-pill) bg-primary text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          <SendHorizontal size={20} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </form>
      {text.length > MAX_MESSAGE_CHARS * 0.9 && (
        <p className="mt-1 text-xs text-muted">
          {text.length} / {MAX_MESSAGE_CHARS}
        </p>
      )}
      <p className="mt-2 text-xs text-muted">{disclaimer}</p>
    </footer>
  );
}
