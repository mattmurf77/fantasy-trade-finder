# Glossary — Fantasy Trade Finder

> **Purpose:** living-memory glossary supplementing the canonical [`../docs/glossary.md`](../docs/glossary.md). Captures new terms as they enter the codebase before they make it to the formal doc, plus project-internal jargon that doesn't merit the main glossary.
>
> **Read at:** when a term in code or docs is unfamiliar. **Write at:** when a new term is coined or first used.
>
> Companion file: [`../docs/glossary.md`](../docs/glossary.md) — the authoritative domain glossary.

---

## Table of Contents
- [Primary Glossary](#primary-glossary)
- [Living Glossary (supplementary)](#living-glossary-supplementary)
- [Conventions for Adding Terms](#conventions-for-adding-terms)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## Primary Glossary

For the authoritative project glossary, see [`../docs/glossary.md`](../docs/glossary.md). Every domain term used in code, comments, or UI should live there.

This file (`living-memory/GLOSSARY.md`) is for terms that:
- Are too new to have settled into `../docs/glossary.md` yet.
- Are project-internal jargon (e.g. nicknames, codenames, abbreviations used in CHANGELOG entries) that don't merit the user-facing glossary.
- Are operator/Claude shorthand from working sessions.

When a term in this file stabilizes (used in production code, in user-facing copy, or repeatedly across files), promote it to `../docs/glossary.md` and delete it here.

---

## Living Glossary (supplementary)

### Dynasty fantasy football terms

| Term | Meaning |
|---|---|
| **Dynasty** | Fantasy format where rosters carry over year to year (vs redraft, which resets annually). |
| **Startup draft** | The very first draft in a new dynasty league — all players available. |
| **Rookie draft** | Annual draft of incoming NFL rookies only. Picks themselves are tradeable assets. |
| **Pick** | A future rookie-draft selection. Tradeable. Format: `<year> <round> <slot?>` (e.g. "2027 1st", "2026 2.05"). |
| **Taxi squad** | Roster slots for developmental (often rookie) players — don't count toward starting lineup limits. |
| **IR (Injured Reserve)** | Roster slots for injured players — don't count toward starting lineup limits. |
| **3-for-1** | A trade where one side sends 3 assets for 1 (typical pattern: depth-for-stud). |
| **Buy low / sell high** | The trade-finding game's core: acquire under-valued assets, ship over-valued ones, both per the FIELD's consensus and per YOUR own valuations. |
| **Mutual gain** | A trade where both sides come out ahead by their own valuations (rare; the algorithm's goal). |
| **Consensus value** | A market-wide valuation (e.g. DynastyProcess CSV) — what the broader dynasty community thinks a player is worth. |
| **Tier** | A player ranking band (e.g. "Elite", "Solid Starter", "Bench", "Depth"). Tier-color invariants live in [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md). |

### Project-internal jargon

| Term | Meaning |
|---|---|
| **Matchup** | A 3-player ranking interaction surfaced by `smart_matchup_generator.py`. User ranks the 3 in order. |
| **Trio** | Synonym for matchup; used in `GET /api/trio`. |
| **Pairwise decision** | A 2-player comparison; what a 3-player ranking decomposes into (3 of them per trio). |
| **Tier-prioritized matchup engine** | Planned redesign of matchup selection: rank top tier first, then mid, then bench. Currently global-Elo-only. See [`NEXT.md`](NEXT.md). |
| **Mismatch (DynastyProcess ↔ Sleeper)** | A player whose name in the CSV doesn't match the Sleeper player name; flagged by `dump_mismatches.py`. |
| **Smart matchup** | Anthropic-powered matchup selection (vs algorithmic fallback). |
| **Trade card** | A generated trade proposal: pieces from side A ↔ pieces from side B. |
| **Liked trade** | A trade card the user has swiped "like" on. |
| **Matched trade** | A trade where both leaguemates liked the mirrored card; surfaces as a real proposal. |
| **Coverage** | Per-league stat: what fraction of league players the user has ranked. |
| **Real league** | A live Sleeper league with actual leaguemates (vs simulated leaguemates from CSV). |
| **Simulated leaguemate** | A synthetic opponent generated for trade discovery before real-league linking. |
| **Ring buffer logger** | In-memory log of the last 200 backend events, accessible via `GET /api/debug/log?n=100`. |
| **Test_League** | The sample league configuration in `Test_League_Trade_Matches.xlsx` used for manual verification. |
| **Tommy Tumble / Ricky Rumble** | Mascot concept candidates. Cartoon-style running back mid-fumble. See [`BRAND.md`](BRAND.md) and [`../context.md`](../context.md). |

### Skills / tools

| Term | Meaning |
|---|---|
| **feature-evaluator** | Custom in-repo skill (`feature-evaluator.skill`). Evaluates code across 7 dimensions. |
| **project-reorganizer** | Custom in-repo skill (`project-reorganizer.skill`). 6-phase reorganization workflow. Benchmarked +40pp vs ad-hoc. |
| **living-memory-format-check** | Custom skill (`.claude/skills/living-memory-format-check/`). Audits files in `living-memory/` against [`FORMAT.md`](FORMAT.md). |
| **ADR** | Architecture Decision Record. Lives in `../docs/adr/`. Format: `NNNN-kebab-title.md`. |

---

## Conventions for Adding Terms

- Group by category (dynasty / project-internal / skills-tools / etc.).
- Define in terms a smart-but-uninitiated reader could grok.
- For acronyms, expand once; subsequent uses can be the short form.
- Cross-reference to the file or test that introduced the term where useful.
- **When a term stabilizes, promote to [`../docs/glossary.md`](../docs/glossary.md)** and delete here. This file should stay <50 terms.

---

## Outstanding / Known Gaps

- No automated check that `living-memory/GLOSSARY.md` and `docs/glossary.md` stay in sync.
- "Tier" definitions specifically: should every tier name live here AND in `cross-client-invariants.md`? Convention TBD.
- Mascot naming (Tommy Tumble vs Ricky Rumble vs other) not finalized.
