# Campus Pulse AI: Design Guide

Companion to `PRD.md`. This file defines how the product looks and feels so that Figma frames and code match. The visual identity continues the approved proposal deck (dark slate surfaces, teal accents, Montserrat, rounded cards, graduation-cap mark).

## 1. Design Principles

1. **Familiar first:** the chat should feel like WhatsApp. Nobody should need instructions.
2. **Trust is visible:** sources, "Verified by" badges and dates are part of every answer, not hidden.
3. **Fast and alive:** streaming text, subtle status messages and quick replies so it never feels slow or boring.
4. **Honest:** a clear "I don't know" state with the right contact is a designed feature.
5. **Calm:** dark teal surfaces, generous spacing, restrained motion.
6. **Works on a phone:** mobile first. Most students and freshers will use it on phones.

## 2. Visual Identity

Values are approximate, taken from the proposal deck. Sample exact colors from the deck in Figma and update `tokens.css` once.

### 2.1 Color tokens (dark theme is default)
```css
:root {
  /* surfaces */
  --bg:            #1C2127;   /* app background */
  --surface-1:     #252C33;   /* cards, bot bubble */
  --surface-2:     #2E363E;   /* inputs, raised cards */
  --surface-teal:  #1B3338;   /* highlighted cards, banners */
  --border:        #343C44;
  --border-teal:   #2A5C63;

  /* brand */
  --primary:       #17A8B4;   /* buttons, active states (use DARK text on it) */
  --primary-hover: #1CBAC7;
  --accent:        #4FD0D6;   /* links, labels, highlights */
  --user-bubble:   #1F5961;   /* user message (white text) */

  /* text */
  --text:          #F2F6F7;
  --text-muted:    #9AA5AD;
  --text-on-primary: #0B1418;

  /* status */
  --success:       #3DD68C;
  --warning:       #F5B84B;
  --danger:        #F0616D;
  --info:          var(--accent);

  /* shape and depth */
  --radius-sm: 8px;  --radius-md: 14px;  --radius-lg: 20px;  --radius-pill: 999px;
  --glow-teal: 0 0 24px rgba(79, 208, 214, 0.25);
}
```
**Contrast rule:** white text on `--primary` fails WCAG AA (about 2.9:1). Always use `--text-on-primary` on teal fills. White on `--user-bubble` passes (about 7.9:1).

### 2.2 Light theme (optional, Should)
Provide the same token names with light values (`--bg: #F4F8F9`, `--surface-1: #FFFFFF`, `--text: #12202A`, `--primary: #0E8A95`). Respect `prefers-color-scheme`, with a manual toggle.

### 2.3 Typography
- **Latin:** Montserrat (400, 500, 600, 700). Fallback `system-ui, sans-serif`.
- **Urdu:** Noto Nastaliq Urdu for message text, Noto Sans Arabic for UI labels. Use larger line height (1.9) for Nastaliq.
- **Scale:** 12 (meta), 14 (secondary), 16 (body and messages), 18 (section titles), 24 (page titles), 32 (hero).
- Messages are 16 px minimum. Never go below 12 px.

### 2.4 Iconography and imagery
- Icon set: Lucide, 1.75 px stroke, 20 px default.
- Brand mark: teal graduation cap inside a white circle with a soft teal glow (as in the deck). Use it as the bot avatar and app icon.
- Optional decorative element: concentric teal rings with a small orbiting dot, used only on the welcome screen and loading states.

### 2.5 Elevation and effects
Flat cards with 1 px borders. Use `--glow-teal` only for the brand mark and the active mic button. No heavy shadows.

## 3. Layout

### 3.1 Breakpoints
| Name | Width | Layout |
|---|---|---|
| Mobile | under 640 px | Single column, full-screen chat, bottom composer |
| Tablet | 640 to 1024 px | Centered chat column (max 720 px) |
| Desktop | over 1024 px | Chat column (max 760 px) with a right side panel (sources, deadlines, profile) |

### 3.2 Chat screen anatomy
```
┌──────────────────────────────────────────┐
│ [cap] Campus Pulse AI        ● online  ⋯ │  header (sticky)
│       Lahore Garrison University         │
├──────────────────────────────────────────┤
│  ┌ Upcoming deadlines ─────────────────┐ │  deadline card (dismissible)
│  │ Fee submission · 12 Oct             │ │
│  └─────────────────────────────────────┘ │
│                                          │
│  (cap) ┌───────────────────────────┐     │  bot bubble
│        │ The tuition fee for BSCS  │     │
│        │ is Rs 7,744 per credit    │     │
│        │ hour (FY 2026-27).        │     │
│        │ ✔ Verified by Admission   │     │  verified badge
│        │   Office · 2 Oct 2026     │     │
│        │ [Fee Structure] [Policies]│     │  source chips
│        │ ▶ Listen   👍  👎         │     │  actions
│        └───────────────────────────┘     │
│                    ┌───────────────────┐ │  user bubble
│                    │ And semester 2?   │ │
│                    └───────────────────┘ │
│  [Admission steps] [Timetable] [Contacts]│  quick replies
├──────────────────────────────────────────┤
│ [ Type a message…            ] [mic/send]│  composer
│ Answers are based on information verified│  disclaimer (12 px, muted)
│ by LGU offices. Please confirm important │
│ decisions with the relevant office.      │
└──────────────────────────────────────────┘
```

## 4. Components

| Component | Spec |
|---|---|
| **Header** | Brand mark avatar, title, status dot (green online, amber reconnecting or waking up, red offline), menu (profile, language, theme, delete my data) |
| **Message bubble (user)** | `--user-bubble`, white text, radius 14 with a smaller bottom-right corner, right aligned, timestamp 12 px muted |
| **Message bubble (bot)** | `--surface-1`, `--text`, radius 14 with a smaller bottom-left corner, left aligned, avatar on first message of a group |
| **Streaming text** | Tokens append in place. A blinking caret while streaming. No layout jump |
| **Typing and status** | Three-dot indicator, then short status text: "Searching fee records…", "Reading the handbook…", "Writing…" |
| **Source chip** | Pill, `--surface-2`, accent text, icon (file or office), title. Opens a bottom sheet with title, office, last verified date, and link |
| **Verified badge** | Small check icon, "Verified by <office> · <date>", success color. If expired: warning color, "May be outdated · last verified <date>" |
| **Passed-date notice** | Inline warning row: "This date has passed. Please confirm with <office>." |
| **Fallback card** | `--surface-teal` card: "I don't have verified information on this." plus office name, phone buttons (tap to call), email, and "Tell us what you were looking for" |
| **Quick replies** | Horizontal scroll chips below the last bot message, max 4 |
| **Deadline card** | Collapsible card with up to 3 upcoming dates, color-coded: danger under 3 days, warning under 14 days |
| **Composer** | Rounded input, grows to 5 lines, mic button when empty, send button when text exists, attach not needed in MVP |
| **Voice note bubble** | Waveform, duration, play and pause, transcript shown under it (collapsible) |
| **Feedback** | Thumbs up and down under each bot message. Thumbs down opens a small sheet with 3 reasons and a free text field |
| **Toasts** | Bottom, 4 seconds, for errors and confirmations |
| **Skeletons** | For history loading and admin tables |

## 5. Voice Experience

### 5.1 Voice message (WhatsApp-style)
1. **Idle:** mic button in the composer (accent outline).
2. **Recording** (hold or tap): the composer turns into a recording bar: red dot, timer, live waveform, "slide to cancel", lock icon to keep recording hands-free. Active mic uses `--glow-teal`.
3. **Sending:** voice bubble appears with a waveform and "Transcribing…".
4. **Transcript:** shown under the bubble, editable via "Edit and resend".
5. **Reply:** bot text streams in. A "Listen" button plays the spoken version (TTS) with a progress bar.
Limits shown in UI: 60 seconds maximum. Permission errors show a friendly "Allow microphone access" explainer.
Browser support: Chrome, Edge and Android Chrome show a live transcript while recording. In other browsers the audio is sent for server transcription and the transcript appears after sending. A small privacy note says that browser speech recognition may send audio to the browser vendor's speech service.

### 5.2 Live mode (hands-free)
- Full-screen overlay launched from a headset icon in the header.
- Center: the brand mark with concentric rings that **pulse with the voice level** (listening = teal, thinking = slow rotation of the orbiting dot, speaking = rings expand with the audio).
- Captions below in 2 lines (what you said, what the agent says).
- Controls: mute, end call, switch to text. Tap anywhere to interrupt the agent.
- Live mode needs speech recognition support. In unsupported browsers show "Live mode works in Chrome and Edge" and keep the headset icon disabled.
- If the microphone, network or provider fails, close gracefully and return to the chat with a note.

## 6. Screens

### 6.1 Public
1. **Welcome:** brand mark with rings, "Hi, I'm Campus Pulse. Ask me anything about LGU.", language toggle (English, اردو), primary button "Start chat", secondary "Continue as student" (profile setup), 4 starter chips.
2. **Chat:** as in Section 3.2.
3. **Student profile (sheet):** program (searchable select), semester, section, language. "Why we ask" note: used only to personalise timetable and fee answers. "Delete my data" link.
4. **Source sheet:** bottom sheet on source tap.
5. **Offline and error states:** see Section 8.

### 6.2 Admin portal (desktop first)
Layout: left sidebar (Dashboard, Content, Approvals, Unanswered, Users, Audit, Settings), top bar with search and profile, content area.

1. **Login:** centered card, brand mark, email and password, error text inline.
2. **Dashboard:** KPI cards (questions today, fallback rate, avg latency, thumbs-up rate), a free-tier usage card (AI calls today, database size against 500 MB, Redis commands this month), line chart (questions per day), bar chart (top categories), table (top 10 questions), "Needs attention" list (expired entries, thumbs-down answers, open unanswered).
3. **Content list:** tabs (Knowledge, Documents, Faculty, Timetable, Fees, Offices, Key dates). Table with status chips (draft, pending, approved, archived), expiry column with warning color, filters, bulk actions.
4. **Entry editor:** two-column form (fields and live preview of how the bot will cite it). Required: category, department, last verified, expiry. Buttons: Save draft, Submit for approval.
5. **Document upload:** drag and drop, extracted text preview, chunk preview count, required metadata, submit.
6. **Timetable import:** upload CSV, validation table with row-level errors highlighted, confirm.
7. **Approvals:** queue with side-by-side diff (current vs proposed), comment box, Approve and Reject.
8. **Unanswered questions:** list with count and last seen, actions "Create entry", "Mark handled", "Ignore".
9. **Users:** table with role, department, active toggle, invite form.
10. **Audit log:** filterable table (actor, action, table, date), row drawer with JSON diff.
11. **Settings:** institution name, disclaimer text, starter questions, contacts, live-fetch sources.

Tables are dense but readable (row height 48 px, zebra off, hover highlight). Destructive actions need a confirm dialog.

## 7. Motion

- Durations: 150 ms (hover, press), 250 ms (sheets, cards), 400 ms (page transitions, ring pulses).
- Easing: `cubic-bezier(0.2, 0.8, 0.2, 1)`.
- Allowed: bubble fade-and-rise on arrival, caret blink, waveform, ring pulse, skeleton shimmer.
- Not allowed: bouncing, full-screen animations during answers, autoplaying sound.
- Respect `prefers-reduced-motion`: disable ring pulses and rise animations, keep instant state changes.

## 8. States and Microcopy

| State | UI | Copy |
|---|---|---|
| Empty chat | Welcome block and starter chips | "Hi, I'm Campus Pulse. Ask me anything about LGU." |
| Loading history | Skeleton bubbles | n/a |
| Streaming | Status line and caret | "Searching fee records…" |
| Fallback | Fallback card | "I don't have verified information on this. The Exam Office can help: 042-37181828." |
| Expired data | Warning badge | "May be outdated · last verified 2 Mar 2026" |
| Passed date | Warning row | "This date has passed. Please confirm with the Admission Office." |
| Offline | Banner, composer disabled | "You're offline. Reconnecting…" |
| Provider down | Banner and plain answer if possible | "The assistant is busy right now. Here is what I found." |
| Rate limited | Inline notice | "You're sending messages fast. Please wait a moment." |
| Waking up (server cold start) | Header dot amber, skeleton reply, progress text | "Waking up the assistant. This can take up to a minute the first time." |
| Assistant at capacity (AI quota) | Inline notice, queue status, then the fallback card | "Lots of students are asking right now. Please try again in a minute, or contact the office." |
| No Urdu voice on this device | "Listen" button hidden for Urdu replies | "Voice playback isn't available in Urdu on this device." |
| Mic denied | Explainer sheet | "Allow microphone access to send voice messages." |
| Admin empty table | Illustration and CTA | "No entries yet. Add the first one." |

Tone: friendly, short, plain English. Avoid slang. Urdu copy must be reviewed by a native speaker. Never promise official outcomes ("You are eligible"). Say "According to the Admission Policy, the minimum is 50%".

## 9. Accessibility and Internationalisation

- WCAG 2.1 AA: contrast, focus rings (2 px `--accent` outline), labels on all controls, touch targets at least 44 px.
- Full keyboard use, including the admin tables. Screen reader labels for the mic button, status changes (`aria-live="polite"` for streaming), and source chips.
- **RTL:** use logical CSS properties (`margin-inline-start`, `padding-inline-end`). Bubbles mirror in RTL. Mixed English and Urdu text uses `dir="auto"` per message.
- Language toggle persists. Dates are shown as "5 Oct 2026" in both languages (Urdu digits are optional).
- Do not use color alone for status. Pair with icon and text.

## 10. Content Rules for the UI

- Bot answers: lead with the answer, then the details, then the source line.
- Fees: always show the currency (Rs), the unit (per credit hour or per semester) and the fiscal year.
- Dates: "Mon, 5 Oct 2026".
- Phone numbers are tappable links. Emails open the mail app.
- Long answers use short paragraphs and at most one list. No headings inside chat bubbles.

## 11. Optional: 3D Avatar (Could, not in the approved proposal)

If time remains after Phase 4:
- Lightweight 3D head or bust (glTF or VRM) shown only in Live mode, replacing the ring animation.
- States: idle, listening (head tilt), thinking, speaking (mouth driven by audio amplitude).
- Must have a 2D fallback (the rings) on low-end devices or when WebGL is unavailable. The chat must never depend on it.

## 12. Figma Handoff Checklist

1. Create a Figma library from Section 2 tokens (color styles, text styles, radius, effects).
2. Build components in Section 4 with variants and dark and light themes.
3. Design mobile frames first: Welcome, Chat (empty, streaming, answer with sources, fallback), Voice recording, Voice note bubble, Live mode, Profile sheet.
4. Then desktop admin frames: Login, Dashboard, Content list, Entry editor, Upload, Approvals, Unanswered, Audit.
5. Add an RTL (Urdu) version of the Chat screen.
6. Export tokens to `apps/web/styles/tokens.css` and keep names identical.
7. Name frames to match route names (`/`, `/chat`, `/admin/dashboard`) so Claude Code can map them.
