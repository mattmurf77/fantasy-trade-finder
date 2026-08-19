# Code-walk proof — placement tier clamp (D-085)

D-056 evidence for a backend-only change. Line numbers are on
`feat/placement-tier-clamp`, based on `origin/main` = `a130dfc`.

---

## 1. Where the band comes from

`backend/ranking_service.py:576` `_placement_bands(pool_ids, released)` — the
band derivation, split out of `_pin_bounds` with **no knob attached**. It is the
former body of `_pin_bounds` moved verbatim; `_pin_bounds:572-578` now keeps its
`pin_tier_bounded` guard and delegates. So there is exactly one definition of
"the tier the user placed him in", and the voting clamp and the pricing clamp
cannot drift apart. Pinned by
`test_placement_bands_agrees_with_tier_bounded_voting`.

Per placed pid it does: look up the player's position → `tier_bands_for(pos,
fmt)` (reads `backend/tier_config.json`) → `tier_for_elo(pin, ...)` → skip if
`None` → `bounds[pid] = (min(lo, pin), max(hi, pin))`.

`backend/ranking_service.py:610` `placement_bands()` — the public read. Guards
on `self._elo_overrides` being non-empty, then calls `_placement_bands(pool_ids,
self._pin_release(pool_ids))`.

Three properties that matter, each with a test:

| Property | Why | Test |
|---|---|---|
| Not gated on `pin_tier_bounded` | That knob governs how VOTES move a pin. With it off a pin is a total *freeze*, so `user_elo` equals the pin exactly and the blend drags hardest — the case the clamp is most for. | `test_placement_bands_is_independent_of_pin_tier_bounded` |
| F2-released pins excluded | `_pin_release` is passed through; a released pin is gone, so there is nothing to honour. | `test_placement_bands_drops_a_released_pin` |
| Below-lowest-band pins excluded | `tier_for_elo` returns `None` below 1150. That is `DEMOTED_ELO` (#161) and the anchor "no value" answer (1100) — "unranked, pending placement" markers, not valuations. Clamping into a sub-1150 non-band would price a player at ~nothing on a marker the user never meant as a value. | `test_a_placement_below_the_lowest_band_is_not_clamped` |

## 2. Where it is read

`backend/server.py:5274`

```python
placement_bands = service.placement_bands() if service else None
```

Sits immediately after the existing `confidence_counts = service.comparison_
counts()` on the same `service` object — no new lookup, no new query, no new
failure mode. Passed at `backend/server.py:5343` as `placements=placement_bands`.

## 3. Where it is applied

`backend/trade_service.py:1221` `_shrink_user_elo`, body at `1254-1268`:

```python
if confidence is None:
    return dict(user_elo)                                    # 1254-1255
n0 = _c("shrink_pseudocount")
bands = placements if (placements and _c("placement_tier_clamp") > 0) else None
for pid, elo in user_elo.items():
    n = max(confidence.get(pid, 0), 0)
    w = n / (n + n0)
    blended = w * elo + (1.0 - w) * seed_elo.get(pid, 1500.0)  # UNCHANGED
    if bands is not None:
        band = bands.get(pid)
        if band is not None:
            blended = min(max(blended, band[0]), band[1])
    out[pid] = blended
```

Four no-op paths, all byte-identical to pre-D-085:

1. `confidence is None` — returns before the clamp is reachable
   (`test_no_confidence_map_means_no_shrinkage_and_no_clamp`).
2. `placements` falsy — `bands is None`.
3. `placement_tier_clamp == 0` — `bands is None`
   (`test_knob_at_zero_is_byte_identical`).
4. `pid not in bands` — every unplaced player
   (`test_unplaced_players_are_never_clamped`).

The clamp is applied **after** the blend, not instead of it. That is what keeps
a mis-placement correctable: a user who keeps voting a placed player down still
moves him inside the band, and the displacement decays to exactly zero once `n`
is large enough to carry the blend back inside on its own
(`test_the_clamp_stops_biting_as_confidence_rises`). This is the difference from
the rejected `w = 1` option, which would have made a mis-pin uncorrectable.

## 4. Both engine arms use the same call

- `backend/trade_service.py:4011` — `_generate_trades_v2` (v2 path)
- `backend/trade_gen_v2.py:814` — `generate_league_suggestions` (gen-v2 path)

Both now call `_shrink_user_elo(user_elo, seed_elo, confidence, placements)`.
Threading: public entry `trade_service.py:3124` → `trade_gen_v2` arm at `:3207`,
`_generate_trades_v2` arm at `:3269` → `_generate_trades_v2` signature `:3966`.
The two arms cannot price a placed player differently.

## 5. Gate isolation — the load-bearing claim, verified not assumed

The scope boundary is the comment block at `trade_service.py:1233` ("A GATE
judges the real package…"). The claim is that this change cannot move any gate.

**Proof by what the gate reads.** The range-overlap fairness gate is at
`trade_service.py:4575-4599`. Its inputs:

```python
gvals = [seed_value(p) for p in give_ids]      # :4581
rvals = [seed_value(p) for p in recv_ids]      # :4582
```

`seed_value` — **consensus**, not `user_value`. The clamp writes only into
`shrunk_elo` (`:4011`) → `user_value` (`:4013`). `user_value` never reaches this
function. The uncertainty half-widths at `:4591-4593` come from
`_value_uncertainty(p, confidence)`, which takes `confidence` only —
`_value_uncertainty` has no `placements` parameter, asserted by
`test_value_uncertainty_ignores_placements` via `inspect.signature`, so a future
edit that adds one fails the suite rather than sliding through.

So both halves of the gate — the point ratio and the interval — are computed
entirely from consensus values and comparison counts. Neither can observe a
placement. **No gate changes.**

`_value_uncertainty` sharing `comparison_counts` with `_shrink_user_elo` is
deliberate and preserved ("one knob turns both consumers back off together" —
`comparison_counts` docstring, `ranking_service.py:1122`). D-085 adds a bound on
the blend, not a second confidence source, so that property is intact.

## 6. What this does NOT explain — the `basis: consensus` question

The framing behind this work was "every one of the 40 most recently served cards
came back `basis: consensus`". **Prod does not show that**, and the clamp is
probably not the lever.

Read-only prod, 2026-08-19:

| Window | consensus | divergence |
|---|---|---|
| Last 40 impressions | 30 | 10 (25%) |
| Last 400 impressions | 369 | 31 (7.8%) |
| All time | 9,287 | 1,263 (12%) |

`basis` is set in two places, and **neither reads the user's board**:

- `trade_service.py:4105` — `if member.has_rankings and member.elo_ratings:`
  gates the divergence path. `has_rankings` is `m.user_id in ranked_ids`
  (`database.py:7614`) — a property of the **OPPONENT**, not of the user.
  Otherwise `_generate_consensus_for_pair` (`:4949`, `basis="consensus"`).
- `trade_service.py:4175` — the zero-divergence fallback: a boarded opponent
  whose divergence path yielded no cards falls back to consensus.

The clamp changes `shrunk_elo`, which feeds the divergence path's *ranking*
terms. It therefore cannot convert a card from the first branch (opponent has no
board) — that is decided before any user value is consulted. It can only help
via the second branch, by making the divergence path produce cards where it
previously produced none.

Whether that fires is not determinable from the impressions table alone, because
the table does not record *why* a consensus card was consensus. **Recommended
follow-up:** instrument the fallback at `trade_service.py:4175` to distinguish
"opponent unboarded" from "divergence path came back empty". Until that exists,
any claim that this clamp will move the divergence share is a hypothesis, not a
measurement. It should not be reported as the cause.

## 7. Real-board impact — measured by replaying the operator's board

Method: rebuild a real `RankingService` from read-only prod — 625-player pool
seeded from the latest `player_value_history` snapshot, all 624 stored
`tier_overrides` pins re-applied with their stamps, all 1,679 in-pool
`swipe_decisions` replayed through `replay_from_db` — then read the genuine
`comparison_counts()` and run `_shrink_user_elo` with and without the clamp.
This is the live configuration (`pin_tier_bounded=1.0`,
`pin_exclude_comparisons=1.0`, `shrink_pseudocount=4.0`), not an estimate.

### The driving example — confirmed exactly

Davante Adams (pid 2133), operator `mattmurf77`, 1qb_ppr:

| | |
|---|---|
| placement band (`third`) | **[1280, 1365]** |
| consensus seed | **1526.0** (`second`) |
| raw personal Elo after voting | 1350.1 |
| **live `comparison_counts` n** | **1** |
| `w = n/(n+4)` | 0.20 |
| **priced WITHOUT clamp** | **1490.8 → `second`** |
| **priced WITH clamp** | **1365.0 → `third`** |
| clamp displacement | **125.8 Elo** |

The defect is real and this fixes it. The user placed Adams in `third`; the
engine priced him in `second`, the tier he was not placed in.

**The mechanism is subtler than "he was barely compared", and worth recording.**
Adams has 36 *distinct comparison opponents* in `swipe_decisions` — he is one of
the most-voted players on the board. But his live `comparison_counts` is **1**,
because `pin_exclude_comparisons=1.0` counts only comparisons that actually
MOVED his Elo, and a tier-bounded player pressed against his band edge stops
moving, so those votes are correctly discarded as non-evidence
(`ranking_service.py:1122` docstring). The result is `w = 0.2`: the engine
priced him **80% consensus** despite 36 votes and an explicit placement. An
estimate from raw distinct-opponent counts gives `n = 36`, `w = 0.9`, and
concludes the clamp is a no-op here — that estimate is wrong, and only the
replay reveals it.

This is the F1/D-085 interaction the task asked about, and it cuts the same way
both times: F1 narrows which comparisons COUNT (correctly), which drives `w`
down, which makes the direction-blind blend lean harder on consensus — and
D-085 is what stops that lean from crossing a tier the user explicitly chose.

### Whole board

| | |
|---|---|
| placed players carrying a band | 615 of 624 pins (9 below the lowest band → never clamped) |
| **clamp actually moves** | **162 (26%)** |
| median displacement | 32 Elo |
| max displacement | 343 Elo (Travis Hunter: placed `firsts_2`, consensus 1445) |

Largest movers are dominated by `n = 0` players — placed, never compared, so
`w = 0` and the blend was **pure consensus** with the placement contributing
nothing at all. That is the population the clamp exists for.

### Other users

Same method, raw-`n` upper-bound estimate (so these under-state the reach, as
the Adams case shows):

| User | placements | below-band (no clamp) | clamp moves |
|---|---|---|---|
| mattmurf77 (operator) | 737 | 13 | 139 → **162 measured** |
| gdubs10 | 644 | 16 | 81 |
| jonbonjourvi | 547 | 283 | 110 |
| 867831697150 | 42 | 37 | 5 |
| acct_1401fad | 16 | 0 | 12 |

Placements are **not** rare: 5 of 18 users have them, and the three active
boards each carry hundreds.
