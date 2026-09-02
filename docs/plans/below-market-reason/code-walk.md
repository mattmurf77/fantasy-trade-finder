# Code-walk proof — below-market card reason (`reason_below_market_frac`)

**Date:** 2026-09-02 · **Branch:** `claude/below-market-reason` (forked from `origin/main` @ `02d2eac2`, rebased onto `e16bb487` — the intervening commits touch neither the engine nor the serializer; see results.md § Suite) · **Scope:** [scope.md](scope.md) · **Measurement:** [results.md](results.md)

Line numbers are the branch tip's `backend/trade_service.py` unless another file is named. Every claim below is either a cited line or a test in `backend/tests/test_below_market_reason.py` (named in brackets).

## 1. The knob is read at CALL time, through `_c`, inside the per-member loop

| Step | Where | What |
|---|---|---|
| declared | `trade_service.py:574` | `"reason_below_market_frac": 0.0` in `_DEFAULT_CFG`, the block directly after `need_fit_weight` (`:559`) — deliberately NOT next to `sweetener_gap_threshold` (`:516`), where a sibling builder is concurrently adding two sweetener knobs |
| seeded | `backend/database.py:2436` | the row after `need_fit_weight` in `_MODEL_CONFIG_DEFAULTS`; the boot migration inserts every tuple `ON CONFLICT DO NOTHING`, and `database.set_config` raises for a key with no row, so without this seed `PUT /api/admin/config/reason_below_market_frac` would 404. [`test_default_registered_in_both_stores_at_the_identity`] |
| read | `trade_service.py:6527` | `_bm_frac = _c("reason_below_market_frac")` — once per league-mate, inside the `for idx, member in enumerate(eligible)` loop of `_generate_trades_v2`, executed on every job, never at import, never via `_ts._cfg.get` (D-098 / G-058 cause 3) |
| `_c` honours the overlay | `trade_service.py:1256-1262` | `_cfg_local.map` first, then `_cfg`, then `_DEFAULT_CFG` — so a `_cfg_override` on the calling thread shadows the process-global row. [`test_knob_is_read_at_call_time_through_the_overlay`]: a global 0.15 under `_cfg_override({knob: 0.0})` stamps nothing, and the reverse stamps |

## 2. The stamping site, and its place in the per-member stack

```
6283  cards = generate_pair_trades_v3(...)            # boarded partner, v3 on   (prod)
6311  cards = self._generate_for_pair_v2(...)         # boarded partner, v3 off
6348  cards = self._generate_consensus_for_pair(...)  # boarded partner, zero divergence cards (fallback)
6350  cards = self._generate_consensus_for_pair(...)  # never-ranked partner
      ... FB-47 partner fit · FB-96 need fit · FB-147 block boost · #175 outlook direction ·
      ... D-060 lane shift · lanes · aggression A/B · negmem      (every multiplier / label)
6527  _bm_frac = _c("reason_below_market_frac")
6528  if _bm_frac > 0:
6529      for c in cards:
6530          _bm = below_market_reason(c.give_player_ids, seed_elo, shrunk_elo,
6532                                    self._players, _bm_frac)
6533          if _bm:
6534              c.reasons.append(_bm)
6536  for c in cards:
6537      c.match_context = match_ctx
6538      c.narrative = build_narrative(c, match_ctx, self._players)
6539  new_cards.extend(cards)
```

* **After every gate and every multiplier.** The stamp is the last card-level step before `match_context` / `narrative`, after the negmem seam (`:6507-6516`), which the negmem comment already documents as "LAST in the per-member multiplier stack". It writes exactly one attribute, `reasons`, and reads none that any later step consumes: `_dedup_and_sort` (`:6559`) keys on ids and sorts on `composite_score`; the C4/C4b caps key on ids and the seed map; `_filter_by_trade_intent` (`:4537`, called at `:4888`) reads ids/positions; the #189 relaxed pass re-runs `_generate_trades_v2` with the same kwargs and stamps `relaxed` afterwards. Nothing downstream can observe the line except the serializer.
* **Ordering relative to the A8 reasons.** The three A8 adjustment reasons (`qb_tax_adjustment` `:4099`, appends at `:4146` / `:4154`; `star_tax_adjustment` `:4160`, append at `:4253`; `roster_clogger_adjustment` `:4259`, appends at `:4307` / `:4311`) are appended ONLY inside the legacy `_generate_for_pair` (`:7898-7908`, the `trade_engine.v2`-OFF path; `:7935` gates the list on the flag). No v2/v3/consensus generator calls them, and their three flags are false in prod (`config/features.json:25-27`). So on every prod card `reasons` is `[]` when the stamp runs and the line is its **only** element — there is no ordering question in prod, and no cap to fall behind (§4). On the legacy path the stamp never runs (§3), so a legacy card can carry A8 reasons and never this one.
* **The shrunk board is the one the engine prices with.** `shrunk_elo` is computed once per job at `:6069` (`_shrink_user_elo(user_elo, seed_elo, confidence, placements)`) and is the same object handed to `generate_pair_trades_v3` (`:6285`), `_generate_for_pair_v2` (`:6313`) and `_generate_consensus_for_pair` (`shrunk_user_elo` in `_consensus_kw`, `:6255`). The stamp reads it, not `user_elo` (raw). Sabotage S1 (results.md) swaps in `user_elo` and [`test_zero_comparisons_never_fires`] goes red: with `confidence = {}` every weight is 0, `_shrink_user_elo` returns the seed (`:1796-1804`), and a raw 23% gap must be invisible.

## 3. The helper, and why the knob-0 identity is structural

```
2016  BELOW_MARKET_REASON = ("You rank {name} below the market — that gap is what this trade cashes in.")
2021  def below_market_reason(give_ids, seed_elo, shrunk_user_elo, players, frac):
2043      if frac is None or frac <= 0: return None          # ← knob 0: no lookup at all
2045      head = deck_give_headliner(give_ids, seed_elo, players)
2048      p = players.get(head) ...; if p is None or is_pick_asset(p): return None
2051      seed_v = elo_to_value(seed_elo.get(head, 1500.0))
2054      user_e = shrunk_user_elo.get(head); if user_e is None: return None
2057      if (seed_v - user_v) / seed_v < frac: return None
2059      name = getattr(p, "name", None)
2061      if not name: return None
2063      return BELOW_MARKET_REASON.format(name=name)
```

* **Knob 0.** The loop at `:6528` is guarded by `if _bm_frac > 0`, and the helper's first line returns `None` for `frac <= 0` anyway. At the default no card object is touched, no `reasons` list is appended to, and the serializer — which emits `reasons` only when the list is non-empty (`server.py:11886-11887`) — produces the same bytes as before. Proof: [`test_wire_at_knob_zero_is_byte_identical_to_origin_main`] — the FULL `generate_trades` deck on the engine-quality fixture, through `trade_card_to_dict`, flag ON, captured on a `git archive origin/main` (`02d2eac2`) tree (8 cards, sha256 `8ad11872…` of the captured line; the branch capture `cmp`'d byte-identical). [`test_the_wire_golden_is_not_vacuous`] shows the same fixture DOES move at 0.15.
* **Headliner = C4b's headliner.** `deck_give_headliner` (`:1948-1980`): give side only, players outrank picks, deterministic id tie-break — so the player the line names is the one `cap_give_headliners` (`:1983`, the `deck_give_headliner_cap` = 3 live cap) keys on. Two consequences the tests pin: a pick that out-seeds the player still does not headline ([`test_a_pick_never_headlines_a_mixed_give_side`]) and a picks-only give side returns a pick, which `is_pick_asset` rejects ([`test_picks_only_give_side_is_silent`]). **Headliner only:** a below-market second give-side player does not fire ([`test_second_give_player_below_market_but_not_headliner_is_silent`]) — the line explains the ask the user feels, not every piece; sabotage S2 (`any(...)` over the give side) turns that test red.
* **Value space.** Both sides through `elo_to_value` (`value = 1000·e^{0.005(elo−1500)}`), so `frac` is a fraction of consensus VALUE and a fixed fraction is a fixed Elo distance: `Δelo = ln(1/(1−frac)) / 0.005` → 0.10 ≈ 21 Elo, **0.15 ≈ 32.5 Elo**, 0.25 ≈ 57.5 Elo below seed *after shrinkage*. Consensus here is the raw seed, NOT the age-preference-adjusted `_vs` (`:6089-6099`): the user's board is blended toward the raw seed (`:1799`), so raw seed is the apples-to-apples "market" for it; `_vs`'s ±10% age multipliers are a deck-side preference, not a market price, and mixing them in would make a 30-year-old at consensus read as "below market" by construction.
* **No name → no line** (`:2059-2062`), never a placeholder ([`test_missing_name_yields_no_reason_not_a_placeholder`]). Prod players are `ranking_service.Player` with a required `name` (`ranking_service.py:254-257`); `trade_narrative.py:17` reads the same attribute.

## 4. Every generation path that reaches the stamp, and whether each carries a user board

`git grep -n "_generate_trades_v2(" -- backend` (non-test): exactly two callers, `_generate_trades_impl` (`:4875`, the `trade_engine.v2` branch — prod) and `_relaxed_targeted_pass` (`:5138`, #189, via `_cfg_override` of gate knobs only — the knob is not overridden, so the relaxed re-run stamps with the same `frac`). Inside `_generate_trades_v2` every card flows through the per-member loop (§2), so:

| Path | Where the cards come from | Reaches the stamp? | User board at the stamp |
|---|---|---|---|
| v3 divergence (prod: `trade_engine.v3` true, boarded partner) | `generate_pair_trades_v3` (`:6283`) | **yes** | `shrunk_elo` (`:6069`) — the same map the optimizer prices with |
| v2 divergence (`trade_engine.v3` off) | `_generate_for_pair_v2` (`:6311`) | **yes** | same |
| consensus, never-ranked partner (84.5% of served cards) | `_generate_consensus_for_pair` (`:6350`) | **yes** | same — the consensus generator receives `shrunk_user_elo` (`:6255`) for its tier multiplier; the stamp uses it for the gap. The partner has no board; the USER may, and that is what the line is about |
| consensus, boarded partner with zero divergence cards (`trade.trade_divergence_fallback`) | `:6348` | **yes** | same |
| #189 relaxed re-run | `_relaxed_targeted_pass` → `_generate_trades_v2` (`:5138`) | **yes** (then `relaxed = True` stamped on top) | same |
| **legacy v1** (`trade_engine.v2` OFF — dark in prod) | `_generate_for_pair` (`:7492`), loop at `:4926-4948` | **no** — the stamp lives in `_generate_trades_v2` only; the legacy loop has no shrunk board (it prices the raw `user_elo`) and carries the A8 reasons instead | n/a |
| **arm A** (bake-off `baseline`) | `bakeoff_runner.py:1538` `with model_a(): generate(...)` → `generate_trades` → `_generate_trades_v2` | **yes** — the knob is EXCLUDED from `MODEL_A_PROFILE`, so arm A inherits the live row (scope.md §2; `_PINNED_KNOBS` comment) | same |
| **arm B** (`current`) | no overlay | **yes** | same |
| **arm D** (`challenger`) | `bakeoff_runner.py:1550` `with model_challenger():` | **yes** — inherits the live row (D-095: the live engine under an overlay; `user_elo_shrink` may be 0 there, in which case `_shrink_user_elo` returns the RAW board (`:1791-1792`) and the line measures the raw gap on arm D — consistent with what that arm prices with) | shrunk or raw per the arm's `user_elo_shrink` |
| **arm C** (`gen_v2`) | `bakeoff_runner.py:1156` `gen_v2_cards` → `trade_gen_v2.generate_league_suggestions` called DIRECTLY; builds its own `TradeCard`s (`trade_gen_v2.py:1192`) and never enters `_generate_trades_v2` | **no** | it computes its own shrunk board (`trade_gen_v2.py:1074`) but nothing stamps `reasons` there |
| **arm `fit`** | `bakeoff_runner.py:1342` `trade_gen_fit.generate_league_suggestions` DIRECTLY; own cards (`trade_gen_fit.py:461`) | **no** | n/a |
| likes-you injection, standing offers, client-echo rebuilds | `server.py:3535`, `:3650`, `:12676` construct `TradeCard`s outside any generator | **no** — those cards are not generated by the engine and carry no `reasons` | n/a |

So on the served arms A/B/D every card can carry the line; on C and `fit` none can (scope.md §2 records the presentation asymmetry for the D-099 log). [`test_reason_is_stamped_on_both_bases`] covers divergence + consensus through the real generator; [`test_deck_is_invariant_at_every_knob_value_on_100_random_leagues`] runs under the live flag set (v3 on, presentment rules, need fit, lanes, …) with random boarded/unboarded partners so every prod path in the table is exercised.

**User with no board (`ranked_player_count == 0`).** The job thread passes `confidence = service.comparison_counts()` (`server.py:6053`), a dict that is EMPTY (not `None`) for a user who has never compared, and `user_elo = elo_map_rt` (`server.py:5903`) from the ranking service, where an un-compared player sits at his seed. Either way the stamp sees `shrunk == seed`: `_shrink_user_elo` with every `n = 0` returns the seed (`:1799-1804`), so `(seed_v − user_v) / seed_v = 0 < frac` and nothing fires. [`test_zero_comparisons_never_fires`] asserts it through the real generator with a RAW 23% gap that shrinkage must erase. (`confidence=None` — a test-only shape; the job thread never passes it — returns the raw board, `:1791-1792`; the line would then measure the raw gap, which is still the board those tests price with.)

## 5. The flag gate on the wire, and the corpus

```
server.py
11886  reasons = getattr(card, "reasons", None)
11887  if reasons:
11888      try:
11889          from .feature_flags import FLAGS as _FLAGS
11890          if _FLAGS.trade_math_human_explanations:
11891              out["reasons"] = list(reasons)
```

* `trade_math.human_explanations` is **true** in prod (`config/features.json:28`). With it on, a non-empty `reasons` becomes the `reasons` key; with it off no card ever carries the key, at any knob value — [`test_wire_flag_off_never_carries_the_reason`] (the in-process stamp still happens; the gate is the serializer's). Sabotage S3 drops the `if _FLAGS...` line and that test goes red. This is the second deploy-free kill switch (`POST /api/feature-flags/reload`).
* **The deck-outcome corpus does NOT carry `reasons`.** `_log_deck_signal_impressions` (`server.py:4378`) builds `features` at `:4498-4529` from named keys — `shape, basis, likes_you, lane, give_positions, receive_positions, give_value, receive_value, …, need_fit, partner_fit, fit_premium, aggression_variant, relaxed, gap_sweetener, ranked_player_count, last_board_update_at, user_value_basis` — and `reasons` is not among them. Consequence (scope.md §1): the flip's effect is measurable only via like/pass on cards whose give headliner is below the user's market, re-derived from the logged give ids + the user's rankings, split by `user_value_basis == "personal"`. A `"below_market_reason": bool` key in that dict is the one-line follow-up if the lead wants the split cheap; it touches the analytics surface and is not in this change.

## 6. The two render sites — cap, truncation, ordering, testID

| Client | Where | Gate | Cap / truncation | Order | testID |
|---|---|---|---|---|---|
| mobile | `mobile/src/api/trades.ts:171` normalizes `raw.reasons` → `reasons?: string[]`; `mobile/src/components/TradeCard.tsx:323-325` `showReasons = reasonsEnabled && Array.isArray(data.reasons) && data.reasons.length > 0`; render `:955-961` | the `trade_math.human_explanations` flag read client-side (`reasonsEnabled`) AND a non-empty list | **none** — `data.reasons!.map((r, i) => <Text key style={type.bodySm}>• {r}</Text>)` renders EVERY string, one `Text` per reason, no `slice`, no `numberOfLines`, no `ellipsizeMode`; the container `styles.reasons` (`:1175-1185`) is a bordered box with `gap: space.xs`, no fixed height | server order (the only line in prod, §2) | none on the reasons block (pre-existing; no testID added or renamed — testid-lint untouched) |
| web | `web/js/app.js:3676-3684` | `window.FTF_FLAG('trade_math.human_explanations')` AND a non-empty array | **none** — `card.reasons.map(r => <li class="trade-reasons-item">${escapeHtml(r)}</li>)`, every item, HTML-escaped | server order | n/a (web) |

**Line length on mobile.** The copy is 80 chars with "Davante Adams" (`test_copy_is_one_short_line` pins ≤ 90 for three representative names). `type.bodySm` inside a card-width box wraps at the container width like any `Text` — a long name wraps to a second visual line *inside the same tile*; it cannot spill into a second tile because there is one `Text` per reason and one reason per card. No wrapping-into-a-second-tile risk exists; no truncation risk exists (no `numberOfLines`). The `• ` bullet prefix is the renderer's, not the copy's — the wire string has none, so the web `<li>` does not double-bullet.

## 7. Not proven here, for the lead

* **No prod board replay.** The harness boards are synthetic (hash offsets); the share-of-cards numbers in results.md bound how often the line fires under two board models, not how often it fires on mattmurf77's board. The prod verification in results.md § After the flip is the runtime check: read the operator's deck in league `1312140920132497408` after the PUT and confirm the Adams-give cards carry the line. The local `data/trade_finder.db` is outside this worktree, so the branch could not calibrate against the operator's actual shrunk gap on Adams.
* **The corpus does not carry the line** (§5). If the lead wants the like-rate split to be a `features_json` query, the one-line follow-up is stated there.
* **Arm C / `fit` asymmetry** (§4) — presentation only, logged with the flip if either is serving.
