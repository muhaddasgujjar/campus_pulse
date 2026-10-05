# Campus Pulse AI

A WhatsApp-style chat, with voice messages and a live voice mode, that answers Lahore Garrison University (LGU) student questions about admissions, fees, timetables, faculty, policies, scholarships and deadlines. Answers come only from **staff-approved, dated** university data: structured tables queried with SQL tools, plus a certified knowledge base searched with RAG on PostgreSQL + pgvector. Every answer shows its source and "verified on <date>". If the bot does not know, it says so and gives the right office contact.

Final year project, LGU Department of Computer Science. Docs: [`docs/`](docs/) (start with [`docs/Memory.md`](docs/Memory.md)).

> **Status:** milestone M1 (scaffold). The chat, agent, voice and admin features are built in M2 to M5. See [`docs/Phases.md`](docs/Phases.md).

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
3. Run without Docker: `make api-dev` (http://localhost:8000/healthz) and `make web-dev` (http://localhost:3000).
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
| `make lint` / `fmt` / `typecheck` | ruff + eslint / auto-fix / mypy + tsc |
| `make test` | pytest + vitest |
| `make build-web` / `docker-api` | Next.js production build / API image with its size |
| `make migrate` / `seed` | Stubs until M2 (Alembic, seed import) |
| `make eval` | Golden-set metrics (placeholders until M2) |

## Environment variables

Templates: [`apps/api/.env.example`](apps/api/.env.example) and [`apps/web/.env.example`](apps/web/.env.example). Each variable has a comment saying where to get it.

> **Never** put `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `DATABASE_URL` or `DATABASE_URL_MIGRATIONS` in the web app, in a `NEXT_PUBLIC_*` variable, or in git. Only `.env.example` files are committed.

| Variable | App | Secret | Purpose |
|---|---|---|---|
| `APP_ENV` | api | no | `local`, `test`, `ci`, `dev`, `prod` |
| `LOG_LEVEL` | api | no | Log level |
| `CORS_ORIGINS` | api | no | Allowed web origins, comma-separated |
| `INSTITUTION_SLUG` | api | no | `lgu` |
| `INSTITUTION_DISCLAIMER` | api | no | Optional override of the chat disclaimer |
| `DATABASE_URL` | api | **yes** | Supabase transaction pooler URL (app) |
| `DATABASE_URL_MIGRATIONS` | api | **yes** | Supabase session pooler URL (Alembic) |
| `SUPABASE_URL` | api | no | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | api | **yes** | Admin API (create staff accounts, M5) |
| `SUPABASE_JWT_SECRET` | api | **yes** | Verify Supabase tokens (M5) |
| `REDIS_URL` | api | **yes** | Upstash Redis TLS URL |
| `GEMINI_API_KEY` | api | **yes** | Google AI Studio key |
| `LLM_PROVIDERS` | api | no | Fallback chain, e.g. `gemini,template` |
| `LLM_MODEL_FAST` / `LLM_MODEL_MAIN` | api | no | Gemini model IDs from AI Studio (no defaults in code) |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | api | no | `gemini-embedding-001` / `768` (D17) |
| `MAX_LLM_CALLS_PER_TURN` | api | no | LLM budget, at most 2 (COST-2) |
| `INTERNAL_JOBS_SECRET` | api | **yes** | Header secret for `/internal/jobs/daily` |
| `CHAT_RETENTION_DAYS` | api | no | Message retention, default 60 |
| `NEXT_PUBLIC_API_URL` | web | no | API base URL |
| `NEXT_PUBLIC_WS_URL` | web | no | WebSocket base URL (M3) |
| `NEXT_PUBLIC_SUPABASE_URL` | web | no | Supabase project URL (Auth only) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | web | no | Public anon key (safe because RLS denies everything) |

## API endpoints (M1)

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Liveness, instant, no DB or Redis (Render health check, wake ping) |
| `GET /readyz` | Checks DB and Redis when configured, otherwise `not_configured` |
| `GET /metrics` | Basic Prometheus-format counters |
| `GET /api/config` | Institution slug and disclaimer |

## Deployment (later)

Deployment to Vercel, Render and Supabase production is milestone **M6**. See `docs/Phases.md` (M6) and `docs/Architectural.md` Section 13. Until then, the `migrate` and `jobs` workflows only run on manual trigger and skip when their secrets are not set.
