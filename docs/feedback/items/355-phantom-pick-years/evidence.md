# Evidence — feedback #355, phantom draft-pick years

All readings taken 2026-08-19. Prod database accessed **read-only** (`SET TRANSACTION READ ONLY`,
SELECT only) via `DATABASE_URL_PROD`. Sleeper reads are the public, zero-auth v1 API.

## 1. What the real horizon is, and how it is derived

**Rule: a Sleeper league carries exactly three consecutive rookie classes, anchored to the first
class that has not yet been drafted.** The window *rolls* — it is not `current_season + N`.

Live probe of every Sleeper league present in prod:

| League | league `season` | draft status | traded-pick seasons reported |
|---|---|---|---|
| `1312140920132497408` (operator) | 2026 | `pre_draft` | 2026, 2027, 2028 |
| `1338231586314780672` | 2026 | `pre_draft` | 2026, 2027 |
| `1312076055586050048` | 2026 | `complete` | 2026, 2027, 2028 |
| `1312146456701829120` | 2026 | `complete` | 2026, 2027, 2028 |
| `1312583962966650880` | 2026 | `complete` | 2026, 2027, 2028, **2029** |

The last row is the load-bearing one. Absence of a traded 2029 pick only proves nobody traded one;
**presence proves the class exists.** A post-draft league reporting real 2029 traded picks, while
no pre-draft league reports any, pins the rule at both ends:

* draft not yet held ⇒ classes are `season, season+1, season+2` (2026-2028; **2029 is phantom**);
* draft complete ⇒ the anchor advances ⇒ `season+1, season+2, season+3` (2027-2029; **2029 is real**).

Per platform:

* **Sleeper** — derived as above, from data we already fetch: `_fetch_sleeper_league_meta` gives
  `season`, `_fetch_sleeper_drafts` gives the completion verdict (both already read by
  `_sync_sleeper_owned_picks` for #228), and `_fetch_sleeper_traded_picks` supplies the
  existence-proof seasons. **No new network call.**
* **MFL** — *not exposed.* MFL publishes the actual grid via the `futureDraftPicks` export
  (`backend/mfl_service.py:680` `parse_future_picks`), stored raw in
  `leagues.platform_future_picks`. Prod confirms the enumeration is real, not synthesised: the one
  MFL league holds 2027 and 2028 only.
* **ESPN** — *not exposed, because there is no source at all.* `git grep` finds no pick fetch in
  `espn_service.py` or `espn_write.py`, and prod holds zero ESPN rows in `draft_picks`. ESPN
  leagues get picks only through the manual assignment grid — see Q-022.

## 2. The phantom rows in prod

`draft_picks` season distribution by platform:

| platform | 2026 | 2027 | 2028 | 2029 |
|---|---|---|---|---|
| sleeper | 140 | 284 | 284 | **284** |
| mfl | – | 56 | 56 | – |

Per-league span, which shows the pre-draft/post-draft split exactly as predicted:

| League | grid span | verdict |
|---|---|---|
| `1312140920132497408` | 2026-2029 | **one phantom class** (pre-draft) |
| `1338231586314780672` | 2026-2029 | **one phantom class** (pre-draft) |
| `11896` | 2026-2029 | not a live Sleeper league (no API record) — legacy/test rows |
| `1312076055586050048` | 2027-2029 | correct |
| `1312146456701829120` | 2027-2029 | correct |
| `1312583962966650880` | 2027-2029 | correct |

Every league whose grid starts at 2027 is already right, because #228's exclusion shifted its
anchor by one. Only the pre-draft leagues over-reach.

## 3. How many served cards were unactionable

Over all 2,651 `deck_impressions` rows carrying `assets_json`, counting a card as polluted when it
contains a pick whose year falls outside its own league's derived horizon:

| Measure | Count | Share |
|---|---|---|
| Impressions with `assets_json` | 2,651 | — |
| …containing at least one pick | 1,459 | 55.0% |
| **…containing an out-of-horizon pick** | **339** | **12.8% of all cards, 23.2% of pick-bearing cards** |
| Phantom pick mentions | 360 | all of them 2029 |

All 339 are in the operator's league `1312140920132497408`, which is also the only league with
meaningful deck volume (1,932 impressions).

Concentration by day — the defect was exercised hardest in exactly the window after D-079 made
round-1 picks flat across years:

| Day | polluted cards served |
|---|---|
| 2026-08-16 | 12 |
| 2026-08-17 | 144 |
| 2026-08-18 | 118 |
| 2026-08-19 | 65 |

## 4. How much of the like/pass signal this polluted

Joining `deck_outcomes` to `deck_impressions` (845 recorded outcomes):

| Action | total | on a phantom-pick card | share |
|---|---|---|---|
| `viewed` | 429 | 52 | 12.1% |
| `pass` | 298 | 47 | 15.8% |
| `like` | 104 | 7 | 6.7% |
| `not_interested` | 14 | 3 | 21.4% |
| **all** | **845** | **109** | **12.9%** |

**~13% of all recorded preference signal was collected on offers the user could not have
executed**, and essentially all of it since 2026-08-17.

The skew matters as much as the volume: phantom cards drew **6.7%** of likes but **15.8%** of
passes and **21.4%** of not-interested. The user was rejecting them at roughly 2-3x the rate he
liked them. Two consequences worth stating plainly:

1. Any model trained or tuned on this window has learned "picks get passed on" partly from cards
   that were rejected for being nonsense, not for being bad trades — so **pick-bearing cards are
   under-valued** by that signal.
2. The pass-rate for this window is not a clean read of trade quality and should be treated as
   contaminated when it is used as a bake-off or propensity baseline.

## 5. Reproducing

Sleeper (no auth):

```
https://api.sleeper.app/v1/league/<league_id>
https://api.sleeper.app/v1/league/<league_id>/drafts
https://api.sleeper.app/v1/league/<league_id>/traded_picks
```

Prod (read-only; DSN from the gitignored `secrets.local.env`, never echoed): the counting query
parses `deck_impressions.assets_json`, matches pick ids against
`^<league>_<season>_<round>_<slot>$`, and compares the season against the horizon table in §1.
