"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { Sheet } from "@/components/chat/Sheet";
import { FEEDBACK_REASONS, type FeedbackReason } from "@/lib/chat/api";

export type RateFn = (
  messageId: string,
  rating: 1 | -1,
  reason?: FeedbackReason,
  comment?: string,
) => Promise<boolean>;

type FeedbackProps = {
  messageId: string;
  rating: 1 | -1 | null;
  onRate: RateFn;
  sheetOpen: boolean;
  onSheetOpenChange: (open: boolean) => void;
  defaultReason?: FeedbackReason;
};

/** Thumbs up and down (CHAT-4). Thumbs down opens a sheet with 3 reasons and free text. */
export function Feedback({
  messageId,
  rating,
  onRate,
  sheetOpen,
  onSheetOpenChange,
  defaultReason,
}: FeedbackProps) {
  const [reason, setReason] = useState<FeedbackReason | undefined>(defaultReason);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "error">("idle");

  const submitDown = async () => {
    setState("sending");
    const ok = await onRate(messageId, -1, reason, comment);
    setState(ok ? "idle" : "error");
    if (ok) onSheetOpenChange(false);
  };

  const buttonClass = (active: boolean) =>
    `inline-flex size-11 items-center justify-center rounded-(--radius-pill) hover:bg-surface-2 ${active ? "text-accent" : "text-muted"}`;

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        aria-label="Helpful"
        aria-pressed={rating === 1}
        onClick={() => void onRate(messageId, 1)}
        className={buttonClass(rating === 1)}
      >
        <ThumbsUp size={18} strokeWidth={1.75} aria-hidden="true" />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        aria-pressed={rating === -1}
        onClick={() => onSheetOpenChange(true)}
        className={buttonClass(rating === -1)}
      >
        <ThumbsDown size={18} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {rating !== null && <span className="text-xs text-muted">Thanks for the feedback</span>}
      {sheetOpen && (
        <Sheet title="What went wrong?" onClose={() => onSheetOpenChange(false)}>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submitDown();
            }}
          >
            <fieldset className="flex flex-col gap-2">
              <legend className="sr-only">Reason</legend>
              {FEEDBACK_REASONS.map((option) => (
                <label
                  key={option.value}
                  className="flex min-h-11 cursor-pointer items-center gap-3 rounded-(--radius-sm) border border-border px-3"
                >
                  <input
                    type="radio"
                    name="reason"
                    value={option.value}
                    checked={reason === option.value}
                    onChange={() => setReason(option.value)}
                    className="size-4 accent-(--primary)"
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted">Anything else? (optional)</span>
              <textarea
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                maxLength={500}
                rows={3}
                className="rounded-(--radius-sm) border border-border bg-surface-2 px-3 py-2 text-base text-text"
              />
            </label>
            <p className="text-xs text-muted">
              Please do not include your CNIC, roll number or phone number.
            </p>
            {state === "error" && (
              <p role="alert" className="text-sm text-danger">
                Could not send your feedback. Please try again.
              </p>
            )}
            <button
              type="submit"
              disabled={state === "sending"}
              className="min-h-11 rounded-(--radius-pill) bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover disabled:opacity-50"
            >
              Send feedback
            </button>
          </form>
        </Sheet>
      )}
    </div>
  );
}
