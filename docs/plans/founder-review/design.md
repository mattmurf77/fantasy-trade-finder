# Founders' review — design

**Date:** 2026-11-11 · **Status:** built on `feat/founder-label-review` (cut from `release/2026-11-12-train`), default off · **Scope block:** [scope.md](scope.md)

Operator ask (2026-11-11): a page just for the founder, inside Calibration, presenting every player split by
position with the tier board's "tap him, then tap the tier" interaction, to review and adjust the win-now
season signal's player labels; and: can a player carry more than one label?

## 1. One label per player — and why the page keeps it that way

The engine (revision 5, `backend/season_value.league_profile`) gives every rostered player **exactly one** of
`cornerstone`, `win_now`, `rebuild`, `depth`, or no label. The four labels are a 2 × 2 of two questions:

| | holds future value | no future value |
|---|---|---|
| **starts now in this league** | `cornerstone` ("Cornerstone") | `win_now` ("Win-now piece") |
| **does not start** | `rebuild` ("Rebuild piece") | `depth` ("Depth") |

No label = he sits inside the starter-line band (borderline), has no projection, or his position has no line.
Picks are always `rebuild` and are not on the page (nothing to review).

"Now **and** future" is not two labels: it is `cornerstone`. So no player needs a second label, and the page
assigns one. Storage keeps the label as a **value** (`label` column, a closed vocabulary), never as booleans
like `is_win_now` / `is_cornerstone`, so a future multi-label model widens the key from `(player_id, scope)`
to `(player_id, scope, label)` and changes the reader, not the table's meaning. Multi-label is not built.

## 2. The override model — scoped per player, applied to the future axis only

**Decision: an override is a judgment about the player's future value, held per player and scope. Whether he
starts stays computed per league.** RB / WR / TE overrides are global (scope `all`). **QB overrides are scoped
by the league's QB format** (operator ruling, 2026-11-12: "Cornerstone QBs in SF are not cornerstone in other
leagues"): an override set while reviewing a superflex / 2QB league holds in every superflex league and in no
single-QB league, and vice versa. This takes the operator's leaning with one correction, below.

- QB format = the repo's one superflex test, `season_value.is_superflex(slots)`: a `SUPER_FLEX` slot or two or
  more `QB` slots — the QB leg of `server._detect_scoring_format_from_meta`, which now calls it. The format
  key (`1qb_ppr` / `sf_tep`) is **not** used: it also folds in TE premium (a 1-QB TE-premium league is
  `sf_tep`), so scoping QBs on the whole key would treat a 1-QB TEP league as superflex. The QB dimension is
  read from the league's lineup slots, which the season evidence already carries (`evidence["slots"]`).
- Scope values: `all` (RB / WR / TE), `superflex`, `single_qb` (QB). The column takes any scope, so a later
  TE-premium scope for tight ends needs no migration (open question, not built).

- Why global for RB / WR / TE: the founder's call ("he is a win-now piece, not a cornerstone") is about the player, and the
  part of a label that is about the player is the future axis (`FUTURE_FLOOR`, the age cliff, `young`). The
  other axis — does he start — depends on each league's starter line, roster sizes and slots; a per-league
  override would ask the founder to re-review every league and would drift. Per-league is not the more
  correct model, so it is not built.
- **Correction to the leaning ("to `rebuild` replaces the engine's label in any league"):** `rebuild` means
  "does not start now". Applied to a player who starts in some league, it would claim a starter does not
  start, the mirror image of the incoherence the operator ruled out ("an override must not claim a bench
  player starts"). So an override never moves the starts axis in either direction. `cornerstone` and
  `rebuild` are one judgment ("holds future value"); `win_now` and `depth` are the other ("no future value").
  The stored value is the band the founder picked (kept for the record and the summary); the effect is the
  future axis.

### 2.1 The rule, case by case (`season_value.league_profile`)

Columns: the stored override. Rows: what the engine computed for that player **in this league**.

| Engine label here (why) | → `cornerstone` | → `win_now` | → `rebuild` | → `depth` |
|---|---|---|---|---|
| `cornerstone` (starts, future) | cornerstone | **win_now** | cornerstone | **win_now** |
| `win_now` (starts, no future or past the cliff) | **cornerstone** | win_now | **cornerstone** | win_now |
| `rebuild` (bench, young with value) | rebuild | **depth** | rebuild | **depth** |
| `depth` (bench, old or cheap) | **rebuild** | depth | **rebuild** | depth |
| no label — borderline (inside the starter-line band) | no label | no label | no label | no label |
| no label — unprojected, or no line at his position | no label | no label | no label | no label |
| pick (`rebuild` by rule) | never overridden (the write route rejects pick ids) | | | |

**Scope (QB only).** A QB override applies only where its scope equals the league's QB format: a `superflex`
row changes that QB's label (per the table) in a superflex league and leaves it untouched in a single-QB league;
a `single_qb` row the reverse. An RB / WR / TE row (`all`) applies in every league. `league_profile` checks the
scope against the player's position and the league's slots (`override_scope`), and `with_label_overrides`
attaches only rows in a scope the league can see, so the digest moves only for leagues of the matching format.

Bold = the override changes the label. Everything else in the profile — `startable`, `future`, the starter
line, the margin, starters — is unchanged; a changed player's entry gains `engine_label` (the label before
the override) so the review page can show "engine: Win-now piece". A borderline or unprojected player keeps
no label: the engine does not know whether he starts here, and the override says nothing about that.

### 2.2 The page cannot ask for an incoherent move

Bands a selected player may be moved to: a starter (`startable` true) → Cornerstone or Win-now piece; a bench
player (`startable` false) → Rebuild piece or Depth; borderline / unprojected → none (his row is shown in "No
label", read-only, with the reason). A target chip is enabled only when it is legal for every selected
player. So what the founder places is exactly what the engine shows in this league; in other leagues the same
judgment lands on that league's starts axis per §2.1.

Moving a player back to the engine's own label here **clears** his override (deletes the row), which returns
him to the engine's label in every league. The page says so.

## 3. Storage

One new additive table, `founder_label_overrides` (`backend/database.py`), created by
`metadata.create_all` (no `migration_cols` row, no destructive migration):

| Column | Type | Meaning |
|---|---|---|
| `player_id` | String, PK | Sleeper player id (QB/RB/WR/TE). |
| `scope` | String, PK | `all` (RB / WR / TE) \| `superflex` \| `single_qb` (QB). One row per (player, scope). |
| `label` | String, not null | `cornerstone` \| `win_now` \| `rebuild` \| `depth` (closed vocabulary, `founder_review.LABELS`) |
| `set_by` | String, not null | the founder's account id (`sess["user_id"]`) |
| `set_at` | String, not null | ISO UTC; changes only when the label changes (an identical re-save is a no-op) |

Delete the row = back to the engine. Account deletion anonymizes `set_by` to `deleted_user` and keeps the
judgment (it is about an NFL player, not a person; deleting it would silently change engine inputs).

## 4. Engine wiring — one seam, digest-carried

- `server._season_evidence` (the one reader of stored forecasts, and the only producer of season evidence for
  the worker and the admin/founder label routes) reads every override row inside its existing `try` and
  calls `season_value.with_label_overrides(evidence, overrides)`.
- `with_label_overrides` (pure) keeps only override rows for players **projected in this league**
  (`evidence["players"]`) whose scope is `all` or this league's QB format, attaches them as
  `evidence["label_overrides"]` (`{player_id: {"label", "scope"}}`) and **recomputes `evidence["digest"]`**
  over the evidence including them. No relevant override ⇒ the same object back:
  byte-identical evidence, digest, request hash, cards.
- `league_profile` reads `evidence["label_overrides"]` and applies §2.1 where the entry's scope is the
  player's here (`override_scope(position, lineup slots)`). Every consumer reads the profile:
  revision 5's plan fit (`_season_lean`, `_mirror_fit`), the conflict rule (`plan_conflict` via
  `_season_signal`), the proof's `season_signal.assets[].label` that `trade_narrative.season_block` prints
  as label tags, and `rows_from_search` (the admin route and the founder page). One seam, same label
  everywhere.
- Cache safety: the request hash (`_owner_selected_assignment`) already joins `{"digest": …}` of the season
  evidence, and every proof records `starter_evidence.evidence_digest`; a changed relevant override moves the
  digest, so cached decks and stored pages keyed on the request hash never serve stale labels. An override
  for a player not in this league, unprojected here, or a QB override of the other QB format, does not join the
  evidence and moves nothing. An
  override on a projected but borderline player, or one equal to the engine label here, does move the digest
  (conservative: the profile that would tell is computed after the hash). The per-impression snapshot keeps
  only the offered assets' override rows, as it already does for `players`.
- `DECK_PIPELINE_VERSION` 27 → **28** (`_season_evidence` is a listed deck-pipeline function); pin in
  `DECK_PIPELINE_PINS[28]` and `FROZEN_PINS`. `season_value.py` is in the engine code hash already.
- Today nothing a user sees changes: revision 5 serves only when `owner_bilateral_revision_5_enabled` = 1
  (it is 0). The page exists so the founder fixes labels **before** it serves.

## 5. Routes and access

| Route | Purpose |
|---|---|
| `GET /api/founder/capability` | `200 {"founder_review": true}` for a founder session, else 404. The app shows the section only on this answer. |
| `GET /api/founder/labels?league_id=` | The page: rows for every rostered QB/RB/WR/TE in the league with engine label, effective label, stored override, the facts to judge by, band order, vocabulary, the summary; or empty rows with `evidence.reason`. |
| `POST /api/founder/labels` | `{league_id, set: {player_id: label}, clear: [player_id]}` in one request; idempotent. |

**Access (server-enforced, every route, 404 with no state change otherwise):** flag `founder.review` on AND
env `FOUNDER_ACCOUNTS` (comma-separated account ids) non-empty AND the request's session (by
`X-Session-Token`) is **verified** (`sess["verified"]`, the account-auth proof; a username-only Sleeper session
cannot pass, so typing the founder's Sleeper username grants nothing) and not a synthetic demo session AND
`sess["user_id"]` is in the list. Never a device id, a header other than the session token, or anything in
the body. Paywall classification: `FREE` (all three).

Write scope: the server derives it — a QB's override is written under the league's QB format (from the
season evidence's slots), anything else under `all`; the client never sends a scope. A write therefore needs a
usable forecast for the league (409 `no_usable_forecast` otherwise; the page has no rows then anyway).

Write validation: labels in the closed vocabulary; `set` ids must be QB/RB/WR/TE players in the league's player
pool (picks and unknown ids → 400 `unknown_player` listing them, nothing written); `clear` ids must be pool
players or have a stored row; an id in both → 400; at most 1,000 entries. The whole request is one
transaction.

## 6. Review summary (aggregates only)

Returned by the read route and shown under the board (per format for QBs, since the page is per league): per
position, `moved` (players whose label here differs
from the engine's) and `corrections` (`engine → founder` pairs with counts, most common first, e.g.
"Win-now piece → Cornerstone: 6"); plus `overrides_total` (rows stored, all leagues) and `overrides_here`.
It is the input for tuning the label rules (`FUTURE_FLOOR`, `past_cliff`, `young`, the margin) so overrides
do not accumulate forever. No player ids in the summary.

## 7. The page (mobile)

Calibration (`CalibrationScreen`) gains a two-segment control, **Grading | Founders' review**, rendered only
when `GET /api/founder/capability` answers 200 (query `['founder', 'capability', userId, revision]`, 404 =
hidden, no retry). Grading is unchanged and stays the default. The Calibration tab itself still appears only
when `grading.blind` resolves true (it is on for everyone today).

`components/founder/FounderLabelReview.tsx` (self-contained: it fetches) for the app's selected league:
position segments QB / RB / WR / TE; five bands in order **Cornerstone, Win-now piece, Rebuild piece, Depth,
No label** (`utils/founderReview.BANDS`, matching `founder_review.BANDS` server-side), each with a count; a
chip per player — name, NFL team, age, projected points a game, value, and a moved player's "engine: …"
note; the position's starter line above the bands. The QB segment names the format being edited — "QB
labels · Superflex leagues" or "QB labels · 1-QB leagues", from the read route's `qb_scope` — and one line says
the other format's QB labels are edited from a league of that format. No format switcher: the other format's
rows would need that format's league and forecast, which this page does not have (not trivial; not built).
RB / WR / TE carry one line saying their labels apply in every league. Tap players (multi-select), then a footer chip to
move them: the tier board's interaction (D-233, `RosterTierBoard` + `TierTargetChips`). **Reused:** the
interaction pattern (select-then-target, footer "Move to" row, VoiceOver "Move to …" actions per chip), the
chip construction (ink-1 cell, hairline, radius sm, 3px position rail, ice border + check when selected) and
`TickLabel` section headers. **Not reused as components:** both are typed on the eight-tier ladder and its tier
colour encodings; the label bands have no colour encoding, so a sibling `LabelBandBoard` copies the
construction rather than widening a shared component another flow depends on.

Footer: "N changed", **Save** (sends only changed players: back to the engine's label ⇒ `clear`, else
`set`), **Reset to engine** (the visible position's rows back to the engine label, locally; Save commits).
Empty state when the server returns no rows: the reason in words (no saved forecast, stale, not a Sleeper
league, …). No `FeedbackFAB` change (a tab-stack screen; RootNav covers it).

## 8. Analytics

None. The taxonomy governs events a client emits; this page emits none, and the founder's actions are
recorded in the table itself. Waived in scope.md §1.
