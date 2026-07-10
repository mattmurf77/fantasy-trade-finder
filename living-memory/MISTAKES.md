# Mistakes — Fantasy Trade Finder

> **Purpose:** approaches tried and rejected. *What I tried → why it failed → what would have to change to reconsider.* Stops the loop where session 3 retries what session 1 already proved doesn't work.
>
> **Read at:** before proposing a new approach to a problem. **Write at:** when you abandon a path.
>
> Companion files: [`GOTCHAS.md`](GOTCHAS.md) for bugs *in the code*; this file is for *approaches that walked us down dead ends*.

---

## Table of Contents
- [2026-05-21 — Initial Capture](#2026-05-21--initial-capture)
- [Mistake Template](#mistake-template)
- [Cross-cutting Lessons](#cross-cutting-lessons)

---

## 2026-05-21 — Initial Capture

The living-memory layer was just adopted; the project has shipped substantial features but most "what was tried and abandoned" history lives in commit messages and `../docs/`. Initial entries below capture explicit mistakes acknowledged in [`../context.md`](../context.md) and the implicit lessons embedded in [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md).

### M-001 — Two-player-only Elo (rejected before shipping)
**Tried:** Initial design used straight 2-player pairwise comparisons.
**Failed because:** information gain per swipe was sub-optimal. The same UI swipe could instead carry the full ordering of 3 players, equivalent to 3 pairwise decisions.
**Why it was wrong:** under-using available cognitive bandwidth. Users were perfectly capable of ranking 3 players in one action.
**What would change to reconsider:** evidence that users find 3-player matchups cognitively overwhelming. To date: no.
**Cost of the mistake:** caught before shipping; 1-day pivot.
**Cross-reference:** [`DECISIONS.md`](DECISIONS.md) §D-002, D-003.

### M-002 — Persistent log files (rejected)
**Tried:** Initial design considered persistent log files (rotated).
**Failed because:** at personal-use scale, the operational overhead (rotation, disk space, log search) exceeded the value. Real-time forensics are better served by an in-memory ring buffer.
**Why it was wrong:** premature optimization for production-scale observability.
**What would change to reconsider:** production deployment with multiple users. Post-crash forensics will need persistence.
**Cost of the mistake:** minimal — early design pivot.
**Cross-reference:** [`DECISIONS.md`](DECISIONS.md) §D-008.

### M-003 — Storing the SQLite DB at both root AND `data/`
**Tried:** Originally the DB sat at the repo root (`./trade_finder.db`). When `data/` was introduced as the canonical location, the root file wasn't cleaned up.
**Failed because:** legacy. Two paths means two potential sources of truth; risk of editing the wrong one.
**Why it was wrong:** "we'll clean it up later" hygiene debt.
**What would change to reconsider:** *N/A* — the cleanup just needs to happen. See [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-001.
**Cost of the mistake:** ongoing low-grade risk until cleaned up.
**Cross-reference:** [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-001.

### M-004 — Assuming DynastyProcess player names match Sleeper exactly
**Tried:** Initial Elo seeding relied on player-name string equality between DynastyProcess CSV and Sleeper.
**Failed because:** non-trivial number of mismatches (apostrophes, abbreviated initials, edge cases). Players with mismatched names silently got default Elo seeds instead of consensus-value-derived seeds.
**Why it was wrong:** trusting two independent data sources to converge on naming.
**What would change to reconsider:** *N/A* — `dump_mismatches.py` was built to find them; fuzzy matching (Q-004) is the path forward.
**Cost of the mistake:** mid — affected initial-seed quality for affected players.
**Cross-reference:** [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-004.

---

## Mistake Template

```markdown
### M-NNN — <Short title>
**Tried:** <what was attempted>
**Failed because:** <root cause, not just symptom>
**Why it was wrong:** <the principle that should have prevented it>
**What would change to reconsider:** <under what circumstances this approach might be revisited>
**Cost of the mistake:** <time / shipped-then-reverted / data invalidation>
**Cross-reference:** <docs links>
```

Number sequentially. Never delete an entry; even superseded mistakes carry information.

---

## Cross-cutting Lessons

- **Trust naming agreement between independent data sources at your peril.** When seeding from a third-party CSV, expect string-matching to fail at non-trivial rate.
- **Information gain per interaction matters more than UI simplicity.** 3-player matchups beat 2-player; the cognitive cost was less than feared.
- **Operational ergonomics beats observability features at personal-use scale.** Persistent log files would have been over-engineering; ring buffer is enough.
- **Legacy artifacts at the repo root accumulate.** Schedule periodic cleanup (or use the `project-reorganizer.skill`).
