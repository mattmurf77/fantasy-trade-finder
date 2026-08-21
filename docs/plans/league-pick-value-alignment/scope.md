# Feature Scope — League-surface pick-value alignment (Q-026)

**Date:** 2026-08-21
**Entry point:** operator ruling logged as [Q-026](../../../living-memory/OPEN_QUESTIONS.md), committed as the immediate follow-up to the per-slot pricing ship (PR [#167](https://github.com/mattmurf77/fantasy-trade-finder/pull/167) → `main` `3192d13`)
**Builder:** agent session on `feat/league-pick-value-alignment`
**Operator sign-off on waivers:** **REQUIRED** — three items in §6, two of them new findings

---

## 0. The ruling, verbatim

> *"I want the league values to reflect the same pick values.. But let's defer that until after finishing this one."*
> — operator, 2026-08-21, on [slot-pricing scope §6 waiver 2](../slot-pricing-unconditional/scope.md)

That deferral expired when `3192d13` merged. The question was never open — it was ruled and sequenced. This branch executes it.

**What was wrong.** [D-146](../../../living-memory/DECISIONS.md) put the per-slot waterfall into the ENGINE only. Two league surfaces kept reading the stored `draft_picks.pool_value`, so the app quoted two different prices for the same asset on two screens:

| pick | league surfaces said | engine said | gap |
|---|---:|---:|---:|
| **2026 1.01** | 2117.0 | **4867.1** | **+2750.1 (+130 %)** |
| 2026 1.12 | 2117.0 | 820.8 | −1296.2 (−61 %) |

**What ships.** Every surface that displays or aggregates an owned pick's value now calls one helper, `server._priced_pick_value`, which is `pick_values.priced_pool_value` under D-090's slot resolution — the identical call the trade engine makes.

---

## 1. Analytics scope

**(c) WAIVED — no analytics needed because** no event fires, no property changes, and no event carries a pick price. This changes the NUMBER two existing read paths serve; it adds no interaction, no surface and no funnel step. The taxonomy (`backend/analytics_taxonomy.py`) is untouched and `analytics_queries.NON_INTENT_EVENTS` needs no new classification.

One consequence worth naming for the analytics owner rather than the taxonomy: **`roster_history.team_value` shifts at this merge** (§7.4). Any query that trends team value across 2026-08-21 crosses a re-pricing boundary. That is a READ-SIDE caveat on existing data, not an event change.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** `draft_picks.pool_value` is neither read differently at write time nor written differently — it is still the sync-written ladder value and is now explicitly step 3 of the waterfall. `docs/data-dictionary.md` updated to say so (its row previously described the stored value as what surfaces serve).
- **New/changed feature flags:** **none.** No flag was added, removed or defaulted differently.
  **But one existing flag widened its blast radius, and this needs the operator's eye:** `picks.slot_labels` was already a pricing flag for the ENGINE as of D-146 (waiver 1 of the prior scope, shipped under recommended-accept). It is now a pricing flag for the **league surfaces too** — turning it off drops Power Rankings, `/api/league/picks` and the eveners from per-slot to the round curve, without a deploy. That is the same lever, reaching further. See §6 waiver 1.
- **New env vars / `model_config` keys:** **none.**
- **Deploy-free rollback lever:** `picks.slot_labels` → off reverts the *per-slot* half of the repricing everywhere at once (engine and surfaces together, which is the coherent unit). Reverting to the stored ladder entirely is still revert-and-redeploy — unchanged from D-146, and unchanged by design, because the ruling forbids pricing being "an option to flip".

## 3. Evidence scope

- **Structural guard:** `backend/tests/test_league_pick_value_alignment.py` — a bidirectional AST walk over `backend/server.py` pinning (a) `priced_pool_value` is called from exactly one function, and (b) the callers of that seam are exactly the five known surfaces. **Sabotage-verified three ways** (§7.5). No `mobile/tests/check-*.js` guard: there is no client change to pin (§3, mobile note).
- **Unit tests:** `backend/tests/test_league_pick_value_alignment.py` (new, 12 tests); `test_league_picks_tier.py` (rewritten, 7 → 12); `test_power_rankings.py` (3 re-derived, incl. one fixture reshaped); `test_trade_evaluate.py` (1 re-derived). Every moved literal re-derived from the pricing functions with inputs pinned as literals; **no tolerance widened**.
- **Code-walk proof:** §7 below — every reader of `draft_picks.pool_value` and of pick values in a display path, aligned or dispositioned.
- **Manual TestFlight checklist:** §8. Runtime proof genuinely matters here: no structural test can see a served Power Rankings screen, and the badge movement is the kind of change a user reads as a bug unless it is expected.
- **`testID`s added/renamed:** none. `mobile/scripts/testid-lint.sh` run locally, green.
- **Mobile note:** `git diff --name-only origin/main -- mobile web extension` returns **zero files**. The clients need no change because the wire keys did not: `/api/league/picks` still carries `pool_value` and `tier`, and the mobile in-league calculator (`mobile/src/components/InLeagueCalculator.tsx:233`) reads `p.pool_value` as its `base` exactly as before — it now receives the priced number. `npx tsc --noEmit` could not be run in this worktree (no `mobile/node_modules`, and `npm ci` needs network which is unavailable here); the honest evidence is the zero-diff, against an `origin/main` whose CI is green at `f01ac9f`. **The operator or CI must confirm typecheck on the pushed sha** — it is asserted as unaffected, not observed.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `/api/league/picks` — `pool_value` and `tier` semantics rewritten (served value is the waterfall; the null contract re-anchored). `/api/league/power-rankings` — `picks[].value` and the `pick_pool_value` sentence corrected. |
| `living-memory/LLD.md` | **updated** | the one-seam convention: a value every surface must agree on gets ONE named helper plus a bidirectional AST guard, not N copies of one expression. |
| `docs/architecture.md` | **n/a** | no module wiring or data flow changed. Same functions, same callers, same reads; one helper extracted inside `server.py`. |
| `living-memory/HLD.md` | **n/a** | no new module, client or major flow. |
| `docs/cross-client-invariants.md` | **updated** | the owned-pick `pool_value` row (clients read a PRICED value now), the Q-026 "two surfaces still disagree" sentence (deleted — it is false as of this merge), and the D-088 invariant's test pointer (the test was renamed in the re-derivation). |
| `docs/data-dictionary.md` | **updated** | `draft_picks.pool_value` — what it is vs what is served; `roster_history.team_value_picks` — the ADR-011 boundary; the `users.pick_pricing_mode` row's Q-026 parenthetical. |
| `docs/config-reference.md` | **updated** | `picks.slot_labels` — the flag now moves LEAGUE-surface prices too, not only engine prices. |
| `docs/glossary.md` | **n/a** | no new domain term. |
| ADR or `DECISIONS.md` entry | **drafted** | D-148, in `decisions-draft.md` beside this file, with the Q-026 closure text. |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` **3986 passed, 1 skipped** (baseline `origin/main` 3969 + 1 skipped; +5 from the `test_league_picks_tier.py` rewrite, +12 new). `mobile/scripts/testid-lint.sh` green. `npx tsc --noEmit` **not runnable in this worktree** — see §3's mobile note; zero client diffs.
- **Golden set:** run **in isolation, before any fixture was touched, and again after** — `test_bakeoff_arm_a_golden.py`, `test_engine_quality_golden.py`, `test_fairness_gate_golden.py`, `test_rnk_elo_golden.py`: **29 tests / 156 assertions, zero edits, both times.** Arm A is structurally immune (it never constructs a `draft_picks` row, so it never reaches `priced_pool_value`) — verified, not assumed.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** §8 checklist, for the operator.
- **Express lane declared by the operator?** **No.** Full gates.

---

## 6. Waivers requiring operator sign-off

### Waiver 1 — `picks.slot_labels` now moves LEAGUE prices, not just engine prices

D-146 shipped this coupling for the engine under the recommended-accept disposition ("labels and prices moving together is coherent — you never show *2026 1.01* while charging generic"). The same argument holds a fortiori here: the Power Rankings item and the `/api/league/picks` row each carry the label AND the value, built from **one** `slot_for` result. Flipping the flag off makes both go generic together, on every screen, which is the honest degradation.

**Recommending accept, as before.** What is new is only the reach: the deploy-free lever is now a whole-app lever rather than an engine lever. `docs/config-reference.md` says so.

### Waiver 2 — NEW FINDING: the Draft Room board and the engine disagree in non-12-team leagues

**This is not something this branch introduced; it is something this branch made visible on three more screens.**

DynastyProcess publishes exactly **one** 12-team slot curve. The two consumers map onto it differently:

| consumer | mapping | a 10-team league's last first |
|---|---|---|
| Draft Room board (`draft_board_service._basis_slot`, plan O3) | percentile within the round, ends anchored | priced as the **1.12** → **820.8** |
| the engine + every surface this branch aligned (`market_pick_slot_value`) | the slot number, literally | priced as the **1.10** → **1069.8** |

So a 10-team league's board displays 820.8 for the pick its own trade card charges 1069.8 for — a **30 % disagreement**, on the same screen family, for the same pick.

The other end of the same gap: a **14-team** league's 1.13 and 1.14 have no DP row at all, so they fall off step 1 onto the round curve (1859.5) while their twelve leaguemates get per-slot prices. A 14-team 1.14 is therefore priced **above** its own 1.12.

**Not fixed here, deliberately.** Fixing it means threading league size into `priced_pool_value`, which reprices the ENGINE in every league that is not 12 teams — a change to trade values in leagues the operator did not ask about, on a branch commissioned to align league surfaces to the engine. The honest move is to name it and let the operator sequence it.

**Pinned rather than left loose:** `test_league_pick_value_alignment.py::test_non_twelve_team_boards_disagree_and_that_is_pinned_not_fixed` asserts both mappings and the exact size of the gap, so a silent change to either one fails CI. **Logged as Q-027.** Needs a call: (a) map the engine through `_basis_slot` too, (b) map the board literally like the engine, or (c) accept, because a 12-team curve applied to a 10-team league is an approximation either way and the board already marks itself `slot_value_approx`.

### Waiver 3 — NEW FINDING: pick-SHARE ratios are dispositioned as STAYING on the legacy scale

`_user_pick_share` (`server.py:5335`) and the opponent-pick-share block inside `_run_trade_job` (`server.py:5570`) both sum the legacy `draft_picks.pick_value` column (the 0–100 round-tier scale), not `pool_value`, and produce a 0–1 **ratio** that feeds `trade_service.infer_team_outlook` — the contend/rebuild classifier.

**Left as-is.** Three reasons, in order of weight:

1. **It is not a surface.** Nothing displays it. The ruling is about the values a user reads; this is an inference input.
2. **Aligning it changes which decks get generated.** The classifier compares the ratio against thresholds; re-weighting a 1.01 to 5.9× a 1.12 moves teams across those thresholds and therefore changes trade suggestions — a behavior change nobody commissioned, and one the golden set would NOT catch (arm A builds no `draft_picks` rows).
3. **It reads a different column** on a different scale, documented as "not a client-facing value" (`docs/cross-client-invariants.md:819`).

**The operator-visible consequence, stated plainly:** the app's guess at whether *you* are contending or rebuilding still counts every 2026 first as the same asset. A team holding the 1.01 and a team holding the 1.12 have identical draft capital in that classifier's eyes. That is the pre-D-146 world, surviving in one inference. **Needs a call:** align it as a follow-up (and re-baseline the outlook distribution), or accept it as a coarse signal that does not need slot precision.

---

## 7. Code-walk proof — every reader of a pick's value, aligned or dispositioned

Traced on `feat/league-pick-value-alignment`. Line numbers are post-change.

### 7.1 The seam

`backend/server.py:10799` —

```python
def _priced_pick_value(p: dict, slot_order: dict | None,
                       scoring_format: str) -> float:
    return priced_pool_value(
        p, scoring_format=scoring_format,
        slot=pick_slots.slot_for(slot_order, p.get("season"), p.get("round"),
                                 p.get("original_roster_id")))
```

`slot_order` is **passed in, never resolved here**: this runs once per PICK, and `_league_slot_order` costs a DB read plus a cache lookup once per LEAGUE. Every caller hoists it. `pick_slots.slot_for` is pure and already refuses a future season (#273), an unknown roster, a malformed blob and an unverifiable snake reversal, so a `None` slot rides step 2 by itself.

### 7.2 The five call sites — all of them, and nothing else

| # | site | file:line | before | after |
|---|---|---|---|---|
| S1a | `_trade_evaluate_impl` (calculator) | `server.py:9840` | already priced (D-146) | **pure refactor** — the identical expression, now through the seam |
| S1b | `get_league_picks` | `server.py:10430` | `{**p}` served the stored column; `_pick_tier` badged it | **ALIGNED** — `pool_value` on the wire is the priced value; `tier` follows it |
| S2 | `_power_picks_by_owner` | `server.py:23376` | `p.get("pool_value")`, NULL re-derived via `pick_pool_value` | **ALIGNED** — NULL re-derived into a row COPY first, so the ladder stays step 3 |
| S3 | `_owned_pick_assets` (deck lane) | `server.py:10909` | already priced (D-146) | **pure refactor**; the now-redundant `_slots` dict removed |
| S4 | `_roster_eveners` | `server.py:1095` | `float(pk.get("pool_value") or 0.0)` | **ALIGNED** — see 7.3 |

The AST guard asserts this table in both directions. A sixth site that prices a pick without appearing here fails CI; one of these five quietly regressing to the stored column also fails CI.

### 7.3 S4 was an actual defect, not just an inconsistency

Both call sites of `_roster_eveners` (`server.py:10060`, `server.py:10080`) live inside `_trade_evaluate_impl`, whose `gap` is computed from **priced** picks. The candidates were sized against the **stored ladder**. So a one-tap "add their 2026 1.01" was offered as closing a 2117.0-sized hole that the same response charged 4867.1 for — the sweetener and the hole came off two different price lists. `scoring_format` was threaded in for exactly this (the waterfall needs a format; the caller's `fmt` is the one the rest of the response used).

### 7.4 The ADR-011 boundary — named, and verified to be a boundary and not a rewrite

`_do_league_history_snapshot` (`server.py:23496`) hands `_power_picks_by_owner`'s dict to `roster_history.snapshot_league_rosters`, whose docstring already states the contract: *"team_value comes out of `compute_power_rankings`' consensus basis via the SAME `_power_picks_by_owner` pricing the Power Rankings screen uses, so the two can never disagree about a team."* That contract is why the history series moves with this ship.

**Two things are true and both matter:**

1. **The series shifts at this merge.** Rows written from 2026-08-21 forward price picks per slot; rows written before do not. `roster_history.team_value` and `team_value_picks` are therefore **not comparable across the boundary** for any pick-holding team. The Wrapped/recap and trends consumers read across it. Measured magnitude in §7.6: on a full 12-team FFV3-shaped grid the per-roster pick component moves **+12.4 % to −40.3 %**, monotonically by draft slot.
2. **Nothing historical is recomputed.** ADR-011's append-only rule holds by construction: `roster_history` has no pricing path of its own — it is HANDED `picks_by_owner` and stores what it is given. Pinned by `test_history_snapshot_reads_the_same_priced_picks_as_power_rankings`, which asserts the module contains no `priced_pool_value`, no `_priced_pick_value`, and no `pick_pool_value` call at all.

### 7.5 Sabotage verification of the structural guard

Each applied to `backend/server.py`, the suite run, then reverted:

| sabotage | what it does | caught by |
|---|---|---|
| 1 | `_power_picks_by_owner` regresses to `p.get("pool_value")` — literally the pre-D-148 line | 4 tests, incl. both AST guards |
| 2 | a surface calls `priced_pool_value` directly with the *identical* expression (behaviourally a no-op) | 3 tests — proving the guard is structural, not behavioural |
| 3 | `_league_slot_order` resolved once per PICK instead of once per league | `test_power_rankings_resolves_the_draft_order_once_per_league` |

### 7.6 Sites SWEPT and dispositioned as staying

Every remaining reader of `draft_picks` values, from `git grep -n "pool_value\|pick_value" -- backend` minus tests:

| site | reads | disposition |
|---|---|---|
| `database.sync_draft_picks` / `_seed_*` / assignment routes (`server.py:12985`, `13186`, `13332`) | **writes** `pool_value` via `pick_pool_value` | **stays.** The stored column is the ladder and must remain so — it is the waterfall's step 3 and the whole safety net when DP is unreachable. Nothing here serves a value. |
| `_user_pick_share` (`server.py:5335`) | sums `pick_value` (legacy 0–100 scale) → ratio | **stays — waiver 3.** Not a surface; aligning changes deck generation. |
| `_run_trade_job` opponent pick shares (`server.py:5570`) | same | **stays — waiver 3**, same reasoning, same column. |
| `draft_board_service._annotate_slot_values` | DP slot prices in **seed-Elo** space | **stays.** Already per-slot and already reads the same DP rows; asserted equal to the engine for a 12-team board (`test_board_and_engine_agree_on_every_slot_of_a_twelve_team_board`). Non-12-team divergence is **waiver 2**. |
| `_pick_firsts_equivalent` / `picks.value_label` (#285/#306) | a literal COUNT over `round`; no dollars | **stays, and must.** D-306-2 exists precisely to keep this off the dollar scale. It moved indirectly only in that the fixture proving it diverges from the dollar answer had to be re-derived (§7.7). |
| `_first_round_ledgers` (`server.py:23617`) | `owner_user_id` / `original_user_id`; **no value at all** | **stays.** Provenance counting, not pricing. |
| `roster_history.pick_fold_for_league` | `pick_id`s only | **stays.** Ids, not values. |
| `og_image.py` | the 8-tier ladder constants; **no pick prices** | **stays.** `git grep -n "pick" backend/og_image.py` returns one comment line. Share cards render stored match/package rows and never price a pick live. |
| `_pick_labels_by_id` (`server.py:10510`) | labels only | **stays.** Already D-090-resolved; no value on that path. |
| `mock_draft_service` ownership overlay (`server.py:14190`) | `original_roster_id` | **stays.** Ownership, not price. |
| trends / wrapped | read `roster_history` rows | **stays** — and inherit the §7.4 boundary rather than a code change. |

### 7.7 Fixtures that moved, and why each moved

| test | what moved | re-derived how |
|---|---|---|
| `test_league_picks_tier.py` (7 → 12) | every badge literal; the null-tier contract; the far-out-first case | from `priced_pool_value` with literal inputs. All three original sabotages (S1 raw scale, S1b wrong inverse, S2 platform-only) **re-verified against the priced values** — each still produces a different tier on ≥2 rows. A fourth (S3: leaving the stored column on the wire) added. |
| `test_power_rankings.py` (3 tests) | the pick-total literals; `_PICKS_306`'s shape | the D-084 "one 3rd separates the literal and dollar label scales" trap **collapsed** under the new prices (2 seconds + 1 third rounds to ≈0.5 firsts on both scales). Re-derived to **three** thirds — 1654.9 dollars ⇒ "≈1 firsts" vs the literal "≈0.5 firsts" — restoring the divergence. Two thirds would not have worked; the file says so. |
| `test_trade_evaluate.py` (1 test) | the evener pick's fixture season | changed 2027 → 2028 so the priced value (1263.0) lands where the ordering assertion needs it, and the row now STORES 1005.3 so "priced, not stored" is provable rather than incidental. |

No tolerance was widened anywhere. No golden fixture was touched.

---

## 7.8 Measured before/after (FFV3-shaped fixture, 1QB, pinned DP snapshot)

12-team linear board, rounds 1–4 of 2026 (48 picks) + 2027/2028 firsts and seconds (48 picks), one owner per draft slot. 96 picks total.

**Per-pick, 2026 round 1** — the ruling's headline:

| pick | before | after | Δ | badge |
|---|---:|---:|---:|---|
| 1.01 | 2117.0 | **4867.1** | +2750.1 | `first_1` → **`firsts_2`** |
| 1.05 | 2117.0 | 2343.2 | +226.2 | `first_1` (unmoved) |
| 1.08 | 2117.0 | 1435.5 | −681.5 | `first_1` → **`second`** |
| 1.12 | 2117.0 | **820.8** | −1296.2 | `first_1` → **`second`** |

**Per-roster pick total** — what a Power Rankings team card moves by:

| roster (by slot) | before | after | Δ | % |
|---|---:|---:|---:|---:|
| slot 1 | 8590.4 | 9653.9 | +1063.5 | **+12.4 %** |
| slot 2 | 8590.4 | 8722.1 | +131.7 | +1.5 % |
| slot 3 | 8590.4 | 7965.4 | −625.0 | −7.3 % |
| slot 6 | 8590.4 | 6439.9 | −2150.5 | −25.0 % |
| slot 9 | 8590.4 | 5598.8 | −2991.6 | −34.8 % |
| slot 12 | 8590.4 | 5124.6 | −3465.8 | **−40.3 %** |
| **league** | 103084.8 | 80298.3 | −22786.5 | **−22.1 %** |

**Badge movement: 50 of 96 picks (52 %).** Composition: 6 of the twelve 2026 firsts (the 1.01 up, the 1.08–1.12 down); 8 of the 2026 seconds; all 12 2026 thirds; all 12 2026 fourths; all 12 **2028 firsts** (`first_1` → `second`). Every 2027 pick and the 2026 1.02–1.07 keep their badge.

**Read the league row honestly: this is DEFLATION at the aggregate, not just dispersion.** The dispersion story is true within 2026 round 1. Across a whole roster the round curve dominates, because it decays future picks hard (a 2028 first: 2117.0 → 1263.0, −40.3 %) where the ladder held every first flat (D-079). Those are the engine's prices as of `3192d13` — this branch does not change them, it stops Power Rankings from disagreeing with them. **A pick-heavy rebuilding team's Power Rankings total will visibly drop at this deploy**, and that is the change working, not failing.

---

## 8. Manual TestFlight checklist (operator)

Backend-only. No client diffs at all, so every check below is "the same screens, different numbers". Runtime proof matters because nothing structural can see a served Power Rankings screen.

1. **Power Rankings — THE HEADLINE.** Open a 12-team league whose 2026 draft order is known. Expect every team's **Draft capital** number to have moved, **monotonically by draft slot**: the team picking 1.01 up (~+12 %), the team picking 1.12 down (~−40 %). *If every team moved by the same %, the slot is not reaching the price and only the round curve landed.*
2. **The same pick, two screens.** Pick one of your own 2026 firsts. Read its value on **League → Picks** and then in a **trade card / calculator**. Expect the **identical number**. *This is Q-026 in one comparison. Before this build a 1.01 read 2117.0 on the list and 4867.1 on the card.*
3. **Badges on the league picks list.** A **1.01 must badge ABOVE a 1.12** — expect `2 firsts` vs `2nd`-ish chips, not two identical `1st` chips. *Catches the tier being computed from the stored value while the number shown comes from the waterfall.*
4. **Label and price agree.** The pick reading ~4867 must be labelled **"2026 1.01"**, not "2026 1st". *One `slot_for` result drives both; two resolutions would look plausible on each screen alone.*
5. **A future pick, on the list.** A 2028 first should read ~**1263.0** and badge **2nd**, with a generic "2028 1st" label. *This is the biggest single mover and the one most likely to be reported as a bug — it is correct: DP's curve decays firsts, the old flat-firsts ladder was D-079's, and it is now only step 3.*
6. **A league with no published draft order** (or an unsupported platform, e.g. MFL). Every 2026 first there should read the **same 1859.5** and label generically, on the list AND on cards. *Step 2, the fallback contract — the thing most likely to break silently.*
7. **Eveners.** Open an uneven trade in the calculator where the sweetener suggestion is a **pick**. Its value should match what that pick costs everywhere else. *Catches S4, which was genuinely wrong before this build.*
8. **Team-value history / Wrapped.** If you look at a team-value trend chart, expect a **step at 2026-08-21**. *Expected and recorded (§7.4) — an append-only boundary, not corrupted history. Nothing before that date was rewritten.*
9. **Known divergence, confirm don't report — non-12-team leagues only.** In a 10-team league the Draft Room board's slot price and the trade card's price for a **late first** will differ (~820 vs ~1070). *Waiver 2 / Q-027, awaiting your call.*
10. **Known non-alignment, confirm don't report.** The contend/rebuild inference still weights all firsts equally. *Waiver 3, awaiting your call.*

**If this looks wrong in the field**, the fastest lever is flipping `picks.slot_labels` off: every pick everywhere drops to the round curve without a deploy (§6 waiver 1). Reverting to the stored ladder entirely is revert-and-redeploy.

---

## 9. Definition of done

- [x] Every league surface that displays or aggregates an owned pick's value calls one seam.
- [x] The seam is the engine's, verified structurally in both directions and sabotage-tested.
- [x] Golden set run in isolation first, zero edits, twice.
- [x] Full suite green; every moved fixture re-derived, no tolerance widened.
- [x] Sweep complete: every `pool_value` / pick-value reader aligned or dispositioned in §7.6.
- [x] The ADR-011 boundary named and proven to be append-only.
- [ ] **Operator ratification of waivers 1, 2 and 3.**
- [ ] **`tsc --noEmit` confirmed on the pushed sha** (not runnable in this worktree; zero client diffs).
