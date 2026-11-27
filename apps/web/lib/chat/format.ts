/** Display helpers for answers (DESIGN.md Sections 4, 8 and 10). Pure functions. */

import type { Source } from "@/lib/chat/protocol";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-05" -> "5 Oct 2026" (same in every locale, DESIGN.md Section 9). */
export function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return null;
  const [, year, month, day] = match;
  const name = MONTHS[Number(month) - 1];
  return name ? `${Number(day)} ${name} ${year}` : null;
}

/** Message time, "14:05" (local clock). */
export function formatTime(epochMs: number): string {
  const d = new Date(epochMs);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export type Badge = { kind: "verified" | "outdated"; text: string };

/**
 * Verified badge (CHAT-3): "Verified by <office> · <date>". The answer is only as fresh as
 * its oldest source. Any expired source: "May be outdated · last verified <date>".
 */
export function verifiedBadge(sources: Source[]): Badge | null {
  const dated = sources.filter((s) => s.last_verified);
  if (dated.length === 0) return null;
  const oldest = dated.reduce((a, b) => ((a.last_verified ?? "") <= (b.last_verified ?? "") ? a : b));
  const date = formatDate(oldest.last_verified);
  if (!date) return null;
  if (sources.some((s) => s.expired)) {
    return { kind: "outdated", text: `May be outdated · last verified ${date}` };
  }
  const office = sources.find((s) => s.office)?.office;
  return { kind: "verified", text: office ? `Verified by ${office} · ${date}` : `Last verified ${date}` };
}

const PASSED = /This date has passed\. Please confirm with the [^.]+\./g;

/**
 * Answers are shown as plain text. The composer is told not to use markdown; if an LLM still
 * sends bold or heading markers, drop the markers and keep the words. "- " lists stay.
 */
export function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/^#{1,6}\s+/gm, "");
}

export type AnswerParts = { body: string; passedNotices: string[] };

/**
 * Split an answer for display: the trailing "Source: ..." line is dropped when source chips
 * and the badge show the same thing, and "This date has passed..." sentences become warning
 * rows (DESIGN.md Section 4, passed-date notice). The stored answer text is unchanged.
 */
export function answerParts(text: string, hasSources: boolean): AnswerParts {
  let body = stripMarkdown(text);
  if (hasSources) {
    const lines = body.split("\n");
    while (lines.length > 1 && /^Source: /.test(lines[lines.length - 1] ?? "")) lines.pop();
    body = lines.join("\n");
  }
  const passedNotices = Array.from(new Set(body.match(PASSED) ?? []));
  body = body.replace(PASSED, "").replace(/[ \t]+\n/g, "\n").replace(/[ \t]{2,}/g, " ").trim();
  return { body, passedNotices };
}

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "phone"; text: string; href: string }
  | { kind: "email"; text: string; href: string };

// Pakistani numbers as written by LGU: 042-37181828, 0322-2757543, 042-37181821-22 (a range).
const LINKS = /(\b0\d{2,3}-\d{7,8}(?:-\d{1,2})?\b)|([\w.+-]+@[\w-]+(?:\.[\w-]+)+)/g;

/** Phone numbers become tel: links and emails mailto: links (DESIGN.md Section 10). */
export function linkify(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(LINKS)) {
    const index = match.index ?? 0;
    if (index > last) out.push({ kind: "text", text: text.slice(last, index) });
    const [whole, phone] = match;
    if (phone) {
      // "042-37181821-22" is a range (…21 and …22): dial the first number.
      const [area, number] = phone.split("-");
      out.push({ kind: "phone", text: whole, href: `tel:${area}${number}` });
    } else {
      out.push({ kind: "email", text: whole, href: `mailto:${whole}` });
    }
    last = index + whole.length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

export const STAGE_TEXT: Record<string, string> = {
  waking: "Waking up the assistant…",
  queued: "Lots of students are asking right now. Please wait…",
  searching: "Searching university records…",
  reading: "Reading approved documents…",
  writing: "Writing…",
};
