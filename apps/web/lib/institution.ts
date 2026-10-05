/**
 * Institution text shown in the UI (ADP-2).
 *
 * M1 placeholder: these strings mirror the API's GET /api/config defaults so the shell can
 * render without the API. From M3 the chat loads them from GET /api/config instead.
 * The disclaimer is PRD CHAT-8 / DESIGN.md Section 3.2.
 */
export const institution = {
  productName: "Campus Pulse AI",
  name: "Lahore Garrison University",
  shortName: "LGU",
  greeting: "Hi, I'm Campus Pulse. Ask me anything about LGU.",
  disclaimer:
    "Answers are based on information verified by LGU offices. Please confirm important decisions with the relevant office.",
} as const;
