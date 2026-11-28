# Campus Pulse AI

A WhatsApp-style chat, with voice messages and a live voice mode, that answers Lahore Garrison University (LGU) student questions about admissions, fees, timetables, faculty, policies, scholarships and deadlines. Answers come only from **staff-approved, dated** university data: structured tables queried with SQL tools, plus a certified knowledge base searched with RAG on PostgreSQL + pgvector. Every answer shows its source and "verified on <date>". If the bot does not know, it says so and gives the right office contact.

Final year project, LGU Department of Computer Science. Docs: [`docs/`](docs/) (start with [`docs/Memory.md`](docs/Memory.md)).

> **Status:** milestone M4 (multimodal voice): voice messages with a live transcript (and a server fallback), spoken replies with a Listen button, and a hands-free live mode, all on browser speech. Built on the M3 real-time chat (WebSocket, sources, verified badges, feedback, reconnect) and the M2 data and RAG core. **M5 (admin portal) is code complete locally:** staff sign-in, role checks on every admin route, content editing with approvals, the audit log, the dashboard, student profiles with "Delete my data", and the deadlines card. Not yet run against the dev Supabase project. Real-device voice results: [`docs/Voice-Test.md`](docs/Voice-Test.md). See [`docs/Phases.md`](docs/Phases.md).

## Free stack (Rs 0 per month, no credit card)

| Part | Service | Free limit to design for |
|---|---|---|
| Web (Next.js, TypeScript, Tailwind) | Vercel Hobby | Personal, non-commercial use |
| API (FastAPI + LangGraph, Docker) | Render free web service | 512 MB RAM, sleeps after 15 min idle (about 1 min cold start), 750 h/month |
| Database, vectors, auth, file storage | Supabase Free (Postgres + pgvector, Auth, Storage) | 500 MB DB, 1 GB storage, 2 projects, pauses after 7 days idle, no backups |
| Sessions, rate limits, cache | Upstash Redis Free | 256 MB, 500,000 commands/month |
| LLM and embeddings | Google Gemini API free tier | Limits not published: read them in AI Studio |
| Voice | Browser Web Speech API + speechSynthesis | Free, depends on the device |
| CI/CD, scheduled jobs | GitHub Actions | Free for public repos, 2,000 min/month private |
| Uptime | UptimeRobot | Free plan |

Limits change. Re-check them in each dashboard and record them in `docs/Memory.md`.

## Repository layout

```
apps/web/      Next.js App Router (TypeScript, Tailwind v4, tokens in styles/tokens.css)
apps/api/      FastAPI service (app/, migrations/ Alembic, tests/)
seed/lgu/      Institution data templates (filled in M2, verified facts only)
eval/          Golden set (golden.jsonl) and runner (run.py)
infra/         Dockerfile (API), docker-compose.yml (local), render.yaml (M6)
.github/       CI, manual migrate and jobs workflows
docs/          PRD, architecture, design, memory, phases
```

## Local setup

Prerequisites (all free):
- **Python 3.11+** and **uv**: `pip install uv` or see https://docs.astral.sh/uv/
- **Node.js 24 LTS** (npm is included). Node 22.22+ also works; avoid odd-numbered releases (25.x)
- **GNU make**: on Windows run the commands from Git Bash and install make (for example `winget install ezwinports.make`), or run the commands inside each target by hand.
- **Docker Desktop** (only for `make up` and image builds)
- Optional: **pre-commit**: `uv tool install pre-commit && pre-commit install`

Steps:
1. `make install`
2. Copy the env templates. Fill them in only after you create the free accounts. Everything runs without them.
   - `cp apps/api/.env.example apps/api/.env`
   - `cp apps/web/.env.example apps/web/.env.local`
3. Try the chat with no cloud accounts: `make api-local` (API on :8000 with an embedded Postgres, migrated and seeded from `seed/lgu`, templates instead of an LLM) and, in a second terminal, `make web-dev`. Open http://localhost:3000/chat. Only one `next dev` can run per app folder.
   With a dev Supabase project in `apps/api/.env`, use `make api-dev` instead.
4. Or run with Docker: `make up` (add `PROFILES=local-redis` for a local Redis), `make logs`, `make down`.
5. Run the checks with `make lint typecheck test`.

Tests need no cloud services. Database tests run only when `DATABASE_URL` is set (CI uses a pgvector container). The LLM is always the FakeLLM in tests.

## Make targets

| Target | Description |
|---|---|
| `make help` | List targets |
| `make install` | `uv sync` (api) and `npm ci` (web) |
| `make up` / `down` / `logs` | Docker Compose: api, web, optional `redis` (profile `local-redis`) |
| `make api-dev` / `web-dev` | Dev servers with reload |
| `make api-local` | API with no cloud: embedded Postgres, migrated and seeded (dev only) |
| `make e2e` | Playwright chat smoke tests (desktop and phone); starts its own API on :8001 and web on :3001. Without a `uv` command on PATH: `UV="python -m uv" make e2e` |
| `make lint` / `fmt` / `typecheck` | ruff + eslint / auto-fix / mypy + tsc |
| `make test` | pytest + vitest |
| `make build-web` / `docker-api` | Next.js production build / API image with its size |
| `make migrate` | Alembic migrations on `DATABASE_URL_MIGRATIONS` (Supabase session pooler) |
| `make seed` | Load `seed/lgu` (idempotent). Uses `DATABASE_URL`, else a local embedded Postgres |
| `make eval` | Golden-set evaluation, offline (no LLM, fake embedder). `make eval EVAL_ARGS="--live"` uses the configured Gemini models and counts against the free quota |

## Admin portal (M5)

Open http://localhost:3000/admin. Staff edit content of their own office or department and submit it; an admin approves it, and the chat answers from it within seconds (approval re-embeds at once). Every change is in the audit log.

**Sign-in.**
- **Cloud (dev, prod):** Supabase Auth in the browser. Staff and admins use email and password; their accounts are created by an admin in **Users** (Supabase Admin API, email pre-confirmed, so no email is sent). Students use anonymous sign-in only when they open their profile. The API verifies the Supabase token (JWKS for the new signing keys, `SUPABASE_JWT_SECRET` for legacy HS256) and reads the role from `profiles`, never from the token.
- **The first admin:** `NEW_USER_PASSWORD=... uv run python -m app.cli user add you@lgu.edu.pk --name "Your Name" --role admin` (needs `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `DATABASE_URL`). Without `NEW_USER_PASSWORD` it asks for the password.
- **Laptop (`make api-local`):** with no `SUPABASE_URL`, `DEV_AUTH` is turned on with a throwaway secret and two accounts are created: `admin@local.test` (admin) and `staff@local.test` (staff, Admission Office). Any password works. `DEV_AUTH` is refused unless `APP_ENV` is `local` or `test`.

**Who can do what** (`docs/Architectural.md` Section 11, enforced by the API on every route): staff create and edit content of their office or department and see the approval queue; only admins approve or reject, manage users, and see the audit log, metrics and settings. Staff without a department cannot edit the timetable (its rows belong to departments). Faculty CSV imports are admin only.

## Command-line admin path

Run from `apps/api` with `uv run python -m app.cli <command>` (`--help` on each). Every write adds an `audit_log` row. The CLI needs direct database access, which only admins have.

| Command | What it does |
|---|---|
| `seed ../../seed/lgu` | Load the seed folder and index the KB entries |
| `kb list` / `kb add` / `kb submit` / `kb approve` / `kb reject` / `kb archive` | Knowledge entries with the approval workflow (approve re-embeds) |
| `import timetable FILE` / `import faculty FILE` | CSV import (dry run unless `--commit`) |
| `doc upload FILE.pdf` | Text PDF: extract the text into a pending document |
| `doc import-web SNAPSHOT.json` | Load a website snapshot as pending documents (unchanged pages skipped, changed pages back to pending) |
| `doc list [--status pending] [--category fees]` / `doc show ID` | Review documents and their text |
| `doc approve ID [ID ...] [--verified YYYY-MM-DD]` | Approve, then chunk and embed (only approved content is used for answers) |
| `reindex` | Re-chunk and re-embed all approved content |
| `user add EMAIL --name NAME --role staff\|admin [--office NAME] [--department NAME]` | Create a staff or admin account (Supabase account with email confirmed, plus the profile) |

### One-time website import (D1 note)

`uv run python -m app.devtools.web_import ../../seed/lgu` reads the student-facing pages of the hosts in `institution.json` (`live_fetch_allowlist`) from the WordPress sitemap, honours robots.txt, waits 1 s between requests and writes `seed/lgu/web/lgu_website_<date>.json`. Load it with `doc import-web`. Every page stays **pending** until a staff member checks it with the office and runs `doc approve`. Run it by hand only: there is no scheduled scraper.

## Evaluation

`eval/golden.jsonl` holds the questions (`question`, `expected_facts`, `expected_tool`, `should_fallback`). The runner ([`apps/api/app/evaluation.py`](apps/api/app/evaluation.py)) loads `seed/lgu` inside a transaction that is always rolled back, runs every question through the real agent and prints the PRD metrics and every failure. Options: `--today YYYY-MM-DD` (pin the date), `--json eval/results/<name>.json` (full report, gitignored), `--min-accuracy 0.8` (exit 1 below it).

## Environment variables

Templates: [`apps/api/.env.example`](apps/api/.env.example) and [`apps/web/.env.example`](apps/web/.env.example). Each variable has a comment saying where to get it.

> **Never** put `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `DATABASE_URL` or `DATABASE_URL_MIGRATIONS` in the web app, in a `NEXT_PUBLIC_*` variable, or in git. Only `.env.example` files are committed.

| Variable | App | Secret | Purpose |
|---|---|---|---|
| `APP_ENV` | api | no | `local`, `test`, `ci`, `dev`, `prod` |
| `LOG_LEVEL` | api | no | Log level |
| `CORS_ORIGINS` | api | no | Allowed web origins, comma-separated |
| `INSTITUTION_SLUG` | api | no | `lgu` |
| `INSTITUTION_DISCLAIMER` | api | no | Optional override of the chat disclaimer (empty = default) |
| `INSTITUTION_UTC_OFFSET_HOURS` | api | no | The institution's UTC offset for "today" in date answers (Pakistan: 5) |
| `DATABASE_URL` | api | **yes** | Supabase transaction pooler URL (app) |
| `DATABASE_URL_MIGRATIONS` | api | **yes** | Supabase session pooler URL (Alembic) |
| `SUPABASE_URL` | api | no | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | api | **yes** | Admin API (create and block staff accounts) |
| `SUPABASE_JWT_SECRET` | api | **yes** | Verify legacy HS256 Supabase tokens (leave empty on the new ES256 signing keys: JWKS is used) |
| `SUPABASE_JWT_AUDIENCE` | api | no | Expected `aud` claim, default `authenticated` |
| `DEV_AUTH` | api | no | Laptop only: local sign-in without Supabase (`make api-local` sets it). Refused outside `APP_ENV=local`/`test` |
| `REDIS_URL` | api | **yes** | Upstash Redis TLS URL |
| `GEMINI_API_KEY` | api | **yes** | Google AI Studio key |
| `LLM_PROVIDERS` | api | no | Fallback chain, e.g. `groq,gemini,template` |
| `LLM_MODEL_FAST` / `LLM_MODEL_MAIN` | api | no | Gemini model IDs from AI Studio (no defaults in code) |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | api | no | `gemini-embedding-001` / `768` (D17) |
| `MAX_LLM_CALLS_PER_TURN` | api | no | LLM budget, at most 2 (COST-2) |
| `LLM_TIMEOUT_SECONDS` | api | no | Abandon an LLM request after this many seconds |
| `GROQ_API_KEY` | api | **yes** | Groq key (free tier, LLM only) |
| `GROQ_MODEL_FAST` / `GROQ_MODEL_MAIN` / `GROQ_REASONING_EFFORT` | api | no | Groq model IDs and gpt-oss reasoning effort |
| `GEMINI_RPM_LIMIT` / `GEMINI_RPD_LIMIT` / `GROQ_RPM_LIMIT` / `GROQ_RPD_LIMIT` | api | no | Per-provider quota guard, copied from each dashboard (empty = none) |
| `QUOTA_MAX_WAIT_SECONDS` | api | no | Wait near the per-minute limit before the busy fallback |
| `RESPONSE_CACHE_TTL_SECONDS` | api | no | Response cache lifetime, 0 = off (Redis when `REDIS_URL` is set) |
| `CHAT_RATE_LIMIT_MESSAGES` / `CHAT_RATE_LIMIT_WINDOW_SECONDS` | api | no | Anonymous rate limit per IP, default 20 per 600 s (CHAT-7) |
| `SESSION_MEMORY_TURNS` / `SESSION_MEMORY_TTL_SECONDS` | api | no | Session memory, default last 6 turns for 24 h (CHAT-5) |
| `CHAT_MAX_MESSAGE_CHARS` | api | no | Longest accepted chat message, default 1000 |
| `STT_MODEL` | api | no | Gemini model ID with audio input for the voice fallback (needs `GEMINI_API_KEY`); empty = off, `fake` for local tests |
| `VOICE_MAX_MB` | api | no | Largest accepted recording for the fallback, default 10 |
| `RETRIEVAL_*` | api | no | Retrieval and grading thresholds, tuned with `make eval` |
| `INTERNAL_JOBS_SECRET` | api | **yes** | Header secret for `/internal/jobs/daily` |
| `CHAT_RETENTION_DAYS` | api | no | Message retention, default 60 |
| `NEXT_PUBLIC_API_URL` | web | no | API base URL |
| `NEXT_PUBLIC_WS_URL` | web | no | WebSocket base URL, e.g. `ws://localhost:8000` |
| `NEXT_PUBLIC_SUPABASE_URL` | web | no | Supabase project URL (Auth only) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | web | no | Public anon key (safe because RLS denies everything) |

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Liveness, instant, no DB or Redis (Render health check, wake ping) |
| `GET /readyz` | Checks DB and Redis when configured, otherwise `not_configured` |
| `GET /metrics` | Basic Prometheus-format counters |
| `GET /api/config` | Institution name, disclaimer and starter questions |
| `WS /ws/chat` | Chat: `user_message`, `resume`, `ping` in; `ack`, `status`, `sources`, `token`, `final`, `error`, `pong` out. Protocol: [`docs/Architectural.md`](docs/Architectural.md) Section 8 |
| `GET /api/conversations/{id}/messages` | Latest 100 messages of a conversation (reload, CHAT-9) |
| `POST /api/feedback` | Thumbs up or down on an answer, with an optional reason and comment (CHAT-4) |
| `GET /api/deadlines?program=` | Upcoming key dates for the deadlines card (CHAT-7) |
| `GET /api/me`, `PUT /api/me/profile`, `DELETE /api/me/data` | Signed-in user: role and permissions, student profile, "Delete my data" (chats and profile details) |
| `/api/admin/*` | Admin portal (Bearer token): `kb`, `documents` (+ `preview`), `approvals`, `review`, `unanswered`, `tables/{faculty,timetable,fees,offices,key-dates}`, `import/{timetable,faculty}`, `lookups`, `users`, `audit`, `metrics`, `settings` |
| `POST /api/auth/dev-login` | Laptop only (`DEV_AUTH`): sign in as a local account. 404 everywhere else |
| `POST /api/voice/transcribe?lang=en\|ur` | Voice fallback for browsers without speech recognition: raw audio body (webm, ogg, mp4, aac, mp3, wav), 10 MB at most, transcribed in memory and never stored (VOI-1) |

Students chat anonymously, rate-limited by IP, unless they have signed in through their profile; then the chat sends `auth` with their token and their conversations become readable only with that token. The WebSocket only accepts origins in `CORS_ORIGINS`. Without `REDIS_URL` the rate limit, session memory and response cache run in process.

## Deployment (later)

Deployment to Vercel, Render and Supabase production is milestone **M6**. See `docs/Phases.md` (M6) and `docs/Architectural.md` Section 13. Until then, the `migrate` and `jobs` workflows only run on manual trigger and skip when their secrets are not set.
