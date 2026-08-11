# Operator decisions — polish lab 2026-08-11 (#297 · #298 · #299 · #302)

> Recorded 2026-08-11 from the `/feedback` session that produced this lab.
> **Decisions only — no code was written from this.** Build agents should treat
> this file plus each item's mockup page as the design contract, and the PRD
> (not yet written) as the implementation contract.
>
> Lab: [`README.md`](README.md) · viewer [`index.html`](index.html)

---

## Table of Contents

- [1. Decided](#1-decided)
- [2. Not decided — #297 is blocked](#2-not-decided--297-is-blocked)
- [3. Carried forward regardless of variant](#3-carried-forward-regardless-of-variant)

---

## 1. Decided

| Item | Decision | Page |
|---|---|---|
| **#298** | **V1** — make the single-pin featured window a deck card for the pinned asset, restoring the Find-a-Trade CTA and accept/decline on the existing `advance()` path. V2 (plain deck + compact calculator above) is rejected. | [`trades-single-pin-recovery.html`](trades-single-pin-recovery.html) |
| **#299** | **32pt** — tier badge moves into the right cluster, left of `posRank`, emptying line 2. 60pt → 32pt (−47%), 64pt → 36pt pitch. Literal 30pt is **rejected**: it buys 2pt and costs a fork of the shared `Badge` primitive with app-wide blast radius. | [`league-tile-density.html`](league-tile-density.html) |
| **#302** | **V2** — `headerLeft` "‹ All teams" + title swap on the already-fixed stack header. V1 (38pt sticky bar) is rejected. | [`drilldown-back-affordance.html`](drilldown-back-affordance.html) |

**Buttons are named "Pass / Like"** (operator, 2026-08-11, decided on the #169
thread but binding here too — it is the same control). This matches the shipped
`trades.pass-btn` / `trades.like-btn` testIDs, so #298 V1 restores the existing
vocabulary rather than introducing "Accept/Decline". Settle it in
[`docs/cross-client-invariants.md`](../../docs/cross-client-invariants.md).

---

## 2. Not decided — #297 is blocked

**#297 has no design decision yet, and must not be built from this lab.**

What is established:

- `LineupImpactTable` (`InLeagueCalculator.tsx:999`, unexported, one render
  site) has **never** been mounted on a deck or featured trade card. `git
  log -S` on the symbol returns only additive commits. Nothing was removed —
  so "regressed" cannot be satisfied by restoring anything.
- The MFL/ESPN silent-`null` path is real: `_sleeper_lineup_slots` returns
  `None` for non-numeric league ids (`server.py:19058`, docstring names
  "ESPN/MFL/Fleaflicker imports"), and the client then renders nothing, with no
  copy.

  > **CORRECTED 2026-08-11.** This section originally read *"but it is not the
  > operator's case — all four of their leagues carry numeric Sleeper ids."*
  > **That was wrong.** It was measured against `data/trade_finder.db`, the
  > **local dev database**, which does not know about the operator's linked
  > accounts. The operator subsequently confirmed: **they have both an MFL and
  > an ESPN league linked.** The MFL/ESPN path is therefore the most likely
  > explanation for #297, and the honest-copy fix was built on that basis.
  > Do not re-derive league platform from the local DB.
- `trades.player_offers_calc`, `trade.position_impact` and
  `trade.finder_targeting` are all **ON**, so on a Sleeper league in single-pin
  mode the table *should* render in the featured-window calculator.

**The gap is therefore a runtime question, not a code-reading one** — most
likely either (a) the operator was looking at a plain deck card, where the table
has never existed, or (b) the Sleeper league-meta fetch returned no
`roster_positions`, which degrades to the same silent `null`. **Next step: a
simulator repro on the operator's own league before any build.**

**Interaction with #298 V1 that the repro must account for:** V1 changes what
the single-pin surface *is* (featured window becomes a deck card). Whatever
#297's fix turns out to be, it lands on a surface #298 is concurrently
rewriting. Same file, same region — one owner, or serialize.

**Instrumentation gap worth closing separately:** the feedback payload records
`platform: ios` (the *device*) but not the active league or its platform. Had
it recorded the league, #297 would have been a five-second answer instead of a
database query. Candidate for the feedback FAB's captured context.

---

## 3. Carried forward regardless of variant

These came out of the lab's investigation, were not named in any report, and
survive whichever variant ships:

1. **#298's second, separate defect.** The strip's team pill →
   `pickSheetOpponent` (`TradesScreen.tsx:618`) → `scopedOpponent` change fires
   the effect at `:1918-1926`, which calls `resetDeckForNewTargets()` but only
   auto-regenerates when `finderMode === 'team'`. The strip keeps the user in
   `'guided'`, so **picking a team silently empties the deck and regenerates
   nothing.** One-line fix; folded into #298 unless the operator objects.
2. **#302 needs an Android `BackHandler`.** There are **zero** registered in
   `LeagueSummaryScreen.tsx`, and the drill-in is component state (`selectedId`)
   rather than a stack push — so Android currently has no back affordance here
   at all. Required by V2 as much as V1.
3. **#299 leaves the draft-capital rows behind.** `styles.pickRow`
   (`LeagueSummaryScreen.tsx:2232`) is not a `PlayerCard` and will not shrink
   with the tiles — it will read as tall beside them. Same pass, or an explicit
   deferral.
4. **#299 must be scoped via an opt-in prop.** The League tiles pass no
   `onPress` (so 44pt does not bind) while the Tiers board's rows *are*
   pressable, draggable, and pass a `statsSlot`. The dense branch must not
   change wholesale.
5. **Screen-library capture gaps.** No drill-in capture for `league-summary`,
   no single-pin capture for `trades` — exactly the states these four items
   live in, so every "current" frame for them is a token-exact reconstruction
   rather than a traced screenshot. Every `trades` capture also used the
   `release` fixture, i.e. the experiment's **control** variant.
