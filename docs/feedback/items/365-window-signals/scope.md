# Feature Scope — the window learns two new signals (#365 net firsts, #371 playoff odds)

**Date:** 2026-08-20
**Entry point:** in-app feedback **#365** (operator `mattmurf77`, v1.15.0, screen `TeamReview`) and
**#371** (same operator). Plan of record: `docs/feedback/items/364-team-review-fixes/plan-remaining.md`
§1 and §5, which specced both and deliberately left them unbuilt.
**Builder:** agent session `agent-a3ea3b1d38e084930` (worktree off `origin/main`)
**Operator sign-off on waivers:** yes — the operator pre-ruled the three open decisions the plan
doc left open (§7 below) and declared **full gates, not express**.

> **#365** — *"Window needs to do more than just age evaluation. I am all in for ffv3 league but
> it's identifying me as a rebuilder. We should look at signals such as number of 1sts owned vs
> traded away as one such signal."*
>
> **#371** — *"Coming back to the outlook bug, we should primarily use the playoff outlook value as
> the decision maker."*

---

## 0. The bright line, and how this build respects it

`infer_team_outlook` (`backend/trade_service.py:2546`) is **not** a Team Review function. Its verdict
feeds `outlook_alpha`, which the **trade engine** consumes (`backend/trade_gen_v2.py:986`,
`backend/trade_service.py:4250`), the **mock draft** reads (`backend/server.py:14013`), and the
**outlook seed** reads (`backend/server.py:5320`). Changing its score changes every deck for every
user.

So the build is arranged around one invariant, which is tested rather than asserted:

> **INV-365.** With `trade.outlook_net_firsts` OFF, `infer_team_outlook` returns a value that is
> equal — tuple, keys and floats — to what `origin/main` returns for the same inputs. Not
> "equivalent"; equal. The new kwarg is accepted and ignored, so even a caller that starts passing
> a ledger early cannot move a deck while the flag is down.

A second, stronger property falls out of the design and is also tested:

> **INV-365b.** With the flag ON but **no ledger supplied**, the score and the buckets are still
> unchanged. Only the Team Review route builds a ledger. The trade engine, the mock draft and the
> outlook seed pass four arguments as they always have, so lighting the flag moves the **window
> beat** and nothing else. Deck movement requires a *second*, deliberate change that this build
> does not make.

`trades.window_from_odds` (#371) never touches `infer_team_outlook` at all — it composes in the
route, after the heuristic has already run, and the heuristic's verdict is preserved in the payload
as `window.roster_inferred` no matter which path drives.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** The window beat's funnel is already instrumented:
  `team_review_beat_viewed` (`{league_id, beat, index}`, `analytics_taxonomy.py:1138`) and
  `team_review_action_taken` (`{league_id, beat, action}`, `:1140` — the outlook write on this very
  beat) fire today and are unchanged. Both new signals change **what the window beat says**, not
  which beats exist, so the beat sequence, the step indices and `meta.beats_skipped` are untouched.
  The before/after question — "does the user's declared outlook agree with the inferred one more
  often once the flag is lit?" — is answerable from `team_review_action_taken` split by flag cohort.
- [x] **(c) WAIVED for a `window_source` event property.** Adding a property to a live event
  mid-flight splits the existing series into NULL-valued and populated halves — the exact NULL-
  `platform` incident the gate exists to prevent. The payload already reports `window.source`, so
  the same question is answerable from a flag-cohort split without touching the taxonomy. If the
  operator later wants it as a property, it should be added as part of a taxonomy change with a
  backfill story, not smuggled in here.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** Both halves read data that already ships.
  `draft_picks.original_user_id` / `.owner_user_id` (`backend/database.py:1050-1052`) have existed
  since #158; the playoff band comes from the existing `outlook.odds` pipeline.

- **New/changed feature flags: two, both default OFF, independent of each other.**

  | Flag | Namespace reason | Gates | Default | Graduation criterion |
  |---|---|---|---|---|
  | `trade.outlook_net_firsts` | `trade.*` is the **engine** namespace, and this term lives inside `infer_team_outlook`. Naming it `trades.*` would understate the blast radius. | The net-first-round term in the score, the two new `model` keys, `signals.firsts`, and the route's ledger read | **false** | Operator confirms on real prod data that the term moves the right teams — see §7.1, where the local corpus argues it may not move the operator's own. **Do not graduate from inside a build session.** |
  | `trades.window_from_odds` | `trades.*` is the client-surface namespace (same as `trades.team_review`); this composes in the route and changes no engine value. | Whether the playoff band drives `window.inferred`, and the `source` / `roster_inferred` / `odds` / `odds_reason` block | **false** | Operator confirms the band-implied window reads true in a league with completed weeks. Sleeper-only by construction. |

  Registered in `backend/feature_flags.py` `FLAG_KEYS` (so `DEFAULT_FLAGS` makes them False) and
  written explicitly `false` in `config/features.json` with a rationale comment, per the file's
  existing convention. Documented in `docs/config-reference.md`.

- **Deploy-free rollback lever (ship-the-knob).** Both flags are hot-reloadable:
  `POST /api/feature-flags/reload` after editing `config/features.json`, or the `FTF_FLAGS` env var.
  **Neither requires a deploy, a client release, or a code revert.** In addition, either term can be
  neutered without touching a flag by setting its weight to zero in `model_config`
  (`infer_w_net_firsts = 0`), which leaves the payload shape intact and the contribution at exactly
  0.0 — useful if the operator wants the card to keep *showing* the ledger while it stops *scoring*
  it.

- **New `model_config` keys: two**, both reported to the client inside `window.model` per D-101
  (a new term that is not in that block is a term that lies on screen):

  | Key | Default | Meaning |
  |---|---|---|
  | `infer_w_net_firsts` | `0.10` | Weight of the net-first-round term. `0` disables the contribution while preserving the payload. |
  | `infer_net_firsts_cap` | `1.0` | Clamp on `net_share`, so one lopsided league cannot produce an unbounded term. |

  Calibration evidence for `0.10` is in §7.1. Documented in `docs/config-reference.md`.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-window-signals.js` (+ `npm run test:window-signals`).
      Pins the four client claims no typecheck or backend test can see:
      1. the screen never hardcodes a weight, a cut or an age threshold — every number in the window
         beat's arithmetic is read from `window.model` (D-101, generalised to the new term);
      2. the beat renders the net-firsts contribution **whenever it renders the term's inputs** —
         a shipped card that shows the ledger but omits it from the arithmetic is the exact defect
         D-101 was written to prevent;
      3. the "we do not read which picks you have traded away" sentence is **conditional** on the
         term being inactive — it is a lie the moment the flag is lit;
      4. the degraded case is *stated*, not silent: a `provenance` other than `observed` renders a
         reason string (operator decision 3).
- [x] **Unit tests:** `backend/tests/test_window_signals.py` — 21 tests, 9 sabotage-proven. Covers
      INV-365 (golden byte-identity against `origin/main` values), INV-365b, the ledger arithmetic,
      the three provenance states, the clamp, the band→window map, the preseason refusal, the
      non-Sleeper fallback, and the `window` payload's flag-off shape identity.
- [x] **Code-walk proof:** `docs/feedback/items/365-window-signals/code-walk.md`, file:line cited.
- [x] **Manual TestFlight checklist:** `docs/feedback/items/365-window-signals/testflight-checklist.md`.
      Runtime proof genuinely matters here: both flags change what a real user is told about their
      own team, and the odds path can only be exercised on a Sleeper league with completed weeks,
      which no unit test can stand in for.
- `testID`s added: `team-review.window.firsts` (the ledger card). No renames — every existing
  `team-review.*` testID is preserved, so `check-team-review.js` claim 4 keeps holding.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `GET /api/league/team-review` row — `window.signals.firsts`, the two new `window.model` keys, and the `window.source` / `roster_inferred` / `odds` / `odds_reason` block, each stated as present **only** under its flag |
| `living-memory/LLD.md` | n/a because | no convention shifted. The build *applies* two existing conventions — "a client reads an encoding, it never restates one" (D-101) and "degrade with the reason named" — rather than introducing one |
| `docs/architecture.md` | n/a because | no module wiring changed. `team_review.py` stays a pure composer; `infer_team_outlook` stays a pure function; no new module, no new dependency, no new I/O beyond one already-existing `load_draft_picks` call |
| `living-memory/HLD.md` | n/a because | no architecture shift — see the row above |
| `docs/cross-client-invariants.md` | **updated** | the band→window map is a shared encoding (the client must never re-derive "likely means contender"), and the `provenance` enum is a cross-client string |
| `docs/glossary.md` | **updated** | **net first-round capital** — new domain term appearing in code and on screen |
| `DECISIONS.md` entry | **updated** | **D-110** (net-firsts as a weighted, flag-gated, ledger-gated term) and **D-111** (odds inform the window, never replace the heuristic). IDs chosen at the operator's instruction from the D-110+ block, not `max+1`, because a concurrent sibling holds D-120+ |

## 5. Ship gate declaration

- **CI green on the committed tree:** `python3 -m pytest backend/tests -q`,
  `cd mobile && ./node_modules/.bin/tsc --noEmit`, every `mobile/tests/check-*.js`, and
  `mobile/scripts/testid-lint.sh`. Counts in `living-memory/TEST_LEDGER.md`.
- **Evidence recorded:** TEST_LEDGER entry naming the suites, the counts and the sabotage table.
- **TestFlight verification:** checklist written (§3); **owed by the operator**, and it is the gate
  on graduating either flag.
- **Express lane declared by the operator?** **No.** Full gates. The change touches feature-flag
  surface and an API contract, which the CLAUDE.md bright line puts outside "quick fix" anyway.
- **Not pushed, not merged.** Committed on this branch only; the operator integrates.

## 6. What is deliberately NOT in this build

- **Graduating either flag.** Both ship dark. Explicitly forbidden by the task.
- **Plumbing the ledger into the engine, the mock draft or the outlook seed.** Those three callers
  keep the four-argument call, which is what makes INV-365b true. Wiring them is a separate change
  with its own evidence and its own TestFlight pass — and it is the change that would actually move
  decks.
- **Moving `infer_contender_cut` / `infer_rebuilder_cut`.** Left where they are, per operator
  decision 1, and §7.1 found no data that argues they must move.
- **The other four items in `plan-remaining.md`** (#366 re-tier, #369 plan beat, #367's toggle,
  #370 repeats). Untouched.
- **`_bin_player`, `analyze_roster_strengths`, `_depth`, the `Depth` and `Plan` components.** Owned
  by a concurrent sibling session.

## 7. Open decisions the operator pre-ruled — and what the data says about them

### 7.1 "Net firsts enters the score as a weighted term" — kept, with a warning

**Kept.** The term enters the score (`score −= w · net_share`) rather than sitting beside it as a
`not_sure` tie-breaker. Behind the flag, this is the honest reading of the operator's ask: he asked
for a *signal*, and a tie-breaker that only fires in the middle band is not one.

**But the real data available locally does not support the premise, and this must be said.** The
only pick corpus reachable from this worktree is `data/trade_finder.db`. It holds round-1 provenance
for exactly two leagues, both named *Lakeview League*:

| League | R1 rows | `mattmurf77` own | held | traded away | acquired | **net** |
|---|---|---|---|---|---|---|
| `1101407304802574336` | 48 (2026–29) | 4 | 5 | **0** | 1 | **+1** |
| `1312076055586050048` | 48 (2026–29) | 4 | 5 | **0** | 1 | **+1** |

Two findings that contradict the plan doc's framing:

1. **In both leagues the operator has traded away zero of his own firsts and acquired one.** The
   signal he asked for, computed on his own data, points him *further toward rebuilder* — the
   opposite of the correction #365 asks for. The term is directionally correct as a model of intent;
   it simply may not be the thing misclassifying *him*.
2. **FFV3 — the league in the report — has no pick rows in the local DB at all**
   (`Fantasy Football Version 3`, ids `1312140920132497408` / `1181674778942836736`: zero
   `draft_picks` rows, and a 291-byte `roster_data` stub, so the local score cannot be recomputed
   either). In that league the term degrades to `provenance: "absent"` and contributes nothing.

Prod Postgres would settle both points and was **not** reachable from this session (the read was
denied by the sandbox). So: the term is built, tested and dark, and the flag's graduation criterion
is an operator check against prod — not a build-session claim. **This is the single most important
thing to read before lighting `trade.outlook_net_firsts`.**

**Weight and cap, from the same corpus.** Across the 24 member-league pairs above, `net` ranges
−3…+3 against an `own_total` of 4, so `|net_share| ≤ 0.75`. At `infer_w_net_firsts = 0.10` the
observed contribution range is **±0.075**, against a `not_sure` band 0.16 wide (±0.08). The term can
therefore move an extreme team one bucket and can never move any team two. That is the intended
authority: enough to matter, not enough to overrule the roster. The cap (1.0) binds only a team that
has traded away more firsts than it originally owned in the horizon.

**The cuts stay.** Nothing in the corpus argues they must move, and moving them would change the
flag-off world.

### 7.2 "#371 does not replace the heuristic" — kept

Kept exactly as ruled. `backend/outlook/league_state.py` registers ESPN, MFL and Fleaflicker as
`NotImplemented` stubs, so the odds engine is Sleeper-only, while the heuristic works anywhere a
roster exists. And `completed_weeks == 0` is the engine's weakest window (D-094, preseason skill
lower CI bound +2.9 %) — which is exactly when window-setting matters most. So:

- odds available **and** flag on **and** `completed_weeks > 0` ⇒ the band drives `window.inferred`,
  `window.source = "odds"`;
- otherwise ⇒ the heuristic drives, `window.source = "roster"`, and `window.odds_reason` names
  which of `odds_unavailable` / `preseason` applied;
- **either way `window.roster_inferred` carries the heuristic's verdict**, so the two definitions of
  "contender" are both visible in one payload instead of one silently replacing the other.

Flags are independent: `trade.outlook_net_firsts` and `trades.window_from_odds` may be lit in any
combination, and the four combinations are what the TestFlight checklist walks.

### 7.3 "Degrade honestly on the card" — kept

`provenance` is a three-valued cross-client string, never a silent zero:

| Value | Means | Card says |
|---|---|---|
| `observed` | at least one first-round pick in this league is recorded under a different owner than its original | the ledger, and the term's contribution |
| `none_traded` | rows exist, but no first is recorded as having moved — either nothing has been traded, or the history predates capture | states both possibilities and that the signal is not counted |
| `absent` | no round-1 rows for this league (ESPN without asserted picks, MFL crosswalk gap, demo, unsynced) | states the league has no pick records here |

The term contributes **0.0** in the latter two, and `applied: false` rides the payload so the client
never has to infer it from a zero.
