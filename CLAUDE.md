# Campus Pulse AI

Read `docs/Memory.md` first, then `docs/Phases.md` to find the current milestone.
Follow the Non-Negotiable Rules and Locked Decisions. Ask before changing a Locked Decision.

Other docs: `docs/PRD.md` (what), `docs/Architectural.md` (how), `docs/DESIGN.md` (look and feel).

## Common commands (run from the repo root, Git Bash on Windows)

| Command | What it does |
|---|---|
| `make install` | Install API (uv) and web (pnpm) dependencies |
| `make api-dev` / `make web-dev` | Run the API on :8000 / the web app on :3000 |
| `make up` / `make down` / `make logs` | Docker Compose (api, web, optional `PROFILES=local-redis`) |
| `make lint` / `make fmt` / `make typecheck` | ruff + eslint / auto-fix / mypy + tsc |
| `make test` | pytest (DB tests skip without `DATABASE_URL`) + vitest |
| `make build-web` / `make docker-api` | Next.js production build / API image |
| `make eval` | Golden-set evaluation (`eval/run.py`) |
| `make migrate` / `make seed` | Stubs until M2 |

## Definition of done (any task)

1. Works locally (`docker compose up` against the dev Supabase project).
2. Tests added or updated and passing.
3. Lint and type checks pass.
4. README or docs updated if behavior changed.
5. Memory.md status and session log updated.

Never read or create real `.env` files. Never ask for secrets in chat. Tests use FakeLLM and fake data.
