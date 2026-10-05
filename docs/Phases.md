# Campus Pulse AI: Phases and Delivery Plan

Companion to `PRD.md`. Milestones M1 to M7 and their week ranges are **the ones in the approved proposal**. This file adds the build tasks, exit criteria and the prompts to give Claude Code.

## 1. Overview

| Milestone | Weeks | Theme | Outcome you can demo |
|---|---|---|---|
| **M1** Requirements and Design | 1-2 | Plan and foundations | Repo, Docker Compose, CI, designs, data list, 100 student questions |
| **M2** Data and RAG Core | 3-5 | Brain | Questions answered from tables and approved knowledge with sources, measured on a golden set |
| **M3** Real-time Chat MVP | 6-8 | Face | WhatsApp-style chat over WebSocket with sources, badges, feedback |
| **M4** Multimodal Voice | 9-11 | Voice | Voice messages with transcript and spoken reply. Live mode (Should) |
| **M5** Admin Portal | 12-14 | Control | RBAC portal, approvals, monitoring, audit, student profiles, deadlines |
| **M6** Deployment and Hardening | 15-16 | Production | Docker API on Render, web on Vercel, Supabase production project, CI/CD, monitoring, security and load tests. All free tiers (the proposal says AWS, so get the wording approved) |
| **M7** Testing and Final Delivery | 17 | Proof | Final eval, UAT results, documentation, demo and viva |

**MVP line:** M1 to M3 plus a minimal data-entry path (built in M2) is the smallest complete product. Everything after that adds the proposal's voice, admin, and deployment promises.

### Sprint plan (Scrum, 2-week sprints)

| Sprint | Weeks | Contents |
|---|---|---|
| S1 | 1-2 | M1 |
| S2 | 3-4 | M2 part 1: schema, seeds, structured tools, minimal admin |
| S3 | 5-6 | M2 part 2: RAG, agent, eval; start M3 chat UI |
| S4 | 7-8 | M3: WebSocket streaming, sources, feedback, Redis |
| S5 | 9-10 | M4: voice messages, STT and TTS, Urdu test |
| S6 | 11-12 | M4 finish (live mode); start M5 admin portal |
| S7 | 13-14 | M5: approvals, monitoring, audit, profiles, deadlines |
| S8 | 15-16 | M6: deployment, CI/CD, hardening |
| Final | 17 | M7 |

Each sprint ends with: demo, eval score, updated `Memory.md`, retrospective notes.

## 2. Cut Rules (protect the schedule)

Review at the end of **W8** and **W11**. If behind, cut in this order:
1. 3D avatar, WebRTC live mode, reminders, email OTP (Could)
2. Light theme, version history, CSV export
3. Live conversational mode (keep voice messages)
4. Live-fetch tool (keep manual key-date updates)
5. Urdu voice (keep Urdu text)

**Never cut:** approval workflow, citations and verified badges, fallback, structured tools, audit log, RBAC, golden-set evaluation, deployment.

## 3. Milestone Details

### M1 · Requirements and Design (W1-2)

**Tasks**
- [ ] Confirm PRD, Architectural, DESIGN, Phases with the supervisors. Get approval for the free-tier hosting instead of AWS and update the stack and architecture slides.
- [x] Create repo with the layout from `Architectural.md` Section 4, plus `CLAUDE.md` containing: "Read docs/Memory.md first." (2026-10-05)
- [ ] **Free accounts (no card):** GitHub, Supabase (create `campus-pulse-dev` and `campus-pulse-prod`), Vercel, Render, Upstash, Google AI Studio, UptimeRobot, Sentry (optional). Confirm AI Studio works from Pakistan.
- [ ] Record every service's free limits (from its dashboard) and the chosen Gemini model IDs in `Memory.md`.
- [ ] `docker-compose.yml`: web, api, optional local redis, connected to the **dev** Supabase project. `make up`, `make down`, `make test`.
- [x] FastAPI skeleton with `/healthz`, `/readyz`, config loader, structured logging. (2026-10-05)
- [x] Next.js skeleton with `tokens.css` from `DESIGN.md`. (2026-10-05)
- [x] GitHub Actions: lint, type check, tests on pull requests. (2026-10-05, first run on GitHub pending)
- [ ] Figma: tokens, components, mobile chat frames, admin frames (see `DESIGN.md` Section 12).
- [ ] Data work: list of LGU documents to upload, 100 real student questions collected (form or WhatsApp), two staff contacts identified.

**Exit criteria:** api and web run locally against the dev Supabase project, CI is green, free accounts created and limits recorded in `Memory.md`, designs reviewed, 100 questions collected.

**Kickoff prompt for Claude Code**
> Read docs/Memory.md, docs/PRD.md and docs/Architectural.md. Execute milestone M1 from docs/Phases.md: create the repo skeleton, docker compose (web, api, optional redis, pointing at a dev Supabase project through env vars), FastAPI health endpoints, Next.js skeleton using DESIGN.md tokens, and GitHub Actions for lint and tests (with a pgvector Postgres service container). Use free services only and do not add any paid dependency. Do not build features yet. Show me what runs, then update Memory.md.

### M2 · Data and RAG Core (W3-5)

**Tasks**
- [ ] Alembic migrations for all tables in `Architectural.md` Section 5, run against the Supabase dev project (session pooler URL): `vector(768)`, HNSW and GIN indexes, RLS enabled with no policies, and the `hybrid_search` SQL function.
- [ ] Seed scripts in `seed/lgu/`: offices, fees, key dates, faculty sample, 30 knowledge entries, timetable sample CSV.
- [ ] Structured tools with unit tests: `get_timetable`, `find_faculty`, `get_fee`, `get_office`, `get_key_dates`.
- [ ] **Minimal admin path** (API plus very simple pages, or CLI import): CRUD for knowledge entries, CSV import for timetable and faculty, text PDF upload. Full portal comes in M5.
- [ ] Ingestion service: extract text, chunk, embed, upsert, re-embed on edit.
- [ ] Retrieval: `hybrid_search` (vector plus keyword, RRF in SQL), filters, embedding cache with Gemini 768-dimension embeddings. No reranker model (optional LLM rerank behind a flag, default off).
- [ ] LangGraph agent v1 within the LLM budget (at most 2 LLM calls and 1 embedding call per turn): normalize, plan, tools, deterministic grader, composer rules, fallback, today's date injection, response cache, template answers for exact data.
- [ ] `eval/golden.jsonl` v1 (at least 50 items) and `make eval` printing metrics.
- [ ] Redaction utility with tests.
- [ ] `LLMProvider` interface with a Gemini adapter, a **fake LLM** for tests, and the quota guard (per-minute and per-day counters).

**Exit criteria:** `make eval` runs. At least 80% correct on golden v1, 0 invented numbers, fallback works, timetable and fee answers match tables exactly.

**Kickoff prompt**
> Execute M2 from docs/Phases.md. Start with migrations and seeds, then the structured tools with tests, then ingestion and retrieval, then the LangGraph agent. Follow the composer rules in Architectural.md Section 6. Build the minimal admin path only. After each part, run tests and show the results.

### M3 · Real-time Chat MVP (W6-8)

**Tasks**
- [ ] WebSocket gateway (`/ws/chat`) streaming `status`, `token`, `sources`, `final` events.
- [ ] Upstash Redis: session memory (last 6 turns), rate limiting, response cache with `data_version`, quota counters. At most 10 commands per turn, in-process fallback.
- [ ] Chat UI per `DESIGN.md`: bubbles, streaming, typing and status, source chips and sheet, verified badge, fallback card, quick replies, feedback, disclaimer, starter questions.
- [ ] Reconnect and resume (CHAT-9).
- [ ] Cold-start handling (COST-6): wake ping on page load, "waking up" state, WebSocket retry with backoff. Test with a sleeping Render service.
- [ ] Anonymous sessions (`anon_id`), conversation history endpoint.
- [ ] Feedback endpoint and `unanswered_queries` logging.
- [ ] Playwright smoke tests for the main chat flow.
- [ ] Golden set grows to 100 items. Re-run eval.

**Exit criteria:** end-to-end chat works on a phone browser. p95 first token under 4 s with the server awake. Rate limit and quota guard work. Golden set at least 85%.
**Checkpoint at the end of W8:** apply the cut rules if needed. **MVP is complete here.**

**Kickoff prompt**
> Execute M3 from docs/Phases.md. Implement the WebSocket protocol from Architectural.md Section 8, Redis session memory and rate limiting, and the chat UI from DESIGN.md Sections 3 and 4. Use tokens.css only. Add Playwright smoke tests. Show me the chat running and the eval score.

### M4 · Multimodal Voice (W9-11)

**Tasks**
- [ ] Voice interfaces (`STTProvider`, `TTSProvider`) with browser adapters (Web Speech API, speechSynthesis) and a server fallback adapter (Gemini audio transcription, processed in memory).
- [ ] Voice message endpoint and UI: record, waveform, send, transcript, edit and resend.
- [ ] Spoken replies: "Listen" button using browser speech synthesis, voice-style answers (short, no markdown), hide the button when the device has no voice.
- [ ] Voice limits (60 s, 10 MB) and MIME checks for the server fallback. Audio is never stored.
- [ ] **Urdu test (W9):** 20 Urdu and Roman Urdu phrases on at least 3 real devices (Android Chrome, Windows Chrome, Windows Edge). Record recognition accuracy and which devices have an Urdu voice in `Memory.md`.
- [ ] **Decision point (W9):** commit to live mode on browser speech (default), or try the Gemini Live API if free quota allows. No WebRTC.
- [ ] Live mode (Should): continuous browser speech recognition, speech synthesis sentence by sentence, barge-in by cancelling playback and generation, overlay UI per `DESIGN.md` Section 5.2. The server sees text only.
- [ ] Voice-specific eval items added to the golden set.

**Exit criteria:** voice message round trip p95 under 8 s. Transcripts shown. Spoken replies work. Live mode works for at least a 3-turn conversation (or is formally cut with a note).

**Kickoff prompt**
> Execute M4 from docs/Phases.md. First the voice interfaces with browser adapters and the server fallback, and voice messages end to end. Then run the Urdu test on real devices and report accuracy honestly. Only after that build live mode on browser speech with barge-in. Do not start WebRTC and do not store audio.

### M5 · Admin Portal (W12-14)

**Tasks**
- [ ] Authentication with Supabase Auth: staff and admin sign in (accounts created by an admin through the Supabase Admin API, email pre-confirmed), students use anonymous sign-in, the API verifies the Supabase JWT and reads the role from `profiles`. RLS deny-by-default tests.
- [ ] RBAC with tests (matrix in `Architectural.md` Section 11): staff limited to their department or office.
- [ ] Admin UI per `DESIGN.md` Section 6.2: dashboard, content tabs, editor, upload, timetable import, approvals with diff, unanswered queue, users, audit log, settings.
- [ ] Approval workflow and immediate re-embed on approval.
- [ ] Expiry review queue and email or in-app reminder to owners.
- [ ] Monitoring dashboard: questions per day, fallback rate, latency, thumbs, top questions.
- [ ] Student accounts and profile (program, semester, section), "Delete my data".
- [ ] Deadlines card from `key_dates`.
- [ ] Live-fetch tool with allowlist (Should), if not already done.
- [ ] Onboard two real staff users and collect feedback.

**Exit criteria:** staff edit an entry, admin approves, the chat reflects it within seconds. RBAC tests pass. Audit log records every action. Dashboard shows real numbers.

**Kickoff prompt**
> Execute M5 from docs/Phases.md. Start with auth and RBAC and write the permission tests first. Then build the admin screens from DESIGN.md Section 6.2, the approval workflow with immediate re-embedding, the audit log and the monitoring dashboard. Then student profiles and the deadlines card.

### M6 · Deployment and Hardening (W15-16)

**Tasks**
- [ ] Production Dockerfile for the api (multi-stage, non-root, one worker, fits 512 MB RAM) and `render.yaml`.
- [ ] Free hosting: Vercel (web), Render free web service (api), Supabase prod project, Upstash Redis. Environment variables and secrets set in each dashboard. Keep dev and prod separate. Set CORS to the Vercel domain.
- [ ] CI/CD: GitHub Actions runs tests and Alembic migrations on merge to `main` (pooler URL in secrets). Render and Vercel auto-deploy. Smoke test `/readyz`. Rollback note.
- [ ] Monitoring: UptimeRobot checks `/readyz`, Sentry free tier (optional), admin dashboard metrics and free-tier usage card, alerts by email or Telegram. Scheduled jobs through GitHub Actions calling `/internal/jobs/daily` (retention, expiry reminders, usage rollup, Supabase keep-alive).
- [ ] Export-all-data button, seed files in git, and a tested restore into a fresh Supabase project (the free plan has no automatic backups).
- [ ] Security pass: dependency scan, headers, upload checks, prompt-injection tests, rate limits, secrets audit.
- [ ] Load test: 10 concurrent chat sessions (limited by free LLM quotas). Record the quota ceiling honestly. Fix bottlenecks.
- [ ] Degraded-mode tests (LLM quota exceeded, LLM down, Redis down, live fetch down, Render cold start, Supabase paused).

**Exit criteria:** public HTTPS URL works. A merge to `main` deploys automatically. Alerts fire in a test. Load and security checks pass.

**Kickoff prompt**
> Execute M6 from docs/Phases.md. Create the production Dockerfile, render.yaml, GitHub Actions workflows (CI, migrate, scheduled jobs), monitoring, export and restore, and the security and load tests. Use free tiers only. List every account or setting I must create by hand, and wait for my confirmation before using any credentials.

### M7 · Testing and Final Delivery (W17)

**Tasks**
- [ ] Final golden-set run and report (accuracy, fallback correctness, latency, injection tests, Urdu items).
- [ ] UAT with at least 15 students and 3 staff: task list, thumbs, comments, time-to-answer.
- [ ] Fix top issues from UAT. Freeze features.
- [ ] Documentation: README, setup guide, user guide for staff, API docs, architecture summary.
- [ ] Demo script (5 minutes) and a backup screen recording.
- [ ] Viva preparation: top 20 expected questions with answers (use `Architectural.md` Section 16).
- [ ] Final `last_verified` pass on all seeded data with the offices.

**Exit criteria:** metrics in `PRD.md` Section 3 are reported honestly, with any misses explained. Demo runs from the deployed system.

**Kickoff prompt**
> Execute M7 from docs/Phases.md. Run the full evaluation and produce a report with tables. Prepare the UAT task sheet and a feedback form. Generate the README and staff user guide. Do not add features.

## 4. Weekly Rhythm (Scrum)

| Day | Activity |
|---|---|
| Sprint day 1 | Plan: choose tasks from this file, write acceptance checks |
| Daily | 10-minute stand-up (team), update `Memory.md` status |
| Mid-sprint | Run `make eval`, review the score trend |
| Sprint last day | Demo to supervisor, retrospective (what to keep, change), update plan |

## 5. Working with Claude Code

1. Keep the five docs in `docs/` and a root `CLAUDE.md` with one line: "Read docs/Memory.md first."
2. One milestone per session. Paste the kickoff prompt, then review the diff and test results.
3. Ask for a plan before large changes ("Show me the plan, then wait").
4. After each session ask: "Update Memory.md status and add a session log entry."
5. Commit small and often. Review RBAC, auth, prompts and migrations by hand.
6. If Claude Code proposes anything in the Non-Goals list (scraping, OCR, graph DB, private records), say no and point to `Memory.md` D1, D2, D11.

## 6. Risk Checkpoints

| Week | Check | If it fails |
|---|---|---|
| W2 | Free accounts created, Gemini key works, free limits recorded, 100 questions collected | Block M2 start until done |
| W5 | Golden v1 at least 80% | Fix data and retrieval before building UI |
| W8 | MVP chat works end to end | Apply cut rules |
| W8 | Quota check: LLM calls per turn and daily usage within the free limits | Reduce calls, add cache and templates, add a second provider |
| W9 | Urdu STT and TTS test, live mode decision | Cut Urdu voice, WebSocket only |
| W11 | Voice messages stable | Cut live mode |
| W14 | Staff can update data and the bot reflects it | Simplify portal, finish approvals first |
| W16 | Deployed on free tiers with CI/CD | Fall back to manual deploys from the Render and Vercel dashboards |
