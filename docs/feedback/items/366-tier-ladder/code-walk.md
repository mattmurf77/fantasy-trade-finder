# Code-walk proof — #366

**Date:** 2026-08-20 · **Branch:** `worktree-agent-a4ab94c51456abb78`
Line numbers are as of the commit on this branch unless a file is named with
`origin/main`. Under [D-056](../../../../living-memory/DECISIONS.md) this
replaces a simulator capture: it is the trace nobody can run, written out.

---

## 1. The defect, traced rather than asserted

`origin/main`, `backend/trade_service.py:1905`:

```python
def _bin_player(value: float) -> str | None:
    if value >= _TIER_ELITE:      # 4000.0  (:1896)
        return "elite"
    if value >= _TIER_STARTER:    # 1500.0  (:1897)
        return "starter"
    if value >= _TIER_BENCH:      #  500.0  (:1898)
        return "bench"
    return None
```

The argument comes from `dynasty_value` (`:1063`), whose player branch is
`:1105-1109`:

```python
fallback = int(_c("ktc_fallback_rank"))              # 300
rank = getattr(player, "search_rank", None) or fallback
rank = max(int(rank), 1)
return round(ktc_max * math.exp(-ktc_k * (rank - 1)), 1)
```

with `ktc_k = 0.0126`, `ktc_max = 10000.0` (`:53-55`, mirrored in
`database.py:2170-2172`). That function is **strictly monotone decreasing in
`search_rank` and reads nothing else about the player**, so each value
threshold is exactly an overall-rank threshold:

| Threshold | `1 + ln(ktc_max / T) / ktc_k` | Means |
|---|---|---|
| 4000 | 73.7 | overall `search_rank` ≤ 73 |
| 1500 | 151.6 | overall ≤ 151 |
| 500 | 238.8 | overall ≤ 238 |

`search_rank` is Sleeper's **overall** ordering across all positions
(`database.py:978` — *"Sleeper's internal rank proxy"*), so the same cut is
applied to a TE and a RB. Applying the three cuts to every core-position row in
`data/trade_finder.db` (2 684 players):

| pos | elite | starter | bench | none |
|---|---|---|---|---|
| QB | 17 | 10 | 11 | 292 |
| RB | 33 | 26 | 20 | 524 |
| WR | 33 | 29 | 38 | 1 094 |
| TE | **7** | 23 | 5 | 522 |

That is the report, quantified: 33 "elite" RBs against 7 "elite" TEs.

**And the third bin was never shown.** `origin/main`
`mobile/src/screens/TeamReviewScreen.tsx`, inside `Depth`:

```tsx
const t = d.tier_depth[pos] || { elite: 0, starter: 0, bench: 0 };
…
{t.elite || 0} elite · {t.starter || 0} starter
```

`t.bench` is destructured into the default and then never rendered.

---

## 2. Flag OFF — the byte-identity path, line by line

`backend/trade_service.py`, `analyze_roster_strengths`:

1. `relative = is_enabled("trade.position_tiers")` → `False`
   `want_handcuff = is_enabled("trade.rb_handcuff")` → `False`
2. `basis` initialises to `{pos: False}` and the `if relative:` block is
   **skipped entirely** — `_pool_depth_by_position` and
   `_positional_rank_map` are never called, so the pool is never scanned.
3. In the loop, `relative and basis.get(pos)` short-circuits on `relative`, so
   the binning call is `_bin_player(dynasty_value(player))` — the identical
   expression `origin/main` used.
4. `want_handcuff and _is_handcuff(player)` short-circuits on `want_handcuff`,
   so **`_is_handcuff` is never entered and no `depth_chart_*` attribute is
   read**. Proven, not asserted: `test_flag_off_never_touches_the_depth_chart`
   passes a player whose `depth_chart_order` is a property raising
   `RuntimeError` (`getattr(…, default)` swallows only `AttributeError`, so the
   landmine cannot be defused by the default).
5. Needs/surplus arithmetic is unchanged text.
6. `out` is built with exactly the three original keys; both
   `if relative:` and `if want_handcuff:` are false, so neither `tier_basis`,
   nor `replacement`, nor `handcuff_rb` is added.

⇒ the returned dict is byte-identical to `origin/main`'s. Pinned twice — by a
frozen literal (`test_flag_off_profile_is_byte_identical_to_legacy`) and by a
key-set assertion at both nesting levels (`test_flag_off_adds_no_keys_anywhere`)
— and sabotage S1/S11 confirm both bite.

This matters beyond the screen: `analyze_roster_strengths` produces
`position_needs` / `position_surplus`, read by `trade_gen_v2.py:930`, `:980`
and `trade_service.py:3413`, `:3440`, `:4096`, `:4172`, `:4259`. Flag off, no
deck moves.

---

## 3. Flag ON — how a player reaches a band

`trade.position_tiers` on, real pool:

1. `_pool_depth_by_position(players)` counts core-position players carrying a
   positive `search_rank`. Live pool: QB 313, RB 568, WR 1 134, TE 516 — all
   ≥ `_POS_TIER_MIN_POOL` (40), so `basis[pos]` is `True` everywhere.
2. `_positional_rank_map(players)` buckets by position, sorts by
   `(search_rank, player_id)` — unranked coerced to `10**9`, so they sort last
   rather than first — and assigns 1-based ranks. Memoized on `id(players)`
   **while holding a strong reference to the dict**, because `id()` is unique
   only among live objects; without the pin a freed pool's address could be
   recycled and serve another pool's ranks.
3. `_bin_player_relative(pos_rank, pos, is_superflex)` picks
   `_POS_TIER_CUTS_SF_QB` when `pos == "QB" and is_superflex`, else
   `_POS_TIER_CUTS[pos]`, then returns the first of
   `("elite", "starter", "bench")` whose cut the rank clears; `None` past the
   last cut, matching `_bin_player`'s "not worth counting".

Worked example, 1QB league, live pool ordering:

| Player | pos rank | QB cuts (6/18/32) | band |
|---|---|---|---|
| the QB6 | 6 | 6 ≤ 6 | elite |
| the QB7 | 7 | 7 > 6, ≤ 18 | starter |
| the QB19 | 19 | > 18, ≤ 32 | bench → rendered **Replacement** |
| the QB33 | 33 | > 32 | not counted |

Superflex re-runs the same walk against `(12, 36, 60)`, so the QB7 becomes
elite — and only QB moves (`test_superflex_widens_qb_and_nothing_else` compares
the other three position dicts for equality).

4. After the loop, `bins["replacement"] = bins["bench"]` — an **alias**, same
   integer, `bench` retained — and `tier_basis` is emitted.

---

## 4. Handcuff — the full path from Sleeper's dump to the card

| # | Stage | File:line | What happens |
|---|---|---|---|
| 1 | Sleeper `/v1/players/nfl` | — | each player carries `depth_chart_position`, `depth_chart_order` |
| 2 | Coerce | `database.py:8726-8730` | `depth_chart_order` → `int`, `None` on any parse failure |
| 3 | Persist | `database.py:8769-8770` | written on every `sync_players` row |
| 4 | Schema | `database.py:970-971` | `depth_chart_position` String, `depth_chart_order` Integer — *"1=starter, 2=backup, etc."* |
| 5 | Refresh | `database.py:8652-8663` | `needs_player_sync` re-syncs when `last_synced` > 24 h |
| 6 | Model | `ranking_service.py:262-263` | `Player.depth_chart_position` / `.depth_chart_order` |
| 7 | Hydrate | `server.py:1580-1581` | `build_universal_pool` copies both onto every pooled `Player` that has a DB row |
| 8 | Reach the profiler | `server.py:22815`, `trade_service.py:3169` | that pool **is** the `players` dict `analyze_roster_strengths` receives |
| 9 | Detect | `trade_service._is_handcuff` | `position == "RB"` ∧ `depth_chart_position.upper() == "RB"` ∧ `int(depth_chart_order) == 2` |
| 10 | Compose | `team_review._depth` | `if "handcuff_rb" in profile:` → pass through verbatim |
| 11 | Render | `TeamReviewScreen.tsx` `Depth` | `d.handcuff_rb !== undefined ? … : null` |

Steps 1–8 are all `origin/main`; **only 9–11 are new.** That is the whole of
[D-121](../../../../living-memory/DECISIONS.md): nothing was ingested, fetched
or migrated for this feature.

Live confirmation that step 3 actually holds data (`data/trade_finder.db`):
149 of 603 RB rows carry a non-null `depth_chart_order`, and they read as real
charts — `ARI` Conner 1 / Benson 2 / Allgeier 3 / Knight 4 / Kiner 5;
`ATL` Bijan 1 / Robinson 2; `BAL` Henry 1 / Hill 2; `BUF` Cook 1 / Davis 2.
The 454 nulls are camp bodies and free agents, on no chart and therefore
nobody's handcuff. `depth_chart_position` for RBs is the literal `"RB"`;
WRs split into `LWR`/`RWR`/`SWR`, which is why step 9 checks it rather than
trusting `depth_chart_order` alone.

**Step 11 is the honesty step.** The gate is `!== undefined`, not `?? 0` and
not truthiness:

- key **absent** → the flag is off, nobody looked → render nothing.
- key **`0`** → we looked, you own no RB2 → *"No handcuffs — none of your RBs
  is the RB2 on his NFL depth chart."*

A truthiness check would swallow the legitimate `0`; a `?? 0` would print the
second sentence when the first is true. Both are sabotage-proven red (S9, and
`test_handcuff_zero_is_present_not_absent` / `test_depth_omits_366_keys…`).

---

## 5. The `bench` → `replacement` rename, and every consumer of it

The report asked for the word "Replacement". A wire rename was rejected
(D-120): the shipped TestFlight build reads `tier_depth[pos]` directly, so
dropping `bench` would render zeros on every existing client. Both keys ship.

Every consumer of `tier_depth`, from `git grep -n "tier_depth"` — checked
individually, not counted:

| Consumer | Reads | Effect of the alias |
|---|---|---|
| `trade_service._position_strength:1976` | `elite` + `starter` | none |
| `trade_service` need-fit `:2040` | `elite` + `starter` | none |
| `team_review._depth:160` | whole dict, pass-through | carries the alias |
| `team_review._partners:354` | `elite` + `starter` (`startable_count`) | none |
| `mobile/src/api/teamReview.ts:98` | type only | `replacement?` added, optional |
| `mobile/.../TeamReviewScreen.tsx` `Depth` | `elite`, `starter`, now `replacement ?? bench` | renders the third layer |
| `backend/tests/test_finder_targeting.py:75`, `test_need_fit.py:77`, `test_team_review.py:71`, `:229` | fixtures | unaffected (flag-off shape) |
| `scripts/deck_eval.py:256` | calls the profiler; does not index bins | none |

**Web and extension consume `tier_depth` nowhere.** `git grep -n "tier_depth"`
returns no `web/` or `extension/` source hit. The one near-miss is
`web/css/styles.css`'s `.tier-depth` class — a 4-level *dynasty value* badge
set (`.tier-elite/.tier-high/.tier-mid/.tier-depth`) that
`docs/cross-client-invariants.md` already flags as a different taxonomy. It is
a CSS class name, not this payload, and nothing about it changes.

---

## 6. What this change deliberately does **not** do

- **Does not light either flag.** Both are `false` in `config/features.json`
  and in the three test flag fixtures. Graduation of `trade.position_tiers` is
  an operator decision with a deck-quality read attached (D-120).
- **Does not touch `infer_team_outlook`, `_window`, or the `Window` / `Plan`
  components** — concurrently owned.
- **Does not fix the IDP blind spot.** `plan-remaining.md` §2 attributes it to
  `analyze_roster_strengths` binning only QB/RB/WR/TE. The real cause is one
  layer up: `database._SYNC_POSITIONS` is `frozenset({"QB","RB","WR","TE"})`
  (`:8646`) and `server.VALID_POSITIONS` matches (`:16799`), so defensive
  players are never ingested into `players` at all. Widening the profiler alone
  would change nothing; this is an ingestion-side item.
