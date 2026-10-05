---
description: Execute a milestone (M1 to M7) from docs/Phases.md
argument-hint: <milestone, e.g. M2>
---

Read docs/Memory.md and docs/Phases.md and execute milestone $ARGUMENTS using its kickoff prompt.

- Follow the Non-Negotiable Rules and Locked Decisions in docs/Memory.md. Ask before changing a Locked Decision.
- Plan first: show a short plan (files, tools, risks, questions), then build.
- Work on a branch `feat/$ARGUMENTS-<short-name>`. Build in small commits with conventional messages that reference requirement IDs.
- Run lint, type checks and tests after each part, and fix failures.
- Do not add scope beyond the milestone tasks and the PRD MoSCoW table.
- Finish by updating docs/Memory.md (status checkboxes with dates, session log entry, pending decisions).
