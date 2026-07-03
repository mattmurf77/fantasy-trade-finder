# Practices — Fantasy Trade Finder

> **Purpose:** the 60-second cheat sheet. The actually-applied conventions of this project, distilled. Not comprehensive — for that, see [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md) and [`../docs/`](../docs/) generally. This is the *prioritized* digest you read before making a change.
>
> **Read at:** session start for fast orientation; before reviewing any code change.
> **Write at:** when a practice solidifies across multiple uses or when a long-standing rule is overturned.
>
> Companion files: [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md), [`BRAND.md`](BRAND.md), [`../docs/CLAUDE.md`](../docs/CLAUDE.md) (the update-trigger table).

---

## Table of Contents
- [2026-05-21 — Curated Top Practices](#2026-05-21--curated-top-practices)
- [The 60-Second Pre-Session Checklist](#the-60-second-pre-session-checklist)
- [The 60-Second Post-Session Checklist](#the-60-second-post-session-checklist)
- [What's NOT here](#whats-not-here)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## 2026-05-21 — Curated Top Practices

### Tier 1 — Apply every code change

1. **Karpathy four principles.** Think before coding; simplicity first; surgical changes; goal-driven execution. (Per [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md).)
2. **No magic numbers in service code.** Tunables go in `config/features.json` or the `model_config` table. New keys documented in [`../docs/config-reference.md`](../docs/config-reference.md).
3. **Update `../docs/` per the trigger table.** Every code change that touches a listed area updates the corresponding doc. The table lives at [`../docs/CLAUDE.md`](../docs/CLAUDE.md).
4. **DB calls via SQLAlchemy Core.** Not the ORM. Stays close to SQL.
5. **Always use the canonical DB path** (`data/trade_finder.db`). The root duplicate is legacy — Q-001 cleanup pending.

### Tier 2 — Apply for cross-client work

6. **Cross-client invariants are sacred.** Tier colors, K-factors, enum strings — anything used by ≥2 clients goes in [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md). Update there + every client.
7. **Feature flags via `config/features.json` only.** Don't hardcode per-client flags.
8. **`POST /api/admin/config/<key>`** is the runtime tuning surface. Use it for live experimentation; persist tuned values to `config/features.json` or the `model_config` table.

### Tier 3 — Apply for new features

9. **New API route?** Add to `backend/server.py`, update [`../docs/api-reference.md`](../docs/api-reference.md), test via curl, add to the relevant client(s).
10. **New DB table or column?** Add to `backend/database.py`, update [`../docs/data-dictionary.md`](../docs/data-dictionary.md), add to seed/migration logic.
11. **New domain term?** Add to [`../docs/glossary.md`](../docs/glossary.md) (or [`GLOSSARY.md`](GLOSSARY.md) if still unstable).
12. **New non-obvious architectural choice?** Write an ADR in [`../docs/adr/`](../docs/adr/) AND add a terser entry to [`DECISIONS.md`](DECISIONS.md).

### Tier 4 — Living-memory discipline (new in 2026-05-21)

13. **`CHANGELOG.md`** gets at least one bullet per meaningful work session.
14. **`HANDOFF.md`** gets overwritten at session end with current state — don't accumulate.
15. **`NEXT.md`** stays at 3–7 items max.
16. **Run `living-memory-format-check` skill** after substantial writes to ensure compliance with [`FORMAT.md`](FORMAT.md).

---

## The 60-Second Pre-Session Checklist

- [ ] Read [`HANDOFF.md`](HANDOFF.md) — what was the last session's state?
- [ ] Skim [`NEXT.md`](NEXT.md) — what's the current priority?
- [ ] Check [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) — any answers came in?
- [ ] Verify Python venv (if used) and that `requirements.txt` is current.
- [ ] If touching DB: confirm `data/trade_finder.db` is the canonical path; check the legacy root duplicate isn't being edited by accident (G-002).

## The 60-Second Post-Session Checklist

- [ ] Update [`HANDOFF.md`](HANDOFF.md) — overwrite with current state.
- [ ] Add to [`CHANGELOG.md`](CHANGELOG.md) — what was done today (1–3 bullets).
- [ ] If a test ran: add to [`TEST_LEDGER.md`](TEST_LEDGER.md).
- [ ] If something failed: add to [`MISTAKES.md`](MISTAKES.md) or [`GOTCHAS.md`](GOTCHAS.md).
- [ ] If a decision was made: add to [`DECISIONS.md`](DECISIONS.md) (and `../docs/adr/` if formal).
- [ ] If touched a `docs/` trigger area: update the corresponding `docs/` file per [`../docs/CLAUDE.md`](../docs/CLAUDE.md).

---

## What's NOT here
- Per-module algorithm details (see [`HLD.md`](HLD.md) and per-module source comments).
- DB schema (see [`../docs/data-dictionary.md`](../docs/data-dictionary.md)).
- API route detail (see [`../docs/api-reference.md`](../docs/api-reference.md)).
- Specific config keys (see [`../docs/config-reference.md`](../docs/config-reference.md)).

If a rule isn't in the top 16, it's still real; it's just not the first thing a new session needs to know.

---

## Outstanding / Known Gaps
- No formal scoring of practice adherence. Discipline is informal.
- `docs/coding-guidelines.md` is the long-form source; if it changes, re-sync this file.
- Living-memory adoption is new — Tier 4 practices haven't been load-tested across many sessions yet.
