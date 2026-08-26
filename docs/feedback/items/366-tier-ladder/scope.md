# Feature Scope — #366 position-relative tier bands + the RB Handcuff tag

**Date:** 2026-08-20
**Entry point:** feedback #366 (operator `mattmurf77`, screen TeamReview)
**Builder:** agent worktree `worktree-agent-a4ab94c51456abb78`
**Operator sign-off on waivers:** not needed (no waivers)

> *"Need one other layer for the startable bodies: Elite, Starter, Replacement. For just RB we
> also should have 'Handcuff' which should simply be the RB2 on every team. And would like to
> review the logic for tagging a player as 'elite'."*

---

## 0. What the report is actually asking, and what the diagnosis found

Three asks, and they turned out to be three different sizes.

**Ask 1 — "review the logic for tagging a player as elite."** Confirmed defect.
`_bin_player` (`backend/trade_service.py:1906` on `origin/main`) is three **absolute,
position-blind** cuts on `dynasty_value`: elite ≥ 4000, starter ≥ 1500, bench ≥ 500. Because
`dynasty_value(p) = ktc_max · e^(−ktc_k·(search_rank−1))` with `ktc_k = 0.0126`,
`ktc_max = 10000` (`trade_service.py:1063`, `:53-55`), those three numbers are a disguised cut
on **Sleeper's OVERALL `search_rank`**: elite = overall ≤ 73, starter = overall ≤ 151,
bench = overall ≤ 238. Applied to the live pool (`data/trade_finder.db`, 2 684 players):

| pos | elite | starter | bench | none |
|---|---|---|---|---|
| QB | 17 | 10 | 11 | 292 |
| RB | 33 | 26 | 20 | 524 |
| WR | 33 | 29 | 38 | 1 094 |
| TE | **7** | 23 | 5 | 522 |

33 "elite" RBs against 7 "elite" TEs. In a 12-team league an "elite RB" is roughly the
third-best RB on an average roster while an "elite TE" is a genuine top-6 asset. One word,
four meanings. That is the defect.

**Ask 2 — Elite / Starter / Replacement as the visible layer.** The third bin already exists
(`bench`); it is simply never rendered — `TeamReviewScreen`'s `Depth` prints
`{elite} elite · {starter} starter` and drops the rest. So this half is a rename plus a render,
not new computation.

**Ask 3 — the RB Handcuff tag.** `plan-remaining.md` §2 assumed *"Handcuff needs a source FTF
does not have… No current feed carries it"* and recommended not building it.
**That assumption is false and the plan doc is wrong.** FTF already ingests Sleeper's depth
chart, end to end:

| Stage | Evidence |
|---|---|
| Schema | `backend/database.py:970-971` — `depth_chart_position` (String), `depth_chart_order` (Integer, *"1=starter, 2=backup"*) |
| Ingestion | `backend/database.py:8726` coerces `depth_chart_order` to int; `:8769-8770` writes both columns on every `sync_players` |
| Refresh | `needs_player_sync` (`database.py:8652`) — re-synced whenever `last_synced` is older than **24 h** |
| Model | `backend/ranking_service.py:262-263` — `Player.depth_chart_position` / `.depth_chart_order` |
| Hydration | `backend/server.py:1580-1581` — `build_universal_pool` copies both onto every pooled `Player` that has a DB row |
| Reaches this function | the `players` dict `analyze_roster_strengths` receives is that same pool (`server.py:22815` `players_meta`, `trade_service.py:3169` `self._players`) |

Live-data check against `data/trade_finder.db`: 149 of 603 RB rows carry a non-null
`depth_chart_order`, and they are exactly the 32 real NFL depth charts — ARI Conner 1 /
Benson 2 / Allgeier 3, ATL Bijan 1 / Robinson 2, BAL Henry 1 / Hill 2, BUF Cook 1 / Davis 2,
and so on. The 454 nulls are camp bodies and free agents, which is correct: they are on no
depth chart, so they are not anybody's handcuff. `depth_chart_position` for RBs is the literal
string `"RB"` (WRs split into `LWR`/`RWR`/`SWR`).

So **Handcuff is built on the real depth chart**, exactly as the operator described it —
`position == RB` ∧ `depth_chart_position == "RB"` ∧ `depth_chart_order == 2`. No approximation,
no new dependency, no new fetch. Staleness characteristics are stated in §2 and on the card.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** nothing new is *interacted* with. The depth
  beat's two existing actions (`Chase` / `Shop` chips → `positions_set`) are untouched, and the
  beat already emits its `beat`-scoped view event under the shipped Team Review taxonomy. This
  change alters the **numbers printed inside a beat the user already sees** and adds one
  read-only line; there is no new tap target, no new screen, and no new funnel step. Adding an
  event here would measure a render, not an intent — and `analytics_queries.NON_INTENT_EVENTS`
  exists precisely to keep those out of the intent funnels.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** `players.depth_chart_position` /
  `.depth_chart_order` already exist and are already populated — this feature is the first
  *reader*, not a new writer. `docs/data-dictionary.md` needs no edit for the same reason.
- **New/changed feature flags:** two, both **default OFF**, registered in
  `backend/feature_flags.py` `FLAG_KEYS` and listed in `config/features.json`.

  | Flag | Default | What ON does | What OFF guarantees |
  |---|---|---|---|
  | `trade.position_tiers` | **false** | `analyze_roster_strengths` bins by **positional rank** instead of absolute value, and emits `replacement` alongside `bench` | `_bin_player`'s three absolute cuts run unchanged; the profile dict is **byte-identical to `origin/main`** — pinned by `test_flag_off_is_byte_identical_to_legacy` |
  | `trade.rb_handcuff` | **false** | the profile gains `handcuff_rb` (int) and the Team Review depth payload gains `handcuff_rb` | the key is **absent entirely** (never `0`, never `null`); no `depth_chart_*` attribute is read |

  **The two are independent kill switches on purpose.** `trade.position_tiers` changes
  `position_needs` / `position_surplus`, which `trade_gen_v2` (`:930`, `:980`) and
  `trade_service` (`:3413`, `:3440`, `:4096`, `:4172`, `:4259`) consume — **it changes every
  deck for every user.** `trade.rb_handcuff` is purely additive: one extra integer on one
  payload, read by nothing in the engine. Tying them together would mean a deck regression
  could only be rolled back by also taking down a harmless label.

  **Graduation criterion (NOT taken in this change — the flags ship dark):**
  `trade.position_tiers` graduates only after a deck-quality read on real leagues comparing
  `position_needs` / `position_surplus` before and after (`scripts/deck_eval.py` is the
  existing harness), because a need that flips from present to absent silently re-ranks a
  deck. `trade.rb_handcuff` graduates on operator eyeball of one TestFlight pass.

  **Deploy-free rollback lever:** edit the value in `config/features.json` and
  `POST /api/feature-flags/reload`. No redeploy, no client release — both flags are read at
  call time (`feature_flags.is_enabled`, whose cache `reload()` drops), and the mobile client
  renders the handcuff line only when the key is present in the payload, so flipping the
  backend flag off removes the line from the next fetch without shipping a build.
- **New env vars / `model_config` keys:** **none** — deliberately. The band cuts are module
  constants, not `model_config` rows, for the reason `backend/pick_values.py` states about
  `GENERIC_PICK_SEEDS`: a knob that silently re-bins every roster in production is worse than
  a revert. The revert is a flag flip (above), which is already deploy-free.

### Why positional rank rather than per-position value thresholds

Two candidate designs, and the second was rejected on evidence.

1. **Positional rank inside the pool (chosen).** A player's band is his rank *among players at
   his own position*, so "elite QB" and "elite TE" mean the same thing by construction, and no
   constant has to be recalibrated when the value curve moves.
2. **Per-position `dynasty_value` cuts (rejected).** Simpler and O(1), but the cuts would have
   to be derived once from a pool snapshot and hardcoded — and the snapshot lies. Deriving
   them from `data/trade_finder.db` put **Tom Brady at QB18 and Derek Carr at QB32**: retired
   players carrying stale `search_rank`s. Baking that into constants ships the noise
   permanently. It also inherits the failure mode the report gestures at — a `ktc_k` /
   `ktc_max` retune moves every threshold at once, and #117 already did exactly that once
   (`docs/runbook.md:441`: *"`_TIER_ELITE`/`_TIER_STARTER` value bins … now bind at
   market-sane depths"*). Rank cuts are immune to both.

   *Correction to `plan-remaining.md` §2:* it attributes the drift to **board-wide value
   inflation**. That is not the mechanism. `dynasty_value` is a pure monotone function of
   Sleeper's `search_rank`, an ordinal — it cannot inflate. The real drift vector is a
   `model_config` retune of `ktc_k`/`ktc_max`. Same conclusion, different cause, and it
   matters because it means the fix has to leave value space, not just subdivide it.

**The bands.** Cuts are stated in positional rank and derived from what a league actually
starts (1 QB, 2 RB, 2 WR, 1 TE; superflex starts 2 QB):

| Band | Definition | QB (1QB) | RB / WR / QB (SF) | TE |
|---|---|---|---|---|
| Elite | top **half** of the league's starting demand at the position — a genuine positional edge | ≤ 6 | ≤ 12 | ≤ 6 |
| Starter | inside **1.5×** the starting demand — a real startable body | ≤ 18 | ≤ 36 | ≤ 18 |
| Replacement | inside **2.5×** — above the waiver pool, below a starter | ≤ 32 | ≤ 60 | ≤ 32 |

(12-team league assumed; `analyze_roster_strengths` is not passed league size and this change
does not add a parameter to a signature six call sites depend on.)

**The small-pool guard, stated rather than hidden.** Positional rank is only meaningful over a
real pool. When fewer than `_POS_TIER_MIN_POOL = 40` players at a position carry a
`search_rank`, the position falls back to the legacy absolute cuts — this is what hand-built
test fixtures and synthetic demo sessions hit. The mode is **reported, not silent**: the
profile carries `tier_basis: "position_relative" | "absolute"`, so nothing has to infer which
path ran. Real Sleeper pools carry 313 QB / 568 RB / 1 134 WR / 516 TE, so production always
takes the relative path.

**Cost.** Building the positional-rank map over the real 2 684-player pool measures **1.31 ms**
(50 iterations, `python3` on the operator's machine). It is memoized on the identity of the
`players` dict — 2 slots, strong references so an `id()` cannot be recycled under the cache —
so the engine's per-member loops (13 calls per deck run) pay it once, not thirteen times.

### Handcuff staleness — the honest characteristics

- **Refresh:** the whole `players` table re-syncs when `last_synced` is older than 24 h
  (`database.py:8652`). So a depth chart is at worst ~24 h stale, and in-season it churns
  faster than that — a Wednesday injury can make Tuesday's RB2 the RB1.
- **Coverage:** only players Sleeper places on a chart have an order at all (149/603 RBs
  today). Everyone else is simply not tagged, which is the correct answer, not a gap.
- **What it is NOT:** it is Sleeper's depth chart, not a committee-usage model. In a true
  committee the `order == 2` back may be a co-starter rather than a handcuff. The tag is
  therefore rendered as *"RB2 on his NFL depth chart"* — the fact, in the words of the source —
  and never as a value or usage claim. This is the whole reason the approximation
  `plan-remaining.md` warned about ("second-highest-valued RB on the same NFL team") was not
  needed: the real field is right there, and it is the field the operator named.
- **Not a tier.** Handcuff is an **overlay**, not a fourth bin: an RB2 is *also* Elite, Starter
  or Replacement. It is therefore reported as a separate top-level `handcuff_rb` count and is
  deliberately **not** added as a key inside `tier_depth[pos]`, whose contract
  (`trade_service.py` docstring) is a disjoint partition. A non-disjoint key inside a bins dict
  is the kind of trap that gets summed by accident two quarters from now.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-team-review-depth.js` (new, dependency-free,
      `npm run test:team-review-depth`) — pins, and each was sabotage-proven:
      1. the `Depth` component reads `replacement ?? bench`, never `bench` alone, so a backend
         on the new key does not silently render a hole;
      2. `TeamReviewDepth.tier_depth`'s value type declares `replacement` **optional**, so a
         client on this build still parses an old (flag-off) payload;
      3. `handcuff_rb` is rendered behind a presence check, never `?? 0` — an absent key must
         print nothing, not "0 handcuffs";
      4. the depth beat renders a `Replacement` label — the report's word — and no longer
         renders the word `bench` to the user;
      5. no new color literal is introduced (Chalkline: ice/flare only; tier hexes are governed
         by `docs/cross-client-invariants.md`).
- [x] **Unit tests:** `backend/tests/test_position_tiers.py` (new, 21 tests) —
      flag-off byte-identity against a frozen `origin/main` expectation, the position-relative
      bands at every boundary, the superflex QB widening, the small-pool fallback and its
      `tier_basis` report, handcuff detection incl. every negative case
      (`order != 2`, null order, `depth_chart_position` mismatch, non-RB, flag off), and the
      engine-facing invariant that `position_needs` / `position_surplus` are unchanged when
      the flag is off. `backend/tests/test_team_review.py` gains 2 tests for the payload keys.
- [x] **Code-walk proof:** `docs/feedback/items/366-tier-ladder/code-walk.md` — file:line trace
      from the Sleeper dump to the rendered line, for both flags, in both states.
- [x] **Measured coverage gap — a graduation blocker, found while building.** The
      pre-existing engine-facing suite (`test_roster_profile`, `test_need_fit`,
      `test_finder_targeting`, `test_presentment_rules` — 65 tests) is **completely
      insensitive** to this change: forcing `relative = True` in source leaves all 65 green.
      The cause was confirmed, not guessed — disabling `_POS_TIER_MIN_POOL` *as well* turns
      exactly 1 of the 65 red, so every one of those fixtures is smaller than the guard and
      cannot distinguish the bands even in principle. Those tests are therefore evidence for
      the flag-**off** path only. **`trade.position_tiers` must not graduate on a green
      suite** — it needs a deck-quality read on real leagues (`scripts/deck_eval.py`) plus
      step 6 of the TestFlight checklist. Recorded here rather than quietly fixed because
      widening those fixtures to production scale is its own change with its own blast
      radius, and it belongs to whoever graduates the flag.
- [x] **Manual TestFlight checklist:** `docs/feedback/items/366-tier-ladder/testflight-checklist.md`
      — 6 numbered steps. Runtime proof matters here because the flag-on path changes numbers
      the operator will read as truth, and one step deliberately verifies a *known* roster
      (his own RBs against nfl.com's depth chart) rather than just that something rendered.
- `testID`s added/renamed: `team-review.depth.handcuff` (new). No renames — renaming an
  existing beat testID would trip `check-team-review.js` assertion 4.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `GET /api/league/team-review` — the `depth` object's `tier_depth` value shape (`replacement` alias) and the conditional `handcuff_rb` key, both flag-scoped |
| `living-memory/LLD.md` | **n/a** | no convention shifted. Flag-gated additive payload keys, one existing pure function extended; the "clients read an encoding, never recompute one" rule this surface already follows is *reinforced* (the client reads `tier_basis` and `handcuff_rb`, it derives neither) |
| `docs/architecture.md` | **n/a** | no module wiring change. `analyze_roster_strengths` keeps its signature and its callers; no new module, no new data source — the depth-chart columns were already ingested and hydrated |
| `living-memory/HLD.md` | **n/a** | no architecture shift for the same reason |
| `docs/cross-client-invariants.md` | **updated** | the note that `tier_depth`'s bins are a backend-internal taxonomy now names the `bench` → `replacement` wire alias, the flag that produces it, the positional-rank band table, and `handcuff_rb` — so a future client cannot re-derive either |
| `docs/glossary.md` | **n/a** | "Handcuff" and "Replacement" are rendered as plain-English phrases on one card, not adopted as codebase-wide domain terms. `tier_basis` is an internal enum, documented where it lives (cross-client-invariants) |
| `DECISIONS.md` entry | **updated** | **D-120** (bands leave value space for rank space) and **D-121** (Handcuff is built on the real depth chart, overturning `plan-remaining.md` §2) |

## 5. Ship gate declaration

- **CI green on this branch:** `python3 -m pytest backend/tests -q`, `tsc --noEmit`, every
  `mobile/tests/check-*.js`, `mobile/scripts/testid-lint.sh` — results table in
  `living-memory/TEST_LEDGER.md`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-08-20 entry, including the
  sabotage table (every new guard reverted, confirmed red, restored, re-run green, with
  `__pycache__` cleared between cycles and restoration verified by `git diff` rather than by a
  test result).
- **TestFlight verification:** checklist written (§3) and **not yet run** — it is the
  operator's, and both flags are OFF, so nothing reaches a build until they are lit.
- **Express lane declared by the operator?** **No.** Full gates. This change touches
  feature-flag surface and an API payload — the CLAUDE.md bright line — so express would not
  have been available for the asking anyway.
- **Not done here, deliberately:** the flags are **not graduated**. Lighting
  `trade.position_tiers` changes every deck and is an operator decision with its own
  deck-quality read, not a builder's.
