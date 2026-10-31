# Feature Scope — The app's value bar on the share card

**Date:** 2026-11-01
**Entry point:** direct ask. head-eng (2026-11-01), on the operator's call via head-product: "Let's just prioritize building and shipping now. The draft pick value is going in". It's the next priority after #511's "% fair" removal (`c2ec824f`), and models-lead and legal may flag concerns but don't hold it. Due before the 11-13 referral date.
**Builder:** eng-mobile/backend worker for league-eng, branch `build/share-card-value-bar`, **stacked on #511** (`fix/share-link-previews` @ `013eac18`).
**Operator sign-off on waivers:** pending, via head-eng. One waiver, §1 (c). The operator also reviews the card render (design rule, 2026-10-31, in parallel with release).

## Contents

- [What ships](#what-ships)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope-mandatory--hld--lld--api)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [Decisions](#decisions)

---

## What ships

The og trade card (`/og/trade/<token>.png`) draws the app's **TradeValueBar** in the band #511 freed between the panels (bottom y=455) and the footer rule (y=560). The package card (`/og/p/<id>.png`) does too, when its scoring format is known.

| Area | Change |
|---|---|
| **Verdict data** (`backend/server.py`) | A pure helper, `_consensus_verdict(give, recv, fmt, league_id=None)`, is pulled out of `_trade_evaluate_impl` so evaluate and the card share one code path. It uses the universal-pool consensus seed for `fmt`, prices league-owned picks by the league's slot order (`load_draft_picks` / `_league_slot_order` / `_priced_pick_value`), and runs `_consensus_packages` and `_fairness_v3`, then `_value_verdict_payload(give_value, receive_value, point_ratio >= 0.95)` in **market** stud-tax mode (the no-session default). **Never a user's private board.** Evaluate's output stays byte-identical. |
| **Routes** (`og_trade_card`, `og_package_card`) | They compute the verdict and pass it, plus pick display labels, into the renderer. `og_image` never imports `server`. Format: a trade match uses `get_league_scoring(match.league_id)`. A package uses an optional `?fmt=` (`1qb_ppr` / `sf_tep`, the `/og/tiers` pattern) on `/s/p/<id>` and its `og:image` URL. **No `fmt`, no bar**, so a superflex package is never priced as 1QB. |
| **Card** (`backend/og_image.py`) | It draws the bar per the mobile component (`mobile/src/components/TradeValueBar.tsx`):<br>• a 14px rail (`#232833`), the centre line (`#59647A`) and ±2nd ticks (`#262C35`);<br>• a fill from the centre toward the side the value favours, clamped at ±1 Mid 1st: `#22C55E` when the sharer wins, `#F59E0B` when they lose, a centred `#56D9EC` nub when even;<br>• the headline "Even" / "You win" / "They win";<br>• the pick-terms margin ("≈ a Mid 2nd", or "≈ 1.4 mid 1sts" when no single pick fits);<br>• a small "Values as of {date}" line.<br>Any space or wording design-lead's card spec changes is adopted when it lands. |
| **Picks on the card** | A draft pick on a shared trade or package showed as "Unknown player". Now owned picks (`{league}_{season}_{round}_{roster}`) and generic picks (`generic_pick_{r}_{tier}`) get display labels from the server and a neutral "PK" chip in ink/chalk. Draft capital never takes a position hex (`docs/cross-client-invariants.md`). Picks are priced in the verdict. |
| **"Values as of"** | `latest_value_snapshot_date(fmt, today)`: the date of the daily consensus value snapshot for that format. There's no schema change. It's computed at render time, and unfurlers cache their first fetch, so it's effectively the share-time snapshot. |

**Not in this PR:**
- the mobile half of `?fmt=`: the calculator share must append the format, which needs a binary, so it's update 1;
- a true share-time snapshot, which needs new columns, so it's out by head-eng's bright line;
- the user_b side reversal in `resolve_trade_share_token`, which is routed to #362 via head-eng.

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** not claimed.
- [x] **(c) WAIVED, no analytics needed:** a server-rendered image element on an unfurl card. An unfurler fetching a card isn't a user action we can attribute (the same reasoning as #511 §1). Surfaced to the operator via head-eng.

## 2. Schema & flag scope

- New or changed tables or columns: **none**.
- New or changed feature flags: **none**. It renders under the existing `growth.share_landing`. Rollback is a revert and redeploy, with no binary.
- New env vars or `model_config` keys: **none**.
- API surface: an optional `fmt` query parameter on `GET /s/p/<id>` and `GET /og/p/<id>.png`. There's no new route.

## 3. Evidence scope

- [x] **Unit tests (pytest), done:** `backend/tests/test_share_card_value_bar.py` (65) and `test_share_side_orientation.py` (3).
  - **Parity:** `_consensus_verdict` equals `POST /api/trade/evaluate` (7 trades × 2 formats, both directions), and evaluate makes exactly one `_consensus_verdict` call. **Evaluate is byte-identical:** 192 captured responses before and after the refactor (market, heavy and off; owned and generic picks; dropped ids; one-sided; `sf_tep`; thresholds 0.5 and 1.0).
  - **Bar:** lean to YOU GET or YOU GIVE, the clamp at ±1 first, the even nub, one neutral fill.
  - **Ticks** at the current Mid-2nd fraction (≈0.287, 600±155). A "≈ a Late 1st" fill ends past the drawn 2nd tick; a "≈ a Mid 2nd" fill ends within ±20px of it; ticks fall back to 600±308 without the fraction.
  - **Words:** the label and basis line per addendum 14, with the long and short basis branches. The render date is UTC, checked with a frozen clock across year ends.
  - **Picks:** labels and the neutral PK chip, with no "Unknown player".
  - **No bar** for an unpriced asset, an empty or zero side, or a package without `fmt`; `?fmt=` carries through `/s/p` into `og:image`.
  - **Descriptions and alt** follow the bar.
  - **No private-board read**, enforced by a test.
  - **The no-bar card is byte-identical to `013eac18`** (12/12 fixtures, plus the route).
  - Two caller registries are updated on purpose (`test_league_pick_value_alignment._SEAM_CALLERS`, `test_pick_assignment._SEVEN_READ_SITES`): the pick pricing moved from `_trade_evaluate_impl` into `_consensus_pricing`.
- **Runs:**
  - the 9 share files: 218 passed;
  - the 11 evaluate files: 328 passed;
  - full `backend/tests` (before the tick and date round): 10168 passed, 2 skipped;
  - `check_web_structure`: 196/196.
- **Sabotage runs, each caught:** flip `favors`; remove the clamp; drop the PK chip; ignore `fmt`; read a private board; change one evaluate field (17 red); hard-code 0.57 (6 red); yesterday's date (10 red); drop the side swap (2 red).
- [ ] **Unit tests (pytest), original plan:**
  - `_consensus_verdict` equals evaluate's verdict for the same ids and format (shared path);
  - the card draws the bar per verdict case: even nub, win fill right, lose fill left, clamp at ±1 first;
  - the pick-terms label and the "Values as of" line;
  - pick labels and the PK chip, with no "Unknown player" for picks;
  - the package card draws no bar without `fmt` and draws it with `fmt=sf_tep`;
  - no private-board read: the verdict is unchanged when a sharer's board differs;
  - sabotage per assertion.
- [ ] **Code-walk:** at the tip.
- [x] **Renders for the operator** (`renders/`, in the PR body): `card-even`, `card-win`, `card-loss` (clamped), `card-picks`, `card-5for1`, `card-package-sftep`, `card-package-nofmt` (no bar), and `card-nobar-unpriced`. Before is #511's no-bar card.
- [ ] **Operator checklist:** after deploy, share a lopsided trade and an even one; check the unfurl bar, the label and the date.
- `testID`s: none (server only).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `/s/p` and `/og/p`: optional `fmt`. `/og/trade` and `/og/p`: the value bar and pick labels. |
| `living-memory/LLD.md` | n/a | No new convention: the verdict helper is the existing shared-verdict rule, now reused by og. |
| `docs/architecture.md` | n/a | No module wiring change. og_image still renders from the data it's given. |
| `living-memory/HLD.md` | n/a | No new module, client or flow. |
| `docs/cross-client-invariants.md` | **updated** | § Trade value-verdict shape → Locations: `_consensus_pricing` / `_consensus_verdict` / `_share_value_bar` and `og_image._draw_value_bar`, plus the card's side-neutral words and the computed tick (the app's 0.57 drift noted). The neutral PK chip follows the existing draft-capital rule. |
| `docs/glossary.md` | n/a | No new term. |
| ADR or `DECISIONS.md` | **proposed, for the scribe** | The bar reverses I6's "no verdict on the public card" for the operator's value bar (head-eng, 2026-11-01). |

## 5. Ship gate declaration

- **CI green** on the pushed sha. **Evidence** in this file. The TEST_LEDGER entry at merge goes to release-lead's scribe.
- The operator's design review of the renders happens in parallel with release. The operator's merge go comes in release-lead's session, after #511.
- Express lane declared by the operator? **No.** Full gates.

## Decisions

1. **Stacked follow-up, not riding #511** (head-eng gave league-eng the choice). #511's meter-removal delta QA keeps moving, and this lands right behind it.
2. **Package cards without a known format draw no bar.** Pricing a superflex package as 1QB would be a wrong public verdict. `?fmt=` is the no-schema fix; the client half is update 1.
3. **Market stud-tax mode.** The card can't know the sharer's mode, and consensus means market. A sharer on heavy or off may see slightly different numbers in the app.
4. **The ±2nd ticks come from current values on the card. This reverses the first draft, which matched the app's `SECOND_IN_FIRSTS = 0.57`.** The worker's picks render showed "≈ a Late 1st" with the fill ending exactly on the "2nd" tick: since D-084, a Mid 2nd is 0.287 of a Mid 1st, not 0.57. A self-contradicting public card is worse than a card that differs from the app. The card now computes `e2v(Mid 2nd) / e2v(Mid 1st)` per render. The app's constant is flagged to head-eng as a separate fix (binary).
5. **The date is the render date (UTC), not the last value-snapshot date.** Legal allows render-time values only if the date shown is the day they were computed, and K-a2 says the date must never differ from the values drawn.
6. **Market stud-tax mode; pick labels without the original owner's name.** "2026 1st" is parsed from the pick id. A leaguemate's username doesn't go on a public image.
7. **No bar** when the format is unknown, a side is empty, any asset is unpriced, a side's value is ≤0, or anything raises (only the error type is logged). The page description and `og:image:alt` follow the image: a bar gets the bar line, no bar gets the fallback line (addendum 14 A).

## 2026-11-01 — K-a2: a stored snapshot at share time (operator: "Yes, add the column")

**Decision.** The operator approved the schema change in head-eng's session on 2026-11-01, on models-lead's K-a2 (a MUST) and legal R28.24's privacy MUST. It supersedes this scope's render-time value source, the "no schema change" line in §2, and decision 5 (the date).

**What changes:**
- **Schema:** a nullable `value_snapshot` TEXT (JSON) column on `trade_share_tokens` and on `shared_packages`. It's written once, at share time, from Mode A consensus only (`_consensus_verdict`, market mode).
  - **It stores:** `favors`, `firsts`, `label` (the pick equivalent), `format`, `league_id` (K-a7 pick pricing; null for packages), `computed_at` (UTC), `second_in_firsts`, and `pool` {`snapshot`, `version`}.
  - **It never stores:** a board, client-sent values, player values or totals, `gap.value` points, or usernames.
  - `shared_packages` stays anonymized: values, labels and the date only.
- **Mint:**
  - `POST /api/share/trade` computes the snapshot on the **sharer-oriented** lists, with the league's format and league id. A re-returned token keeps its original snapshot.
  - `POST /api/share/package` takes an optional `scoring_format`. The app doesn't send it yet (update 1), so package shares draw no bar until then.
  - **K-a6 at mint:** if any asset is unpriced, a side is empty, or a side values at 0 or less, no snapshot is stored, so no bar.
- **View:** `/og/trade` and `/og/p` draw ONLY from the snapshot and never recompute (a test patches the pricing to raise on view).
  - A share with no snapshot, which means every share made before this change, draws no bar, and its page uses the fallback description.
  - **The date is the snapshot's `computed_at` date**, which keeps legal's "absolute date matching the drawn values".
  - **The view-time `?fmt=` is removed** from `/s/p` and `/og/p`. The format lives in the snapshot, and a view must not price. That's a deviation from head-eng's note: the format moves into the mint request (`scoring_format`) instead of a view-time query parameter.
- **Ticks:** `second_in_firsts` is stored in the snapshot at mint, so the ticks match the values drawn.

**Docs table changes:**
- `docs/data-dictionary.md` is **updated** (the new column on both tables).
- `docs/api-reference.md` is **updated** (both mint routes, both og routes, `/s/p`).
- Account deletion and export coverage is updated for the new column.
- §2 now reads "one new column on two tables (operator-approved 2026-11-01)".

**The operator's colour decision (11-01, via head-product, "Green and amber"):** the single neutral fill is replaced by the app's mapping. Leaning to YOU GET is pos green, leaning to YOU GIVE is warn amber, and even is the ice nub. The constants are `og_image.SEMANTIC_POS` / `SEMANTIC_WARN` / `ICE_BASE`, citing `TradeValueBar.tsx` and `chalkline.ts`.

**Evidence:**
- **Migration:** the repo's own `_migrate_db` → `migration_cols` → `_add_missing_columns` → `_add_column_guarded` path. It inspects first; on Postgres it runs under the `lock_timeout` and `statement_timeout` guard. Fresh databases get the column from `create_all`, with no default and no backfill. Tested on an old-schema SQLite file with rows: exactly two `ALTER TABLE … ADD COLUMN value_snapshot TEXT`, and the old rows read NULL.
- **Pool identifier:**
  - `pool.snapshot` is the existing `vsn1` content hash (`roster_snapshot.values_snapshot_id`) of the consensus seed and the league's pick rows. It doesn't cover the DP pick-price file, a stated limit.
  - `pool.version` is `"evaluate-mode-a/market/market_slots"`. No code-version constant exists for this path; `value-core-4` belongs to the deck engine and would mislead.
- **Mint:** the trade snapshot is priced on the sharer-oriented lists (swapped for user_b), in the league's format, with owned picks. A re-share keeps its original snapshot. A package needs `scoring_format`, and with no league only generic picks price.
- **Deletion and export:** trade tokens are deleted with the sharer (the snapshot goes with the row) and exported with `value_snapshot`. Packages are anonymized and their snapshot stays, holding nothing that names the sharer. Covered by a new test.
- `test_share_card_value_bar.py` has 79 tests, all minting through the real routes.
  - **A view never prices:** pricing patched to raise on view still serves the bar from the snapshot.
  - A pool change after mint leaves the image unchanged.
  - A NULL or malformed snapshot draws no bar and uses the fallback description.
  - K-a6 at mint.
  - The snapshot's key set is pinned: no values, totals, gap points, ids or usernames.
  - The date comes from `computed_at`, not the view clock.
  - The pos/warn/ice mapping.
- **Runs:** share set 232; evaluate files 407 (192 golden responses still identical); deletion and data rights 75; full backend 10189 passed / 2 skipped; `check_web_structure` 196/196. The no-bar card is still byte-identical to `013eac18`.
- **Sabotage runs, each caught:** the view recomputes (17 red), a board read at mint, `gap.value` stored, the column dropped from the export, no NULL handling (17 red), the date from the view clock, and pos and warn swapped (5 red).
