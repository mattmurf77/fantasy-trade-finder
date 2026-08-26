# LLD — Counterparty breaker (draft A, implementer lens)

**Date:** 2026-08-21 · **Status:** DRAFT for cross-review.
Sits under [PLAN.md](../PLAN.md) (AMENDED, authoritative) and [HLD.md](../HLD.md)
(CONVERGED — this draft does not contradict it; where the HLD deferred, §9 flags every ruling
made here). Register precedent: [../../fit-challenger/LLD.md](../../fit-challenger/LLD.md).
**Rule of citation:** every symbol and line anchor below was re-verified against this checkout
(`claude/counterparty-breaker-plan` planning worktree, 2026-08-21). Line numbers drift;
re-cite at build (PLAN A-3 discipline).
**Operator ruling honored throughout: NO ghost cards, full stop.** Nothing in this LLD creates,
reads, or measures ghost impressions; the ghost-split code path is treated as an inert code
location only (§1.2).

Contents:
§0 Scope & Reference · §1 Interfaces & API · §2 Data Structures & Schema · §3 Core Logic ·
§4 Knob table (25 keys) · §5 Error Handling & Edge Cases · §6 Backward Compat & Migration ·
§7 Testing · §8 Calibration-readout spec skeleton · §9 Open Questions

---

## 0. Scope & Reference

### 0.1 What this LLD specifies

One new module `backend/trade_breaker.py` (evaluation layer, leaf), one new pure template
function in `backend/trade_narrative.py`, four surgical edits in `backend/server.py` (seam
block, features block, serialization block, nothing else), 25 `model_config` knobs, two flags,
one mobile card element, one structural guard, and the full test list. No new tables, no new
routes, no migrations (`breaker_` table prefix stays reserved-unused).

### 0.2 Verified anchor table (the build re-cites all of these)

| Symbol | Location (this checkout) |
|---|---|
| `_DEFAULT_CFG` head / five-registration discipline comment / `_cfg` | `backend/trade_service.py:40` / `:890-898` / `:966` |
| `_c` knob accessor | `trade_service.py:1004` |
| `elo_to_value` / `package_value_v2` | `trade_service.py:1267` / `:1298` |
| G6 predicates: `overpay_ok` / `pos_net_ok` / `pick_gap_ok` / `need_gate_ok` | `trade_service.py:1869` / `:1891` / `:1916` / `:1950` |
| `_POS_TIER_CUTS` (12-team assumption) | `trade_service.py:2071-2076` |
| `analyze_roster_strengths` | `trade_service.py:2211` |
| `_now_lean` | `trade_service.py:2648` |
| `infer_team_outlook` (INV-372b docstring; score+cuts) | `trade_service.py:3084` (invariants `:3166-3175`; cuts `:3313-3318`) |
| `LeagueMember` / `League` | `trade_service.py:3613` / `:3753` |
| Engine's declared-else-inferred partner-outlook resolution (the shape §3.2 mirrors) | `trade_service.py:4948-4956`; same shape `trade_gen_v2.py:982-989` |
| `waiver_slot_cost` default 425.0 | `trade_service.py:184` |
| `_consensus_packages` / `_pos_counts` / `_feasible_after` / `_subset_pos_delta` / `_starters_at` | `trade_optimizer.py:99` / `:150` / `:161` / `:180` / import `:57` |
| `_opponent_frame` (thresholds) / `build_narrative` / honesty comment / 2-sentence cap | `trade_narrative.py:86` (`:94-99`) / `:103` / `:119-125` / `:168` |
| `stamp_fit_diag` (stamp-shape precedent) | `trade_gen_fit.py:857` |
| `_served_cards` | `server.py:4007` |
| `_log_deck_signal_impressions` def / bakeoff features guard / fit keys | `server.py:4020` / `:4193` / `:4205-4206` |
| `_run_trade_job` / prefs load / `opponent_outlooks` build | `server.py:5412` / `:5482-5486` / `:5516-5527` |
| M3 fit_diag stamp block | `server.py:5698-5716` |
| Mutation stack: F7 split / likes-you / F3 / `_order_deck` / F7 wildcard / F9 | `server.py:5722-5725` / `:5748` / `:5794` / `:5900` / `:5926+` / `:5966-6029` |
| **The seam**: end of F9 block → `served_final = final_cards` | insertion immediately before `server.py:6030` (comment) / `:6034` |
| Ghost split (inert under the ruling) / impressions call / signal_v2 republish | `server.py:6036-6046` / `:6101` / `:6115-6128` |
| `trade_card_to_dict` / fit serialization block | `server.py:10976` / `:11055-11060` |
| co-owner `league_members` keying comment ("keyed on the primary owner's id") | `server.py:16972-16975` |
| `co_owner_ids` / `owns_roster` | `backend/sleeper_roster.py:34` / `:61` |
| `_MODEL_CONFIG_DEFAULTS` / `set_config` / `save_deck_impressions` | `database.py:2188` / `:4191` / `:5503` |
| `PASS_REASON_LAYER2` (the vocabulary anchor) | `database.py:5579-5583` |
| `ASSET_PREF_LISTS` / `load_asset_preferences` | `database.py:8657` / `:8660` |
| `FLAG_KEYS` / `DEFAULT_FLAGS` / `FLAGS` proxy | `feature_flags.py:47` / `:939` / `:1082` |
| Precedent tests: `test_fit_diag_inert` / `test_organic_never_imports_fit` / `test_impressions_uniform_columns` | `backend/tests/test_trade_gen_fit.py:681` / `:883` / `test_bakeoff_serving.py:1170` |
| `_PINNED_KNOBS` / inventory guard | `test_bakeoff_arm_a_golden.py:471` / `:546-547` |
| Mobile mount region (fitLine row → consensus-note) | `mobile/src/components/TradeCard.tsx:452-478` (narrative comment `:437`) |

### 0.3 Import discipline (binding, from HLD §2.2)

`trade_breaker` imports `from . import trade_service as ts` and
`from . import trade_optimizer as topt` — MODULE imports (fit T1 discipline), every symbol
reached as `ts.<name>` / `topt.<name>` at call time so knob rebinds and monkeypatches
propagate (`test_breaker_binding_sabotage`, §7.1). It **never** imports `trade_gen_fit`
(organic-isolation contract stays intact; the them-lens number is read off `card.fit_diag`,
never rescored — HLD D-3), never imports `server`, never calls `_shrink_user_elo` (T3: raw
boards only). `trade_service` never imports `trade_breaker`. The only production caller is the
§1.2 seam block (`test_flag_off_never_imports_breaker`).

---

## 1. Interfaces & API

### 1.1 `backend/trade_breaker.py` — public surface

```python
"""trade_breaker.py — counterparty-breaker evaluation layer (v1: stamp + narrate).

Spec: docs/plans/counterparty-breaker/{PLAN,HLD,LLD}.md.

Predicts the counterparty's most likely decline reason for every SERVED card,
in the shipped trade_pass_reasons layer-2 vocabulary (database.py:5579-5583)
plus the one registered extension `roster_crunch` (producer=breaker).

BOUNDARIES (all test-enforced):
  * evaluation only — never reorders, filters, or mutates any existing card
    field; the ONLY writes are the new attributes card.breaker /
    card.breaker_shadow (test_breaker_inert, test_breaker_zero_ordering_effect)
  * raw boards only — member.elo_ratings / the job's raw viewer map; this
    module must never import or call _shrink_user_elo (T3)
  * one production caller: the server.py post-mutation-stack seam. Never
    imported by trade_service, any generator, or bakeoff_runner (D-11 grep
    guard). Never imports trade_gen_fit (their-lens read via card.fit_diag).
  * no DB writes, no HTTP, no LLM, no RNG, no wall clock in any verdict
    (NFR-4; `ms` is diagnostics, never an input).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from . import trade_service as ts        # T1 — MODULE import
from . import trade_optimizer as topt    # T1 — same discipline

logger = logging.getLogger(__name__)

#: Pinned evaluator version — stamped into every breaker/breaker_shadow
#: payload AND hardcoded as a literal in the server rung-5 handler
#: (test_rung5_marker_version_pinned keeps the two equal). Bump on ANY change
#: to predicates, severity math, floors semantics, evidence shapes, or the
#: format envelope. Calibration readouts filter on this alone (HLD §5.5).
BREAKER_VERSION = "brk-1"

#: The v1 objection classes, in pass order (§3.4). Closed set = the 9 coded
#: PASS_REASON_LAYER2 codes minus other_text, restricted to the 6 evaluated
#: in v1, plus the registered extension. producer=breaker for all seven
#: taxonomy rows this plan contributes; emitting a producer=negmem code
#: (shape_aversion) is a defect (test_breaker_vocabulary_closure).
PASS_1_CLASSES = ("fit_outlook", "fit_duplicate", "value_giving",
                  "other_player_keep")
PASS_2_CLASSES = ("fit_new_weakness", "roster_crunch")     # feasibility tier
ALL_CLASSES = PASS_1_CLASSES + PASS_2_CLASSES

#: Classes whose evidence is public-observable and therefore ever
#: narration-ELIGIBLE (HLD D-6 whitelist). other_player_keep is permanently
#: dark in v1; value_giving is eligible on the consensus basis ONLY
#: (board-basis value_giving is narration-ineligible outright, D-7).
NARRATABLE_CLASSES = frozenset({"fit_outlook", "fit_new_weakness",
                                "fit_duplicate", "value_giving",
                                "roster_crunch"})

#: Depth-based classes gated by the format envelope (§3.7).
ENVELOPE_CLASSES = frozenset({"fit_new_weakness", "fit_duplicate",
                              "roster_crunch"})
```

```python
def stamp_breaker(
    cards: list,                         # the post-mutation-stack served list
    *,
    league: ts.League,                   # g_league
    players: dict,                       # players_dict
    seed_elo: dict[str, float],          # seed_map
    scoring_format: str,                 # active_format
    league_id: str,
    viewer_user_id: str,                 # g_user_id
    viewer_roster: list[str],            # _generate_kwargs["user_roster"]
    viewer_elo: dict[str, float],        # elo_map_rt — RAW (T3); shadow board
    viewer_outlook: str | None,          # outlook_value (declared or #8-seeded)
    declared_outlooks: dict[str, str] | None = None,  # opponent_outlooks (may
                                         # be empty when trade.outlook_infer is
                                         # off — PartnerContext then resolves
                                         # declared prefs itself, §2.2)
    pick_shares: dict[str, float] | None = None,      # opponent_pick_shares
) -> None:
    """Evaluate every card from the counterparty's seat and set
    `card.breaker` (+ `card.breaker_shadow` when breaker_shadow_run >= 1).
    Attribute-setting only; no return; two deck-wide passes under
    breaker_ms_budget with the §5 degradation ladder. EVERY card leaves this
    function carrying the attribute — scored payload or minimal marker;
    absence is impossible by construction (M4 pattern)."""
```

```python
def compose_narration(cards: list, *, players: dict) -> None:
    """Deck-level narration pass (flag trade.breaker_narrative, checked at the
    CALLSITE — this function assumes it is wanted). For each card with a
    scored vector: apply the eligibility chain (§3.8 — per-class switch,
    whitelist, basis rule, format envelope, floors + breaker_min_severity,
    outlook narration margin), then deck-level repetition suppression, then
    call trade_narrative.hesitation_line(objection, players) and write
    card.breaker["narrated"] / ["suppressed"] / ["tmpl_ver"]. Never touches
    card.narrative, card order, or breaker_shadow (shadow never narrates)."""
```

Private per-class predicate functions (§3.3–§3.6), each
`_obj_<code>(card_view, pctx) -> dict` returning one objection entry
`{code, severity, evidence}` — always; a non-firing class returns
`severity 0.0` with its evidence shape's mandatory keys (M4: absence impossible, only
zero/skip representable). `_partner_context(...)` builds §2.2 lazily, cached per
`target_user_id` per call.

### 1.2 The server seam — `_run_trade_job`, post-F9, pre-ghost-split

**Insertion line:** immediately after the F9 block's final `except br_err` handler
(`server.py:6029`), immediately before the `# suggestion.telemetry — split the final deck…`
comment (`server.py:6030`) and the `served_final = final_cards` assignment (`:6034`). At that
line `final_cards` is the exact list `_log_deck_signal_impressions` receives at `:6101`
(mutation stack complete; likes-you-injected cards included), and every name the breaker reads
is in scope: `g_league`, `players_dict`, `seed_map`, `active_format`, `league_id`,
`g_user_id`, `elo_map_rt`, `outlook_value`, `opponent_outlooks`, `opponent_pick_shares`,
`real_user_ids`, `ghost_on`, `job_id`, `_generate_kwargs`.

```python
        # Counterparty breaker (v1) — evaluate + stamp + (flag 2) narrate.
        # Post-mutation-stack, pre-ghost-split: `final_cards` here is the
        # exact list _log_deck_signal_impressions receives (likes-you-
        # injected cards included — they carry no fit_diag; their `them`
        # passthrough is null, D-3). Attribute-only; zero ordering effect
        # (test_breaker_zero_ordering_effect); fail-open with LABELED
        # degradation (LLD §5) — never a bare null, never a missing key on
        # a flag-on deck. Ghost split below is inert (no-ghost ruling):
        # served_final == final_cards.
        if FLAGS.trade_breaker:
            try:
                from .trade_breaker import stamp_breaker, compose_narration
                # lazy — flag-off never imports (NFR-3,
                # test_flag_off_never_imports_breaker)
                stamp_breaker(
                    final_cards,
                    league            = g_league,
                    players           = players_dict,
                    seed_elo          = seed_map,
                    scoring_format    = active_format,
                    league_id         = league_id,
                    viewer_user_id    = g_user_id,
                    viewer_roster     = _generate_kwargs["user_roster"],
                    viewer_elo        = elo_map_rt,
                    viewer_outlook    = outlook_value,
                    declared_outlooks = opponent_outlooks,
                    pick_shares       = opponent_pick_shares,
                )
                if FLAGS.trade_breaker_narrative:
                    compose_narration(final_cards, players=players_dict)
                    # Republish so the narrated payload reaches the snapshot
                    # the client actually receives on EVERY flag combination
                    # (§1.5) — the deck.signal_v2 republish at :6115 is
                    # conditional and must not be relied on. Same idiom as
                    # the F7/F9 republishes above.
                    if any((getattr(c, "breaker", None) or {}).get("narrated")
                           for c in final_cards):
                        snapshot = []
                        for c in _served_cards(final_cards, league_id, ghost_on):
                            d = trade_card_to_dict(c, players_dict)
                            d["real_opponent"] = c.target_user_id in real_user_ids
                            d["outlook"]       = outlook_value
                            snapshot.append(d)
                        with _trade_jobs_lock:
                            j = _trade_jobs.get(job_id)
                            if _job_live(j):
                                j["cards"] = snapshot
            except Exception as bk_err:
                log.warning("breaker stamp failed (non-fatal): %s", bk_err)
                # Rung 5 — minimal marker on EVERY card, constructed with no
                # breaker state (the import itself may be what failed). The
                # "brk-1" literal is version-pinned against
                # trade_breaker.BREAKER_VERSION by
                # test_rung5_marker_version_pinned.
                _mark = {"ver": "brk-1", "degraded": "exception_outer",
                         "objections": None}
                for _bc in final_cards:
                    _bc.breaker = dict(_mark)
                    if (trade_service._c("breaker_shadow_run") >= 1.0
                            and getattr(_bc, "breaker_shadow", None) is None):
                        _bc.breaker_shadow = dict(_mark)
```

Two structural differences from the M3 fit stamp (`server.py:5698-5716`), restated from HLD
§2.3: the guard is `FLAGS.trade_breaker`, not `bakeoff_run is not None` (organic decks stamp
too), and the input is the served deck, not per-arm ranked lists (D-9).

### 1.3 Snapshot-republish analysis — every flag combination

The HLD deferred the republish site; here is the full matrix. Streaming snapshots are
published by `on_opponent_done` (`server.py:2985-3001`), then conditionally replaced by the
F7-split republish (`:5726-5740`), the likes-you republish, the F9 shaping republish
(`:5996-6013`, first decks only), and finally the deck.signal_v2 post-impression republish
(`:6115-6128`, which re-serializes every card via `trade_card_to_dict` but runs **only** when
`deck.signal_v2` is on AND `imp_by_card` is truthy).

| Flag state | Payload carries `breaker`? | Carrier |
|---|---|---|
| `trade.breaker` off | no (no key, no import) | n/a — snapshots byte-identical to today |
| breaker on, narrative off (dark window) | **no key at all** (§1.6 narration gate) | no republish runs in the seam block (the `any(narrated)` guard is False because `compose_narration` never ran) — snapshots byte-identical to flag-off (test_breaker_payload_absent_during_dark_window) |
| breaker on, narrative on, ≥1 narrated, `deck.signal_v2` on | yes | the seam republish (§1.2) delivers it; the `:6115` republish re-serializes later and preserves it (`trade_card_to_dict` reads the attribute) — either alone suffices, both are correct |
| breaker on, narrative on, ≥1 narrated, `deck.signal_v2` **off** | yes | **the seam republish is the only carrier** — this row is why the block owns one |
| breaker on, narrative on, 0 narrated | no key | no republish (guard False); correct and cheap |
| job superseded mid-run | n/a | `_job_live` guard inside the republish — same posture as every other republish site |

The republish precedes the ghost split, so it uses the `_served_cards(final_cards, …)` idiom
exactly like F7/F9 (`ghost_on` is False in prod under the no-ghost ruling; the helper is kept
for byte-parity with the neighboring sites, not for ghost behavior).

### 1.4 `_log_deck_signal_impressions` — the features block

Placed immediately **after** the `if bakeoff_run is not None:` guard block that carries the
fit keys (`server.py:4193-4207`), **outside** that guard (organic rows stamp too — HLD §3.3),
before the wildcard block (`:4208`):

```python
        # Counterparty breaker (LLD §1.4) — OUTSIDE the bakeoff_run guard:
        # organic decks stamp too. `breaker` is REQUIRED on every card of a
        # flag-on deck — scored stamp or the §5 minimal marker — so this is
        # a bare attribute read, NOT getattr-with-default: a missing
        # attribute here is a seam bug and must fail loudly into the
        # impressions try/except (coverage tripwire surfaces it, NFR-6).
        # `breaker_shadow` may be None only when breaker_shadow_run is off.
        # Both ride INSIDE features_json (one column) — the
        # save_deck_impressions executemany first-row-keys trap
        # (database.py:5503) cannot drop them.
        if FLAGS.trade_breaker:
            features["breaker"]        = card.breaker
            features["breaker_shadow"] = getattr(card, "breaker_shadow", None)
```

Flag off ⇒ no key ⇒ rows byte-identical (NFR-3). Uniform at the JSON level on every row of a
flag-on deck, both draft paths (`test_impressions_breaker_uniform_keys` extends
`test_impressions_uniform_columns`, `test_bakeoff_serving.py:1170`).

### 1.5 `trade_card_to_dict` — narration-gated serialization

One additive block after the fit block (`server.py:11055-11060`):

```python
    # Counterparty breaker (HLD §3.6) — NARRATION-GATED: during the dark-
    # stamp window (trade.breaker on, trade.breaker_narrative off) the
    # payload carries NO breaker key at all — dark-class codes must never
    # ship as inspectable structured data. The full objection vector never
    # serializes (features_json only); card.breaker_shadow NEVER serializes
    # (test_breaker_shadow_never_serialized).
    _bk = getattr(card, "breaker", None)
    if _bk is not None and _bk.get("narrated"):
        out["breaker"] = {
            "code":     _bk["top"]["code"],
            "severity": _bk["top"]["severity"],
            "sentence": _bk["narrated"],
        }
```

`compose_narration` populates `narrated` only for graduated, whitelist-clean, above-floor
classes, so the serialized `code` is restricted to that set by construction.
`docs/api-reference.md` gains the row (scope.md §4).

### 1.6 `trade_narrative.py` — the pure template function

```python
#: Template version — stamped by compose_narration into breaker.tmpl_ver.
#: Bump on ANY wording change (narration A/B readouts key on (ver, tmpl_ver)).
HESITATION_TMPL_VERSION = "brt-1"

def hesitation_line(objection: dict, players: dict) -> str | None:
    """One deterministic hesitation sentence for one objection, or None.

    D-053 mechanically: renders ONLY ids/numbers/enums present in
    objection["evidence"] (§2.4 enumerates the keys per code); player names
    resolve from evidence ids via `players` at render time — the sentence can
    never name what the analysis didn't produce. Returns None on an unknown
    code, a non-narratable code, or any missing evidence key (never guesses,
    never substitutes). Pure; no flag reads, no knob reads — eligibility
    lives in trade_breaker.compose_narration, the flag at the server seam.
    Inherits the positional-honesty covenant (trade_narrative.py:119-125).
    """
```

Template table (exact v1 wording — PRD may polish, `tmpl_ver` bumps if it does):

| code (basis/branch) | Template |
|---|---|
| `fit_outlook` (rebuilder/jets) | `"Their likely hesitation: their roster leans rebuild, and this sends them {name}, a {age}-year-old {pos}."` |
| `fit_outlook` (contender/championship) | `"Their likely hesitation: they look win-now, and this asks them to take back future capital."` |
| `fit_new_weakness` | `"Their likely hesitation: giving up {name} may leave them thin at {pos}."` |
| `fit_duplicate` | `"Their likely hesitation: they're already deep at {pos}, so {name} may not move their lineup."` |
| `value_giving` (consensus basis only) | `"Their likely hesitation: by consensus value they'd likely see this as giving up more than they get."` |
| `roster_crunch` | `"Their likely hesitation: taking back {extra} more players than they send is a roster squeeze."` |
| `other_player_keep` | — none. Permanently dark in v1 (D-6); `hesitation_line` returns None for it unconditionally |

Copy rules (HLD §5.2) audited per template: roster/observable claims only, hedged modality
("likely", "may"), no mental states, no "FTF data shows". `build_narrative` and
`_opponent_frame` are untouched. A snapshot test pins every template string
(`test_hesitation_templates_snapshot`) and `test_hesitation_line_honesty` fuzzes evidence
dicts with missing keys → None.

### 1.7 Flags

Both registered in `config/features.json` + `FLAG_KEYS` (`feature_flags.py:47`) +
`DEFAULT_FLAGS` (`:939`) + the release-fixture mirror + `docs/config-reference.md`, both
default false. Dotted key → underscore attribute (`FLAGS.trade_breaker`,
`FLAGS.trade_breaker_narrative` — the `trade_likes_you` precedent, `server.py:3015-3016`).
`trade.breaker_narrative` alone does nothing (the narration call sits inside the
`FLAGS.trade_breaker` block — the requires-relationship is structural, not checked twice).

### 1.8 Mobile — the hesitation element

`mobile/src/components/TradeCard.tsx`, mounted after the FB-47 partner-fit line row
(`:452-458`) and before the consensus-note block (`:460-478`) — the same muted, hint-tier
band of the card:

```tsx
{/* Counterparty breaker — "their likely hesitation" (flag
    trade.breaker_narrative; the server serializes `breaker` only for
    narrated cards, so payload presence IS the gate). Chalkline: type
    tokens + flare for the informational dot (ADR-005) — no new colors,
    no emoji, radius within spec. */}
{data.breaker?.sentence && (
  <View style={styles.breakerRow} testID="trade-card.breaker-hesitation">
    <View style={styles.breakerDot} />
    <Text style={type.bodySm} testID="trade-card.breaker-hesitation.body">
      {data.breaker.sentence}
    </Text>
  </View>
)}
```

- `styles.breakerRow` / `styles.breakerDot` mirror `fitRow` / `fitDot` shapes with the dot on
  `flare.base` (informational accent — ADR-005; ice stays reserved for actions). All colors by
  token reference; the structural guard greps for hex literals in the new styles.
- testIDs follow the repo's dot idiom (`trade-card.consensus-note` precedent, `:475`), pass
  `mobile/scripts/testid-lint.sh`. (scope.md's example spelling
  `trade-card-breaker-hesitation` is superseded by the repo idiom — flagged for cross-review.)
- The TS card-payload type (the type carrying `real_opponent` / `fitPremium`) gains
  `breaker?: { code: string; severity: number; sentence: string }` — additive, optional.
- Web and extension: no change; they ignore the key (mobile-only surface in v1, HLD §2.4).
- No `FeedbackFAB` question: no new screen (PLAN §7).

---

## 2. Data Structures & Schema

### 2.1 `card.breaker` — exact schema

Set by `stamp_breaker` on every card of a flag-on deck. Types are exact; every key present on
every scored stamp (M4: absence impossible):

```jsonc
{
  "ver": "brk-1",                  // str — BREAKER_VERSION
  "tmpl_ver": null,                // str|null — HESITATION_TMPL_VERSION; null
                                   // until compose_narration runs on this card
  "top": {                         // object|null — argmax severity over classes
    "code": "fit_outlook",         //   clearing their per-class floor (post-
    "severity": 0.82,              //   haircut); null when nothing clears
    "evidence": {…}                //   (a selection, not a score — D-4)
  },
  "objections": [                  // list — EVERY v1 class exactly once, pass
    {"code": "fit_outlook",        // order §3.4; below-floor classes still
     "severity": 0.82,             // listed (the §6.4 counterfactual needs the
     "evidence": {…}},             // full vector); envelope-gapped classes
    {"code": "fit_duplicate",      // carry severity null + skip marker:
     "severity": 0.0, "evidence": {…}},
    {"code": "fit_new_weakness",
     "severity": null, "skipped": "format_gap", "evidence": {}},
    …                              // severity: float 0–1 rounded to 3 dp | null
  ],
  "them": 41.3,                    // float|null — card.fit_diag them-score
                                   // PASSTHROUGH (D-3); null on organic decks
                                   // and likes-you-injected cards
  "narrated": null,                // str|null — the hesitation sentence
  "suppressed": null,              // null | "repetition" | "below_floor" |
                                   //   "class_ineligible" | "format_gap"
  "outlook_src": "legacy",         // "declared" | "legacy" | "composite"
  "outlook_pair": {                // BOTH sources retained (D-8 agreement rule)
    "declared": null,              //   str|null — private; stamps only, never
    "inferred": "rebuilder",       //   narrated from (item 14)
    "score": -0.041                //   float — infer_team_outlook score
  },
  "board_auth": "consensus",       // "board" | "board_suspect" | "consensus"
  "identity_src": "owner_id",      // §2.3 co-owner ruling marker
  "format_gap": null,              // null | ["fit_new_weakness", …] (§3.7)
  "degraded": null,                // null | rung marker (§5)
  "skipped": null,                 // null | {"classes": [...], "reason": "budget"}
  "ms": 4.1                        // float — evaluation wall-ms, diagnostics only
}
```

**Minimal marker** (every degraded/exception path; never a bare null; the attribute/key is
absent only when the flag is off):

```jsonc
{ "ver": "brk-1", "degraded": "exception_outer", "objections": null }
```

### 2.2 `PartnerContext`

```python
@dataclass
class PartnerContext:
    """One counterparty's present-state snapshot. Built lazily, once per
    target_user_id per stamp_breaker call, ONLY for partners appearing in
    the served deck. All reads are state the job already holds or one
    load_asset_preferences / load_league_preference row per partner."""
    user_id: str                      # LeagueMember.user_id (league identity —
                                      # primary-owner keyed, server.py:16972-16975)
    username: str
    roster: list[str]
    counts: dict[str, int]            # topt._pos_counts(roster, players)
    profile: dict                     # ts.analyze_roster_strengths(roster,
                                      #   players, scoring_format) — tier_depth,
                                      #   position_needs, position_surplus
    outlook: str                      # resolved: declared else inferred (§3.2)
    outlook_src: str                  # "declared" | "legacy" | "composite"
    outlook_declared: str | None
    outlook_inferred: str
    outlook_score: float              # infer_team_outlook score (margin input)
    board: dict[str, float] | None    # member.elo_ratings RAW iff
                                      # member.has_rankings and elo_ratings;
                                      # never shrunk (T3)
    board_auth: str                   # "board" | "board_suspect" | "consensus"
    prefs: dict                       # load_asset_preferences(user_id,
                                      # league_id) — untouchables/targets/
                                      # not_interested (§2.3 identity ruling)
    format_gap: list[str]             # ENVELOPE_CLASSES gapped for this league/
                                      # roster (§3.7); [] when fully modeled
    identity_src: str = "owner_id"
    degraded: str | None = None       # "partner_snapshot" when construction
                                      # failed (rung 1)
```

Construction (`_partner_context`): resolve `member = {m.user_id: m for m in
league.members}.get(card.target_user_id)`; missing member (G-045 partner pruned, demo
opponents dropped, any identity drift) ⇒ rung-1 context (`degraded="partner_snapshot"`,
predicates skip per §5). The **viewer context** for the shadow run is the same dataclass built
from `viewer_roster` / `viewer_elo` / `viewer_outlook` / the viewer's own prefs
(`load_asset_preferences(viewer_user_id, league_id)`), `outlook_src="declared"` when
`viewer_outlook` came from prefs (the seam can't distinguish declared from #8-seeded;
stamped `"declared"` either way with the pair recording both — acceptable for a
never-serialized shadow, noted in §9).

### 2.3 Identity ruling — co-owners (deviation from HLD §3.4, flagged)

HLD §3.4 rules "resolve over `{owner_id} ∪ co_owner_ids(roster)` via `sleeper_roster`". At the
seam **no raw Sleeper roster dict exists**: `League`/`LeagueMember`
(`trade_service.py:3613/:3753`) carry no `co_owners`, the `league_members` DB rows are keyed
on the **primary owner's id** (`server.py:16972-16975`), and nothing persists the co-owner
list server-side — `co_owner_ids` (`sleeper_roster.py:34`) is only ever fed by live Sleeper
fetches (`server.py:14531`). Fetching live inside the trade job would add a network call to
every deck (NFR-2/NFR-4 violation). **v1 ruling:** counterparty state resolves under
`member.user_id` alone; every stamp carries `identity_src: "owner_id"`; the co-owner fixture
test (§7.1) pins that a co-owner's prefs stored under a *different* account id are NOT read
(documented limitation, not silent wrongness). Implementing the HLD's union requires
persisting `co_owners` at league-sync time — registered as §9 Q-3 for cross-review and the
operator. `board_src` conflict handling (two boards) is thereby moot in v1: at most one board
exists per league identity.

### 2.4 Evidence key enums (closed, per code — the whitelist's mechanical form)

Values are ids, numbers, and enum strings ONLY — no free text, no player names
(names resolve from ids at template time). `hesitation_line` may read only these keys.

| code | evidence keys (all mandatory when scored) |
|---|---|
| `fit_outlook` | `outlook` (enum), `lean` (float, §3.3 quantity), `asset` (pid of the highest-consensus-value incoming player driving the lean; null for all-pick packages), `age` (int\|null), `pos` (enum\|null) |
| `fit_new_weakness` | `pos` (enum), `before` (int), `after` (int), `need` (int), `asset` (pid of the highest-value outgoing player at `pos`) |
| `fit_duplicate` | `pos` (enum), `bench_n` (int), `value_share` (float), `asset` (pid of the highest-value incoming player at `pos`) |
| `value_giving` | `basis` ("board"\|"consensus"), `margin` (float, their-seat surplus), `n_give` (int), `n_recv` (int) — **board-basis rows stamp dark; the margin still stamps for calibration** |
| `other_player_keep` | `asset` (pid), `list` ("untouchable") — **private; stamps dark, never renders (D-6)** |
| `roster_crunch` | `extra` (int), `slot_cost` (float), `pileup` (list of pos enums, possibly empty) |

### 2.5 `card.breaker_shadow`

Same schema as §2.1 evaluated from the **viewer's** seat (no give/receive swap), with
`narrated`/`suppressed`/`tmpl_ver` permanently null and `them` null (the fit them-score is a
partner quantity). Present on every card of a flag-on deck when `breaker_shadow_run ≥ 1`
(minimal marker on degraded paths — unlabeled shadow missingness would corrupt the §8 primary
calibration population exactly as breaker missingness would); permitted null only when the
shadow knob is off. **Never serialized** (`test_breaker_shadow_never_serialized`).

### 2.6 Schema deltas

None. No tables, no columns, no routes. `deck_impressions.features_json` gains the two keys
(data-dictionary rows at build: `features_json.breaker` — §2.1 shape | §2.1 minimal marker,
present on every row of a flag-on deck; `features_json.breaker_shadow` — same | null).

---

## 3. Core Logic

### 3.1 Card mirroring (D-10)

Evaluation swaps give/receive **as a view at evaluation time**, never as data:

```python
@dataclass
class _CardView:                      # partner seat
    give_ids: list[str]               # = card.receive_player_ids (they send these)
    recv_ids: list[str]               # = card.give_player_ids  (they receive these)
```

No partner-frame shape labels are minted (taxonomy §2.1); the shadow run uses the unswapped
view. Value accessors, built once per call: `cval(pid) = ts.elo_to_value(seed_elo.get(pid,
1500.0))`; per-partner `oval(pid) = ts.elo_to_value(pctx.board.get(pid, 1500.0))` iff boarded.
Raw maps throughout (T3).

### 3.2 Window resolution — mirrored from the engine, verbatim shape

`PartnerContext` resolves exactly the declared-else-inferred shape the engine uses at
`trade_service.py:4948-4956` / `trade_gen_v2.py:982-989`:

```python
declared = (declared_outlooks or {}).get(member.user_id)
if declared is None and not declared_outlooks:
    # trade.outlook_infer off ⇒ the job built no declared map; the breaker
    # reads the same source directly (one row per partner in the deck).
    declared = (load_league_preference(user_id=member.user_id,
                                       league_id=league_id) or {}).get("team_outlook")
inferred, score, signals = ts.infer_team_outlook(
    member.roster, players,
    (pick_shares or {}).get(member.user_id, 0.0),
    num_teams)          # num_teams = len(league.members) + 1 — re-verify at
                        # build against trade_service._num_teams's source
outlook      = declared or inferred
outlook_src  = ("declared" if declared else
                ("composite" if (signals.get("starters") or {}).get("applied")
                 else "legacy"))
```

The breaker passes **no** `starter_signal`/`odds_signal`/`first_round_ledger` — so by
INV-372b (`trade_service.py:3166-3175`) it scores the LEGACY vector today and inherits the
composite automatically the day the engine's own callers supply the signal (`outlook_src`
shows the seam date in the data — D-8). Both values + the score are retained in
`outlook_pair` (D-8 agreement rule). `not_sure` resolved outlook ⇒ `fit_outlook` scores 0.0
(no window claim without a window).

### 3.3 `fit_outlook` — predicate + severity (coherence-first quantity)

**Quantity (LLD ruling, flagged for cross-review):** `lean` = arithmetic mean of
`ts._now_lean(pos, age)` (`trade_service.py:2648`) over the assets the partner would
**receive** (`view.recv_ids` = the viewer's give side) — byte-parallel to
`trade_narrative._give_side_now_lean` (`trade_narrative.py:71-83`), deliberately NOT the
value-weighted `ts.signed_lane_shift`. Why: `_opponent_frame` (`trade_narrative.py:86-100`)
asserts window-FIT from exactly this quantity at |lean| ≥ 0.05; computing the breaker's
window-PUSH from the same number with mirrored thresholds makes the §7.1 coherence test a
*proof* (the two writers cannot disagree about the same scalar) instead of a hope. Equality of
the two computations is itself pinned (`test_lean_quantity_parity`); any future threshold or
quantity change lands breaker-side (HLD §2.4).

**Fire condition and severity:**

```python
o = pctx.outlook
if o in ("rebuilder", "jets"):      push = max(0.0,  lean - 0.05)   # aging
elif o in ("contender", "championship"): push = max(0.0, -lean - 0.05)  # youth/picks
else:                               push = 0.0                       # not_sure
sev = min(1.0, push / 0.35)                       # 0.40 lean ⇒ 1.0; constants
                                                  # pinned under BREAKER_VERSION
if pctx.outlook_src == "legacy":
    sev *= ts._c("breaker_outlook_haircut_legacy")                   # D-8
if (pctx.outlook_declared and pctx.outlook_declared != pctx.outlook_inferred):
    pass   # severity unchanged; NARRATION blocked by §3.8 agreement rule
```

`_opponent_frame` fires at `lean ≤ -0.05` (rebuilder) / `lean ≥ +0.05` (contender); the
breaker fires at `lean > +0.05` / `lean < -0.05` respectively — disjoint by construction for
any single outlook value. The §7.1 characterization test also pins the precondition that both
writers consume the same outlook value (HLD §2.4).

### 3.4 Pass-1 classes (cheap arithmetic over the prebuilt context)

**`fit_duplicate`.** Players only (`ts.is_pick_asset` excluded). For each incoming position
`pos` (of `view.recv_ids`) with `pos in pctx.profile["position_surplus"]`:
`value_share = Σ cval(incoming at pos) / Σ cval(all incoming players)` (0 if no incoming
player value); `bench_n = pctx.profile["tier_depth"][pos]["bench"]`;
`sev = min(1.0, 0.40 + 0.40*value_share + 0.20*min(bench_n, 4)/4)`. Multiple surplus
positions: keep the max-severity one (evidence names it). No surplus overlap ⇒ 0.0.

**`value_giving`** — ONE code path both deck types (D-3): their-seat surplus in the live
value space, byte-parallel to the fit `_surplus` shape (fit LLD §1.7):

```python
rvals = [val(p) for p in view.recv_ids]; gvals = [val(p) for p in view.give_ids]
v_max = max(rvals + gvals)
recvd = ts.package_value_v2(rvals, v_max, n_other=len(gvals), other_values=gvals)
sent  = ts.package_value_v2(gvals, v_max, n_other=len(rvals), other_values=rvals)
extra = len(view.recv_ids) - len(view.give_ids)
if extra > 0: recvd -= ts._c("waiver_slot_cost") * extra
margin = recvd - sent
sev = min(1.0, max(0.0, -margin) / ts._c("breaker_value_scale"))
```

`val` = `oval` when `pctx.board_auth == "board"`, else `cval` (board_suspect and unboarded
both fall to consensus optics — PLAN F-3 — with `board_auth` recording why);
`basis` = "board"/"consensus" accordingly in evidence. `fit_diag` never feeds this number
(passthrough only, D-3).

**`other_player_keep`.** `hits = set(view.give_ids) ∩ set(pctx.prefs["untouchables"])`
(what they'd send away ∩ their untouchable list — `ASSET_PREF_LISTS`, `database.py:8657`).
`sev = 0.0` if none; else `0.9`, `+0.1` when a hit is the package-wide max-`cval` asset.
Permanently dark (D-6); evidence stamps the hit pid for calibration.

**Board authenticity (F-3 heuristic, `board_auth`).** Computed at context build when a board
exists: `divergent = |{pid ∈ board : |board[pid] − seed_elo.get(pid, board[pid])| ≥
ts._c("breaker_board_div_min")}|`; `board_auth = "board"` iff `divergent ≥
ts._c("breaker_board_min_divergent")`, else `"board_suspect"`; no board ⇒ `"consensus"`.
Cheap (one pass over the board dict), deterministic, and the clone-board fixture (§7.1) pins
both sides of the threshold.

### 3.5 Pass-2 classes (feasibility tier — run whole or dropped whole, §3.9)

**`fit_new_weakness`** — the `topt._feasible_after` shape (`trade_optimizer.py:161`) from
their seat, slack-graded instead of boolean:

```python
out_d = topt._subset_pos_delta(view.give_ids, players)
in_d  = topt._subset_pos_delta(view.recv_ids, players)
worst_pos, worst_slack, need_at = None, 99, 0
for pos, base in pctx.counts.items():                 # QB/RB/WR/TE
    need  = topt._starters_at(pos, scoring_format)    # sf bumps QB to 2
    after = base - out_d.get(pos, 0) + in_d.get(pos, 0)
    slack = after - need
    if out_d.get(pos, 0) > 0 and slack < worst_slack:
        worst_pos, worst_slack, need_at = pos, slack, need
sev = {True: 1.0}.get(worst_slack < 0) or {0: 0.60, 1: 0.30}.get(worst_slack, 0.0)
```

(Written out at build as a plain if/elif; the table is the spec: infeasible ⇒ 1.0 — the
mirror of the K3 kill the served card may never have been tested against, since only the v3
path runs `_feasible_after` for both rosters; slack 0 ⇒ 0.60; slack 1 ⇒ 0.30; ≥2 ⇒ 0.0.)
Only positions they actually send from can fire (`out_d > 0`) — receiving can't open a hole.

**`roster_crunch`** (extension code, `producer=breaker`; new logic ⇒ conservative maturity,
D-6/§2.7). Fires from slot math + positional pile-up — bench size is NOT modeled
(`_feasible_after` docstring, `trade_optimizer.py:165-172`), so the "forced drop of a player
they demonstrably value" limb from the PLAN's definition is **not computable in v1** and is
recorded as an evidence gap (§9 Q-4), not approximated:

```python
extra = len(view.recv_ids) - len(view.give_ids)       # net bodies they absorb
if extra <= 0: sev = 0.0
else:
    pileup = [pos for pos in incoming_positions
              if pctx.profile["tier_depth"][pos]["bench"] >= 3]
    sev = min(1.0, (extra * ts._c("waiver_slot_cost"))
                    / ts._c("breaker_crunch_scale")
                   + 0.15 * min(len(pileup), 2))
```

Default scales: one extra body ⇒ 425/850 = 0.50; two ⇒ 1.0 (capped).

### 3.6 The `them` passthrough

`stamp_breaker` copies `getattr(card, "fit_diag", None)` → `breaker["them"] =
fit_diag["them"]` when the M3 stamp exists (bake-off decks, `server.py:5698-5716`), else
null (organic decks; likes-you-injected cards, which entered after M3). Never recomputed
(D-3; `test_them_is_passthrough` monkeypatches `fit_diag` to a sentinel and asserts the
sentinel rides through).

### 3.7 Format envelope (v1 enumeration)

The fully-scored envelope for `ENVELOPE_CLASSES` — every condition must hold, else the class
list lands in `format_gap` and those classes stamp `severity: null, skipped: "format_gap"`
and are narration-ineligible:

1. `league.platform == "sleeper"` (ESPN/MFL roster models unverified for depth math in v1).
2. `len(league.members) + 1 == 12` — the `_POS_TIER_CUTS` 12-team assumption
   (`trade_service.py:2071-2076`).
3. `scoring_format` ∈ {`"1qb_ppr"`} ∪ {any `sf*`} (the two `_starters_at` regimes).
4. No asset on the partner's roster prices 0.0 while holding a non-QB/RB/WR/TE/PICK position
   (the G-026 IDP/K corruption test — one pass over the roster).

`fit_outlook`, `value_giving`, `other_player_keep` score everywhere (age/value/list math is
format-independent). A 14-team or IDP league gets fewer named hesitations, not wrong ones;
share-of-decks-with-≥1-gapped-class rides diagnostics (the case for/against widening in v2).

### 3.8 `compose_narration` — eligibility chain + repetition suppression

Deck-level, deterministic, in served order. For each card with a scored vector
(rungs 0–2; marker-only cards are skipped — nothing to narrate):

1. `top` must be non-null; let `obj = top`, `code = obj["code"]`.
2. **Class switch:** `ts._c(f"breaker_narrate_{code}") >= 1.0` — else
   `suppressed = "class_ineligible"`.
3. **Whitelist:** `code ∈ NARRATABLE_CLASSES` (blocks `other_player_keep` regardless of
   switch); `value_giving` additionally requires `evidence["basis"] == "consensus"` —
   board-basis is ineligible OUTRIGHT (D-7; the switch governs the consensus basis only).
4. **Envelope:** `code ∉ breaker["format_gap"]` — else `suppressed = "format_gap"`.
5. **Floors:** `severity ≥ max(class floor per §4, ts._c("breaker_min_severity"))` — else
   `suppressed = "below_floor"`. (`value_giving` consensus basis reads
   `breaker_floor_value_giving_consensus`.)
6. **Outlook narration margin (D-8, `fit_outlook` only):** when `outlook_src == "legacy"`,
   require `|outlook_pair["score"] − cut| ≥ ts._c("breaker_outlook_narrate_margin")` where
   `cut` is the crossed threshold (`infer_contender_cut` / `infer_rebuilder_cut`,
   `trade_service.py:3313-3318`) — the narration bar sits above the stamp bar. When a
   declared outlook exists it may only RAISE confidence on agreement: declared ≠ inferred ⇒
   not narrated for this card (`suppressed = "class_ineligible"`); the stamp records both
   (item 14 default).
7. Survivors are grouped by `(card.target_user_id, code)`. Within a group larger than
   `ceil(ts._c("breaker_max_repeat_frac") × cards_for_that_partner)`, only the max-severity
   card (tie: first in served order) narrates; the rest set
   `suppressed = "repetition"` (D-7).
8. For each remaining card: `sentence = trade_narrative.hesitation_line(obj, players)`;
   `narrated = sentence` (None ⇒ stays null — a template refusal is honest silence);
   `tmpl_ver = trade_narrative.HESITATION_TMPL_VERSION`.

Shadow payloads are never visited. The function mutates only
`narrated`/`suppressed`/`tmpl_ver`.

### 3.9 Two-pass budget evaluation (NFR-2, HLD §2.6)

```
t0 = time.monotonic(); budget = ts._c("breaker_ms_budget") / 1000.0
if budget <= 0: every card gets the minimal marker {ver, degraded:
    "budget_exhausted", objections: null}; return          # documented disable
PASS 1 — for each card in served order: build/fetch PartnerContext (rung 1 on
    failure); evaluate PASS_1_CLASSES (+ the shadow pass-1 when the shadow
    knob is on); per-card exception ⇒ rung-4 marker for that card.
    If elapsed() > budget mid-pass: every REMAINING card gets the minimal
    marker (rung 3 — rank-correlated by construction, therefore labeled;
    readouts exclude the deck).
CHECKPOINT — if elapsed() > ts._c("breaker_budget_checkpoint_frac") * budget:
    pass 2 is DROPPED WHOLE: every card appends the two skip entries and
    stamps skipped = {"classes": ["fit_new_weakness", "roster_crunch"],
    "reason": "budget"} (rung 2 — deck-uniform, unbiased-by-rank).
PASS 2 — else evaluate PASS_2_CLASSES for every card (+ shadow), buffering
    results; pass 2 is ATOMIC: if elapsed() > budget mid-pass, the buffered
    pass-2 results are DISCARDED for the whole deck and every card stamps the
    rung-2-shaped skip marker with reason "budget_exhausted" + degraded:
    "budget_exhausted" — pass-1 scores are KEPT (labeled, deck-uniform;
    LLD refinement of the HLD rung-3 row, flagged §9 Q-5).
FINALIZE — top selection (argmax over per-class floors, post-haircut), them
    passthrough, provenance markers, ms.
```

Cost envelope (HLD §5.4): ≤10 PartnerContexts × (`analyze_roster_strengths` +
`infer_team_outlook` + one prefs row) ≈ ≤1 ms each; per-card work is dict arithmetic +
`package_value_v2` — expected 10–100 ms/deck against the 250 ms default budget and the 60 s
job timeout. The pre-flag-on dry run (fit W0 precedent) hands the operator the measured
number before `trade.breaker` lights.

---

## 4. Knob table — 25 keys (final count)

Count derivation: 6 narration switches + 7 floors (6 classes + the separate consensus-basis
`value_giving` floor D-7 demands — one more than the HLD's "per class" sketch, flagged §9
Q-6) + 12 singletons = **25**. Every key follows the five-registration rule **in the
consumer's commit** (discipline comment `trade_service.py:890-898`):
`trade_service._DEFAULT_CFG` (tail, `:964`) · `database._MODEL_CONFIG_DEFAULTS`
(`database.py:2188`; without the row `set_config` KeyErrors, `:4191`, and the rollback ladder
is theater) · `_PINNED_KNOBS` (`test_bakeoff_arm_a_golden.py:471`; inventory guard `:546-547`
fails BY NAME) · the disposition sentence in
`docs/plans/three-model-bakeoff/scope-phase2.md` · the `docs/config-reference.md` row.

Disposition sentence, all 25 keys (the D-095 wording pattern): *"Evaluation-layer knob for
`backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the
deck-mutation stack completes and mutates only a new card attribute; no effect on
MODEL_A_PROFILE output."*

| Key | Default | Disable | One-line description |
|---|---:|---:|---|
| `breaker_ms_budget` | 250.0 | 0 | per-deck evaluation budget, ms; 0 ⇒ evaluation off, every card stamps the minimal marker |
| `breaker_budget_checkpoint_frac` | 0.6 | 1.0 | fraction of budget at which pass 2 is dropped whole (§3.9) |
| `breaker_degraded_share_max` | 0.05 | 1.0 | graduation criterion: max share of rung-1..3 rows (NFR-6) |
| `breaker_min_severity` | 0.60 | 1.1 | global narration bar over the per-class floors |
| `breaker_max_repeat_frac` | 0.34 | 1.0 | per-(partner, code) narration share above which repetition suppression keeps only the top card |
| `breaker_shadow_run` | 1.0 | 0 | viewer-seat shadow evaluation (operator decision 5); 0 ⇒ `breaker_shadow` null everywhere |
| `breaker_outlook_haircut_legacy` | 0.70 | 1.0 | severity multiplier on `fit_outlook` when `outlook_src="legacy"` (D-8) |
| `breaker_outlook_narrate_margin` | 0.06 | 99 | inferred-window score margin over the crossed cut required to NARRATE `fit_outlook` (stamp bar unchanged) |
| `breaker_board_div_min` | 25.0 | — | Elo divergence from seed for a board row to count as "divergent" (F-3) |
| `breaker_board_min_divergent` | 10.0 | 0 | divergent rows required for `board_auth="board"`; below ⇒ `board_suspect` (⇒ consensus basis) |
| `breaker_value_scale` | 400.0 | 1e9 | their-seat negative margin that maps `value_giving` severity to 1.0 |
| `breaker_crunch_scale` | 850.0 | 1e9 | slot-cost total that maps `roster_crunch` severity to 1.0 |
| `breaker_floor_fit_outlook` | 0.35 | 1.1 | top-selection floor (floors shape the stamp distribution, never narration policy — D-6) |
| `breaker_floor_fit_new_weakness` | 0.30 | 1.1 | 〃 |
| `breaker_floor_fit_duplicate` | 0.30 | 1.1 | 〃 |
| `breaker_floor_value_giving` | 0.30 | 1.1 | board-basis floor |
| `breaker_floor_value_giving_consensus` | 0.75 | 1.1 | consensus-basis floor — materially higher (D-7: 86.3% near-tautology) |
| `breaker_floor_other_player_keep` | 0.50 | 1.1 | 〃 |
| `breaker_floor_roster_crunch` | 0.40 | 1.1 | 〃 |
| `breaker_narrate_fit_outlook` | 0.0 | 0 | narration switch (D-6 maturity ladder; ALL default 0 — graduation is an operator `set_knob` flip, logged in `model_config_changes`) |
| `breaker_narrate_fit_new_weakness` | 0.0 | 0 | 〃 |
| `breaker_narrate_fit_duplicate` | 0.0 | 0 | 〃 |
| `breaker_narrate_value_giving` | 0.0 | 0 | 〃 — governs the CONSENSUS basis only; board basis is ineligible outright (D-7) |
| `breaker_narrate_other_player_keep` | 0.0 | 0 | registered for symmetry; the D-6 whitelist blocks narration even at 1 — flipping it alone renders nothing (documented in its config-reference row) |
| `breaker_narrate_roster_crunch` | 0.0 | 0 | 〃 (new-logic class: last to graduate, §2.7) |

`_MODEL_CONFIG_DEFAULTS` descriptions ≤90 chars each, e.g.
`("breaker_ms_budget", 250.0, "breaker: per-deck eval budget ms; 0 disables (minimal markers)")`.
Severity-curve constants baked into predicates (the 0.05/0.35 lean window, the slack table,
the 0.40/0.40/0.20 duplicate weights, the 0.9/1.0 keep severities) are deliberately NOT knobs
— they are `BREAKER_VERSION`-pinned semantics; re-leveling across classes is what the floor
knobs are for (D-4). Flagged §9 Q-7.

---

## 5. Error Handling & Edge Cases

### 5.1 Degradation ladder (HLD §2.6, made exact)

Bare null is never stamped; an absent key means flag-off, nothing else. Marker shapes:

| Rung | Trigger | Stamp on affected cards | Scope |
|---|---|---|---|
| 0 | normal | full §2.1 payload | all |
| 1 | PartnerContext build fails (G-045 pruned partner, unknown `target_user_id`, prefs read error, profile exception) | scored vector for computable classes; classes needing the failed input stamp `severity: null, skipped: "partner_snapshot"`; whole-context failure ⇒ minimal marker `degraded: "partner_snapshot"` | that partner's cards |
| 2 | checkpoint trips after pass 1 | pass-1 vector + `skipped: {"classes": ["fit_new_weakness","roster_crunch"], "reason": "budget"}` | every card (deck-uniform) |
| 3 | budget exhausted mid-pass-1 | minimal marker `degraded: "budget_exhausted"` | remaining cards (rank-correlated ⇒ labeled; readouts exclude the deck). Mid-pass-2 exhaustion: §3.9 atomic-discard variant — pass-1 kept, deck-uniform skip marker + `degraded: "budget_exhausted"` |
| 4 | per-card exception | minimal marker `degraded: "exception_card"`; logged + counted | that card |
| 5 | outer exception (incl. import failure) | seam handler stamps minimal marker `degraded: "exception_outer"` on EVERY card (§1.2) + warning log | all |

### 5.2 Input-wrongness table (degrade-and-mark is normative — HLD §3.5)

| Input defect | Behavior | Marker |
|---|---|---|
| Partner absent from `league.members` | rung 1 | `degraded: "partner_snapshot"` |
| Board bulk-seeded / clone (F-3) | consensus basis for `value_giving` | `board_auth: "board_suspect"` |
| Unboarded partner | consensus basis | `board_auth: "consensus"` |
| Co-owned roster, prefs under co-owner account id | not read (v1 ruling §2.3) | `identity_src: "owner_id"` |
| 14-team / non-Sleeper / IDP-K roster | depth classes skip + narration-ineligible | `format_gap: [...]`, per-class `skipped: "format_gap"` |
| `not_sure` window | `fit_outlook` scores 0.0 | evidence carries `outlook: "not_sure"` |
| Likes-you-injected card (no `fit_diag`) | `them: null`; everything else scores normally | — |
| Board staleness | NOT handled in v1 (Q-2/A-6 open) | — |
| Empty give or receive side (defensive) | classes score 0.0; no exception | — |

### 5.3 Job-level containment

The seam block is the only caller; its try/except is the rung-5 envelope. The breaker never
raises across the seam. `_log_deck_signal_impressions`'s bare `card.breaker` read (§1.4) is
the deliberate hard edge: a seam bug that leaves a flag-on card unstamped fails the
impressions write into its existing non-fatal except (`server.py:6129-6130`), craters the
coverage metric, and trips the NFR-6 tripwire — known, not discovered.

### 5.4 Determinism (NFR-4)

No RNG, no LLM, no wall-clock in any verdict (`ms` and the budget affect *which rung* stamps
— labeled — never a score). Iteration orders: cards in served order; classes in
`ALL_CLASSES` order; positions in `pctx.counts` insertion order (`_STARTER_NEED` fixed);
ties broken by pid ascending, then served order. `test_breaker_deterministic` runs the same
fixture twice and asserts deep equality of every payload.

---

## 6. Backward Compat & Migration

- **No migrations.** No tables, no columns, no routes, no env vars. `breaker_` prefix stays
  reserved-unused (a grep test in §7.1 pins that no `breaker_` table exists).
- **Flag-off byte identity (NFR-3):** module never imported; no card attribute; no
  `features_json` key; no payload key; no republish. Rows and payloads byte-identical to
  today (`test_flag_off_features_json_byte_identical`, `test_flag_off_payload_byte_identical`).
- **Dark window compat:** `trade.breaker` on alone changes exactly two things —
  `features_json` gains the two keys, and job wall time gains the measured stamp cost.
  Payloads stay byte-identical (§1.3 row 2).
- **Client compat:** the payload key is additive; web/extension ignore it; mobile renders
  only when present. Old mobile builds ignore unknown keys (fit precedent).
- **Draft-path compat:** the stamp is draft-agnostic (`compose_deck` and `team_draft`,
  `group_size ∈ {0, N}` — F-6 trap) — parametrized in §7.1.
- **Rollback ladder (HLD §5.3):** narrative flag off (hot) → `breaker_min_severity 1.1` or
  per-class switch to 0 (`set_knob`, logged) → `trade.breaker` off (compute gone, key gone)
  → revert commit. Nothing persisted needs cleanup: old `features_json.breaker` blobs are
  version-stamped inert data.
- **Version discipline:** any predicate/threshold/evidence-shape change bumps
  `BREAKER_VERSION`; any template change bumps `HESITATION_TMPL_VERSION`; readouts refuse
  cross-version pooling (fit M2 precedent).

---

## 7. Testing

Fixture idiom: the `test_bakeoff_challenger.py` pattern — local `_Player`, literal Elo maps,
`LeagueMember`/`League` inline, every input a literal. Shared fixture: 12-team-shaped league
(11 members + viewer); `_OPP_REBUILDER` (young roster, boarded with ≥10 divergent rows),
`_OPP_CONTENDER` (vet-heavy, clone board — 3 divergent rows), `_OPP_UNBOARDED`,
`_OPP_THIN_TE` (exactly `_starters_at` TEs); a mirrored card pair; a served deck of ~8 cards
across 3 partners.

### 7.1 `backend/tests/test_trade_breaker.py` (new) — names are the spec

| Test | Asserts |
|---|---|
| `test_breaker_deterministic` | two identical runs ⇒ deep-equal payloads, every card (NFR-4) |
| `test_breaker_vocabulary_closure` | every emitted `code` ∈ the 9 coded `PASS_REASON_LAYER2` codes ∪ {`roster_crunch`}; **`other_text` never emitted**; `shape_aversion` never emitted in any field (producer-column enforcement, D-2); codes cross-checked against `database.PASS_REASON_LAYER2` by import, not by copy |
| `test_fit_outlook_predicate` | rebuilder receiving a 29-y/o RB fires with the §3.3 severity; contender receiving picks fires; `not_sure` ⇒ 0.0; legacy haircut applied (knob override moves it) |
| `test_fit_new_weakness_predicate` | `_OPP_THIN_TE` sending its only startable TE ⇒ 1.0 with `{pos:"TE", before, after, need}`; slack-1 fixture ⇒ 0.30; receive-side can't fire |
| `test_fit_duplicate_predicate` | surplus-position incoming fires with `value_share`/`bench_n` per §3.4; non-surplus ⇒ 0.0 |
| `test_value_giving_one_code_path` | boarded-authentic partner ⇒ `basis:"board"` margin from `oval`; unboarded AND clone-board ⇒ `basis:"consensus"` from `cval`; the severity function is the same object on both paths (one helper, asserted by call) |
| `test_other_player_keep_predicate` | untouchable in their give side ⇒ 0.9/1.0; targets/not_interested lists never fire it |
| `test_roster_crunch_predicate` | 1-for-2 from their seat ⇒ extra=1, sev 0.50 at defaults; pile-up bonus caps at +0.30; extra ≤ 0 ⇒ 0.0 |
| `test_board_auth_heuristic` | divergent-row counts on both sides of `breaker_board_min_divergent` ⇒ `board`/`board_suspect`; no board ⇒ `consensus` |
| `test_lean_quantity_parity` | breaker lean == `trade_narrative._give_side_now_lean` for shared fixtures (coherence precondition) |
| `test_opponent_frame_breaker_coherence` (characterization) | over a fixture grid (outlook × lean ∈ {−0.2, −0.05, 0, +0.05, +0.2}): never both `_opponent_frame` non-None and breaker `fit_outlook` fired for the same (card, outlook value); pins today's `:94-99` thresholds; also asserts both writers consumed the same outlook value or the test fails (HLD §2.4 precondition) |
| `test_mirrored_card_cross_seat_coherence` (§2.7) | mirrored fixture: high breaker `fit_new_weakness` from seat B ⟺ B's own viewer-seat `need_gate_ok`/feasibility view flags the mirror |
| `test_breaker_binding_sabotage` (sabotage) | monkeypatch `ts._c` override of `waiver_slot_cost` ⇒ `value_giving`/`roster_crunch` severities move; module-attribute monkeypatch of `ts.package_value_v2` to a sentinel ⇒ verdicts move — value-binding would no-op and fail the assert |
| `test_them_is_passthrough` | sentinel `fit_diag.them` rides through untouched; absent `fit_diag` ⇒ `them` null (likes-you fixture) |
| `test_partner_snapshot_rung1` | unknown `target_user_id` ⇒ rung-1 marker, other partners' cards unaffected |
| `test_budget_ladder_labeling` (sabotage) | `breaker_ms_budget` tiny + a slowed predicate (monkeypatch sleep): checkpoint trip ⇒ deck-uniform rung-2 skip markers; mid-pass-1 exhaust ⇒ rung-3 markers on remaining cards only; `breaker_ms_budget=0` ⇒ minimal markers everywhere |
| `test_exception_rungs` (sabotage) | per-card raising predicate ⇒ rung-4 marker for that card, rung 0 elsewhere; `stamp_breaker` monkeypatched to raise at the seam ⇒ rung-5 marker on EVERY card (server-level fixture) |
| `test_rung5_marker_version_pinned` | the seam literal == `trade_breaker.BREAKER_VERSION` |
| `test_co_owner_prefs_not_read` | co-owner fixture: prefs stored under a different account id are not consulted; `identity_src == "owner_id"` (§2.3 pin) |
| `test_format_envelope` | 14-team league / IDP roster / non-sleeper platform ⇒ depth classes `skipped: "format_gap"` + narration-ineligible; `fit_outlook`/`value_giving` still score |
| `test_objections_vector_complete` | every scored payload lists all 6 classes exactly once, pass order, incl. below-floor and gapped entries (M4) |
| `test_shadow_run` | knob on ⇒ `breaker_shadow` §2.5 shape on every card, viewer-seat verdicts (unswapped fixture check); knob off ⇒ attribute absent/None; shadow `narrated` always null |
| `test_outlook_declared_vs_inferred` | declared present ⇒ `outlook_src "declared"`, pair records both; declared absent ⇒ `legacy`; mirrored engine call shape asserted against `trade_service.py:4948-4956` semantics (declared wins) |

### 7.2 Narration + composition

| Test | Asserts |
|---|---|
| `test_narration_switch_ladder` | all switches 0 ⇒ zero narrated on a hot deck (flag-on renders NOTHING by design); flipping one class narrates only that class |
| `test_narration_whitelist_dark_classes` | `other_player_keep` top + its switch forced 1 ⇒ still never narrated; board-basis `value_giving` never narrated with its switch on (consensus basis narrates) |
| `test_narration_floors_and_min_severity` | below class floor / below `breaker_min_severity` ⇒ `suppressed: "below_floor"` |
| `test_narration_outlook_margin` | legacy-source `fit_outlook` inside the margin ⇒ not narrated, stamp untouched; declared≠inferred ⇒ not narrated, pair stamped |
| `test_repetition_suppression` | 5 same-(partner, code) candidates on one deck at frac 0.34 ⇒ only max-severity card narrates, rest `suppressed: "repetition"` |
| `test_hesitation_templates_snapshot` | every §1.6 template string pinned; `HESITATION_TMPL_VERSION` pinned |
| `test_hesitation_line_honesty` | missing evidence key ⇒ None; unknown code ⇒ None; rendered names resolve from evidence ids only (D-053); no template contains "FTF" or an unhedged mental-state verb |
| `test_tmpl_ver_stamped` | narrated card carries `tmpl_ver == "brt-1"`; un-narrated carries null |

### 7.3 Seam, serving, and serialization (server-level)

| Test | Asserts |
|---|---|
| `test_breaker_zero_ordering_effect` (sabotage; **parametrized `bakeoff_group_size ∈ {0, N}` + organic**) | served deck (trade ids in order) byte-identical with `trade.breaker` on vs off, both draft paths and organic; the fit `test_fit_diag_inert` delete-attribute variant: stripping `breaker` from every card changes nothing served |
| `test_breaker_inert_seam_creep_guard` (D-11) | grep-guard: no module outside `server.py` (seam + features + serialization) and `trade_breaker.py` reads `card.breaker`/`breaker_shadow`; `inspect.getsource(trade_service)` and each generator contain no `trade_breaker` reference |
| `test_flag_off_never_imports_breaker` | flag off + full job ⇒ `"backend.trade_breaker" not in sys.modules` |
| `test_flag_off_features_json_byte_identical` | flag off ⇒ impressions rows byte-identical (no key) |
| `test_impressions_breaker_uniform_keys` (extends `test_impressions_uniform_columns`) | flag-on deck, mixed rungs: every row's `features_json` decodes with `breaker` non-null (scored or marker) and `breaker_shadow` present; organic AND bake-off rows both carry them (outside-the-guard placement pinned) |
| `test_breaker_payload_absent_during_dark_window` | stamped card, narrative flag off ⇒ `trade_card_to_dict` output has NO `breaker` key |
| `test_breaker_shadow_never_serialized` | shadow-stamped card, all flags on ⇒ no `breaker_shadow` key in any payload; serialized `breaker` object has exactly `{code, severity, sentence}` |
| `test_narrated_payload_reaches_snapshot_all_flag_combos` | parametrized over `deck.signal_v2 ∈ {on, off}`: after the job, the stored job snapshot's cards carry `breaker.sentence` for narrated cards (the §1.3 matrix, incl. the signal-v2-off row where the seam republish is the only carrier); dark window ⇒ snapshot byte-identical |
| `test_likes_you_card_stamped` | injected card carries a scored stamp with `them` null |
| `test_no_breaker_tables` | no table in `database.metadata` matches `breaker_%` (prefix reserved-unused) |

### 7.4 Structural guard — `mobile/tests/check-breaker-card.js`

House idiom (regex + brace matcher, no simulator — see `check-analytics-297-302.js` header).
Assertions:

1. `TradeCard.tsx` contains testIDs `trade-card.breaker-hesitation` and
   `trade-card.breaker-hesitation.body`.
2. The element render is conditional on `data.breaker?.sentence` (regex pins the guard
   expression — no unconditional render path).
3. The rendered text node interpolates `data.breaker.sentence` and contains no string
   literal sentence (server-composed copy only — no client-side objection wording).
4. The new styles block references token identifiers only (no `#`-hex literals, no
   `borderRadius` > 8).
5. The card-payload TS type declares optional `breaker` with `code`/`severity`/`sentence`.
6. No other mobile file references `breaker_shadow` (client never sees the shadow).
7. `testid-lint.sh` passes on the tree (CI already runs it).

### 7.5 Code-walk proof + TestFlight checklist (D-056 evidence)

At build: a file:line-cited walk of both seams (stamp block placement relative to F9/ghost
split/impression call; features block placement outside the bakeoff guard) — the §0.2 table
re-cited at the build sha. Before `trade.breaker_narrative` lights (launch step 4, HLD §5.1):
operator TestFlight checklist — (1) narrated card shows the hesitation element with the
expected sentence; (2) a suppressed/below-floor card shows nothing; (3) dark-window build
shows nothing anywhere; (4) element styling matches Chalkline reference screens; (5) pass
flow still files decline reasons normally. Logged in TEST_LEDGER.

---

## 8. Calibration-readout spec skeleton (the preregistered artifact — committed before `trade.breaker` first lights)

This section IS the artifact the HLD D-6 commits to; the TBD cells are filled by the operator
+ build session **before flag-on**, then frozen (changes require a new `ver` window).

**Populations.** (a) Counterparty-seat: mirrored card served to the counterparty within the
A-5 window AND a coded pass reason filed — long-horizon accumulator, never a launch gate
(n≈0 today). (b) Viewer-seat shadow (`features_json.breaker_shadow.top` vs the viewer's own
filed layer-2 code) — the PRIMARY population, labeled proxy validation with its selection
caveat. (c) The §2.7 cross-seat consistency check — population-independent third signal.

**Join.** `deck_impressions.features_json` ⨝ `trade_pass_reasons` on `impression_id`;
`ver` filter mandatory; filed `other_text` rows are unmatched-by-construction and excluded
from every per-class precision denominator (D-1). Boundaries restated verbatim from PLAN §6:
no ghost rows ever (ended 2026-08-21 00:43Z); D-091 window (2026-08-16→08-19) excluded; QB
value-optics not comparable across the 04:46Z 1QB repricing seam; `model_config_changes`
censors windows (M1).

**Per-class gate table (all classes; a class graduates only from its own row):**

| Class | min n (cell) | required margin over majority-class baseline (40% `value_giving`, n=208 — re-derive at readout) | required margin over stratified-random baseline | Notes |
|---|---|---|---|---|
| fit_outlook | TBD-operator | TBD-operator | TBD-operator | reported per `outlook_src` stratum separately |
| fit_new_weakness | TBD | TBD | TBD | envelope rows only |
| fit_duplicate | TBD | TBD | TBD | envelope rows only |
| value_giving | TBD | TBD | TBD | reported per basis stratum; consensus stratum flagged near-tautological (R-4) |
| other_player_keep | TBD | TBD | TBD | dark class — calibration only, no graduation target in v1 |
| roster_crunch | TBD | TBD | TBD | extension code: no filed-reason anchor exists; precision measured against `other_text` free-text hand-coding is FORBIDDEN (other_text excluded); its row may remain unpassable in v1 — stated, not hidden |

**Stratification (minimum, pinned):** `outlook_src` × board basis (`board` /
`board_suspect` / `consensus`); every reported precision carries its cell n; cells below
min-n print "insufficient" — never pooled silently. **Coverage criteria restated (NFR-6):**
scored coverage ≥99% of served impressions AND rung-1..3 share < `breaker_degraded_share_max`
— rung-marked rows are never "covered". **Also reported, never a gate:** class-entropy of
`top.code` (D-7 red line before any narration graduation), per-class fire rate, degraded
share by rung, `ms` p50/p95, mirrored-serve narration-divergence count (R-6 monitor).

---

## 9. Open Questions (for cross-review + operator; none block drafting)

| # | Question | Draft-A position |
|---|---|---|
| Q-1 | `num_teams` source at the seam (§3.2) — `len(league.members)+1` vs the job's own value | re-verify against `trade_service._num_teams` at build; a wrong count only shifts the pick-centering term |
| Q-2 | Board staleness (A-6): is last-ranked-at recoverable? | not handled in v1; `board_auth` does not encode staleness (inherited open item) |
| Q-3 | Co-owner union (§2.3): HLD §3.4 is unimplementable without persisting `co_owners` at sync | v1 = owner-id-only + `identity_src` marker + fixture pin; persisting co_owners is a named v1.1 candidate needing its own (tiny) scope block |
| Q-4 | `roster_crunch` forced-drop limb needs a bench-size model that doesn't exist | omitted, not approximated; evidence gap documented; class stays last in the maturity ladder |
| Q-5 | §3.9 atomic-pass-2 refinement vs the HLD rung-3 literal reading (discard buffered pass-2 to keep missingness deck-uniform) | adopt refinement; HLD's anti-rank-bias principle outranks its rung-3 table cell |
| Q-6 | 7 floor knobs, not 6 (separate consensus-basis `value_giving` floor) | required by D-7; count updated to 25 |
| Q-7 | Severity curve constants pinned under `BREAKER_VERSION` instead of knobs | keeps the knob surface small and the version honest; cross-review may promote specific constants |
| Q-8 | testID spelling: repo dot-idiom `trade-card.breaker-hesitation` vs scope.md's hyphen example | dot idiom; scope example treated as illustrative |
| Q-9 | Shadow `outlook_src` cannot distinguish declared from #8-seeded viewer outlook (§2.2) | stamped "declared" either way; shadow is never serialized and the readout notes it |

---

*End of draft A. Every §0.2 anchor re-verified this checkout 2026-08-21; line drift expected
at build — re-cite everything (PLAN A-3).*
