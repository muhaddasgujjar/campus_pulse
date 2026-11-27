import { linkify } from "@/lib/chat/format";

/** Answer text with tappable phone numbers and emails (DESIGN.md Section 10). */
export function AnswerText({ text }: { text: string }) {
  return (
    <>
      {linkify(text).map((segment, index) =>
        segment.kind === "text" ? (
          <span key={index}>{segment.text}</span>
        ) : (
          <a
            key={index}
            href={segment.href}
            className="text-accent underline decoration-1 underline-offset-2"
          >
            {segment.text}
          </a>
        ),
      )}
    </>
  );
}
