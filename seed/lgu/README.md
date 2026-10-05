# Seed data: Lahore Garrison University (`lgu`)

Institution-specific data lives here, not in code (ADP-1, ADP-2, Memory D13).
In M1 these files are **templates only: headers, no data rows.** The import scripts arrive in M2 (`make seed`).

## Rules (Memory.md Section 3)

1. **Never invent LGU facts.** Add only facts from LGU offices, the public LGU website or approved documents.
2. Every row needs `last_verified` (the real date an office confirmed it) and `source_url` and/or `verified_by`.
3. Fees always carry `fiscal_year`. The fee page mixes years, so keep the year per row.
4. Dates are `YYYY-MM-DD`. Times are 24-hour `HH:MM`. Days in the timetable: 1 = Monday ... 7 = Sunday.
5. List values inside one CSV cell are separated with `|` (for example `phones`, `topics`, `courses`).
6. Contact emails are typed by hand (the LGU site obfuscates them). Re-verify everything before the demo.

## Files

| File | Table | Columns |
|---|---|---|
| `offices.csv` | `offices` | name, phones, email, hours, location, topics, last_verified, source_url, verified_by |
| `fees.csv` | `fees` | program_group, level, fiscal_year, admission_fee, tuition_per_credit_hour, misc_per_semester, credit_hours_sem1, notes, last_verified, source_url, verified_by |
| `key_dates.csv` | `key_dates` | title, date, kind, program_scope, last_verified, source_url, verified_by |
| `faculty.csv` | `faculty` | name, designation, department, email, office_room, courses, status, last_verified, source_url, verified_by |
| `timetable.csv` | `timetable` | program, semester, section, day, start_time, end_time, course_code, course_name, faculty_name, room, effective_from, effective_to |
| `kb_entries.json` | `kb_entries` | see `_template` in the file |

`kind` in `key_dates.csv`: `admission`, `fee`, `scholarship`, `exam`, `semester`, `holiday`, `other`.

Facts already collected from public pages are listed in `docs/Memory.md` Section 6 and `docs/PRD.md` Section 9. They are entered here in M2, after checking them again.
