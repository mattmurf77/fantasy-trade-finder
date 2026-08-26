# LLD delta — Team Review

**Date:** 2026-08-19 · **Items:** #357 / #358 / #359 · **Flag:** `trades.team_review` (dark)
**Companion to** [`hld-delta.md`](hld-delta.md). This document is the build contract: two agents working blind on backend and mobile must produce compatible code from it.

---

## Table of contents

- [1. File-ownership table](#1-file-ownership-table)
- [2. `GET /api/league/team-review` — full contract](#2-get-apileagueteam-review--full-contract)
- [3. `backend/team_review.py` — function-level spec](#3-backendteam_reviewpy--function-level-spec)
- [4. Writes — no new route](#4-writes--no-new-route)
- [5. Mobile — screen, state, navigation](#5-mobile--screen-state-navigation)
- [6. Flag wiring](#6-flag-wiring)
- [7. Analytics wiring](#7-analytics-wiring)
- [8. Error and degradation matrix](#8-error-and-degradation-matrix)

---

## 1. File-ownership table

Disjoint, so backend and mobile can be built in parallel worktrees.

| Owner | Files |
|---|---|
| **Backend agent** | `backend/team_review.py` (new) · `backend/server.py` (one route + one helper, plus the guarded `run_outlook` call, appended near `/api/league/power-rankings`) · `backend/feature_flags.py` (`FLAG_KEYS`) · `backend/analytics_taxonomy.py` · `backend/analytics_queries.py` · `backend/tests/test_team_review.py` (new) · `backend/tests/test_analytics_taxonomy.py` · `config/features.json` · `docs/api-reference.md` · `docs/config-reference.md` |
| **Mobile agent** | `mobile/src/screens/TeamReviewScreen.tsx` (new) · `mobile/src/components/TeamReviewEntryCard.tsx` (new) · `mobile/src/api/teamReview.ts` (new) · `mobile/src/screens/TradesScreen.tsx` (entry-card mount only) · `mobile/src/navigation/TabNav.tsx` (one `TradesStack.Screen`) · `mobile/tests/check-team-review.js` (new) · `mobile/package.json` (one script). **Reads but does not modify** `mobile/src/state/useFinderTargets.ts` (the #330 handoff store). |
| **Shared, sequenced** | `docs/cross-client-invariants.md` and `docs/glossary.md` — backend agent writes first, mobile agent reviews. Never edited concurrently. |

---

## 2. `GET /api/league/team-review` — full contract

### Request

```
GET /api/league/team-review?league_id=<str>&basis=consensus|personal
```

| Param | Required | Default | Notes |
|---|---|---|---|
| `league_id` | no | the session's active league | 400 if absent and no session league |
| `basis` | no | `consensus` | `personal` uses the caller's board for value resolution, mirroring `/api/league/power-rankings`. `redraft` → **501** with the same `not_available` body power-rankings returns, for parameter-shape parity. |

**Decorators, in this order:** `@app.route(...)` then `@_gate_unverified_read`.
The whole route is gated — unlike `/api/league/power-rankings`, which cannot be,
because its consensus basis is league-shared by design. Team Review is per-user
by construction (your team, your board, your preferences), so wholesale gating is
correct and matches its nearest sibling, `GET /api/league/preferences`.

**Flag gate is first, before the session load:** `if not is_enabled("trades.team_review"): return jsonify({"error": "not_found"}), 404`
— the same shape and position as `/api/league/outlook` (`server.py:23211`).

### Response `200`

All value figures are the same scale `/api/league/power-rankings` serves.
All shares are `0..1` fractions. `null` means *not available*, never *zero*.

```jsonc
{
  "league_id": "1312140920132497408",
  "platform": "sleeper",                    // from get_league_draft_context
  "basis": "consensus",
  "meta": {
    "num_teams": 12,
    "scoring_format": "sf_tep",
    "completed_weeks": 0,
    "beats": ["standing","window","depth","divergence","partners","plan"],
    "beats_skipped": ["divergence"],        // beats the client must not render
    "scoring_available": false,
    "scoring_unavailable_reason": "preseason"   // | "platform_unsupported" | null
  },

  "standing": {
    "value_rank": 6,
    "value_total": 12,
    "roster_value": 48210.5,
    "position_value": [                     // always all four, value-desc
      { "position": "WR", "value": 18800.2, "share": 0.390, "rank": 3 },
      { "position": "RB", "value": 14900.1, "share": 0.309, "rank": 4 },
      { "position": "QB", "value": 10600.0, "share": 0.220, "rank": 7 },
      { "position": "TE", "value":  3910.2, "share": 0.081, "rank": 11 }
    ],
    "scoring": null,                        // see §8 for the populated shape

    // #169 odds — present ONLY when `outlook.odds` is on AND the league is
    // Sleeper AND the outlook call succeeded. Absent (not null-filled) in
    // every other case; the client renders the chip iff the key is present.
    // `band` is computed SERVER-SIDE here, unlike LeagueSummary which bands
    // client-side — see the note below for why that is deliberate.
    "outlook": {
      "band": "tossup",                     // likely | tossup | unlikely
      "playoff_pct": 0.51,                  // raw fraction — for the a11y label ONLY, never displayed
      "projected_seed": 6,
      "beta": true,                         // weeks 0-5: bands + order only, NO win-loss numbers
      "is_preseason": true,
      "strength_source": "roster_value",
      "priced_slot_coverage": {             // IDP/K honesty caption; qualify only when
        "fraction": 0.4667,                 // affects_strength is true AND fraction < 1
        "total_slots": 15, "priced_slots": 7,
        "unpriced_slots": ["K","DL","DL","LB","LB","DB","DB","IDP_FLEX"],
        "affects_strength": true
      }
    }
  },

  "window": {
    "inferred": "contender",                // contender | rebuilder | not_sure ONLY
    "declared": null,                       // the stored league_preferences value, or null
    "signals": {
      "vet_share": 0.61, "youth_share": 0.12,
      "pick_share": 0.05, "equal_pick_share": 0.0833,
      "score": 0.31
    },
    "options": ["championship","contender","rebuilder","jets","not_sure"]
  },

  "depth": {
    "tier_depth": { "QB": {"elite":1,"starter":0,"bench":2}, "RB": {...}, "WR": {...}, "TE": {...} },
    "position_needs":   ["TE"],
    "position_surplus": ["RB"],
    "weakest_slot": {                       // nullable — see §8
      "slot": "TE",
      "player_id": "4034",
      "name": "Hunter Henry",
      "position": "TE",
      "tier": "fourth",
      "pos_rank": 31
    },
    "acquire_positions":    [],             // current stored prefs, so the client
    "trade_away_positions": []              // renders the chips pre-selected
  },

  "divergence": {
    "source": "consensus_seed",             // league_community | consensus_seed | null
    "baseline_user_count": 0,
    "board_judged_players": 41,             // players with wins+losses > 0 — NOT len(user_elo)
    "board_interactions": 63,               // RankSet.interaction_count (position=None)
    "higher_than_market": [                 // ≤5, gap-desc — YOUR EASIEST SELLS
      { "player_id":"11566","name":"Bijan Robinson","position":"RB",
        "user_elo":1712.0,"comparison_elo":1604.5,"gap":107.5,
        "user_pos_rank":2,"comparison_pos_rank":6,"pos_rank_gap":4,
        "on_roster": true }
    ],
    "lower_than_market": [ /* ≤5, same shape, on_roster false for buys */ ]
  },

  "partners": {
    "opposed_window": [                     // ≤3, by (opposition, pick capital)
      { "user_id":"...","username":"MangoPatti","value_rank":11,
        "inferred_outlook":"rebuilder","pick_capital_share":0.14,
        "first_round_picks":3 }
    ],
    "fills_your_need": [                    // ≤3
      { "user_id":"...","username":"gdubs10","position":"TE","startable_count":3 }
    ]
  }
}
```

**Field rules that are contract, not preference:**

- `window.inferred` is **only** `contender` | `rebuilder` | `not_sure`.
  `infer_team_outlook` deliberately never infers the extremes — inference
  confidence does not justify α = 1.00 / 0.10. `window.options` carries all five
  because a user may *declare* an extreme.
- `meta.beats_skipped` is authoritative. The client renders exactly
  `beats` minus `beats_skipped`, in `beats` order. It never decides for itself
  that a beat is empty — that keeps the analytics `beat` values and the step
  indices consistent between client and server.
- **`title_pct` and `bye_pct` appear nowhere in this payload, at any week**
  ([D-094](../../../../living-memory/DECISIONS.md)). `title_pct` is unrenderable
  on an absence of demonstrated skill, so it is not merely unshown — it is not
  serialized, which removes the temptation entirely. Asserted in
  `test_team_review.py` over the serialized JSON.
- **`standing.outlook.playoff_pct` is served but must never be displayed as a
  number.** It exists so the client can build the VoiceOver label
  ("Projected 51 percent chance to make the playoffs" is acceptable to a screen
  reader in a way a visible "51%" is not, because the ribbon and band travel
  with it). The visible surface is `band` only.
- **`band` is computed server-side here, and that is a deliberate divergence
  from `LeagueSummaryScreen`,** which bands client-side from the raw fraction.
  Reason: Team Review's payload is a narrative assembled server-side, and a
  second client-side implementation of the threshold walk is a second place for
  the invariant to drift. The thresholds remain the cross-client invariant's;
  the server reads them, it does not re-derive them. `check-outlook-bands.js`
  continues to pin the client copy that League Summary still uses.
- `position_value[].rank` is the user's rank *at that position* across the
  league — the number that makes "you're 3rd at WR but 11th at TE" sayable.

### Error responses

| Status | Body | When |
|---|---|---|
| `404` | `{"error":"not_found"}` | `trades.team_review` off. Checked before anything else. |
| `400` | `{"error":"league_id is required"}` | No param and no session league. |
| `400` | `{"error":"basis must be one of consensus, personal, redraft"}` | Bad `basis`. |
| `404` | `{"error":"league_not_found"}` | `_power_ranking_inputs` returns `members is None`. |
| `501` | `{"error":"not_available","message":"…dynasty-only…"}` | `basis=redraft`. |
| `403` | the existing `_verified_read_denial` body | Unverified account (P2.5). |
| `500` | `{"error":"internal_error"}` | Anything else, logged. |

**There is no `501 not_supported` for platform.** A non-Sleeper league gets a
`200` with `scoring_unavailable_reason: "platform_unsupported"`. That is the
whole point of the degradation design — the feature must never fail on ESPN/MFL,
it must fail *one card*.

---

## 3. `backend/team_review.py` — function-level spec

Pure. No DB, no HTTP, no Flask import. Every input is passed in, mirroring
`power_rankings.compute_power_rankings`.

```python
def build_team_review(
    *,
    teams: list[dict],            # compute_power_rankings output (already has is_you)
    you_user_id: str,
    user_roster: list[str],
    players: dict,                # player_id -> Player
    scoring_format: str,
    lineup_slots: list[str] | None,
    picks_by_owner: dict[str, list[dict]],
    stored_prefs: dict,           # load_league_preference output, or {}
    user_elo: dict[str, float] | None,      # None when basis=consensus and no board
    seed_elo: dict[str, float],             # the universal DP seed
    community_rankings: dict[str, dict],    # load_community_elo_for_league output
    league_members: list[dict],
    weekly_scores: dict[int, list[float]] | None,   # None => scoring unavailable
    points_for: dict[int, float] | None,
    roster_id_of: dict[str, int] | None,
    completed_weeks: int,
    scoring_unavailable_reason: str | None,
    tier_of,                      # (elo, pos) -> tier band name
    pos_rank_of,                  # player_id -> int | None
) -> dict:
```

### Beat assembly rules

| Beat | Built from | Skip condition (→ `meta.beats_skipped`) |
|---|---|---|
| `standing` | `teams` (rank by `value`, per-position sums), `weekly_scores`/`points_for` | never skipped |
| `window` | `infer_team_outlook(user_roster, players, pick_share, num_teams)` | never skipped — `not_sure` is a valid answer |
| `depth` | `analyze_roster_strengths(...)` + `optimal_starter_slots(...)` | never skipped; `weakest_slot` is `null` when `lineup_slots` is falsy |
| `divergence` | `compute_consensus_gap(...)` when `has_baseline`, else the seed-delta fallback below | **skipped** when the caller's `RankSet.threshold_met` is false — see the trap below |
| `partners` | `infer_team_outlook` per member + `picks_by_owner` + `analyze_roster_strengths` per member | **skipped** when the league has fewer than 2 other members |
| `plan` | nothing — a client-side recap of the session's writes | never skipped |

### The divergence trap — read this before writing the beat

**`user_elo` is NOT a list of players the user has ranked.** `RankingService.get_rankings(position=None)`
calls `_pool(None)`, which is documented as returning *"ALL players for a position
(unfiltered)"* (`backend/ranking_service.py`), and computes an Elo for every one
of them. A user who has never made a single comparison still gets a full-pool
`user_elo` map — every entry sitting at (or near) the seed.

Two consequences, both load-bearing:

1. **Any skip condition of the form `len(user_elo) < N` never fires.** Use the
   service's own bar instead: `RankSet.threshold_met` for `position=None`, which
   is `interaction_count >= 16` (`POSITION_THRESHOLDS[None]`). This is the same
   bar the app already uses to decide a board is worth trusting — not a new
   magic number.
2. **A player the user has never judged has a structurally-zero gap**, because
   his board Elo *is* the seed. Including such players would pad both divergence
   lists with non-opinions. Filter every candidate on
   `RankedPlayer.wins + RankedPlayer.losses > 0` — the user actually compared
   him — before computing any gap. `board_judged_players` in the payload is the
   count of players passing this filter, and it is the number the client shows
   in the thin-board copy.

Both rules apply to the `consensus_seed` branch and, for the per-player filter,
to the `league_community` branch as well.

### The divergence fallback — precise

Two sources, tried in order. This is the one place the module chooses between
inputs, so it is specified rather than left to the builder:

1. **`league_community`** — `compute_consensus_gap(...)` returns
   `has_baseline: True` (≥3 other rankers, `trends_service.py:180`). Map
   `easiest_sells` → `higher_than_market` (`on_roster: true`) and `easiest_buys`
   → `lower_than_market` (`on_roster: false`). `comparison_elo` is
   `community_elo` for sells and `owner_elo` for buys.
2. **`consensus_seed`** — otherwise, compute per-player
   `gap = user_elo[pid] - seed_elo[pid]` **over judged players only**
   (`wins + losses > 0`, per the trap above). The user's board starts *at* the
   seed and diverges as they rank, so for a judged player this gap is exactly
   "how far you have moved him from consensus". Positive gaps on roster →
   `higher_than_market`; negative gaps off roster → `lower_than_market`. Top 5
   each by `abs(gap)`.
3. **`null`** — beat skipped (see the skip condition above). `source: null`,
   both lists empty.

`pos_rank_gap` is computed the same way in both branches, via `pos_rank_of`, so
the client renders one shape.

### Partner selection — precise

- `opposed_window`: members whose `infer_team_outlook` differs from the user's in
  the contending direction (user `contender`/`championship` → members inferred
  `rebuilder`; user `rebuilder`/`jets` → members inferred `contender`). Sorted by
  `pick_capital_share` desc when the user is contending (they hold what a
  contender wants to buy), by `value_rank` asc when the user is rebuilding (the
  best rosters have the vets a rebuilder sells to). Cap 3.
- `fills_your_need`: members whose `analyze_roster_strengths.position_surplus`
  intersects the user's `position_needs`. Sorted by that position's
  `startable_count` desc. Cap 3.
- A member may appear in both lists. That is not a bug — it is the best possible
  partner.
- **`not_sure` members are excluded from `opposed_window`**, never bucketed as
  either side. Inference that declined to commit must not be laundered into a
  recommendation.

---

## 4. Writes — no new route

| Beat | Write | Route | Body |
|---|---|---|---|
| `window` | `team_outlook` | `POST /api/league/preferences` (existing, `server.py:15447`) | `{league_id, team_outlook}` |
| `depth` | `acquire_positions`, `trade_away_positions` | same route | `{league_id, acquire_positions, trade_away_positions}` |
| `divergence` | pin an asset into the finder | existing finder-pin path (unchanged) | — |
| `partners` | scope the deck to one member | the existing **#330 handoff store** `mobile/src/state/useFinderTargets.ts` — `setHandoff({opponent, autoRun: true})`, one-shot, focus-gated, consumed by `TradesScreen` | — |

**No new write endpoint, no partial-update semantics invented.** The client sends
the same body shape the Trade DNA sheet already sends. If a write fails, the beat
surfaces the failure inline and the flow continues — an analytics event is *not*
emitted for a failed write.

---

## 5. Mobile — screen, state, navigation

### Registration

`mobile/src/navigation/TabNav.tsx`, inside `TradesStackNav`, gated:

```tsx
const teamReviewOn = useFlag('trades.team_review');
…
{teamReviewOn ? (
  <TradesStack.Screen
    name="TeamReview"
    component={TeamReviewScreen}
    options={subScreenOptions('Team review', 'TradesHome')}
  />
) : null}
```

`subScreenOptions` is mandatory, not stylistic: it is the shared always-on back
control the repo adopted because native back is dead on iOS 26 (RNS#3294) — the
same reason `TradeCalculator` and `TodaysTrade` use it.

### The entry card collapses; it never disappears

Dismissing the card **collapses it to a one-line row**, it does not remove it.
This is the D-025 precedent applied verbatim: the League-Summary outlook section
defaults to "a collapsed one-line 'your outlook' strip (per-league, per-user
persisted) with the full section one tap away". Same shape here, for the same
reason — a permanently dismissible entry means the user who most needs the
feature can lose it forever with one accidental tap, and there is no other
always-present surface to recover it from.

Consequently `team_review_opened.source` has exactly three values —
`trades_home_card` (the expanded card), `collapsed_row`, `deck_empty` — and
there is no `overflow` surface. *(An earlier draft of this spec listed
`overflow` as a source without specifying where it lived; it does not exist.)*

### FeedbackFAB — do NOT mount one

`TeamReview` is a **tab-stack** screen. Per CLAUDE.md #188 it is already covered
by the single global `FeedbackFAB` mount in `RootNav.tsx` (inside the `Main`
screen). A local mount is the #196/#197 double-FAB bug. Pinned by
`check-team-review.js` assertion 2.

The B6 beat has a pinned bottom CTA bar, so it calls
`setPinnedBottomBarHeight` (exported by `FeedbackFAB`) rather than adjusting the
FAB offset by hand.

### State

Local and disposable — a `useState` step index plus a `useRef` set of actions
taken (for the `plan` recap and the `team_review_exited.outcome`). **Nothing
persists across a mount** except:

- the entry card's per-league **collapse** state (`AsyncStorage`, key
  `team_review.entry_collapsed.<league_id>`) — see the entry-card rule below, and
- the preference writes themselves, which persist server-side because they are
  real preferences.

Re-entering Team Review re-runs the review from beat 1 against fresh data. That
is correct: the whole point is that the read reflects the roster *now*.

### Rendering rules (Chalkline, binding)

- **Ice is actions only** — the Next / Confirm / Find-my-trades buttons and the
  selected preference chip. Ration to ≤3 ice elements per beat.
- **Flare is informational highlight only** — never on a button. Reserved here
  for the "new since your last review" marker if that is ever added; unused at v1.
- **Need/surplus chips reuse the existing dashed treatment** from Trade DNA
  (dashed `warn` for need, dashed `pos` for deep) so the vocabulary is one thing
  across surfaces.
- **No emoji as icons. No gradients. No blur. Radius ≤ 8px** except the specced
  avatar pill.
- Position hexes come from `chalkline.position`, which re-exports `colors.ts` —
  a cross-client invariant, never re-derived.
- Every projected or inferred figure carries the word **inferred** or
  **projected** adjacent to it. `window.inferred` renders under the label
  "inferred from roster shape", never as a bare verdict.

---

## 6. Flag wiring

| File | Change |
|---|---|
| `config/features.json` | `"trades": { …, "team_review": false }` + a `_comment_team_review` block stating what ON and OFF mean, per the file's established convention |
| `backend/feature_flags.py` | add `trades.team_review` to `FLAG_KEYS` |
| `backend/server.py` | `is_enabled("trades.team_review")` guard, first statement in the route |
| `mobile/src/…` | `useFlag('trades.team_review')` gates the screen registration and the entry card |
| `docs/config-reference.md` | new row |

**Never add `trades.team_review` to the launched-flag defaults** until the
operator flips it — the same rule `outlook.odds` carries.

**OFF is byte-identical:** route 404s, screen unregistered, card unrendered, no
event emitted. There is no code path where the flag being off changes an existing
behavior.

---

## 7. Analytics wiring

`backend/analytics_taxonomy.py`:

```python
ALLOWED_CLIENT_EVENTS |= {
    "team_review_opened", "team_review_beat_viewed",
    "team_review_exited", "team_review_action_taken",
}
# property allowlists
"team_review_opened":       frozenset({"league_id", "source"}),
"team_review_beat_viewed":  frozenset({"league_id", "beat", "index"}),
"team_review_exited":       frozenset({"league_id", "beat", "index", "outcome"}),
"team_review_action_taken": frozenset({"league_id", "beat", "action"}),
```

Extended enums (documented in the property comment, matching the existing
`outlook_saved` comment style): `outlook_saved.source` gains `review`;
`finder_target_pinned.source` gains `review`.

`backend/analytics_queries.py`:

```python
NON_INTENT_EVENTS |= {"team_review_beat_viewed", "team_review_exited"}
```

with the block comment naming the reason (impression class / terminator class),
matching the `league_team_closed` and `league_pos_candidates_viewed` precedents.
`team_review_opened` and `team_review_action_taken` are deliberately **absent** —
they are intent.

**All of the above lands in the same commit as the emitters.** This is the
NULL-`platform` rule and it is not negotiable.

---

## 8. Error and degradation matrix

| Condition | Detection | Payload | Client renders |
|---|---|---|---|
| Preseason | `completed_weeks == 0` | `standing.scoring: null`, `reason: "preseason"` | "No games played yet — 2026 hasn't started. This fills in from week 1." |
| ESPN / MFL / Fleaflicker | `platform != "sleeper"` — checked **before** calling `build_league_state`, so `NotImplementedError` is never raised in the first place | `standing.scoring: null`, `reason: "platform_unsupported"` | "Not available for ESPN leagues yet — we can't read weekly scores there. Everything else in this review works." |
| In-season Sleeper | `completed_weeks >= 1` | `standing.scoring: {"ppg": 118.4, "ppg_rank": 11, "record": {"w":3,"l":1,"t":0}}` | The PPG rank card, labelled **actual**, never projected |
| `build_league_state` throws for any other reason | caught | `scoring: null`, `reason: "platform_unsupported"`, warning logged | same as the ESPN copy — degrade, never 500 |
| Thin board | `RankSet.threshold_met` false for `position=None` (i.e. `interaction_count < 16`) — **never** `len(user_elo)`, see the trap in §3 | `divergence` beat in `beats_skipped`, `source: null`, `board_judged_players` still reported | Beat not rendered. The `plan` beat offers "Rank some players" as a follow-up, citing `board_judged_players`. |
| No league baseline (`<3` other rankers) | `has_baseline: false` | `source: "consensus_seed"` | Rendered normally — the comparison is to the market seed, and the caption says so. |
| No lineup template | `lineup_slots` falsy | `weakest_slot: null` | The depth beat drops that one card; `tier_depth` still renders. |
| Solo/2-team league | `< 2` other members | `partners` in `beats_skipped` | Beat not rendered. |

### Odds-specific degradation (#169, `outlook.odds`)

| Condition | Payload | Client renders |
|---|---|---|
| Flag on, Sleeper, call OK | `standing.outlook` present | Band chip + "Projected · preseason · beta" ribbon beside the value rank |
| Flag **off** | `standing.outlook` **absent** | No chip. Nothing else about the beat changes. |
| Non-Sleeper league | `standing.outlook` **absent** | No chip — the same honest absence `LeagueSummaryScreen`'s `outlookSupported` gate already produces. Never a 501, never an error card. |
| Outlook call throws / times out | `standing.outlook` **absent**, warning logged | No chip. **The beat must still render** — an odds hiccup may never cost the user their value rank. |
| `meta.beta` true (weeks 0–5) | `beta: true` | Band + ribbon, **no win-loss numbers and no projected record** — a projected record is the same false-precision point estimate as a percentage in another unit. |
| IDP/K league (`affects_strength` true, `fraction < 1`) | `priced_slot_coverage` populated | The chip carries the coverage caption ("based on your offensive starters"). **This field has never been rendered by any client — Team Review is its first consumer.** |

**The governing rule:** every degradation names its actual reason in the copy.
No spinner that never resolves, no empty card, no "something went wrong" standing
in for "the season hasn't started".
