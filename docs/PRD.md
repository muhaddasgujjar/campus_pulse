# Campus Pulse AI: Product Requirements Document (PRD)

| | |
|---|---|
| **Version** | 3.0 (Oct 2026): zero-cost stack (Supabase and other free tiers), aligned with the approved FYP proposal deck |
| **Product** | Campus Pulse AI, a real-time multimodal university student support platform |
| **Institution** | Lahore Garrison University (LGU), Department of Computer Science |
| **Team (per proposal)** | Semab Rafi (Fa23-BSCS-270), Farheen Ali (Fa23-BSCS-256) |
| **Supervisor / Co-supervisor** | Ma'am Faria Khan / Muhammad Muhhadas |
| **Companion docs** | `Architectural.md`, `DESIGN.md`, `Memory.md`, `Phases.md` |
| **Audience** | Claude Code (build agent), the team, and the supervisors |

---

## 1. Summary

Campus Pulse AI gives LGU students fast, personalised support through a **WhatsApp-style chat** where users can **type or send voice messages**, plus a **live conversational (voice) mode**. Answers come from **official, staff-approved, dated university information**, not from scraped data and not from the model's own memory.

**Core idea:** information is owned by LGU staff, approved by an admin, and dated. Freshness comes from a **staff portal and a live-fetch tool**, not from a crawler. Every answer shows its source and "verified on <date>". If the bot does not know, it says so and gives the right office contact.

## 2. Problem and Users

**Problem (from proposal):** information on fees, deadlines, admission steps, timetables, scholarships, rules and exams is scattered across websites, PDFs, notice boards and staff desks. Students wait long for simple answers, staff repeat the same answers all day, and late information causes missed fee or scholarship dates.

| User | Need | Priority |
|---|---|---|
| **Freshers (main users)** | Admission steps, eligibility, entry test, required documents, fee at admission, scholarships, hostel, dress code, rules | Primary |
| **Current students** | Timetable, fees, exams, policies, deadlines, offices | Primary |
| **University staff** | A separate portal to manage and update information, see what students ask | Primary (content owners) |
| **Other universities** | Adapt the platform to their own data | Design-for only (see ADP) |

## 3. Goals, Non-Goals, Success Metrics

### Goals
1. Quick, correct answers to common LGU questions, in text and voice, in English and Urdu.
2. Exact answers for exact data (timetable, faculty, fees, contacts) using SQL, not vector guessing.
3. Staff can update information themselves and the bot reflects it **immediately**.
4. Never invent information. Honest fallback with the right office contact.
5. Help students not miss deadlines.
6. Production-style delivery: secure (RBAC, audit logs), observable, containerised, deployed with CI/CD, **at zero cost** (free tiers only, no credit card).

### Non-Goals (do NOT build)
- **No website crawler or scheduled scraping pipeline.**
- **No OCR model or pipeline.** Image-only content (for example the academic calendar image) is typed in by an admin.
- No access to private student records (results, attendance, fee status) and no login to `student.lgu.edu.pk`. Future scope.
- No model training or fine-tuning (retrieval only).
- No graph database or knowledge graph.
- No multi-tenant admin UI for other universities (the data model is ready for it, the UI is not built).
- **No paid services and no credit card.** Every component must run on a free tier. AWS is out of scope (Docker keeps the API portable to AWS later).

### Success metrics (targets, to be agreed with supervisors)
| Metric | Target |
|---|---|
| Correct answers on golden set (100+ questions) | at least 85% |
| Correct fallback on questions with no data | at least 90% |
| Answers carrying a valid source | 100% (excluding small talk) |
| Invented phone numbers, fees or dates | 0 |
| Exact-data answers (timetable, fees) matching tables | 100% |
| First token latency (text), p95, server awake | under 4 s |
| Voice message round trip (send to text reply), p95, server awake | under 8 s |
| Monthly cost | Rs 0 (free tiers only, no card) |
| UAT thumbs-up rate (at least 15 students and 3 staff testers) | at least 80% |
| Time for staff to update one entry | under 2 minutes |

## 4. Product Principles
1. **Verified or silent:** no source, no answer.
2. **Dated:** every fact shows when it was last verified. Past deadlines are called out as passed.
3. **Structured first:** if the answer lives in a table, query the table.
4. **Staff own the truth:** each entry has an owner, an approver and an expiry date.
5. **Chat that feels familiar:** WhatsApp-style, quick, friendly, never boring.

## 5. Scope Summary (MoSCoW)

| Priority | Items |
|---|---|
| **Must** | WhatsApp-style chat with WebSocket streaming, RAG plus structured tools, certified KB with approval workflow, document upload (text PDFs), fallback, citations and verified badges, voice messages (STT, TTS), admin portal with RBAC and audit log, Redis (sessions, rate limit, cache), Docker, free-tier deployment (Vercel, Render, Supabase) with CI/CD, monitoring, golden-set evaluation |
| **Should** | Student profile (program, semester, section) for personalised answers, upcoming-deadlines card, live-fetch tool for volatile pages, live conversational voice mode (hands-free), Urdu and Roman Urdu quality pass, expiry review queue, unanswered-questions queue |
| **Could** | WebRTC-based live agent, LGU-email OTP to verify a student, deadline reminders (email or push), weekly "page changed" alerts, 3D avatar |
| **Won't** | See Non-Goals |

Phase mapping and week plan: see `Phases.md`.

## 6. User Journeys

**Fresher:** opens the chat, taps "How do I apply?", gets the admission steps, eligibility (with source and date), and the fee at admission. Sees "Last date to apply has passed. Please confirm with the Admission Office" if the data shows a past date, and gets the office's phone numbers.

**Current student:** creates a profile once (program, semester, section). Asks "What's my timetable on Tuesday?" and gets an exact answer from the timetable table. Sends a voice note asking about the datesheet and gets a text reply, optionally spoken.

**Staff (office or department):** logs in, edits an entry or uploads a PDF, submits it. Admin approves. Within seconds the bot answers with the new information. Staff also see which questions the bot could not answer.

## 7. Functional Requirements

Priority key: **M** Must, **S** Should, **C** Could. IDs are referenced by tests and commits.

### 7.1 Authentication and RBAC
| ID | Requirement | P |
|---|---|---|
| AUTH-1 | Roles: `anonymous` (chat only), `student` (optional account), `staff`, `admin` | M |
| AUTH-2 | Staff and admin sign in with **Supabase Auth** (email and password). Accounts are created by an admin (no email sending needed). The API verifies the Supabase JWT on every request and reads the role from the `profiles` table | M |
| AUTH-3 | RBAC enforced on the **server** for every admin endpoint. Staff can edit only rows of their own department or office | M |
| AUTH-4 | Students use Supabase **anonymous sign-in** by default (no email needed). The server stores only a profile (program, semester, section, language). No roll number or CNIC | S |
| AUTH-5 | Verify a student with a one-time code sent to an LGU email address (needs a free custom SMTP provider) | C |

### 7.2 Chat (WhatsApp-style)
| ID | Requirement | P |
|---|---|---|
| CHAT-1 | Familiar chat UI: bubbles, timestamps, typing indicator, scrollable history. See `DESIGN.md` | M |
| CHAT-2 | Real-time streaming of answers over WebSocket. First token under 4 s (p95) with the server awake | M |
| CHAT-3 | Each answer shows source chips, a "Verified by <office>" badge and the `last_verified` date | M |
| CHAT-4 | Thumbs up and down with an optional comment | M |
| CHAT-5 | Session memory: last 6 turns kept in Redis for 24 hours | M |
| CHAT-6 | Starter questions on the empty screen (apply, fees, timetable, faculty, contacts, scholarships) | M |
| CHAT-7 | Rate limit anonymous users (for example 20 messages per 10 minutes per IP), enforced in Redis | M |
| CHAT-8 | Disclaimer footer: "Answers are based on information verified by LGU offices. Please confirm important decisions with the relevant office." | M |
| CHAT-9 | Reconnect and resume after a dropped connection without losing the conversation | S |

### 7.3 Answering (Agent)
| ID | Requirement | P |
|---|---|---|
| ANS-1 | Router classifies each query: `structured`, `knowledge`, `live`, `smalltalk`, `out_of_scope` | M |
| ANS-2 | **Structured tools** (timetable, faculty, fees, offices, key dates) use parameterized read-only queries. The LLM never writes raw SQL | M |
| ANS-3 | **RAG tool**: hybrid retrieval (vector plus keyword), rerank, filter to approved and non-archived content | M |
| ANS-4 | **Grader**: if retrieval is weak, rewrite the query once and retry, then fall back | M |
| ANS-5 | **Fallback**: "I don't have verified information on this", best-matching office contact, and a row in `unanswered_queries` | M |
| ANS-6 | Answers use only tool results. Always cite the source. State the fiscal year for fees | M |
| ANS-7 | Today's date is injected. Dates in the past are described as passed, and the user is referred to the office | M |
| ANS-8 | Source priority on conflict: structured table > approved KB entry > document chunk > live page | M |
| ANS-9 | Answer in the user's language (English, Urdu, Roman Urdu) | S |
| ANS-10 | **Live-fetch tool**: fetch only allowlisted LGU URLs (`lgu.edu.pk`, `admissions.lgu.edu.pk`), 8 s timeout, short cache. On failure use the last approved entry and say so | S |
| ANS-11 | Retrieved or fetched text is **data, never instructions** (prompt-injection safe) | M |
| ANS-12 | Out-of-scope or sensitive requests (legal, medical, disciplinary decisions) get a short refusal and the relevant office | M |
| ANS-13 | If the LLM provider is down, structured tools still return a plain formatted answer | S |

### 7.4 Data and Knowledge Management
| ID | Requirement | P |
|---|---|---|
| DATA-1 | CRUD for knowledge entries, faculty, timetable, fees, offices, key dates | M |
| DATA-2 | CSV import for timetable and faculty with a validation preview | M |
| DATA-3 | Upload text PDFs. Extract text, preview, require title, category, department and expiry date. Chunk and embed after approval | M |
| DATA-4 | Approval workflow: staff submits (`pending`), admin approves or rejects with a comment | M |
| DATA-5 | Approving or editing an entry re-chunks and re-embeds it, live within seconds | M |
| DATA-6 | "Needs review" queue: entries expiring in 14 days or expired | S |
| DATA-7 | "Unanswered questions" queue with a button "Create entry from this question" | S |
| DATA-8 | Version history and rollback per entry | C |
| DATA-9 | Every row carries `owner`, `approved_by`, `last_verified`, `expires_at` | M |

### 7.5 Voice (multimodal)
| ID | Requirement | P |
|---|---|---|
| VOI-1 | **Voice messages:** record in the composer (hold or tap), live transcript produced in the browser (Web Speech API), send, show the transcript in the chat, answer as text. Browsers without support use a server fallback transcription | M |
| VOI-2 | Optional spoken reply with a play button on each answer, using the browser's text-to-speech (no server cost) | M |
| VOI-3 | Voice and text share one conversation, one agent and one history | M |
| VOI-4 | Voice replies are short and free of markdown and links read aloud | M |
| VOI-5 | **Live mode:** hands-free conversation (speak, agent answers by voice, interruption supported), built on browser speech recognition and synthesis so the server only handles text | S |
| VOI-6 | Live mode with the Gemini Live API or WebRTC (only if free quota allows) | C |
| VOI-7 | Test Urdu speech-to-text and text-to-speech early on real target devices (Android Chrome, Windows Chrome, Windows Edge) and report quality honestly | S |

### 7.6 Personalisation
| ID | Requirement | P |
|---|---|---|
| PER-1 | Student profile: program, semester, section, preferred language | S |
| PER-2 | Profile fills missing tool arguments ("my timetable", "my fee") | S |
| PER-3 | No private records. Personalisation uses only the self-declared profile in MVP | M |

### 7.7 Deadlines
| ID | Requirement | P |
|---|---|---|
| DDL-1 | Home screen shows an "Upcoming deadlines" card from `key_dates` (admission, fee, scholarship, exams) | S |
| DDL-2 | Reminders by email or push for chosen deadlines | C |

### 7.8 Admin Portal, Monitoring, Audit
| ID | Requirement | P |
|---|---|---|
| ADM-1 | Separate staff and admin portal with a role-aware dashboard | M |
| ADM-2 | Audit log of every create, update, approve, delete and login, viewable by admin | M |
| ADM-3 | Monitoring dashboard: questions per day, top questions, fallback rate, thumbs-down answers, average latency, tool usage | M |
| ADM-4 | User management (create staff, set role and department, deactivate) | M |
| ADM-5 | Export unanswered questions and feedback as CSV | S |

### 7.9 Security, Observability, Delivery
| ID | Requirement | P |
|---|---|---|
| SEC-1 | Secrets only in environment variables. `.env.example` provided | M |
| SEC-2 | CORS restricted, input length limits, parameterized queries, security headers | M |
| SEC-3 | Redact CNIC, phone and roll-number patterns from logs and stored chat text | M |
| SEC-4 | Dependency and image scanning in CI | S |
| SEC-5 | Redact personal data before text goes to the free LLM tier (providers may use free-tier data to improve products) and show a privacy note in the app | M |
| OBS-1 | Structured JSON logs with request ID. Health endpoints `/healthz` and `/readyz` | M |
| OBS-2 | Metrics endpoint and an admin dashboard computed from the database. Error tracking on a free tier (optional) | M |
| OBS-3 | LLM call logging (tool used, latency, tokens, quota usage) in the database. Optional free-tier tracing tool | S |
| OPS-1 | Dockerfile for the api (deployed on Render). `docker compose up` runs api, web and Redis locally against a development Supabase project | M |
| OPS-2 | GitHub Actions CI: lint, test, migrate. Auto-deploy through the Render and Vercel Git integrations | M |
| OPS-3 | Seed files in git plus an admin "Export all data" button, and a documented, tested restore (the free plan has no automatic backups) | S |

### 7.10 Adaptability
| ID | Requirement | P |
|---|---|---|
| ADP-1 | Every content table has `institution_id`. LGU is institution 1 | M |
| ADP-2 | Institution-specific text (name, disclaimer, contacts, allowlisted domains, starter questions) lives in config and seed files, not in code | M |

### 7.11 Zero-Cost Operation
| ID | Requirement | P |
|---|---|---|
| COST-1 | Every service runs on a free plan without a credit card. Record each service's free limit in `Memory.md` and re-check it in week 1 | M |
| COST-2 | **LLM budget:** at most 2 LLM calls and 1 embedding call per user turn. Exact-data answers may use templates with 0 LLM calls | M |
| COST-3 | Cache answers to repeated questions (normalized text, language, `data_version`) so common fresher questions cost nothing | M |
| COST-4 | Quota guard: count LLM calls per minute and per day. Near the limit, queue briefly, then show a friendly busy message with the office contact. Show usage in the admin dashboard | M |
| COST-5 | LLM provider interface with a fallback chain: primary free LLM, optional second free provider, then template answers | S |
| COST-6 | Cold-start handling: wake the API when the page loads, show a "waking up" state, retry the WebSocket with backoff | M |
| COST-7 | Keep the free Supabase project active (real traffic plus a scheduled daily check) and alert if it is paused | M |
| COST-8 | Stay under the 500 MB database limit: 768-dimension embeddings, chat retention of 60 days by default, size alert at 80% | M |
| COST-9 | Never store audio. Voice is transcribed in the browser, or in memory on the server for the fallback | M |

## 8. Non-Functional Requirements
- **Accuracy over fluency:** refuse before guessing.
- **Latency:** see success metrics. Cache structured lookups in Redis with invalidation when data changes.
- **Availability:** chat keeps working if live fetch or voice providers fail.
- **Privacy:** store only chat text, optional profile and feedback. Do not ask for CNIC, roll numbers or passwords. Redact if shared.
- **Accessibility:** keyboard navigation, readable contrast, RTL layout and a proper Urdu font.
- **Maintainability:** typed code, tests for every tool and the router, clear README per milestone.
- **Cost:** Rs 0 per month. Free tiers only, no card. Use the LLM budget (COST-2), cache repeated questions, and keep the database and Redis within their free limits.

## 9. Content and Seed Data

Collected from public LGU pages in Oct 2026. **Verify with the offices before the demo** and set `last_verified` to the real verification date.

**Structure:** four faculties (Social Sciences, Computer Sciences, Languages, Basic Sciences) and the departments and offices listed in the site menu (Registrar, Academics Branch, Treasurer, HR, IT, QEC, ERP, Student Affairs and Counselling, ORIC, Internationalization, IBTIDA, Procurement and Purchase, Project Department).

**Contacts**
- Admission Office: 0322-2757543, 0329-4292976, 042-37181827, 042-37181821-22, admissions@lgu.edu.pk
- Exam Office: 042-37181828
- Hours: Monday to Friday, 08:00 to 16:00
- Address: Main Campus, Sector C, DHA Phase 6, Lahore

**Fees FY 2026-27 (sample rows from the fee-structure page)**
- Faculty of Computer Sciences (BSCS, BSSE, BSIT, BSDS, BSAI, BS CySec): admission fee 17,500; tuition per credit hour 7,744; misc 6,360 per semester; about 18 credit hours in semester 1
- BBA: tuition per credit hour 7,392; misc 5,360
- The HND table on the same page is FY 2024-25. Store the fiscal year per row and always state it.

**Admissions (Fall 2026 page)**
- Minimum 50% marks in intermediate. Mathematics is the basic eligibility for BS programs. Students without mathematics take 6 credits of deficiency courses. F.A and I.Com are not eligible for Computer Science programs.
- Entry tests are walk-in. The page listed "Last Date to Apply: 02 Oct 2026", which has passed as of 5 Oct 2026, so the bot must say it has passed and refer to the office.
- Some programs need no entry test and admit on merit.

**Documents for upload (text PDFs from the Policies page):** Student Handbook, Admission Policy (Undergraduate and Graduate), Undergraduate Education Policy, Financial Assistance and Scholarship Policy, Grievances Management Policy, Hostel SOP, Anti-Plagiarism Policy.

**Typed by hand:** key dates from the academic calendar image (semester start, mid-terms, finals, breaks).

**Golden FAQ set:** 100 to 150 real student questions with verified answers, collected from classmates and offices. This is also the evaluation set.

## 10. Evaluation and Acceptance
- `eval/golden.jsonl` with at least 100 items: `question`, `expected_facts`, `expected_tool`, `should_fallback`. Include 20 questions with no data, 10 prompt-injection attempts, 10 Urdu or Roman Urdu questions.
- `make eval` prints the metrics in Section 3.
- **UAT (week 17):** at least 15 students and 3 staff members use the system for real tasks. Collect thumbs, comments and time-to-answer.
- Load test: 10 concurrent chat sessions (the ceiling is set by free LLM quotas) without errors and with p95 first token under 6 s. Report the quota limits honestly.

## 11. Risks and Mitigations
| Risk | Mitigation |
|---|---|
| Staff do not maintain data | Seed everything first, onboard 2 real staff, expiry reminders, unanswered-questions queue |
| Live voice takes too long | Voice messages first. Live mode on browser speech, no WebRTC. Decide at week 9 |
| Urdu speech quality is weak | Test in week 9, keep text Urdu as the baseline, report limits honestly |
| Wrong answer on fees or deadlines | Structured tables, fiscal year, date check, disclaimer, golden set |
| "Cannot verify identity" gap from the proposal | MVP uses self-declared profile only. Email OTP verification is a Could. Private records are future scope |
| Scope too large for 17 weeks | MoSCoW and the cut rules in `Phases.md` |
| Free LLM quota is small and unpublished | LLM budget of 2 calls per turn, response cache, template answers, quota guard, optional second provider, fake LLM in tests |
| Render free cold starts (about 1 minute) and 512 MB RAM | Wake ping, waking-up state, no local ML models, single worker |
| Supabase free project pauses after 7 days idle and has no backups | Daily keep-alive job, traffic during UAT, export button, seed files in git |
| 500 MB database limit | 768-dimension vectors, 60-day chat retention, size alert |
| Free-tier LLM data may be used by the provider | Redact personal data, no private records, privacy note in the app |
| Hosting differs from the proposal (AWS) | Docker keeps the API AWS-ready. Ask the supervisors to accept free hosting and update the slide wording |

## 12. Open Questions
1. Who are the first two real staff users (Exam Office, one department)?
2. Where does the timetable come from (spreadsheet from the department)?
3. Does Google AI Studio (Gemini free tier) work from the team's accounts in Pakistan, and which model IDs will we use?
4. Do the supervisors accept "Docker, AWS-ready, hosted on free tiers" instead of AWS in the proposal?
5. Should the 3D avatar from the earlier idea stay in scope? It is not in the approved proposal, so it is a Could.

## 13. Traceability to the Proposal

| Proposal slide | Promise | Requirements |
|---|---|---|
| Abstract | RAG on official sources | ANS-3, DATA-1 to 5 |
| Abstract | Text and voice messages plus live agent | VOI-1 to 6 |
| Abstract | Secure and deployable (RBAC, observability, cloud) | AUTH-3, ADM-2, ADM-3, OBS-1 to 3, OPS-1 to 3 |
| Problem | Scattered information | DATA-1 to 5, ANS-2, ANS-3 |
| Problem | Long waiting times | CHAT-2, success metrics |
| Problem | Repetitive staff load | Deflection through the golden set, DATA-7 |
| Problem | Missed deadlines | DDL-1, DDL-2, ANS-7 |
| Target users | Freshers, students, staff portal | Section 2, ADM-1 |
| Target users | Adaptable to other universities | ADP-1, ADP-2 |
| Related work gap | University-specific, verified, chat plus voice | Principles 1 to 4 |
| Related work | Cannot verify identity | AUTH-4, AUTH-5, Risk table |
| Scope | WhatsApp-style chat, real-time, speech, secure backend, monitoring | CHAT, VOI, ADM, OBS |
| Methodology | Scrum with 2-week sprints | `Phases.md` sprint plan |
| Tech stack and architecture | Next.js, FastAPI, PostgreSQL with pgvector (Supabase), Redis (Upstash), WebSocket, Docker, GitHub Actions. AWS replaced by free hosting (Vercel, Render) because of zero budget | `Architectural.md` |
| Milestones | M1 to M7 over 17 weeks | `Phases.md` |
