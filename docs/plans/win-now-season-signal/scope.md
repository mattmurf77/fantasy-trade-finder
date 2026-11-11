# Feature Scope — Win-now season signal (first shippable slice)

**Date:** 2026-11-11
**Entry point:** direct operator ask ("If I'm win now, how does the generator know which RBs to
suggest to me?"), research `docs/research/window-asset-identification/`, operator decisions of
2026-11-11 ([README](README.md))
**Builder:** not started; work items in the [build plan](build-plan.md)
**Operator sign-off on waivers:** not needed (no waivers). Express lane: not declared, and not
available: this touches a card payload, flags and `model_config`.

**The slice.** Bilateral revision 5 (`owner-v2-bilateral-5`) built dark: season evidence captured
per owner job; the viewer's lineup scored in projected points for All-in and Contending teams; the
label table as the plan-fit input; candidate seats by label; the plan-conflict rule (flag,
push-down, sentence) for all four saved plans; seller–buyer matching behind its own knob; the card's
season line and labels; the operator's label review tool; a Calibration round. Nothing serves until
the gates in [validation](validation.md) pass.

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events and records cover it:**

  | Question | Existing record |
  |---|---|
  | What did a served card carry (engine, season numbers, labels, conflict)? | the frozen owner proof stored with each `deck_impressions` row (new `season_signal` field inside it) |
  | Do users like, pass or send season-positive cards more? | `swipe_decisions`, `trade_proposals`, joined to impressions |
  | Does "wrong for my window" fall? | `trade_pass_layer1` / `trade_pass_layer2` (reason `fit_outlook`); Calibration tag `wrong_for_my_window` |
  | Was a card seen? | `trade_card_viewed`, `deck_card_viewed` (unchanged) |
  | How often is the forecast usable? | one server log line per owner job (`season-signal: …`, counts only) |

  The card's new lines are display only: no tap target, so no client event. A later tap target
  needs a tracking-plan addendum first.
- [ ] (c) Waived: not applicable.

## 2. Schema & flag scope

- **New or changed tables or columns:** none. The owner proof (JSON inside impression features)
  gains a `season_signal` object under revision 5 only; `docs/data-dictionary.md` gets a note on
  that field. `grading_sessions.round_id` gains a value, `outlook-v2-v5-1`.
- **New feature flags** (`config/features.json`, `backend/feature_flags.py` `FLAG_KEYS` and
  `DEFAULT_FLAGS`, the flag fixtures under `backend/tests/fixtures/flags/`,
  `docs/config-reference.md`):

  | Flag | Default | Graduation |
  |---|---|---|
  | `trade.season_signal` | false | on for stage A once the worker tests and the byte-identity tests pass; stays on |
  | `grading.season_round` | false | a measuring tool; on for stage B, off after the read |

- **New `model_config` keys** (`database._MODEL_CONFIG_DEFAULTS`, `trade_service._DEFAULT_CFG`,
  `docs/config-reference.md`):

  | Key | Default | Role |
  |---|---|---|
  | `owner_bilateral_revision_5_enabled` | 0 | the serving selector; exactly 1 selects revision 5 |
  | `season_conflict_demotion` | 0.10 | the push-down; 0 keeps the flag and sentence without it |
  | `season_partner_matching` | 0 | 1 = stage 2 |

- **New env vars:** none.
- **Ship-the-knob, deploy-free rollback:** `owner_bilateral_revision_5_enabled = 0` through
  `PUT /api/admin/config/<key>` returns every deck to revision 2. `trade.season_signal` false plus
  `POST /api/feature-flags/reload` stops the read. Both are independent.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-season-signal.js` (+ `npm run test:season-signal`)
  pins: the normalizer accepts `season_block` only at `v === 'season-1'` and drops anything
  malformed; the card renders the season line, conflict sentence and label text verbatim from the
  payload (no client-side wording or arithmetic); both hide on an edited card; the fit block's
  `fit-2` handling is untouched; the three `testID`s exist; no emoji, gradient or new colour token.
- [x] **Unit tests** (each proven red against a named sabotage, [lld §10](lld.md#10-invariants-and-their-tests)):
  `backend/tests/test_season_points.py`, `test_season_value.py`,
  `test_trade_gen_bilateral_season.py`, `test_season_copy.py`, `test_season_signal_worker.py`,
  `test_calibration_season_round.py`; `test_deck_pipeline_digest.py` (new pin);
  `test_trade_first_page.py` extended at the join.
- [x] **Code-walk proof** (to be written by the builder, file:line-cited, in the build notes):
  (1) an installed build shows the new You lead with no app change: the server sends
  `lead.text`, the normalizer keeps any `lead.code` (`mobile/src/api/trades.ts:197-202`), the card
  prints `lead.text` (`mobile/src/components/TradeCard.tsx:703`); (2) with no usable forecast,
  every override in revision 5 returns `super()`'s value, traced method by method; (3) the
  penalty is applied after `utility` is computed (`trade_gen_bilateral.py:244`), so it cannot
  reject.
- [x] **Manual TestFlight checklist:** draft in the [build plan §4](build-plan.md#4-manual-testflight-checklist-draft).
  Runtime proof matters here: the copy is server-composed and league-dependent.
- [ ] Waived: not applicable.
- `testID`s added: `trade-card.season-line`, `trade-card.season-conflict`,
  `trade-card.asset-label.<id>` (must pass `mobile/scripts/testid-lint.sh`).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | to update | trade card payload: `season_block`, new fit-block lead codes; `GET /api/admin/season-signal/labels`; Calibration `round_id` value |
| `living-memory/LLD.md` | to update | "bilateral revisions are mixins over a search; a revision's inputs travel on the owner context and are popped from hashes when dark" |
| `docs/architecture.md` | to update | bilateral revision 5; `season_value.py`, `league_projections/season_points.py`; the forecast now has a second reader |
| `living-memory/HLD.md` | to update | the trade engine reads the saved league forecast (a new data flow between two features) |
| `docs/cross-client-invariants.md` | to update | label strings (`Win-now piece`, `Cornerstone`, `Rebuild piece`) and the `season-1` payload version: server-composed, never re-derived by a client |
| `docs/glossary.md` | to update | season value, starts for you, starter line, win-now piece, cornerstone, rebuild piece, plan conflict, season evidence |
| ADR or `DECISIONS.md` | to update | one ADR (next free number): "the deck reads this-season projections for win-now teams; labels are an engine input"; `DECISIONS.md` entries for the three operator decisions of 2026-11-11 |
| `docs/config-reference.md` | to update | two flags, three knobs |
| `docs/data-dictionary.md` | to update | note on the proof's `season_signal` field and the new round id; no column change |
| `docs/runbook.md` | to update | "season signal reads `unavailable`": the reasons table and what each means |
| `docs/integrations/` | n/a because no new external call: the Sleeper projections are fetched by the existing forecast capture |
| `docs/plans/README.md` | updated | row added with this folder |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) +
  `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`: the named-sabotage results, the replay
  numbers against the bars in [validation §3.4](validation.md), the label review counts, the
  Calibration read.
- **TestFlight verification:** the checklist, run by the operator, outcome in TEST_LEDGER. Stage A
  and B change nothing a user can see, so they ship without it; stage C needs it.
- **Pre-push hook:** `FTF_SKIP_SIM_GATE=1` (D-056 standing posture), with the evidence above named
  in its place.
- **Express lane declared by the operator?** No.
