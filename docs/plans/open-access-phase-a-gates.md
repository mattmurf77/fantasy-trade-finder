# Open-access onboarding — Phase A pre-flip gates

*QA run 2026-08-15. Gates specified by [`docs/business/product/2026-08-14-open-access-onboarding.md`](../business/product/2026-08-14-open-access-onboarding.md) §5 Phase A item 3, ratified by the operator 2026-08-15.*

> Every claim below is labelled **measured** (produced by a command run in this session, artifact cited),
> **code-verified** (read at a cited `file:line`), or **assumed**. No source, test, or flag file was modified;
> production was read-only throughout; nothing was committed, pushed, or deployed. The only writes are this
> file, `onboarding-conversion/deck-eval-report-2026-08-15.md`, and gitignored build/test artifacts
> (`mobile/ios/build`-style output in a scratch dir, `data/ui-test` reseeded by the hermetic sim harness,
> `feedback-workspace/deck-eval/`).

## Contents

- [Verdicts at a glance](#verdicts-at-a-glance)
- [Gate (a) — v2 deck-quality eval against current production data](#gate-a--v2-deck-quality-eval-against-current-production-data)
- [Gate (b) — S-43: does the `s5.1` payoff beat render?](#gate-b--s-43-does-the-s51-payoff-beat-render)
- [Manual TestFlight check for `s5.1`](#manual-testflight-check-for-s51)
- [Evidence index](#evidence-index)
- [What the operator has to decide](#what-the-operator-has-to-decide)

## Verdicts at a glance

| Gate | Verdict | One line |
|---|---|---|
| **(a)** v2 deck-quality eval vs current production data | **PASS** (needs-operator-step on one named defect) | 0% empty decks, 1.48% insult rate against a <3% bar — but every insulting card is a `likes_you` injection sitting at deck position 1–3 of a brand-new user's first deck |
| **(b)** S-43 — prove `s5.1` renders | **FAIL** | Proven on the simulator: with the S-43 variant walk it still lands on `s5.0`. Root cause found — the reveal reads the **pre-regeneration** deck, so `fresh` is **structurally always 0** and `s5.1` can never fire. HLD R17's worst case, confirmed |

**Gate (a) does not block the flip.** Gate (b) does, on the plan's own terms: §5 Phase A item 3 makes proving
`s5.1` a pre-flip condition *"since it carries the whole trades-first argument,"* and HLD R17 says a failure
here is *"the most important defect in the set"* and must reach the operator **before** any first-session test.
It is now proven broken. The fix is small and localised (two adjacent defects in `TradesScreen.tsx`, no schema,
no API, no flag) — see [gate (b)](#gate-b--s-43-does-the-s51-payoff-beat-render).

## Gate (a) — v2 deck-quality eval against current production data

**Full report: [`onboarding-conversion/deck-eval-report-2026-08-15.md`](onboarding-conversion/deck-eval-report-2026-08-15.md).**
Spec: `onboarding-conversion/plan.md` build item 2; prior run + thresholds:
`onboarding-conversion/deck-eval-report.md` (2026-07-17).

### What was run

*(measured.)* `scripts/deck_eval.py`, unmodified, against the **9 numeric Sleeper leagues that exist in
production** — 108 brand-new-user first-run simulations, 540 first-5 cards. Production Postgres was accessed
**read-only** (`SELECT` only) and mirrored into a throwaway local SQLite so that `backend.server`'s import-time
`init_db()` DDL could never touch prod. 10 816 `member_rankings`, 156 `league_members`, 1 104 `draft_picks`,
2 513 `swipe_decisions`, 135 `model_config` rows and the rest came across; rosters came live from the public
Sleeper API. Prior run for comparison: 4 leagues, 47 sims, local dev DB.

### Result against the bar

| Bar (prior report's own Thresholds table) | Result | |
|---|---|---|
| Empty-deck rate < 5% | **0.0%** (0/108) | PASS |
| Insult rate < 3% | **1.48%** (8/540) | PASS |
| Latency compatible with <60s warm TTFT | gen mean 278.9 ms / p95 1015.3 ms; init p95 1.4 ms | PASS |

**The bar was never ratified.** *(code-verified.)* `plan.md` build item 2 writes the thresholds as
"insult rate <3%, empty-deck <5%, **proposed**", and `living-memory/DECISIONS.md` has no entry adopting them.
This run uses them as written and asks the operator to ratify.

**The prior run never produced an insult number at all.** *(measured.)* All 235 first-5 rows in the committed
2026-07-17 report still have blank `insulting?` / `would consider?` columns, and its insult cell still reads
*"score below, then compute."* `git log` shows one commit on that file. So this is the first execution of the
gate's scoring half — the prior "pass" covered empty-deck rate and latency only.

**Scoring rule** *(QA-authored — see the report for the full statement and sensitivity curve)*: a first-5 card
is insulting when the user is net-negative in consensus value by `|Δ| ≥ 500` **and** either eats a ≥20%
haircut on what they give (**lowball**) or receives a waiver-floor asset (≤350) while giving a top asset
(≥2500) (**junk-filler**). The 20%-haircut half is standard; the `|Δ| ≥ 500` materiality floor is the one
judgement call, and the verdict is sensitive to it:

| Materiality floor | This run | Prior run |
|---|---|---|
| none | 3.70% ✗ | 0.85% |
| ≥ 250 | 2.41% ✓ | 0.85% |
| **≥ 500 (primary)** | **1.48% ✓** | 0.85% |
| ≥ 500, exempting honest n-for-fewer consolidations | 1.48% ✓ | **0.00%** |

### The finding that matters

*(measured + code-verified.)* **8 of 8** insulting cards — and 19 of 20 under a zero floor — are
`likes_you: true`: leaguemates' own liked trades mirrored into the new user's perspective by
`_inject_likes_you_cards_impl` (`backend/server.py:2819`) and boosted to `max(composite) + 1.0`
(`:2858`), i.e. straight to the **top of the deck**. That path applies **no fairness gate and no user-gain
gate** — its docstring says the pull is *"they already want this, not its score."*

- 24 of 108 first decks (22%) carry one inside the first five; observed positions are only 1, 2, or 3.
- 51 of those 66 cards are net-negative for the new user; 7 are ≤ −1000.
- Worst: `@MangoPatti` card #3 — give A.J. Brown (4168) + James Cook (5677) + CeeDee Lamb (6862), receive
  Jaxon Smith-Njigba (8073) + Devin Singletary (**228**) + Malik Davis (**229**). Δ **−8177**.

This is newly live because production now has real league likes and real leaguemate boards; the July run had
**zero** `likes_you` and **zero** divergence cards in its first-5 set. Removing these 8 cards takes the insult
rate to **0.00%** at the primary floor and **0.19%** with no floor at all.

**Recommendation:** before the flip, either turn `trade.likes_you` off for the Phase A cohort or add a
user-gain floor to the injection. It is a coarse global flag today (`config/features.json`), and the first-run
pregen shares `/api/trades/generate`, so there is no first-run-only suppression to reach for.

**Secondary observation, not a blocker** *(measured + code-verified)*: 39 first-5 cards sit below the engine's
0.75 fairness threshold and **all** are `basis: divergence`, which is by design —
`fairness_floor_divergence = 0.55` (`backend/trade_service.py:154`). Their user-visible effect is the opposite
of an insult (e.g. Δ **+4095** at fairness 0.50). Against a chip that promises "CONSENSUS VALUES" this is a
credibility risk on first impression, not a fairness one. Recommend routing to `pm-pfo` as an observation.

## Gate (b) — S-43: does the `s5.1` payoff beat render?

Specs: `audit-p0-remediation/hld.md:324` (S-43), `:755` (R17); `audit-p0-remediation/lld-p0-8-9.md:522-620`
(§5.3, the proof design) and `:664` (the disposition table).
### Layer 1 — code-path analysis. Conclusion: `fresh` is structurally always 0

**The chain, every link cited** *(code-verified)*:

| # | Link | Where |
|---|---|---|
| 1 | Quick Set ladder finishes; if `onboardingReturn`, post the regen handoff and navigate to Trades — **unconditionally, whether or not any chip was selected** | `mobile/src/screens/QuickSetTiersScreen.tsx:336` (inside the `idx >= TIERS.length` branch, `:309`) |
| 2 | Trades consumes the handoff on focus, snapshots `prevIds` from the deck currently on screen, rewinds the index and forces a job — **it does not clear the deck** | `mobile/src/screens/TradesScreen.tsx:2665-2673` |
| 3 | Job snapshots **append** into the deck, de-duped by `trade_id`: `return fresh.length === 0 ? prev : [...prev, ...fresh]` | `TradesScreen.tsx:1427-1435` (deps `[job?.cards.length, job?.status]`) |
| 4 | When the job reaches `complete`, `fresh` = cards whose `trade_id` was not in `prevIds`; `pendingRegenRef` is cleared on this **first** pass | `TradesScreen.tsx:2693-2697` (deps `[job?.status, deck]`) |
| 5 | Single ternary: `fresh > 0 ? GUIDE.s5_1(fresh, pos) : GUIDE.s5_0(pos)` | `TradesScreen.tsx:2708` |
| 6 | The beat — celebrate pose, *"There it is. ${nNew} new trades that only exist because of your numbers."* | `mobile/src/components/analystScript.ts:72-75` |
| 7 | The branch only runs when the tour owns the surface | `TradesScreen.tsx:2704` → `guidedAvatarActive()`, `mobile/src/state/useGuide.ts:76-81` |
| 8 | Tour flag = master AND own flag | `mobile/src/state/useFeatureFlags.ts:171-176`; `config/features.json` has `onboarding.v2: true` and **`onboarding.guided_avatar: true`** |
| 9 | Entry needs the prompt card or the provenance chip, both gated on `onboarding.quickset_prompt`; the deck needs `onboarding.trades_first` for `firstRun` | `TradesScreen.tsx:2612`, `:4652-4653` |

**Defect 1 — the reveal reads the pre-regeneration deck, so `fresh` is always 0.** *(code-verified.)*
`deck` is `useState` (`TradesScreen.tsx:389`) and is written **only from inside the append effect** at
`:1429`. On the commit where `job.status` flips to `'complete'`, effect 4's `deck` closure is still the render's
**old** deck — a `setDeck` issued by effect 3 in the same commit is not visible to it. So effect 4 computes
`fresh = 0`, renders `s5.0`, and **nulls `pendingRegenRef`**. The next commit, where the new cards have actually
landed, finds `pending === null` and returns immediately. `s5.1` is unreachable by construction, for every
user, on every Quick Set return — no data, board state, or chip selection can change it.

**Defect 2 — `trade_id` is a fresh UUID per generation, so the count would be meaningless once defect 1 is
fixed.** *(code-verified + measured.)* Card ids are `str(uuid.uuid4())[:8]`
(`backend/trade_service.py:3644`, `:3815`, `:4314`) and `f"likesyou_{uuid4().hex[:12]}"`
(`backend/server.py:2921`) — never derived from the package. Two back-to-back generations for the same
brand-new user on an unchanged board (prod-mirrored data, league `1312076055586050048`, `@mlakejr`):

```
run1: 33 cards      run2: 33 cards
trade_id overlap ............................... 0 of 33
package overlap (same give/receive/opponent) ... 33 of 33
=> cards the client would count as "fresh" ..... 33 of 33
```

So the moment defect 1 is fixed, `s5.1` will announce *"33 new trades that only exist because of your
numbers"* for a deck whose 33 packages are identical to the 33 the user just saw — after a Quick Set they may
have skipped entirely (link 1). **Both defects have to be fixed together**, and the same `fresh` value also
drives the non-guided **diff banner** (`TradesScreen.tsx:2713-2715`) and the `deck_regenerated.new_trades`
analytics event (`:2698-2702`) — the metric Phase A would read its aha moment from.

**Defect 3 (adjacent, same root) — the post-Quick-Set deck doubles.** *(code-verified.)* Because link 2 never
clears the deck and link 3 de-dupes on the UUID, the regenerated cards are **appended** to the old ones. The
user is rewound to index 0 (`:2672`) on a deck that now contains every package twice under two different ids.
Every other deck-invalidating path in this screen resets first (`:796`, `:1462`, `:2001`); the Quick Set regen
path is the one that does not.

**What this does to the LLD's proof rubric.** `lld-p0-8-9.md:605-607` classifies an observed `s5.0` as
*"Inconclusive, NOT a defect — the walk failed to move the board"*, on the premise (`:557-563`) that empty
saves leave the board unchanged so the regen re-prices to the same deck and `fresh === 0`. With UUID ids that
premise is false: an unchanged board still yields a full set of unseen ids. **`s5.0` is therefore not
inconclusive — it is positive evidence of defect 1**, and the rubric would have mis-triaged the run below as
"re-run with more chips."

### Layer 2 — runtime proof (achieved). Result: `s5.0`, on the S-43 variant walk

*(measured.)* The harness was made to run on this machine: `maestro 2.5.1` with
`JAVA_HOME=/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home`, a fresh
`mobile/scripts/sim-build.sh` Release build (the pre-existing binary was from 2026-08-11 07:28, which
predates `e47d865` — the P0-8 tour commit S-43 belongs to — so it was not usable as evidence), and
`mobile/scripts/sim-run.sh` against the canonical simulator `FTF-iOS18`, profile `fresh`, flags
`backend/tests/fixtures/flags/onboarding-v2.json`, flow
`mobile/.maestro/capture/onboarding-tour@fresh.yaml` (which already carries the S-43 variant walk — the rung
loop taps `quick-set.chip.*` at `index: 0/1/2` before each save, `:269-318`).

**Result: `[Passed] onboarding-tour@fresh (3m 43s)` — and it captured `onboarding__s5-0.png`. No `s5-1.png`
was produced.** The frame shows The Analyst in the `oops` pose reading *"Honest result: same trades. Your WR
board agrees with consensus more than you'd think…"* over a **populated** deck (a live card,
@qa_opp_unranked, Jaylen Waddle → Colston Loveland, is visible behind the bubble).

The walk really did move the board and the regeneration really did run *(measured, from the hermetic backend
log)*:

```
18:22:14  POST /api/tiers/save   tiers/save [1qb_ppr] WR … saved: ['WR']
18:22:21  POST /api/tiers/save   tiers/save [1qb_ppr] WR … saved: ['WR']
18:22:24  POST /api/trades/generate     (forced regen, job 56c966ec…)
18:22:33  GET  /api/trades/status?job_id=56c966ec…
18:22:43  → screenshot onboarding__s5-0.png
```

Two real tier saves, a forced job, a completed poll — and the deck non-empty in the frame. Under defect 2 that
combination makes `fresh === 0` **impossible** unless the reveal evaluated the stale deck. The runtime result
and the code analysis agree, and together they close D3 in the negative.

**Verdict on S-43: FAIL.** `s5.1` does not render, has never rendered, and cannot render as built. Per
`lld-p0-8-9.md:664` the disposition for this outcome is *"fix in this commit (HLD R17 / S-43) — it is the
payoff beat and nothing else in the tour is worth testing if it is broken."*

**Suggested fix shape** (for whoever picks it up — not implemented here, this session wrote no code):
make the diff **content-based and late-bound**. Compare package identity (`give` + `receive` + opponent), not
`trade_id`; keep `pendingRegenRef` alive until the deck actually changes (e.g. resolve on the deck-append
commit rather than the status flip, or capture the job id and diff against `job.cards` directly); and clear
the deck on the Quick Set regen path the way every other invalidating path does. That fixes the beat, the diff
banner, `deck_regenerated.new_trades`, and the doubled deck in one change.
## Manual TestFlight check for `s5.1`

The simulator proof was achieved, so this is no longer the fallback — it is the **operator's confirmation on
real data** during the Phase A TestFlight pass (§5 Phase A item 4), and the **regression check after the fix
lands**. Five steps, ~5 minutes.

**Preconditions.** Phase A flags live for the tester: `onboarding.trades_first` and
`onboarding.quickset_prompt` on (plus `onboarding.v2` and `onboarding.guided_avatar`, already true).
**Delete and reinstall the app first** — `ftf_onboarding_state` must be clear or the tour's `once: true` steps
are already burned and the beats will not re-fire.

1. **Land on the deck and count it.** Sign in with a Sleeper username on a league you own, let the first-run
   deck generate, and note **how many cards it has** before touching anything — call this **D**. (The card
   counter / swiping to the end both work; you only need it roughly.)
2. **Take the ranking ask.** Swipe 2–3 cards until The Analyst offers *"Two minutes on one position and I'll
   re-price the whole deck with your board"* and tap **Fix <POS> →**. If the bubble does not appear, tap the
   **CONSENSUS VALUES** provenance chip on a card — same destination, same handoff.
3. **Rank for real.** In Quick Set, actually select players — 3–5 genuine names in tier 1 and tier 2 — and
   finish the ladder to the end. (Do *not* skip through; skipping is the case that must also be checked, but
   check the honest case first.)
4. **Read what The Analyst says on the return to Trades.** Wait for the deck to rebuild (up to ~30 s on a cold
   Render dyno). Screenshot whichever bubble appears.
   - **Expected today (defect present):** the `oops` pose and *"Honest result: same trades. Your <POS> board
     agrees with consensus more than you'd think…"* — even though you just ranked players. That is the bug.
   - **Expected after the fix:** the `celebrate` pose and *"There it is. **N** new trades that only exist
     because of your numbers. Your board, your market."*
5. **Sanity-check the number and the deck.** If you see the celebrate beat, **N must be smaller than D** and
   the deck must not have grown — swipe a few cards and confirm you are not seeing the *same* trades you
   already saw before Quick Set, now repeated. `N ≈ D`, or the same packages appearing twice, means the
   content-diff half of the fix (defect 2/3) did not land even though the beat now fires.

**Also worth one pass:** repeat with an **all-skip** Quick Set walk (tap Save on every rung with nothing
selected). Correct behaviour there is the honest `s5.0` "same trades" beat — if that walk produces a
celebration, the fix over-corrected.

**What to file.** Both screenshots plus D and N, into `screens/mobile/onboarding/` (`s5-1.png` is the missing
library entry) and a line in `living-memory/TEST_LEDGER.md`.

## Evidence index

| Artifact | Path | Type |
|---|---|---|
| Gate (a) full report | `docs/plans/onboarding-conversion/deck-eval-report-2026-08-15.md` | measured |
| Gate (a) machine artifact (this run) | `feedback-workspace/deck-eval/deck_eval_20260815T220047Z.json` (gitignored) | measured |
| Prior run's machine artifact (re-scored under the same rule) | `feedback-workspace/deck-eval/deck_eval_20260717T231038Z.json` (gitignored) | measured |
| Prior run's report (scoring columns never filled) | `docs/plans/onboarding-conversion/deck-eval-report.md` | measured |
| `likes_you` injection — boosted to top, no fairness/user-gain gate | `backend/server.py:2804`, `:2819`, `:2858` | code-verified |
| Divergence fairness floor 0.55 | `backend/trade_service.py:154` | code-verified |
| Random per-generation `trade_id` | `backend/trade_service.py:3644`, `:3815`, `:4314`; `backend/server.py:2921` | code-verified |
| Deck **appends**, de-duped on `trade_id`; regen path never clears it | `mobile/src/screens/TradesScreen.tsx:1427-1435`, `:2665-2673` | code-verified |
| `fresh` computation, `pendingRegenRef` cleared on the first `complete` pass, `s5.1`/`s5.0` ternary | `mobile/src/screens/TradesScreen.tsx:2693-2715` | code-verified |
| `s5.1` copy | `mobile/src/components/analystScript.ts:72-75` | code-verified |
| Quick Set posts the handoff even on an all-skip walk | `mobile/src/screens/QuickSetTiersScreen.tsx:309`, `:336` | code-verified |
| S-43 variant walk (real chip selections) already in the flow | `mobile/.maestro/capture/onboarding-tour@fresh.yaml:269-343` | code-verified |
| **Simulator run: `[Passed] onboarding-tour@fresh (3m 43s)`, captured `s5-0`, no `s5-1`** | 11 frames + `flask.log` + `junit.xml` in this session's scratch dir (`…/scratchpad/capture-out/`, `…/scratchpad/capture-report/`) — **ephemeral, copy them out before the session ends if they are wanted as a durable artifact**; the backend log shows 2× `POST /api/tiers/save` (18:22:14, 18:22:21) then the forced `POST /api/trades/generate` (18:22:24) and its completed status poll (18:22:33), with `s5-0.png` written at 18:22:43 | measured |
| `s5-1.png` still absent from the screen library | `screens/mobile/onboarding/` (has `s5-0.png`) | measured |

## What the operator has to decide

1. **`s5.1` is broken — fix before the flip, or waive the gate?** This is the only decision that gates Phase A.
   §5 Phase A item 3(b) and HLD R17 both make it a pre-flip condition. The fix is client-side only (no schema,
   no API, no flag), so it is inside the express lane if the operator wants it there — but note the bright-line
   rule does *not* apply, since nothing here touches schema, contracts, flags, or the analytics taxonomy.
   Shipping without it means the tour's payoff beat is dead, the diff banner never shows, and
   `deck_regenerated.new_trades` reads 0 for every user — i.e. Phase A would launch with no instrumentation on
   its own aha moment.
2. **Rule on `likes_you` on first-run decks** (gate (a)). Cheapest reversible option: `trade.likes_you` off for
   the Phase A cohort. Better long-term: a user-gain floor inside `_inject_likes_you_cards_impl`. Doing nothing
   is defensible — the gate passes as written — but 22% of new users' first decks lead with a counterparty's
   wish, and the worst is Δ −8177.
3. **Ratify or replace gate (a)'s thresholds.** `<3%` insult / `<5%` empty deck are marked "proposed" in
   `plan.md` and nothing in `living-memory/DECISIONS.md` adopts them; the `|Δ| ≥ 500` materiality floor in this
   run's scoring rule needs the same nod, since without it the same data reads 3.70% and the gate fails.
4. **The deck doubles after Quick Set** (defect 3). It is inside the same fix and the same file, but it is a
   separate user-visible bug and should be named in the CHANGELOG rather than discovered later.
