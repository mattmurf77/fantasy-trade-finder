# Context — Fantasy Trade Finder

> **Purpose:** the "always true" backdrop. Who this is for, what we're trying to do at the level of intent (not implementation), what the stakes are.
>
> **Read at:** session start, by any new agent. **Write at:** rarely; only on major scope or stakeholder shifts.
>
> Companion files: [`HLD.md`](HLD.md) for what the system *is*; [`../context.md`](../context.md) for detailed orientation.

---

## Table of Contents
- [What This Project Is For](#what-this-project-is-for)
- [Stakeholders](#stakeholders)
- [What "Success" Looks Like](#what-success-looks-like)
- [What "Failure" Looks Like](#what-failure-looks-like)
- [Boundaries](#boundaries)
- [Time Constraints](#time-constraints)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## What This Project Is For

A trade-finding tool for dynasty fantasy football managers. The fundamental insight: **valuation mismatches between leaguemates are the source of mutual-gain trades**. The app captures each user's personal valuations (via 3-player Elo ranking interactions), compares them across leaguemates, and surfaces trade cards where both sides come out ahead by their own measure.

Sleeper is the identity + data layer (no separate account creation). Initial Elo seeds come from DynastyProcess consensus values; user rankings drift from there as they swipe. Trade cards are mutual-gain only.

## Stakeholders

- **The operator** — single user; same person writing the code and using the app for actual dynasty trades.
- **No team, no clients, no investors** — personal-use scale.
- **Potential future:** open-source community of dynasty managers if the product proves itself.

This matters because:
- No PRD process — decisions live in [`DECISIONS.md`](DECISIONS.md) and [`../docs/adr/`](../docs/adr/).
- No external support obligation — features ship on the operator's cadence.
- No multi-tenant data model yet — current architecture assumes a single user (or co-located users via local Sleeper accounts).

## What "Success" Looks Like

- **Tactical:** find ≥1 trade per league per season where the user's leaguemate accepts and both sides come out ahead by post-hoc evaluation.
- **Mechanical:** ranking interactions are clean, fast, and high-information (3-player matchups working better than 2-player would, per Elo information theory).
- **Methodological:** changes to the algorithm (matchup selection, trade generation, package weighting) ship with documented before/after evidence.

## What "Failure" Looks Like

- Shipping a feature that breaks the Sleeper API integration without noticing.
- Trade cards that are obviously bad (one side losing significantly by their own valuations).
- Mobile client diverging from web client on shared invariants (tier colors, K-factors) — see [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md).
- Leaving the SQLite DB at two paths (root + `data/`) indefinitely — guarantees confusion.

## Boundaries

- **Personal use** until proven otherwise. Not building for paying users.
- **Dynasty only** — no redraft / season-long without dynasty assets.
- **Sleeper-only identity** — no plans to support Yahoo, ESPN, MFL leagues.
- **Trade discovery only** — no waiver pickup recommendations, no draft tool, no DFS lineups.
- **Backend in Python** — not migrating to Node/Go/Rust.

## Time Constraints

- **No hard external deadlines.** Dynasty trades happen year-round; no Wed-night-lock equivalent.
- **Football season cadence:**
  - **March–August (offseason):** rookie drafts, startup drafts, deep trade activity.
  - **September–January (regular season + playoffs):** in-season trades, waivers.
  - **Highest user motivation:** May (post-rookie-draft trade churn) and October–November (in-season trade deadlines).

---

## Outstanding / Known Gaps

- No formal logging of operator's actual trade outcomes. Plan: a `RESULTS.md` if a pattern is worth capturing.
- No multi-user data model yet — productization requires this.
- Mobile + web + extension can drift; cross-client invariants are documented but not automatically enforced.
