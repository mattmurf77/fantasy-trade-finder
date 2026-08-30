# Reconciliation log — G-410 (#410 · #411 · #412 · #409-copy)

> What the operator ruled, what the Author decided in their absence, and every
> place [prd.md](prd.md) departs from [plan.md](plan.md). Written so a build
> agent never has to guess whether a difference was a decision or a slip.
>
> **Date:** 2026-08-30 · **Author agent** on `claude/fb-410-412-trade-card-polish`
> (`11c8903c`) · Input: the Planner's `plan.md`.

## Table of contents

- [1. Operator rulings, verbatim](#1-operator-rulings-verbatim)
- [2. Resolutions to the Planner's four open questions](#2-resolutions-to-the-planners-four-open-questions)
- [3. Deviations from the plan](#3-deviations-from-the-plan)
- [4. Things the plan claimed that did not survive verification](#4-things-the-plan-claimed-that-did-not-survive-verification)
- [5. Open seams handed forward](#5-open-seams-handed-forward)

---

## 1. Operator rulings, verbatim

### R-#410 — the control is a bare ✕

> *"It does mean pass / Keep the x button."*

**Context in which it was given, which matters for the record:** the operator was
shown (a) [D-157](../../../../living-memory/DECISIONS.md), including that a
tester (Segrave, build 128) read the bare ✕ **in this exact cell** as the deck's
pass control and cleared his canvas mid-tour, and (b)
[`canvas-results-spec.md` §4](../402-more-offers-shop/canvas-results-spec.md)'s
contract line *"placement: with the pager, never inside the action row's 50/30/20
cells"*. They chose the ✕ knowingly, and gave the reasoning themselves: the cell
**now genuinely means pass**, which is precisely what Segrave's misread was
about.

**Consequences built to it:** PRD R-1 (the fork), R-2 (bare ✕ during a browse
session, Clear otherwise), R-3 (50/30/20 byte-identical), R-5 (optional host
prop, never a flag read inside the component), R-9 + PRD §13 (the D-169 entry and
the spec amendment, with the operator's reasoning recorded), R-10 (the n19
re-check).

**Not re-opened.** The Planner's §2.3 recommended a *word* ("Pass"/"Decline") on
D-157's authority, and its Q-1 put the choice to the operator. The operator
answered. The PRD builds the ✕ and does not restate the word option as a live
alternative — it appears in D-169's "Alternatives considered" as *rejected by the
operator, knowingly*, which is where a superseded recommendation belongs.

### R-#411 — tag move **and** shrink the name

The operator chose **tag move + reduce the compact name's type size**, over the
two-line option, **after being told the tag move alone leaves star names
truncated**.

Constraints attached to the ruling, all treated as absolute in the PRD:

- the Chalkline **11pt floor** is absolute (`docs/design/design-system.md:107`);
- the position chip stays the specced Badges-&-chips construction and its colors
  remain a `docs/cross-client-invariants.md` data encoding — it is **moved**,
  never restyled or dropped;
- **`numberOfLines` stays 1** — wrapping was explicitly not chosen and is not
  added anywhere.

**Consequences built to it:** PRD R-11 (chip to the meta line), R-12 (13pt),
R-13 (the meta-line shrink policy the move made necessary), R-14 (clamp stays 1,
stacked page byte-identical), §3.3 (the size decision with measured fit rates),
§6.1 (the honest truncation table).

### R-#412 — proceed as planned

Presentational slot on `TradeSide` under the give column's "Add player"; the
pager copy is removed; handler, gate and `shop_opened` unchanged. No operator
ruling conflicts — the current pager placement was a QA agent's design
compensation built under the standing ship order (code comment,
`mobile/src/screens/TradesScreen.tsx:7336-7346`), **not** a decision. Verified:
searching `docs/` for `B-C4` returns only a verification step in
`docs/feedback/items/402-more-offers-shop/testflight-checklist.md`. No decision
entry is owed for #412.

### Orchestrator decision — #409's refusal copy is in scope

`mobile/src/utils/queueCalcTrade.ts:43-44` renders the `not_league_member`
refusal as `` `@${name} isn't in this league.` ``. That one server reason covers
**three** causes and **two are caller-side**
(`backend/server.py:13139-13143`) — which is why the operator reported "a user
isn't in this league" when the server was complaining about the caller. A
**minimal, neutral, client-only** copy change is in scope. **Splitting
`CalcQueueReason` or changing any server contract is explicitly out of scope**
(PRD §11).

**Consequence built to it:** PRD R-17, one string plus the file-header comment
carve-out that keeps a future editor from "fixing" the partner's name back in.

---

## 2. Resolutions to the Planner's four open questions

The operator is away and delegated these to the Author. Each is decided here,
with reasoning, and is binding on the build.

### Q-1 (#410, copy) — **settled by the operator's ruling: a bare ✕.**

Not an Author decision. Recorded in §1 and in D-169. The Planner's
recommendation (a word) is preserved in D-169's alternatives as the thing the
operator overrode, so a future reversal has the original argument to hand.

### Q-2 (#412, scope) — **RESOLVED: browse-only. Keep today's gate.**

`shopEnabled && browseLive && sortedDeck.length > 0 && rawTopCard.give_players.length > 0`.

Reasoning, in order of weight:

1. **The report is a placement complaint, not a scope request.** *"Reversion from
   prior version.. move more offers underneath the add a player button."* Shipping
   a new capability under a move is how a "restore what I had" item turns into a
   surface nobody specced.
2. **"Always" is not a gate change, it is a new code path.** `openShopForCard`
   takes a **`TradeCard`** (`TradesScreen.tsx:3240`) and forks on
   `card.give_players`. A hand-built canvas has no card. Serving the always-case
   needs either a synthetic card or a second entry function — and then
   `shop_opened`, whose taxonomy comment pins it as naming *the tap on Trades*,
   starts firing for a context it was never classified against. That is a
   taxonomy question, and the scope block's "no new analytics" claim would stop
   being true.
3. **It would break a green guard for no user-visible gain in the reported
   flow.** `check-canvas-results.js:601` (`12i5`) asserts exactly three
   `openShopForCard(` occurrences — one definition, the deck chip, the browse
   entry. A fourth path needs that re-specced without a report asking for it.
4. **Reversibility.** Browse-only is what exists today; if the operator later
   wants the hand-built case, it is additive and can be specced on its own.

Recorded as PRD R-16 and PRD §11.

### Q-3 (#412, semantics) — **RESOLVED: shop the engine's original (`rawTopCard`), unchanged.**

Reasoning:

1. **Consistency with the sibling signal.** `handleBrowsePass` deliberately
   passes on `sortedDeck[deckIdx]` — the **original** idea, never the user's
   edited variant — and says so at `TradesScreen.tsx:5744-5749`: the pass signal
   is about the engine's suggestion. Shop is the same kind of question ("keep this
   asset the engine chose, find me other offers around it"). Two adjacent controls
   on the same idea disagreeing about which trade they refer to would be worse
   than either choice alone.
2. **It keeps the change a move.** `rawTopCard` is today's argument. Changing it
   turns #412 from "the control is in the wrong place" into a behavior change,
   which invalidates the scope block's `shop_opened`-unchanged claim and the
   "handler unchanged" guardrail.
3. **The edit map is not a trade.** `browseSession.edits[id]` is a canvas prefill
   snapshot; it feeds the seeding effect and the ✓ queue (canvas-results §3). It
   is not a card and has no `give_players` shape to fork on.

**Accepted cost, stated rather than hidden** (PRD §6.4): under the give column
the control *looks* like it shops the column. If the user swaps the engine's give
asset for their own, the entry's accessibility label still names the original and
the shop window still searches for it. Mitigations required by the PRD: a code
comment at the slot's construction site mirroring `handleBrowsePass`'s
original-vs-edited note, and the limit recorded in §6.4 so a future report about
it lands on a known seam rather than a surprise.

### Q-4 (#411, depth) — **settled by the operator's ruling: no wrapping.**

The Planner's R-7 (`numberOfLines={2}`) is **not built**. The operator chose
tag-move-plus-shrink after being told the tag move alone was insufficient, which
is a direct answer to Q-4. PRD R-14 pins `numberOfLines={1}` and PRD §11 lists
wrapping as out of scope.

**The honest consequence is recorded rather than glossed** (PRD §6.1): 13pt
single-line fixes 2 of the operator's 5 pressure-test names and leaves 3
ellipsized — fewer than half — and **"Christian McCaffrey" and "Amon-Ra St.
Brown" cannot fit on one line at any size at or above the 11pt floor** (100.1pt
and 99.5pt against 97.5pt available). Wrapping was the lever that would have
fixed them, and it was declined. That is the trade, written down.

---

## 3. Deviations from the plan

Ordered by how much a build agent needs to know about them.

| # | Plan said | PRD says | Why |
|---|---|---|---|
| **D-1** | §2.3 / R-2: the cell renders a **word** ("Pass"/"Decline"), not a bare glyph — D-157's principle | **Bare ✕**, `semantic.neg`, 16pt, with `accessibilityLabel="Pass on this trade idea"` carrying the verb | **Operator ruling.** The a11y label is the Author's addition — it is the part of D-157's principle that survives a glyph, costs nothing, and was not in the plan. |
| **D-2** | R-6/R-7: the compact name stays `type.title` 16/22 and gains `numberOfLines={2}`; *"type is not shrunk"* | The compact name **shrinks to 13pt** (`type.bodySm` metrics, Archivo 600, `chalk.base`) and stays `numberOfLines={1}` | **Operator ruling** (tag move + shrink, no wrapping). The plan's §3.3 was written before the ruling and is superseded, including its "type is not shrunk" line. |
| **D-3** | Nothing — the plan did not measure the meta line after the chip lands on it | **New requirement R-13**: `TierBadge size="sm"` in compact mode, `minWidth: 0` on the meta text, `flexShrink: 0` on the chip and badge | **The plan's own fix creates a collision it did not check.** Measured: a WR row with a `4+ 1sts` badge puts chip + gaps + badge at **101.6pt** against a 97.5pt line, and `Card` sets `overflow: 'hidden'` — the **tier badge**, i.e. the price, would be clipped. `size="sm"` brings the realistic worst case to 97.6 (0.1pt, sub-pixel). Full arithmetic in PRD §3.3/§6.2. |
| **D-4** | §3.2's width table is *"estimated"* at ~8.4pt average advance | Every width is **measured** from the shipped `Archivo_600SemiBold.ttf` in `mobile/node_modules/@expo-google-fonts/archivo/`, via fontTools `hmtx`; fit rates computed over the 340-player `backend/tests/fixtures/player_pool_2026.json` corpus ranked by `dp_value_1qb` | The operator asked for a pressure test. An estimate cannot answer it. The plan's estimates were close but wrong in a load-bearing direction: it called "Nico Collins" borderline at 16pt when it measures 88.5pt and **fits**, and it did not surface that the fix takes the top-100 from **1/100** to **83/100**. |
| **D-5** | R-4: the pager ✕ is removed | Same, **plus R-7**: `browseDecline` is passed as `null` whenever `declineReasonProps` is falsy | The plan missed that the pager ✕ is gated on `declineReasonProps` (`TradesScreen.tsx:7390`, the `feedback.decline_reasons` kill switch) and that `handleBrowsePass` early-returns at `:5752`. Without R-7 the new cell renders a dead ✕ under the kill switch. |
| **D-6** | §8.1: `check-shop-deck.js` — *"confirm the deck's chip is untouched"*; `check-calc-merged-behavior.js` — *"re-spec"* | `check-shop-deck.js` is **untouched and its passing run is the evidence**; `check-calc-merged-behavior.js` gets **additions, not a re-spec** | Verified: `check-shop-deck.js` carries no `canvas-results` assertion (its two mentions are comments) and `check-calc-merged-behavior.js` contains nothing about the middle cell (`calc.action.confirm` at `:387` is the only action-row reference). |
| **D-7** | §8.1: `check-calc-merged-layout.js` rules **16 / 16b / 17** must be re-keyed | Only **17** is re-specced; **16 and 16b stay green, unedited**, and 16 is *extended* | Verified against `:261-275`. Rule 16 asserts one bare `numberOfLines={1}` preceded by `styles.compactName` — both facts survive R-12/R-14. 16b counts the two `numberOfLines={compact ? 1 : undefined}` clamps (team name + meta text), neither touched. Editing green assertions is how a guard quietly loses its charter. |
| **D-8** | §8.1: `check-canvas-results.js:269` (`4l`) *"will fail until re-specced"* | The **assertion stays green**; its **message** is re-specced and a sibling is added | Verified: `4l` is `!/canvas-results/.test(calcCode)` at `:270-271`. Under R-5 the prop is `browseDecline`, so the regex never matches. What became false is the sentence the assertion advertises (*"the pass control lives with the pager"*). |
| **D-9** | Risk 10 / §5.2: n19's copy *"must be re-checked and updated if it misdescribes the UI"* | **Checked; no change owed.** Finding recorded in PRD R-10 and in D-169's consequences | `mobile/src/components/analystScript.ts:549-558` reads *"Clear became this cross. It records why you passed; the check still accepts."* — which after R-1 describes the UI **more literally** than before. Its `target: 'trades.pass-btn'` is registered only by `TradeCard` (`TradeCard.tsx:274`, `:792`), which canvas-results retires on this host, so the spotlight was **already dark on this path before #410**. Re-targeting is Wave-B tour work and is deliberately not done here. |
| **D-10** | Risk 5: a wrapped name adds 22pt per row and could push the action row out of frame | **The row gets 4pt shorter, not taller** | With no wrapping and a 13pt name, line 1 goes 22 → 18 while the meta line stays 20pt (set by the tier badge, whose height is unchanged by the chip's arrival: chip 18pt, badge 20pt). The #384 one-frame constraint is relieved, not stressed. Risk 5 is closed. |
| **D-11** | §6: the `testID` list is not stated for #412 | `trades.canvas-results.more-offers` → **`calc.give.more-offers`** | The id should not claim a pager home it no longer has, and `testid-lint` needs the rename registered either way. |
| **D-12** | §2.2 documents the edit-map corruption in prose | It is **numbered requirement R-6** with its own assertions (T-1, T-2) and its own sabotage (**S-1 "helpful cleanup"** — the decline handler also calling `clear()`), plus checklist step 8 | The orchestrator's instruction, and correct: it is a data-loss defect, not a rationale. S-1 is the specific way a well-meaning builder would reinstate it while every other assertion passes. |
| **D-13** | Not in the plan at all | **R-17**, the #409 refusal copy | Orchestrator decision, folded into this group because it ships in the same build as the FB-409 server fix already on this branch. |

**No deviation is a silent one.** Everywhere the PRD departs from the plan, the
plan's position is preserved either in a "Known limits" entry, in D-169's
alternatives, or in this table.

---

## 4. Things the plan claimed that did not survive verification

Separate from deviations: these are **factual corrections**, listed so the build
agent does not act on them. All were re-checked against the working tree at
`11c8903c` on 2026-08-30.

1. **`check-calc-merged-layout.js` rules 16 and 16b do not break.** (§3 D-7.)
2. **`check-canvas-results.js` `4l` does not fail.** (§3 D-8.)
3. **`check-canvas-results.js` `12i5` does not break.** `count(/openShopForCard\(/g) === 3` still holds after R-15: the call stays in `TradesScreen`, inside the slot it hands down.
4. **`check-shop-deck.js` needs no re-spec.** (§3 D-6.)
5. **`check-calc-merged-behavior.js` has nothing to re-spec.** (§3 D-6.)
6. **The plan's per-name width estimates are off by up to ~14pt** and one verdict flips: "Nico Collins" measures **88.5pt** at 16pt and **fits** in 97.5, where the plan called it borderline. Its aggregate conclusion — *"the move alone does not deliver the ask"* — is nonetheless **correct and confirmed**: at 16pt with the chip moved, only 32 of the top 100 dynasty assets fit.
7. **The plan's "~106pt" figure for the middle cell** (quoted from D-157's own note) is a 30% share of 375pt before the row's `space.xs` gaps and the page gutter; the true cell is narrower. It does not matter for the ✕ and is noted only so nobody re-derives a word's fit from it.

---

## 5. Open seams handed forward

Not blockers. Recorded so they land on a known seam if they resurface.

- **S-1 — the n19 spotlight.** `trades.pass-btn` is unreachable on the
  canvas-results host. If the tour is ever unsuppressed there, `n19.target`
  becomes `calc.action.decline`. (PRD R-10, D-169 consequences.)
- **S-2 — the two longest names.** "Christian McCaffrey" and "Amon-Ra St. Brown"
  cannot fit one line at any legal size in 97.5pt. If the operator later wants
  them, the levers are wrapping (declined here) or widening the info column by
  moving the 32pt remove control to the meta line (buys 36pt; still fails both).
  (PRD §6.1.)
- **S-3 — the residual meta-line overhang.** A PICK row at `2 1sts` or better
  would overflow by 1.7–9.6pt. Judged implausible (a single pick does not price
  at two firsts), and the TestFlight checklist step 11 is the falsification test.
  (PRD §6.2.)
- **S-4 — one cell, two meanings.** If a tester misreads the ✕ the way Segrave
  misread it, **D-169 is what gets revisited, not D-157.** The decision entry
  records the operator's reasoning precisely so a reversal has something to
  reverse. (PRD §6.5.)
- **S-5 — `not_league_member` still conflates three causes.** The client cannot
  honestly name a side. Splitting the enum is a cross-client contract change and
  was ruled out of scope; if the ambiguity keeps producing reports, that split is
  the fix and it needs its own scope block. (PRD §11.)
