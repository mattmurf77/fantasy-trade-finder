# Trade-Logic Interview — 2026-07-17

Matt asked to be interviewed about how he identifies, analyzes, and decides
trades, with the answers folded into the trade engine. Five rounds (20
questions) were completed before he called "start building." This document is
the durable record: every answer, what shipped from it, and the deferred
backlog. A concurrent feedback-batch session was implementing #141–#144 at the
same time; this work builds AROUND its junk-filler gate (`filler_ok`), not
over it.

## Interview record

### Round 1 — how he evaluates a trade
| Question | Answer |
|---|---|
| First thing checked on any trade | **Roster fit** — does the return fill a hole / move a surplus for the specific roster |
| Consensus vs own opinions | **Split by purpose** — his board decides what he WANTS; consensus decides what the other side will ACCEPT |
| Is divergence-hunting (the engine's core premise) how he trades? | **Partly** — divergence matters, but needs/fit and timeline mismatches are equally the trigger |
| Reaction to current cards | **Right idea, off** — right players/partners, packages/amounts off |

### Round 2 — what's wrong with today's cards
| Question | Answer |
|---|---|
| How are packages off? | **Weird throw-ins** — too many near-zero-value players added to both sides, making evaluation harder |
| Suggest need-filling trades that lose a little value? | **Yes, flag it** — show honestly: "you lose a little value but fix your RB hole" |
| Marginal (over-replacement) valuation? | **Depends on position/format** — RB/WR depth is precious in 1QB (small discount); QB/TE depth matters in SF/TEP; depth matters more when actively competing; career length differs by position (RBs short, WR/QB/TE long) |
| Opening-offer aggression | **Test all three** (slightly-light / fair / slightly-generous) to see what's best for the app |

### Round 3 — building the package
| Question | Answer |
|---|---|
| Throw-in rule | **See feedback #141** — threshold of player value to enter a suggested trade, judged on the MAX of the player's value across both users' boards |
| Package shapes that get accepted | **All of**: clean 1-for-1, 2-for-1 consolidation, 1-for-2 spread, player+pick |
| Consolidation premium size | **Depends on the stud** — a true tier-1 asset commands a huge premium; a mid-tier "best player" barely any |
| SF/TEP depth handling | **All of the above**: guard QB depth in SF, TE ≠ QB, and think in startable-slot terms |

### Round 4 — fairness and getting to yes
| Question | Answer |
|---|---|
| Value floor for package pieces | **Both floors** — absolute (rosterable+, no clogger bodies) AND relative (% of the trade's best asset) |
| Consensus ~lopsidedness veto | **Loosen it** — what matters is both boards agreeing; consensus should only veto extreme cases |
| Acceptance psychology | **Their team story** — frame around THEIR window: contenders accept win-now pieces, rebuilders accept youth/picks |
| Star tax (ON at the time) | **Wrong tool** — the consolidation premium already handles tier gaps; a second penalty double-counts |

### Round 5 — reading a roster
| Question | Answer |
|---|---|
| Determining team window | **Infer + confirm** — engine proposes from roster/record, user confirms; the league-summary feature (#142) is already building team labels |
| How strongly window steers targets | **Two lanes** — show "window moves" and "value moves" as separate labeled groups |
| Age in the math | **Age = tiebreak** — age is already priced into market values; don't double-adjust; use for tie-breaking and narratives |
| Positional-need definition | **Bodies vs slots is fine, but keep it a light multiplier** |

## Shipped in this pass

All backend, on branch `trade-engine-v2`; 618 backend tests pass.

1. **Absolute asset floor** (`asset_floor_abs` = 450, value space): every
   non-headliner piece must clear it on the max-of-boards metric, layered
   into `filler_ok` alongside #141's relative `filler_min_frac`.
   `filler_min_frac = 0` remains the master kill-switch.
2. **Star tax OFF, crown-asset premium ON** (`config/features.json`):
   `trade_math.star_tax → false`, `trade.crown_asset → true`. The crown
   premium now scales with the stud's absolute value
   (`crown_elite_value` = 6000: full 12% premium at/above it, linearly less
   below — "depends on the stud").
3. **Position/format-aware bench credit** in `marginal_value`:
   `bench_credit_qb/rb/wr/te` (0.10/0.30/0.30/0.10) with `bench_credit_qb_sf`
   (0.35) and `bench_credit_te_tep` (0.25) overrides. RB/WR depth keeps far
   more of its value in 1QB; QB/TE depth becomes guarded capital in SF/TEP.
4. **Loosened consensus fairness veto for divergence cards**
   (`fairness_floor_divergence` = 0.55): when both members have real boards,
   the effective consensus gate is `min(fairness_threshold, 0.55)` — an
   extreme-case veto only. Consensus-basis cards (unranked opponents) keep
   the full threshold. Applied in both the v2 pair generator and the v3
   optimizer (including the sweetener band).
5. **Age = tiebreak**: `trade.outlook_blend → false` — player values are no
   longer age-curve-adjusted by outlook. Window/age return in phase 2 as
   lane labels and narratives, not value edits.
6. **Lighter need multiplier**: `need_fit_weight` 0.30 → 0.15 (±7.5%
   composite), with an idempotent DB migration for rows still at the old
   default.

Test updates: crown tests re-pinned to the scaled premium (+ new
`test_premium_scales_with_stud_value`); marginal unit test uses the
per-position rate (+ new SF case); four tests that sweep the fairness
threshold now pin `fairness_floor_divergence` so their fixtures keep
exercising their actual subject (range overlap, knife-edge gate, sweetener
rescue, marginal ordering); `flags/release.json` fixture mirrors the flag
flips.

## Phase 2 — shipped 2026-07-17 (same day, second pass)

New flags (all ON in `config/features.json`): `trade.lanes`,
`trade.fit_premium`, `trade.aggression_ab`, plus `trade.outlook_infer` and
`trade.outlook_seed` flipped ON for their new label roles. New
`model_config` keys: `lane_shift_frac` (0.10), `fit_premium_max_loss`
(300), `aggression_weight` (0.20).

1. **Two lanes** — `classify_lane` stamps every card `lane: window|value`
   from the user's declared/seeded window, using the age curves as LABELS
   on consensus values (scoring untouched). Serialized; lane filter pills
   on mobile + web; logged in swipe events.
2. **Window infer + confirm** — `trade.outlook_seed` ON: GET
   /api/league/preferences returns `inferred_outlook` when none declared;
   mobile shows a one-tap confirm banner (Confirm / Change), web pre-selects
   the suggested option with a SUGGESTED tag.
3. **Flagged need-fill value-loss cards** — `fit_premium_1for1` relaxes the
   #108 raw-board gate for a 1-for-1 filling a positional need from a
   non-need spot, loss capped at `fit_premium_max_loss`; card carries
   `fit_premium {value_paid, position}`, an honest narrative lead, and a
   flare "PAYS FOR FIT" badge on both clients.
4. **Aggression A/B** — stable md5 bucket per user (light/fair/generous)
   reweights which acceptable offers lead the deck (consensus-tilt
   direction); `aggression_variant` serialized on cards and joined into
   swipe `user_events` props (with lane + fit_premium) for acceptance-rate
   analysis.
5. **Acceptance framing** — opponent outlook resolution decoupled from the
   value blend (`trade.outlook_infer` = label role only); narratives add
   "They're rebuilding — the youth going back fits their timeline" /
   "They're pushing to win now…" when the give side actually fits.

## Still deferred (phase 3 candidates)

- **Player + pick balancing**: picks as sweetener/balancer assets in the v3
  path (picks aren't roster assets in that code path yet — needs pick
  ownership plumbed into `LeagueMember`).
- **Depth-when-competing**: bench credit scaling with the user's contending
  status. Still deliberately out — keeps outlook fully out of value math.
- **Aggression variants as offer CONTENT** (floor/fair/ceiling versions of
  the same core trade): revisit once the A/B events show which bucket wins.
