import { describe, expect, it } from "vitest";

import { answerParts, formatDate, linkify, verifiedBadge } from "@/lib/chat/format";
import { parseServerEvent, type Source } from "@/lib/chat/protocol";

const source = (patch: Partial<Source> = {}): Source => ({
  title: "Test Fee Page",
  office: null,
  url: null,
  last_verified: "2026-10-05",
  expired: false,
  ...patch,
});

describe("formatDate", () => {
  it("formats ISO dates as '5 Oct 2026' and rejects junk", () => {
    expect(formatDate("2026-10-05")).toBe("5 Oct 2026");
    expect(formatDate("2026-01-31T10:00:00Z")).toBe("31 Jan 2026");
    expect(formatDate("yesterday")).toBeNull();
    expect(formatDate(null)).toBeNull();
  });
});

describe("verifiedBadge", () => {
  it("names the office and the oldest verified date", () => {
    const badge = verifiedBadge([
      source({ last_verified: "2026-10-09" }),
      source({ title: "Other", office: "Test Office", last_verified: "2026-10-02" }),
    ]);
    expect(badge).toEqual({ kind: "verified", text: "Verified by Test Office · 2 Oct 2026" });
  });

  it("says 'Last verified' when no office is known", () => {
    expect(verifiedBadge([source()])?.text).toBe("Last verified 5 Oct 2026");
  });

  it("warns when any source is expired", () => {
    expect(verifiedBadge([source({ expired: true })])).toEqual({
      kind: "outdated",
      text: "May be outdated · last verified 5 Oct 2026",
    });
  });

  it("is absent without dated sources", () => {
    expect(verifiedBadge([])).toBeNull();
    expect(verifiedBadge([source({ last_verified: null })])).toBeNull();
  });
});

describe("answerParts", () => {
  it("drops the trailing source line only when chips show the sources", () => {
    const text = "Fee is Rs 1,000.\nSource: Test Fee Page · last verified Mon, 5 Oct 2026";
    expect(answerParts(text, true).body).toBe("Fee is Rs 1,000.");
    expect(answerParts(text, false).body).toBe(text);
  });

  it("turns passed-date sentences into notices", () => {
    const text =
      "Last date to apply: Fri, 2 Oct 2026. This date has passed. Please confirm with the Test Office.";
    const parts = answerParts(text, false);
    expect(parts.body).toBe("Last date to apply: Fri, 2 Oct 2026.");
    expect(parts.passedNotices).toEqual(["This date has passed. Please confirm with the Test Office."]);
  });
});

describe("linkify", () => {
  it("links phone numbers (dialling the first of a range) and emails", () => {
    const segments = linkify("Call 000-1234567 or 0000-1234567-22, or write to test@example.edu.");
    expect(segments.filter((s) => s.kind !== "text")).toEqual([
      { kind: "phone", text: "000-1234567", href: "tel:0001234567" },
      { kind: "phone", text: "0000-1234567-22", href: "tel:00001234567" },
      { kind: "email", text: "test@example.edu", href: "mailto:test@example.edu" },
    ]);
    expect(segments.map((s) => s.text).join("")).toBe(
      "Call 000-1234567 or 0000-1234567-22, or write to test@example.edu.",
    );
  });

  it("leaves fees and dates alone", () => {
    expect(linkify("Rs 7,744 per credit hour, FY 2026-27")).toEqual([
      { kind: "text", text: "Rs 7,744 per credit hour, FY 2026-27" },
    ]);
  });
});

describe("parseServerEvent", () => {
  it("accepts known events and ignores the rest", () => {
    expect(parseServerEvent('{"type":"pong"}')).toEqual({ type: "pong" });
    expect(parseServerEvent('{"type":"shout"}')).toBeNull();
    expect(parseServerEvent("not json")).toBeNull();
    expect(parseServerEvent("[1]")).toBeNull();
  });
});
