# Feature Scope — Fit-first card copy (WS4, recommendation R11)

**Date:** 2026-11-10
**Entry point:** direct operator ask, [offer-learnings plan](plan.md) §3 WS4 ("I'm aligned. But the fit evaluation and description needs to be solid.")
**Builder:** WS4 builder session, branch `feat/fit-first-copy`
**Operator sign-off on waivers:** needed for §1 (analytics waived) — surfaced in the builder's report

Evidence behind it: [offer-history.md](../realtime-trade-engine/offer-history.md) finding 8. "Value too low" was the
least common reason managers gave for declining; direction, attachment and picks came first.

---

## 0. What a production card says today (the map that decided where this goes)

Production serves owner-only bilateral **revision 2** cards (`owner-v2-bilateral-2`,
`backend/trade_gen_bilateral_candidate.py`, which runs the shared survivor block in
`backend/trade_gen_bilateral.py::_generate_with_search`).

| Field | Set by | Serialized by `server.trade_card_to_dict` | Rendered by the app (`mobile/src/components/TradeCard.tsx`) |
|---|---|---|---|
| `narrative` | **nobody** on bilateral cards (`build_narrative` runs only in the legacy `trade_service` paths, `trade_service.py:5202`, `:6803`) | only when set, so absent | **never** — no mobile or web file reads `narrative` |
| `reasons` | survivor block, `trade_gen_bilateral.py:504-508`: only process caveats ("Closest alternative…", "Larger package…", "Other manager's preferences are unknown; fit uses market and team context.") | when `trade_math.human_explanations` (on) and non-empty | bullet list at the **bottom** of the card, after the value bar |
| `match_context` | `trade_gen_bilateral.py:510`: `owner_benefits`, `counterparty_benefits`, `counterparty_preference_evidence`, `support_kind` | reduced to `{owner_benefits}` for the bilateral arm (`counterparty_*` is private) | not rendered (only `opponent_surplus` is read, for the FB-47 partner-fit line, which bilateral cards never carry) |
| `basis` | `trade_gen_bilateral.py:502` | always | consensus note under the header when `consensus` |
| `lane` | `trade_gen_bilateral.py:503` | when set | not on the card |
| `give_value` / `receive_value` / `favors` / `gap` | survivor block from the proof's market terms | always | `TradeValueBar`, below the player sides |
| `selection_notice` | `_owner_public_selection` | partial selections only | under the header |

So the bilateral card carries **no copy at all about fit** today. Its only sentences are the
consensus note (when unranked), the selection notice, and process caveats at the bottom. The
value bar is the card's verdict. The frozen proof (`card.owner_evaluation`) holds everything a fit
sentence needs: both teams' outlook and its source, both teams' usable-depth proxy before and
after per position, and the market value of every asset.

**Where the change goes.** A pure composer in `trade_narrative.py` (`fit_lines`), called from
`trade_card_to_dict`, which adds a new key `fit_lines`. The app does not render `narrative` and
renders `reasons` last, so a backend-only change could not lead the card: the card component
gains one block under the header (plus the normalizer and wire type, which whitelist fields).
`TradesScreen.tsx` is untouched.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** the copy is behind a default-off flag and the
  operator grades it by TestFlight first. When it is turned on for an A/B, the existing
  `deck_impressions` / `deck_outcomes` rows plus the payload's `fit_lines[].code` are the join;
  a stamp of `FIT_TMPL_VERSION` into `features_json` would be the first addition, specced then.
  **Operator sign-off needed.**

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New feature flag: `trade.fit_first_copy`, default **false** — `backend/feature_flags.py`
  `FLAG_KEYS`, `config/features.json` (with `_comment_fit_first_copy`),
  `backend/tests/fixtures/flags/{release,profiles-on,onboarding-v2}.json`,
  `docs/config-reference.md` § Flags — Fit-first card copy. Graduation: the TestFlight checklist
  in §3 passes and the operator approves the wording.
- New env vars / `model_config` keys: none. Thresholds are module constants
  (`trade_narrative.FIT_*`), pinned by test. Rollback lever: the flag. The app double-gates on
  it, so turning it off hides lines already stored on a page without waiting for a rebuild.

## 3. The templates

One line per side at most, the other team's first. Per side the first template that fires wins:
**plan, then need, then surplus**. No line on a side means that side shows nothing new; no line
on either side means the card is byte-identical to today. There is no generic sentence.

Inputs (all from the frozen proof `card.owner_evaluation.as_dict()` unless noted):
`generator`, `eligible`, `assets[].id/market`, `viewer|counterparty.outlook`,
`.outlook_source`, `.benefits` (viewer only), `.usable_depth_before[pos]`,
`.usable_depth_delta[pos]`. Names, positions and ages come from the job's `players` map (the same
map the proof was built from). Gate: `generator == "owner_v2_bilateral"`, `eligible is True`,
and `evidence.matches(card)` (ids and market terms unchanged).

| Code | Wording (exact) | Fires when | Falls back when |
|---|---|---|---|
| `plan_rebuild.you` | `Fits your rebuild: you add {asset}.` | viewer `outlook` ∈ {rebuilder, jets}, `outlook_source == "declared"`, viewer `benefits` contains `outlook` (rev 1–2) or `future_pick_capital` (rev 3), and the viewer receives a pick or a QB/WR/TE at or under the generator's youth band (`trade_gen_bilateral._YOUNG`: QB 27, WR 25, TE 25). Names the highest-market qualifying asset | no plan benefit, or only young RBs / older players come back (the generator scores a young RB near zero for a rebuild) |
| `plan_rebuild.you_roster` | `Fits your rebuild-leaning roster: you add {asset}.` | as above with `outlook_source == "inferred"`: the window is the engine's roster read, so the line does not claim the viewer declared a plan | as above |
| `plan_win_now.you` | `Fits your win-now plan: you add {asset}.` | viewer `outlook` ∈ {contender, championship}, declared, plan benefit present, and the viewer receives a QB/RB/WR/TE whose `trade_service._now_lean(pos, age) ≥ 0.05` | as above |
| `plan_win_now.you_roster` | `Fits your win-now roster: you add {asset}.` | as above, inferred | as above |
| `plan_rebuild.them` | `Fits their rebuild-leaning roster: they add {asset}.` | counterparty `outlook` ∈ {rebuilder, jets} **and** `outlook_source == "inferred"`, **and** the public shape of the trade points their way: market-weighted now-lean of what they get minus what they give, over the trade's gross market, ≤ −0.05. Same asset rule as the viewer's rebuild line | a DECLARED counterparty outlook (never named), a shift short of 0.05, or no qualifying asset |
| `plan_win_now.them` | `Fits their win-now roster: they add {asset}.` | counterparty contender/championship, inferred, shift ≥ +0.05, and they receive a player with now-lean ≥ 0.05 | as above |
| `need.you` / `need.them` | `Upgrades your {pos} group with {name}.` / `Upgrades their {pos} group with {name}.` | side's outlook is not rebuilder/jets; at a position P where the side receives a QB/RB/WR/TE (named: the highest-market one there, age known), `usable_depth_delta[P]` is **more than** the proxy's backup credit for him (0.15 × market × `age_now_mult`) **and** at least 10% of `usable_depth_before[P]`. Highest relative lift wins | a bench-only addition, a lift under 10%, a rebuilding/tanking side |
| `surplus.you` / `surplus.them` | `Your {pos} group barely changes without {name}.` / `Their {pos} group barely changes without {name}.` | the side gives a QB/RB/WR/TE at P, receives nobody at P, `usable_depth_before[P] > 0`, and `usable_depth_delta[P]` is ≤ 0 and its drop ≤ 2% of before. Names the highest-market such player | a drop over 2%, or a same-position swap |

`{asset}` is `draft pick {name}` for a pick and `{name}, a {age}-year-old {pos}` for a player; a
player with no age never fills it. Template version `FIT_TMPL_VERSION = "fit-1"`; any reword
needs a bump (pinned by `test_template_table_and_version_are_pinned`).

**What "group" means.** `usable_depth_*` is the generator's own value proxy
(`trade_gen_owner._lineup`): the market value, scaled by age, of the players the lineup slots
would hold at that position plus 15% of the best backup. It is not projected points, so the copy
never says "starter" or "points"; revision 2's proof says the same
(`starter_evidence.state = "unknown"`).

**Privacy.** The other team's line uses only facts a viewer already has about a league-mate:
their roster, consensus values, ages, and the engine's roster read of their window (Team Review's
partners beat shows league-mates' inferred windows today). It never reads the counterparty's
`benefits` (their plan benefit uses their private board in revision 2), `intent`,
`preferences`, `preference_evidence`, `counterparty_personal` / `counterparty_preference`, or a
DECLARED outlook. `test_their_line_ignores_every_private_counterparty_field` mutates all of those
and requires an identical line. The existing route-level privacy assertions
(`test_bilateral_routes.py`, `test_bilateral_revision_routes.py`) stay green. Absence of a line
is not a claim, so suppressing a need line for a declared-rebuilding team leaks nothing.

## 4. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-fit-first-copy.js` (`npm run test:fit-first-copy`)
  — 8 checks: the flag read and the edited-card gate; the block sits under the header and before
  the standing-offer line, consensus note, Match strength, the player sides, the value bar and
  the reasons list; them row before you row; server text only (no `code` read, no literal copy);
  token styles; the optional wire type; the normalizer validates and omits an empty key; the npm
  script.
- [x] **Unit tests:** `backend/tests/test_fit_first_copy.py` (35 tests): every template's trigger
  and threshold edge, the declared/roster variants, side order and priority, the fallbacks
  (wrong generator, ineligible, missing or NaN market, missing depth, unknown or nameless asset),
  the private-field invariance, the pinned template table, serialization on real revision-2
  cards (flag off adds nothing and never calls the composer; flag on with no line is
  byte-identical; a card whose market terms no longer match its proof gets no line; payload
  lines equal the composer's), and registration in all mirrors.
- [x] **Sabotages** (each red, then green on revert): S1 need-lift-zero, S2 no-backup-guard,
  S3 need-for-rebuild, S4 surplus-drop-5pct, S5 surplus-ignores-replacement,
  S6 their-declared-outlook-named, S7 their-plan-from-benefits, S8 viewer-plan-without-benefit,
  S9 young-rb-rebuild, S10 roster-read-claimed-as-plan, S11 viewer-line-first,
  S12 need-before-plan, S13 any-generator, S14 win-now-lean-high, S15 reword-without-bump,
  S16 flag-ignored, S17 empty-list-serialized, S18 no-proof-match, S19 fixture-flag-missing;
  mobile M1 block-below-strength-bar, M2 flag-not-read, M3 viewer-row-first,
  M4 edited-card-shows-lines, M5 empty-key-sent.
- [x] **Code-walk proof:**
  1. Generation is untouched: no file under `backend/trade_gen_*.py` changed; the survivor block
     still sets `reasons` / `match_context` / `basis` / `lane` (`trade_gen_bilateral.py:502-513`).
  2. `server.trade_card_to_dict` (`server.py:20984-20992`) reads the flag and
     `evidence.matches(card)` inside the existing `if evidence is not None` block, reusing the
     already decoded `identity`; adds `fit_lines` only when the list is non-empty. Flag off:
     the branch is skipped and no key is written.
  3. `trade_narrative.fit_lines` (`trade_narrative.py:555`) loops them → you
     (`:580`) and picks plan → need → surplus (`:587`).
  4. `mobile/src/api/trades.ts:192-200` validates each line; `:296` spreads the key only when
     a line passed.
  5. `TradeCard.tsx:264-267` reads the flag and hides lines on an edited card; `:634-648`
     renders them right after the header, before `<StrengthBar` (`:729`), `<TradeValueBar`
     (`:966`) and the reasons list (`:1003`).
  6. Stored pages: `trade_narrative.py` is in `_ENGINE_CODE_MODULES`, so this change moves every
     page's engine version and stored first pages rebuild on deploy (expected). The flag is not
     part of the page key: after turning it on, lines appear on decks generated from then on;
     after turning it off, the client gate hides any stored line at once.
- [x] **Manual TestFlight checklist** (operator, with `trade.fit_first_copy` on via `FTF_FLAGS`
  plus `POST /api/feature-flags/reload`, then a fresh deck):
  1. Open Trades in a league where the bilateral owner engine serves the deck. On the top card,
     a "Fits their…/Upgrades their…/Their … barely changes…" line, when present, sits directly
     under "Trade with @name", above Match strength and the player sides. A "your" line, when
     present, is below it. The value bar is still below the sides.
  2. Every line names a player or pick that is on the card, on the correct side ("they add X":
     X is under YOU SEND; "you add Y": Y is under YOU GET; "without Z": Z is on the giving side).
  3. No line ever says "good fit", carries an emoji or an exclamation mark, or mentions a
     league-mate's declared outlook. For a league-mate who has set an outlook in the app, their
     card carries no "Fits their … roster" line.
  4. Swap a player on a card (edit): the fit lines disappear, like Match strength.
  5. Turn the flag off and reload flags in the app (relaunch): the lines disappear from the same
     cards without regenerating the deck. The rest of the card is unchanged.
  6. A card with no lines looks exactly as before the build.
- `testID`s added: `trade-card.fit-lines`, `trade-card.fit-line.them`, `trade-card.fit-line.you`
  (`mobile/scripts/testid-lint.sh` passes).

## 5. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | trade card payload: the optional `fit_lines` key |
| `living-memory/LLD.md` | n/a because no schema, route or invariant convention shifted; one optional payload key under an existing route |
| `docs/architecture.md` | n/a because no module wiring changed: `trade_card_to_dict` calls a pure function in an existing module |
| `living-memory/HLD.md` | n/a because no architecture shift |
| `docs/cross-client-invariants.md` | n/a because web and extension ignore the key; the codes are not a client enum (the card never switches on `code`) |
| `docs/glossary.md` | updated | "Fit line (fit-first copy)" |
| `docs/config-reference.md` | updated | § Flags — Fit-first card copy |
| ADR or `DECISIONS.md` entry | updated | `living-memory/DECISIONS.md` D-219: the other team's line uses public facts only |

## 6. Ship gate declaration

- **CI green:** `backend-tests` is expected RED on `test_deck_pipeline_digest` only:
  `trade_card_to_dict` is in `server.DECK_PIPELINE_FUNCTIONS`. Left red on purpose for the
  coordinator's single integrated `DECK_PIPELINE_VERSION` bump (new digest at this commit:
  `d4dab1ecbc0dfc1b`). `mobile-typecheck` (tsc + all `check-*.js`) and `maestro-testid-lint` pass.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** checklist above, run by the operator before the flag is lit.
- Express lane declared by the operator? no.
