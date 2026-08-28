# Reconciliation log — #403 "Shop a player"

> Every round of the Phase 1 dual-agent doc loop: operator rulings consumed,
> orchestrator arbitrations, Planner claims the Author revised, and the
> objections/resolutions of each review round. Per
> `.claude/skills/feedback/references/plan-phase.md`.

**Tree verified against:** `origin/main` @ `6e94ff71` (the Planner wrote against
`30070f36`; the tree moved during the round — every backend line number in
`plan.md` still holds, several mobile ones shifted and are re-cited below).

## Contents

- [Round 0 — operator rulings consumed](#round-0--operator-rulings-consumed)
- [Round 0 — orchestrator arbitration: the #402 vocabulary](#round-0--orchestrator-arbitration-the-402-vocabulary)
- [Round 0 — Planner claims the Author revised](#round-0--planner-claims-the-author-revised)
- [Round 0 — Author decisions on questions the operator did not rule](#round-0--author-decisions-on-questions-the-operator-did-not-rule)
- [Still open for the operator](#still-open-for-the-operator)
- [Round 1 — Planner critique](#round-1--planner-critique)

---

## Round 0 — operator rulings consumed

| Q | Operator ruling, as handed down | Where it lands | Author's handling |
|---|---|---|---|
| **Q-A** | "**like** = queue it as a real offer" — maps to `POST /api/trades/queue`, idempotent, visible to the counterparty, **not** `/api/trades/swipe`; **must not move the user's Elo board**. Wiring `onLikeTrade` (today absent, so the ✓ is disabled at `InLeagueCalculator.tsx:1157`) is in scope. | R-5, R-6 | **Accepted with one contradiction surfaced.** The route half is implementable as ruled and needs zero backend work. The "must not move Elo" half **contradicts the shipped route**: `/api/trades/queue` calls `service.record_trade_signal(decision="like")` at `backend/server.py:13196` and `save_trade_swipes(k_factor=trade_k_like·fit_mult)` at `:13213`. It moves the board exactly as a deck like does. See the revision table below — the Planner's Q-A row described queue as the *non*-Elo option, which is very likely what the operator ruled against. Resolution: **R-6** specs an additive `record_elo: false` body field (default absent ⇒ today's behavior byte-identical) and flags it as needing a confirming yes, because it is a bright-line API contract change. |
| **Q-B** | "**dismiss** = deck-pass behavior — Elo movement and the permanent dismiss-cooldown — **plus an undo**." | R-7, R-8 | **Accepted in full, and the undo is cheaper than the ruling assumed.** The orchestrator's framing ("no undo exists today"; "Elo is path-dependent so a later write cannot be inverted") is **wrong on both counts** — see the revision table. The shipped answer is a **deferred write**: hold the POST for `UNDO_HOLD_MS` (5000) and let Undo cancel it. Nothing is written, so nothing needs inverting, and the copy is honest without qualification. Three shipped precedents cited in the LLD. |
| **Q-D** | "**positions = same-value swaps only**" — applies to `lateral`, not `upgrade`/`downgrade`; the picker must **replace** the #198 same-position predicate for `lateral`, never filter over its results. | R-9, R-10 | **Accepted, and made unmissable.** `lld-delta.md` §3.2 shows why a naive replacement leaks: the shipped gate (`trade_service.py:5205`) is **one predicate covering both the lateral and the upgrade band** (`vc >= lo`). Replacing `_same_pos` in place would widen `upgrade` too, which Q-D forbids. The LLD specs a band-split with a boundary-by-boundary equivalence proof. |
| **Q-G** | "keep **'Shop a player'**", accepting the overload with Chasing/**Shopping**/Avoiding (`trade_away_positions`). Add a `docs/glossary.md` entry recording **both** senses. | R-14 | **Accepted verbatim.** Glossary row specced in `scope.md` §4 and `prd.md` R-14, naming both senses and pointing each at its own mechanism. |

## Round 0 — orchestrator arbitration: the #402 vocabulary

**Status: PROVISIONAL. The critique round is explicitly invited to overturn this
with a better argument.**

**The situation.** `plan.md` §5 correctly deferred the group-copy question
(Q-H) and the "which tier up/down UI?" question (Q-I) to #402. But
`docs/feedback/items/402-*/` **does not exist** in the tree (verified:
`ls -d docs/feedback/items/40*` returns only `403-shop-a-player`), and #402
has not been selected for build. Orchestrator ruling: **#403 is being specced
now, so #403 picks the vocabulary and #402 inherits it.** The dependency
direction in `plan.md` §5 is inverted for copy only.

**The two shipped vocabularies.**

| Vocabulary | Where it ships | Verified |
|---|---|---|
| "Tier up" / "Tier down" (+ "Consolidate") | `TRADE_INTENTS` in `mobile/src/components/TradeDnaSheet.tsx:210-212`; exported as `TRADE_INTENT_LABEL` at `:218-220` | yes |
| "Upgrade at {pos}" / "Lateral moves at {pos}" / "Downgrade ideas" | `groupTitle()` in `mobile/src/components/AssetIdeasPanel.tsx:41-43` | yes |

**Arbitration: "Tier up" / "Tier down" / "Same value".**

Justified from the operator's own words, not from taste:

1. **#403's report uses "tier up / tier down" twice** and never uses
   "upgrade" or "downgrade": *"trade options to **tier up, tier down**, explore
   position specific swaps of similar value"* and *"a similar response to the
   current **tier up/ tier down** UI"*.
2. **#402's report uses the same two words**: *"below the trade chip where
   **'tier up', 'tier down'** options are presented in line."* So the
   vocabulary #403 is being asked to match is the vocabulary #402 will
   independently reach for. The arbitration costs #402 nothing.
3. It is already a **shipped, exported constant** (`TRADE_INTENT_LABEL`),
   which means #402 can consume it instead of re-typing string literals — the
   mechanism that made "Win-now moves" / "Team-fit moves" diverge in a prior
   batch.

**The third group is the hard part, and it is a genuine Author decision, not
an operator quote.** The operator called it *"position specific swaps of
similar value"* / *"position swap"*. Rejected candidates:

| Candidate | Rejected because |
|---|---|
| "Lateral" (today's `AssetIdeasPanel` word) | Loses on point 1 — the operator never used it, and it is the vocabulary the arbitration is discarding. |
| "Same tier" | **A lie.** The band is `asset_ideas_lateral_band` = ±10% of *consensus value* (`trade_service.py:5083-5084`, `database.py:2473`), not a tier band. A lateral idea can and does cross a tier boundary. |
| "Swap" | Collides with a live, different mechanic: `SwapPlayerSheet`, the `swap` glyph, and the `trade-card.swap-suggest.<asset_id>` testID (replace one player inside a card). |
| **"Same value"** ✅ | Honest against the ±10% consensus band; the closest short form of the operator's "swaps of similar value"; no existing collision (`git grep -in "same value" -- mobile/src` finds only code comments, no UI string). |

**Attack surface for the critique round** — the strongest case against:
"Tier up / Tier down / Same value" is not internally parallel. "Tier up" and
"Tier down" name a *direction of tier movement*; "Same value" names *value*,
not tier. A reviewer who prefers strict parallelism should propose the whole
trio in one axis and argue it; if the trio moves, `prd.md` R-11 and
`docs/design/components.md` move with it.

## Round 0 — Planner claims the Author revised

| # | Planner / orchestrator claim | Verdict | Evidence |
|---|---|---|---|
| **V-1** | `plan.md` §2 Q-A(b): `/api/trades/queue` "records a like the counterparty will see… is idempotent", presented in contrast to (a) "which **moves the user's Elo board**". | **WRONG, and consequential.** Queue moves the Elo board too. | `backend/server.py:13196` (`service.record_trade_signal(... decision="like", fit_mult=fit_mult)`) and `:13213` (`save_trade_swipes(k_factor=_rs_c("trade_k_like") * fit_mult, …)`). `docs/api-reference.md:239` states the same in prose ("on a refusal records **nothing at all**: no `trade_decisions` row, no Elo"). The operator's Q-A ruling was made against this row. |
| **V-2** | Orchestrator brief: "**No undo exists today.**" | **WRONG.** Flag `ux.swipe_undo` is `true` in `config/features.json:147` and undo ships in three places. | `MatchesScreen.tsx:406-411` (design note), `:495-509` (match dismiss), `:530-552` (awaiting dismiss); `TradesScreen.tsx:2392-2440` (`undoPass`), `:4896-4903` (the deferred POST); `TradeCalculatorScreen.tsx:1067-1075` (cleared-undo). |
| **V-3** | Orchestrator brief: "Elo is path-dependent: each match updates ratings from the *current* ratings, so a later write cannot be inverted." | **Half right, and the half that is wrong is the load-bearing half.** The per-match update *is* path-dependent, but the board is **derived state recomputed by replaying an ordered log** — `RankingService._compute_elo` replays `self._trade_swipes` (`ranking_service.py:1528-1538`), which `replay_from_db` rebuilds from `swipe_decisions` at every `session_init` (`:1195-1219`). So "invert the delta" was never the only option. It is moot anyway: the recommended design writes nothing until the undo window closes. | see cites |
| **V-4** | `plan.md` §4.2 / R-1: the pager needs a `Gesture.Pan()`, and gesture collision with the deck's like/pass pan is a **High** risk needing spike **S-1**. | **Revised — the risk is designed out, not mitigated.** The pager is a `FlatList horizontal pagingEnabled`, a ScrollView. There is no `Gesture.Pan` anywhere in #403's tree, so there is no gesture-handler arbitration question. **S-1 is not needed.** A structural assertion pins the absence (`check-shop-deck.js` A-7). | `lld-delta.md` §4.2 |
| **V-5** | `plan.md` §11 / root `CLAUDE.md` §Stack: "the `mobile/tests/check-*.js` structural suites are `npm run`-only and **gate nothing yet**". | **STALE.** They gate CI. | `.github/workflows/ci.yml:44` — `- run: for f in tests/check-*.js; do echo "── $f"; node "$f" \|\| exit 1; done` inside `mobile-typecheck`, plus the comment at `:9-10`: "mobile-typecheck globs mobile/tests/check-*.js, so a guard is live in CI the moment the file exists — no npm script needed." A root-`CLAUDE.md` correction is spawned separately; #403 does not edit it. |
| **V-6** | Q-B's premise that the deck's pass is the behavior to copy, i.e. Elo movement is what a pass does today. | **Revised — today's deck pass usually does NOT move Elo.** `feedback.decline_reasons` is `true`, so the ✕ is replaced by reason tiles and the tap routes to `POST /api/trades/pass-reason`, where `pass_reason_elo_suppression` (default `1.0` = ON) writes the Elo signal **only** on a `value_giving` answer (`docs/api-reference.md:240`). #403's dismiss going through `/api/trades/swipe` is therefore *stricter* than the live deck. Specced as ruled, discrepancy surfaced in `prd.md` §Open. | see cite |
| **V-7** | `plan.md` §4.2: the shop surface should be a "modal/sheet or its own pushed screen". | **Resolved to its own root-stack pushed screen**, with reasons (FeedbackFAB #188 compliance, room for a full `TradeCard` + controls, free back handling, any-host entry). One consequence the Planner did not name: a native-stack push enables the iOS interactive-pop edge gesture by default, which competes with a left-edge horizontal drag. `lld-delta.md` §4.1 specs `gestureEnabled: false` on the route. | `hld-delta.md` §3 D-1 |
| **V-8** | `plan.md` §4.2 / §8: `ShopDeck` needs a client-side trade identity for like/dismiss, implied to be new work. | **Revised — it already exists and needs no new code.** `mobile/src/utils/ideaToCard.ts:56` already synthesizes `asset-idea:${assetIdeaKey(idea)}` for an idea with no server `trade_id`, and `assetIdeaKey` (`:27`) is `counterparty.give_ids-receive_ids` — deterministic and exactly the FB-46 reconstruction context. #403 **imports** it (no edit), so the file stays #402's. | see cites |
| **V-9** | `plan.md` §8: the entry point is "the chosen host file… named at PRD time", recommended default `PlayerContextMenu` mounted on `TradesScreen`. | **Revised on ownership grounds.** `TradesScreen.tsx` is #402's and contended. W1's entry point is the `PlayerContextMenu` action row in `MatchesScreen.tsx` (uncontended, `menuActionsFor` at `:1568`) plus the route itself. The deck mount — the highest-value one — is deferred and handed to #402's agent as a patch. **The discoverability cost is stated plainly in `prd.md` §Open, not buried.** | `prd.md` R-2 |
| **V-10** | Mobile line numbers in `plan.md` (`PlayerContextMenu` mount `TradesScreen.tsx:6969`, `MatchesScreen.tsx:1284/:1390`, `TradesScreen.tsx:1478/:1498/:1506/:1511/:1613/:1631/:6606/:6621/:6879/:7926/:4688`). | **Stale by drift** (the tree moved `30070f36` → `6e94ff71`). Re-cited where used: `PlayerContextMenu` mounts at `TradesScreen.tsx:7726` and `MatchesScreen.tsx:1541`; `pendingPassRef` `TradesScreen.tsx:2163`; `undoPass` `:2392`; deferred POST `:4896`; undo toast `:4988-4997`. Backend numbers all hold. | verified this round |

## Round 0 — Author decisions on questions the operator did not rule

`plan.md` §2 raised nine questions; the operator ruled four. The rest are
Author calls, each labeled as an assumption in `prd.md`.

| Q | Author decision | Basis |
|---|---|---|
| **Q-C** direction | **`give` only in v1.** `direction` is hard-coded `"give"`; `receive` is out of scope. | "Shop him around" is give-side in the fantasy idiom; the report's three options ("tier up / tier down / position swaps") all read as *what do I get for him*. `receive` is one prop away if the operator wants it. |
| **Q-E** tiles or cards | **Cards.** Not a coin flip: the report's other three requirements — a `1/X` counter, left/right paging between them, and a **per-card** like/dismiss pair — only cohere on the card reading. A tile grid has no 1-of-X and nothing to page. | The report, read as a whole. |
| **Q-F** entry point | **W1: `PlayerContextMenu` row on `MatchesScreen` + the pushed route. Deferred: the deck menu (a patch to #402). Explicitly not taken: `TradeCalculator`**, where #403 was filed, because a mount there means editing `InLeagueCalculator.tsx` (#384's, 1,100+ lines). Flagged for the operator. | File ownership (`prd.md` §File ownership). |
| **Q-H / Q-I** copy | See the arbitration above. | |
| **Server-side gate for `swap_positions`** (the contract call `plan.md` §9 left to the Author) | **NO server-side flag gate — with a caveat the Planner did not raise.** Reasoning in `hld-delta.md` §3 D-4. | |

## Still open for the operator

Carried into `prd.md` §Open questions, each with a specced recommended default
so the build is not blocked:

- **O-1 (blocking-ish, bright line).** Q-A's "must not move Elo" vs. the shipped
  `/api/trades/queue`. Recommended: add `record_elo: false`. Needs a confirming
  yes per `CLAUDE.md` §Feature gates.
- **O-2.** W1's only entry point is a long-press on Matches. Accept, or serialize
  with #402 to get the deck mount in W1?
- **O-3.** The shop dismiss moves Elo unconditionally while the live deck pass
  (under `feedback.decline_reasons`) mostly does not. Accept the asymmetry?
- **O-4.** S-2 (`plan.md` §10) — cross-position lateral yield. Recommended: run it
  before W2's picker UI, not before W1.

## Round 1 — Planner critique

*Pending. Objections and their resolutions go here, each labeled
blocking / non-blocking.*
