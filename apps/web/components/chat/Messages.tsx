"use client";

import { CircleAlert, RotateCw } from "lucide-react";
import { useState } from "react";

import { AnswerText } from "@/components/chat/AnswerText";
import { FallbackCard } from "@/components/chat/FallbackCard";
import { Feedback, type RateFn } from "@/components/chat/Feedback";
import { SourceChips, VerifiedBadge } from "@/components/chat/Sources";
import { BrandMark } from "@/components/brand/BrandMark";
import { answerParts, formatTime, STAGE_TEXT } from "@/lib/chat/format";
import type { ChatMessage } from "@/lib/chat/state";

/** User bubble: right aligned, smaller bottom-right corner (DESIGN.md Section 4). */
export function UserBubble({
  message,
  onRetry,
}: {
  message: ChatMessage;
  onRetry: (localId: string) => void;
}) {
  return (
    <div className="bubble-in flex flex-col items-end gap-1">
      <div
        dir="auto"
        className="max-w-[85%] rounded-(--radius-md) rounded-ee-(--radius-sm) bg-user-bubble px-4 py-2 whitespace-pre-wrap text-on-user-bubble"
      >
        {message.text}
      </div>
      <p className="flex items-center gap-2 text-xs text-muted">
        {message.status === "failed" ? (
          <>
            <span className="flex items-center gap-1 text-danger">
              <CircleAlert size={14} strokeWidth={1.75} aria-hidden="true" />
              Not sent
            </span>
            <button
              type="button"
              onClick={() => onRetry(message.localId)}
              className="inline-flex min-h-8 items-center gap-1 text-accent underline"
            >
              <RotateCw size={14} strokeWidth={1.75} aria-hidden="true" />
              Retry
            </button>
          </>
        ) : (
          <>
            <time>{formatTime(message.createdAt)}</time>
            {message.status === "sending" && <span>Sending…</span>}
          </>
        )}
      </p>
    </div>
  );
}

function Typing({ stage }: { stage: ChatMessage["stage"] }) {
  return (
    <div className="flex items-center gap-3 text-sm text-muted">
      <span className="typing-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span>{stage ? STAGE_TEXT[stage] : "Thinking…"}</span>
    </div>
  );
}

/** Bot message: answer, passed-date notices, verified badge, source chips, feedback. */
export function BotMessage({
  message,
  onRate,
  showAvatar,
}: {
  message: ChatMessage;
  onRate: RateFn;
  showAvatar: boolean;
}) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const streaming = message.status === "streaming";
  const { body, passedNotices } = answerParts(message.text, message.sources.length > 0);

  return (
    <div className="bubble-in flex items-start gap-2">
      <div className="w-8 shrink-0">{showAvatar && <BrandMark size={32} />}</div>
      <div className="flex max-w-[85%] min-w-0 flex-col gap-2">
        {message.fallback ? (
          <FallbackCard office={message.office} onTellUs={message.id ? () => setFeedbackOpen(true) : undefined} />
        ) : (
          <div className="flex flex-col gap-2 rounded-(--radius-md) rounded-es-(--radius-sm) bg-surface-1 px-4 py-3">
            {streaming && !message.text ? (
              <Typing stage={message.stage} />
            ) : (
              <p dir="auto" className="whitespace-pre-line">
                <AnswerText text={body} />
                {streaming && <span className="caret" aria-hidden="true" />}
              </p>
            )}
            {passedNotices.map((notice) => (
              <p
                key={notice}
                className="flex items-start gap-2 rounded-(--radius-sm) bg-surface-2 px-3 py-2 text-sm text-warning"
              >
                <CircleAlert size={16} strokeWidth={1.75} aria-hidden="true" className="mt-0.5 shrink-0" />
                {notice}
              </p>
            ))}
            {!streaming && <VerifiedBadge sources={message.sources} />}
            {!streaming && <SourceChips sources={message.sources} />}
          </div>
        )}
        {!streaming && message.id && (
          <div className="flex items-center gap-2">
            <time className="text-xs text-muted">{formatTime(message.createdAt)}</time>
            <Feedback
              messageId={message.id}
              rating={message.rating}
              onRate={onRate}
              sheetOpen={feedbackOpen}
              onSheetOpenChange={setFeedbackOpen}
              defaultReason={message.fallback ? "not_helpful" : undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}
