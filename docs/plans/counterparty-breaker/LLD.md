# LLD — Counterparty breaker

**Date:** 2026-08-21 · **Status:** REVISED POST-CROSS-REVIEW (synthesis of drafts A + B under
the orchestrator's merge rulings M-1..M-12; the cross-review round's consolidated fixes —
blocking F1–F6, ruling T-1, and all accepted non-blocking items — applied 2026-08-21).
**Binds under:** [PLAN.md](PLAN.md) (AMENDED, authoritative) → [HLD.md](HLD.md) (CONVERGED —
not contradicted here except where §0.2 records a ruled erratum) → this LLD. Drafts preserved
at [drafts/LLD-draft-A.md](drafts/LLD-draft-A.md) / [drafts/LLD-draft-B.md](drafts/LLD-draft-B.md);
rulings at [drafts/LLD-merge-rulings.md](drafts/LLD-merge-rulings.md).
Register precedent: [../fit-challenger/LLD.md](../fit-challenger/LLD.md).
**Rule of citation:** every symbol and line anchor below was re-verified against this checkout
(worktree `trading-engine-eval-8ab7bc`, branch `claude/counterparty-breaker-plan`, 2026-08-21,
re-walked during merge synthesis). Line numbers drift; re-cite at build (PLAN A-3 discipline).
**Operator ruling honored throughout (M-12): NO ghost cards, full stop.** Nothing in this LLD
creates, reads, or measures ghost impressions; the ghost-split code path is treated as an inert
code location only (§1.2); every breaker readout filters `is_ghost = 0` regardless (belt under
the ruling's braces).

Contents:
§0 Scope & Reference (incl. HLD errata) · §1 Interfaces & API · §2 Data Structures & Schema ·
§3 Core Logic · §4 Knob table (25 keys) · §5 Error Handling & Edge Cases ·
§6 Backward Compat & Migration · §7 Testing · §8 Calibration-readout spec skeleton ·
§9 Open Questions

---

## 0. Scope & Reference

### 0.1 What this LLD specifies

One new module `backend/trade_breaker.py` (evaluation layer, leaf), one new pure template
function in `backend/trade_narrative.py`, two new read-only bulk readers in
`backend/database.py` (§2.2 — no schema change), four surgical edits in `backend/server.py`
(seam block, features block, serialization block, nothing else), 25 `model_config` knobs, two
flags, one mobile card element, one structural guard, and the full test list. No new tables, no
new routes, no migrations (`breaker_` table prefix stays reserved-unused).

### 0.2 HLD ERRATA (ruled during LLD merge — apply to HLD.md after LLD convergence)

Four places where this LLD deliberately contradicts the HLD's literal text, each a recorded
orchestrator ruling; the HLD's *intent* survives in every case:

| # | HLD text | Erratum (ruling) |
|---|---|---|
| E-A (M-2) | §3.3 impression-copy sketch: `if flags.trade_breaker: features["breaker"] = card.breaker` — flag-gated bare-attribute read, "no getattr default" | The copy is **ATTRIBUTE-gated with a synthetic degradation-marker fallback** (§1.4). The HLD's version has a live crash path: a mid-job hot flag flip (`POST /api/feature-flags/reload` is a route) or an injected-card race makes the bare read raise, and because the impression row loop has **no per-row try/except** (`server.py:4122-4233`), one AttributeError loses the *entire deck's* impressions to the outer catch (`:6129`). The HLD's real invariant — never a bare null, absence impossible on a flag-on row — is preserved by the synthetic marker `{ver: null, degraded: "flag_flip_or_unstamped", objections: null}` and enforced in tests (§7.3) |
| E-B (M-3) | §5.4 cost model: "~30 served cards" | `bakeoff_deck_limit` was raised 30→60 at the A-1 boundary (`model_config_changes`, 2026-08-21 00:43:33Z — PLAN §10 A-1). **All ms budgets, checkpoint math, the size budget (§2.7), and the pre-flag-on dry-run contract use 60** as the bake-off deck bound |
| E-C (M-4) | §2.5/§5.4: PartnerContext built "over data the job already loaded" | True for rosters, boards, and league state; **false for partner `asset_preferences` and declared `league_preferences`** — the job loads only the VIEWER's untouchables (`server.py:5546-5556`). Fixed by two read-only bulk readers (§2.2), one `IN (...)` select each per job — not per-partner query loops |
| E-D (cross-review) | §2.6 rung-4 row: a per-card exception ⇒ whole-card rung-4 marker | **Per-CLASS containment** (§5.1 field-level row / E-14): an exception inside ONE class's predicate stamps that class alone `severity: null, skipped: "predicate_error"`; the card stays rung 0 with the other classes scored. Whole-card rung 4 is reserved for failures outside any class predicate. One flaky predicate must not zero the coverage metric for all six classes — the narrowing preserves the HLD's degrade-and-mark intent |

### 0.3 Verified anchor table (the build re-cites all of these)

| Symbol | Location (this checkout) |
|---|---|
| `_DEFAULT_CFG` head / five-registration discipline comment / `_cfg` | `backend/trade_service.py:40` / `:888-899` / `:966` |
| `reload_config` / `_cfg_override` (thread-local overlay, exits with the arm's `with` block) / `_c` accessor | `trade_service.py:969` / `:995` / `:1004` |
| `stud_tax_override` (contextmanager; unpinned at the post-F9 seam ⇒ `'market'` default) | `trade_service.py:1089` |
| `elo_to_value` / `package_value_v2` | `trade_service.py:1267` / `:1298` |
| G6 predicates: `overpay_ok` / `pos_net_ok` / `pick_gap_ok` / `need_gate_ok` | `trade_service.py:1869` / `:1891` / `:1916` / `:1950` |
| `_POS_TIER_CUTS` (12-team assumption, comment `:2069-2070`) / SF QB cuts / `_POS_TIER_MIN_POOL = 40` (tier_basis fallback reporting `:2266`) | `trade_service.py:2071-2077` / `:2078` / `:2086` |
| `analyze_roster_strengths` | `trade_service.py:2211` |
| `_now_lean` | `trade_service.py:2648` |
| `infer_team_outlook` (INV-372b docstring; score+cuts) | `trade_service.py:3084` (invariants `:3166-3175`; cuts `:3313-3318`) |
| `LeagueMember` / `League` | `trade_service.py:3613` / `:3753` |
| Engine's declared-else-inferred partner-outlook resolution (the shape §3.2 mirrors) | `trade_service.py:4948-4956`; same shape `trade_gen_v2.py:982-989` |
| `waiver_slot_cost` default 425.0 | `trade_service.py:184` |
| `_consensus_packages` / `_pos_counts` / `_feasible_after` / `_subset_pos_delta` / `_starters_at` | `trade_optimizer.py:99` / `:150` / `:161` / `:180` / import `:57` |
| `_opponent_frame` (thresholds ±0.05 at `:96-99`) / `_give_side_now_lean` / `build_narrative` / honesty comment / 2-sentence cap | `trade_narrative.py:86` / `:71` / `:103` / `:119-126` / `:168` |
| `stamp_fit_diag` (stamp-shape precedent; per-card try/except) | `trade_gen_fit.py:857` |
| `_job_live` / `_job_superseded` | `server.py:2902` / `:2917` |
| Streaming publish (`on_opponent_done` snapshot) | `server.py:2984-3006` |
| `_served_cards` (the render gate every publish loops through) | `server.py:4007` |
| `_log_deck_signal_impressions` def / empty-deck early return / per-row loop (served + ghost entries; **no per-row try/except**) / bakeoff features guard / fit keys | `server.py:4020` / `:4060-4061` / `:4120-4122` / `:4193` / `:4205-4206` |
| `_run_trade_job` / per-format `trade_svcs` instance / prefs load (viewer only) / `opponent_outlooks` build | `server.py:5412` / `:5438-5440` / `:5546-5556` / `:5516-5527` |
| M3 fit_diag stamp block | `server.py:5698-5716` |
| Mutation stack + its conditional republishes: F7 split / likes-you / F3 / `_order_deck` / F7 wildcard / F9 (republish loops at `:5728/:5769/:5819/:5914/:5955/:6003`) | `server.py:5722-5725` / `:5747` / `:5794` / `:5900` / `:5937` / `:5997-6028` |
| **The seam**: end of F9 block (`except br_err` handler `:6027-6028`) → telemetry-split comment `:6030` → `served_final = final_cards` | insertion between `server.py:6028` and `:6030`; `served_final` at `:6034` |
| Ghost split (inert under the ruling) / impressions call / signal_v2 republish / outer catch | `server.py:6035-6046` / `:6101` / `:6115-6128` / `:6129-6130` |
| `trade_card_to_dict` / fit serialization block | `server.py:10976` / `:11054-11060` |
| co-owner `league_members` keying comment ("keyed on the primary owner's id") | `server.py:16970-16975` |
| `_MODEL_CONFIG_DEFAULTS` / `set_config` / `save_deck_impressions` (executemany first-row-keys trap) | `database.py:2188` / `:4191` / `:5503-5516` |
| `PASS_REASON_LAYER2` (the vocabulary anchor) | `database.py:5579-5583` |
| `ASSET_PREF_LISTS` / `load_asset_preferences` / `league_preferences` table | `database.py:8657` / `:8660` / `:987-991` |
| `FLAG_KEYS` / `DEFAULT_FLAGS` / `FLAGS` proxy | `feature_flags.py:47` / `:939` / `:1082` |
| Precedent tests: `test_fit_diag_inert` / `test_organic_never_imports_fit` / `test_impressions_uniform_columns` | `backend/tests/test_trade_gen_fit.py:681` / `:883` / `test_bakeoff_serving.py:1170` |
| `_PINNED_KNOBS` / inventory guard | `test_bakeoff_arm_a_golden.py:471` / `:546-547` |
| Mobile mount region (fitLine row → consensus-note; narrative comment `:437`) | `mobile/src/components/TradeCard.tsx:452-478` |

### 0.4 Import discipline (binding, from HLD §2.2)

`trade_breaker` imports `from . import trade_service as ts` and
`from . import trade_optimizer as topt` — MODULE imports (fit T1 discipline), every symbol
reached as `ts.<name>` / `topt.<name>` at call time so knob rebinds and monkeypatches
propagate (`test_breaker_binding_sabotage`, §7.1) — plus `from . import trade_narrative` (for
`hesitation_line` + `HESITATION_TMPL_VERSION`) and the two §2.2 bulk readers from `database`.
It **never** imports `trade_gen_fit` (organic-isolation contract stays intact; the them-lens
number is read off `card.fit_diag`, never rescored — HLD D-3), never imports `server`, never
imports `bakeoff_runner`, never calls `_shrink_user_elo` (T3: raw boards only). `trade_service`
never imports `trade_breaker`. The only production caller is the §1.2 seam block
(`test_flag_off_never_imports_breaker`). The breaker uses module-level `ts` helpers plus
explicit arguments only, never the session's per-format `TradeService` *instance*
(`server.py:5438-5440`) — see §5.5 E-22.

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
from . import trade_narrative            # hesitation_line + TMPL version

logger = logging.getLogger(__name__)

#: Pinned evaluator version — stamped into every breaker/breaker_shadow
#: payload AND hardcoded as a literal in the server rung-5 handler
#: (test_rung5_marker_version_pinned keeps the two equal). Bump on ANY change
#: to predicates, severity math, floors semantics, evidence shapes, the
#: tie-break priority order, or the format envelope. Calibration readouts
#: filter on this alone (HLD §5.5).
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

#: M-6 — argmax tie-break priority when two classes clear their floors at
#: equal (3-dp-rounded) severity: earlier in this tuple wins. A module
#: CONSTANT pinned under BREAKER_VERSION, never a knob — an unpinned
#: dict-order tie-break is a determinism bug waiting for a Python bump.
TIEBREAK_PRIORITY = ("fit_new_weakness", "fit_outlook", "other_player_keep",
                     "fit_duplicate", "roster_crunch", "value_giving")

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

#: The closed breaker-owned knob list, read ONCE per stamp_breaker call into
#: a frozen per-job snapshot (§3.0 — M-5). Enumerated to match the 25 §4
#: registrations exactly; the knob-inventory guard pins those two lists
#: equal. The SNAPSHOT key set is the union of this list and
#: _SHARED_ENGINE_KNOB_KEYS below — the inventory guard still pins exactly
#: the 25 registrations; the snapshot list pins the union.
_BREAKER_KNOB_KEYS: tuple[str, ...]

#: Engine-owned knobs the breaker also reads (§3.4 waiver adjustment, §3.5
#: roster_crunch). ALREADY five-registered as engine keys — they need NO new
#: registration and are not counted in §4's 25 — but they MUST be in the
#: frozen snapshot: reading them live via ts._c mid-job would reintroduce
#: the §3.0 hot-flip hazard, and leaving them out of `cfg` is a KeyError.
_SHARED_ENGINE_KNOB_KEYS: tuple[str, ...] = ("waiver_slot_cost",)
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
                                         # off — the bulk reader then resolves
                                         # declared prefs itself, §2.2/§3.2)
    pick_shares: dict[str, float] | None = None,      # opponent_pick_shares
) -> "BreakerJob":
    """Evaluate every card from the counterparty's seat and set
    `card.breaker` (+ `card.breaker_shadow` when breaker_shadow_run >= 1).
    Attribute-setting only; two deck-wide passes under breaker_ms_budget with
    the §5 degradation ladder. EVERY card leaves this function carrying the
    attribute — scored payload or minimal marker; absence is impossible by
    construction (M4 pattern). RAISES NOTHING: every exception is absorbed
    into rung-4/5 markers internally; the server-side try/except (§1.2) is
    belt-and-braces for the import line and a bug in the marker path itself.
    Idempotent: a second call overwrites card.breaker wholesale. `cards` may
    be empty (F3 can empty a deck) — no-op, zeroed report. Returns the
    per-job holder (§3.0): the frozen knob snapshot plus the diagnostics
    report (HLD §5.5, FitReport precedent — no DB)."""
```

```python
def compose_narration(cards: list, *, players: dict,
                      job: "BreakerJob") -> int:
    """Deck-level narration pass (flag trade.breaker_narrative, checked at the
    CALLSITE — this function assumes it is wanted). For each card with a
    scored vector: apply the eligibility chain (§3.8 — per-class switch,
    whitelist, basis rule, format envelope, floors + breaker_min_severity,
    outlook narration margin), then deck-level repetition suppression, then
    call trade_narrative.hesitation_line(objection, players) and write
    card.breaker["narrated"] / ["suppressed"] / ["tmpl_ver"]. Returns the
    count narrated (0 is normal and is the M-1 republish condition). Never
    touches card.narrative, card order, or breaker_shadow (shadow never
    narrates). Idempotent; must run after stamp_breaker in the same job; a
    card without card.breaker stamps nothing and is counted in diagnostics
    (defensive — reachable only via a bug, never an exception). Per-card
    internal exceptions stamp `suppressed: "template_error"` (§5.5 E-15),
    never raise. `job` is stamp_breaker's return: this function reads
    job.cfg — the SAME §3.0 knob snapshot, held per-job, never a re-read —
    and UPDATES job.report's narration counters (narrated /
    suppressed_by_reason)."""
```

```python
@dataclass
class BreakerReport:               # FitReport precedent — per-job diagnostics,
    cards_seen: int; stamped: int  # rides job diagnostics only, no DB
    degraded_by_rung: dict[int, int]
    narrated: int; suppressed_by_reason: dict[str, int]
    class_fires: dict[str, int]    # top.code histogram
    predicate_errors: int          # §5.5 E-14 per-class containment counter
    format_gapped_decks: int       # 0/1 — this deck had ≥1 gapped class
    partner_ctx_built: int; partner_ctx_failed: int
    ms_total: float; ms_p50_card: float; ms_p95_card: float
    pass2_ran: bool                # False ⇒ rung-2 fired


@dataclass
class BreakerJob:                  # the §3.0 per-job holder — stamp_breaker's
    cfg: dict                      # return value. Carries the frozen knob
    report: BreakerReport          # snapshot AND the report; compose_narration
                                   # receives it and updates report in place.
                                   # Ephemeral (job diagnostics only, no DB).
```

Private per-class predicate functions (§3.3–§3.6), each
`_obj_<code>(card_view, pctx) -> dict` returning one objection entry
`{code, severity, evidence}` — always; a non-firing class returns
`severity 0.0` with its evidence shape's mandatory keys; a class inapplicable to the inputs
returns `severity: null, skipped: "not_applicable"` per the §3.10 degenerate-input table
(M4: absence impossible, only zero/skip representable). `_partner_context(...)` builds §2.2
lazily, cached per `target_user_id` per call (§2.3 identity ruling — owner-id keyed).

### 1.2 The server seam — `_run_trade_job`, post-F9, pre-ghost-split (M-1)

**Insertion line:** immediately after the F9 block's final `except br_err` handler
(`server.py:6027-6028`), immediately before the `# suggestion.telemetry — split the final
deck…` comment (`server.py:6030`) and the `served_final = final_cards` assignment (`:6034`).
At that line `final_cards` is the exact list `_log_deck_signal_impressions` receives at
`:6101` (mutation stack complete; likes-you-injected cards included), and every name the
breaker reads is in scope: `g_league`, `players_dict`, `seed_map`, `active_format`,
`league_id`, `g_user_id`, `elo_map_rt`, `outlook_value`, `opponent_outlooks`,
`opponent_pick_shares`, `real_user_ids`, `ghost_on`, `job_id`, `_generate_kwargs`.

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
        # Both flags read ONCE, up front (§5.5 E-8): the pair the whole
        # block acts on is one coherent read. (Flag and knob reads at call
        # time INSIDE engine helpers — e.g. trade_crown_asset and the _c()
        # knob reads in _package_value_market — are the accepted
        # engine-wide residual, §5.5 E-8.)
        # Skips (T-1 ruling, §9 Q-10): the demo league (consistent with
        # every neighboring mutation layer, server.py:5631-:5981, and the
        # demo-guarded impressions block :6066/:6092; a PRD open question
        # records the "narrate on demo as demo material" lift option) and
        # superseded jobs (pure wasted-compute avoidance — no correctness
        # dependency either way, §5.5 E-13).
        _bk_on   = FLAGS.trade_breaker
        _bk_narr = FLAGS.trade_breaker_narrative
        if (_bk_on and league_id != "league_demo"
                and not _job_superseded(job_id)):
            try:
                from .trade_breaker import stamp_breaker, compose_narration
                # lazy — flag-off never imports (NFR-3,
                # test_flag_off_never_imports_breaker)
                _bk_job = stamp_breaker(
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
                _n_narrated = 0
                if _bk_narr:
                    _n_narrated = compose_narration(final_cards,
                                                    players=players_dict,
                                                    job=_bk_job)
                if _n_narrated:
                    # M-1 republish contract: republish iff narrated_count
                    # > 0, so the narrated payload reaches the snapshot the
                    # client actually receives on EVERY flag combination
                    # (§1.3) — the deck.signal_v2 republish at :6115 is
                    # conditional and must not be relied on. Same idiom as
                    # the F7/F9 republishes above (standard decoration,
                    # _served_cards path, _job_live-guarded).
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
                # BOTH markers stamped with NO knob read and NO module
                # reference: in _run_trade_job the local `trade_service` is
                # the per-format TradeService INSTANCE (server.py:5440),
                # which has no `_c` — and a live knob read at failure time
                # would violate the §3.0 one-job-one-knob-state rule anyway.
                # A shadow marker on a shadow-off deck is harmless (readouts
                # treat markers as degraded either way); an existing shadow
                # stamp is preserved.
                for _bc in final_cards:
                    _bc.breaker = dict(_mark)
                    if getattr(_bc, "breaker_shadow", None) is None:
                        _bc.breaker_shadow = dict(_mark)
```

Two structural differences from the M3 fit stamp (`server.py:5698-5716`), restated from HLD
§2.3: the guard is `FLAGS.trade_breaker`, not `bakeoff_run is not None` (organic decks stamp
too), and the input is the served deck, not per-arm ranked lists (D-9).

Contract points the build is held to (converged, B §2.3):

1. **Republish only when `_n_narrated > 0`.** A dark-stamp deck (narrative flag off, or on
   with zero narrated) publishes nothing new — flag-1-only byte-identity extends to the
   *publish stream* (NFR-1/NFR-3; §7.4 republish-matrix test pins publish counts).
2. The breaker republish precedes impression logging, so it never carries `impression_id`;
   the `:6115` republish restores that when `deck.signal_v2` is on. Ordering: breaker
   republish (sentence, no iids) → impressions → final republish (sentence + iids). Clients
   tolerate the intermediate state — it is the same state every mutation-layer republish
   already produces.
3. The rung-5 outer marker is constructed inline with **no breaker-module dependency** — the
   import line is one of the failure modes it must cover (NFR-2's "constructible with no
   breaker state" made literal).
4. The seam block carries **both skips** — `league_id != "league_demo"` and
   `not _job_superseded(job_id)` — per the T-1 cross-review ruling (§9 Q-10, closed). Neither
   is load-bearing for correctness: superseded jobs already skip the signal block
   (`:6092-6093`) and every publish is `_job_live`-blocked, so no wrong rows and no wrong
   renders were possible without them. The demo skip buys consistency with every neighboring
   mutation layer (`server.py:5631-:5981`) and the demo-guarded impressions calls
   (`:6066`/`:6092`) — and avoids narrating synthetic demo partners; a PRD open question
   records the deliberate "narrate on demo as demo material" lift option as a product call.
   The superseded skip is pure wasted-compute avoidance.

### 1.3 Snapshot-republish analysis — every flag combination (M-1)

The HLD deferred the republish site; here is the verified picture. Streaming snapshots are
published by `on_opponent_done` (`server.py:2984-3006`), then conditionally replaced by the
mutation-layer republishes — F7 split (`:5726-5736`), likes-you (`:5768-5777`), F3
(`:5815-5827`), `_order_deck` (`:5911-5922`), F7 wildcard (`:5953-5963`), F9 (`:6002-6011`,
first decks only) — **every one conditional on its layer having changed the deck**, and
finally the deck.signal_v2 post-impression republish (`:6115-6128`), which re-serializes every
card via `trade_card_to_dict` but runs **only** when `deck.signal_v2` is on AND `imp_by_card`
is truthy AND the job is live. With `deck.signal_v2` off there is **no unconditional
post-mutation publish at all** (completion comment `:6145-6146`) — a narrated sentence stamped
post-F9 would exist in `features_json` and never reach any client on that flag combination.
That finding is why the seam block owns a republish:

| Flag state | Payload carries `breaker`? | Carrier |
|---|---|---|
| `trade.breaker` off | no (no key, no import) | n/a — snapshots byte-identical to today |
| breaker on, narrative off (dark window) | **no key at all** (§1.5 narration gate) | no republish runs in the seam block (`_n_narrated == 0` because `compose_narration` never ran) — snapshots byte-identical to flag-off (test_breaker_payload_absent_during_dark_window) |
| breaker on, narrative on, ≥1 narrated, `deck.signal_v2` on | yes | the seam republish (§1.2) delivers it; the `:6115` republish re-serializes later and preserves it (`trade_card_to_dict` reads the attribute) — either alone suffices, both are correct |
| breaker on, narrative on, ≥1 narrated, `deck.signal_v2` **off** | yes | **the seam republish is the only carrier** — this row is why the block owns one |
| breaker on, narrative on, 0 narrated | no key | no republish (guard False); correct and cheap |
| narrated but impressions insert failed (`imp_by_card` falsy) | yes | sentence already published by the seam republish; measurement lost for that deck (existing failure class), exposure NOT lost; the A/B readout excludes such decks (no outcome rows to join) |
| job superseded mid-run | n/a | job superseded BEFORE the seam ⇒ the T-1 guard skips the whole block (no stamp, no publish); superseded DURING the block ⇒ the `_job_live` guard inside the republish blocks it — same posture as every other publish site |

The republish precedes the ghost split, so it uses the `_served_cards(final_cards, …)` idiom
exactly like F7/F9 (`ghost_on` is False in prod under the no-ghost ruling; the helper is kept
for byte-parity with the neighboring sites, not for ghost behavior). §7.4's flag-matrix test
(B's T-13, required by M-1) parametrizes `deck.signal_v2` × streaming state × breaker-flag
combination and asserts the sentence reaches the final stored `j["cards"]` exactly per this
table.

### 1.4 `_log_deck_signal_impressions` — the features block (M-2; HLD §3.3 erratum E-A)

Placed immediately **after** the `if bakeoff_run is not None:` guard block that carries the
fit keys (`server.py:4193-4206`), **outside** that guard (organic rows stamp too — HLD §3.3),
before the wildcard block (`:4207`):

```python
        # Counterparty breaker (LLD §1.4, ruling M-2) — OUTSIDE the
        # bakeoff_run guard: organic decks stamp too. ATTRIBUTE-gated, not
        # flag-gated: a mid-job hot flag flip must not make this block see a
        # flag state the stamp site never saw, and this loop has NO per-row
        # try/except — one AttributeError here would lose the whole deck's
        # impressions (fit keys included) to the outer catch at :6129.
        # When the flag reads ON at log time but a card lacks the attribute
        # (hot-reload flip mid-job, injected-card race), a SYNTHETIC
        # degradation marker is written — never a bare null, never a crash,
        # never a silent absence on a flag-on row (invariant lives in tests:
        # test_impressions_breaker_uniform_keys, test_midjob_flag_flip).
        # Both keys ride INSIDE features_json (one column) — the
        # save_deck_impressions executemany first-row-keys trap
        # (database.py:5503) cannot drop them. Ghost rows (inert under the
        # no-ghost ruling) take the same copy; readouts filter is_ghost=0
        # regardless.
        _bk = getattr(card, "breaker", _BK_SENTINEL)
        if _bk is not _BK_SENTINEL:
            features["breaker"]        = _bk
            features["breaker_shadow"] = getattr(card, "breaker_shadow", None)
        elif FLAGS.trade_breaker:
            features["breaker"] = {"ver": None,
                                   "degraded": "flag_flip_or_unstamped",
                                   "objections": None}
            features["breaker_shadow"] = None
```

`_BK_SENTINEL` is a module-level `object()` in `server.py`, defined beside `_served_cards`
(`server.py:4007`) — a fresh sentinel (never `None`) so "attribute absent" stays
distinguishable from any stamped value.

Flag off at both sites ⇒ no key ⇒ rows byte-identical (NFR-3). Uniform at the JSON level on
every row of a flag-on deck, both draft paths (`test_impressions_breaker_uniform_keys` extends
`test_impressions_uniform_columns`, `test_bakeoff_serving.py:1170`). The synthetic marker's
`ver` is null by construction — at log time the module may never have been imported, so no
version literal can honestly be claimed; readouts treat `ver: null` rows as degraded
(never-covered), exactly like rung-3+ markers (§8). A stamped card's payload rides through
regardless of the flag's log-time state (the stamp existed at serve — the correct fact to
record).

### 1.5 `trade_card_to_dict` — narration-gated serialization

One additive block after the fit block (`server.py:11054-11060`):

```python
    # Counterparty breaker (HLD §3.6) — NARRATION-GATED: during the dark-
    # stamp window (trade.breaker on, trade.breaker_narrative off) the
    # payload carries NO breaker key at all — dark-class codes must never
    # ship as inspectable structured data. The full objection vector never
    # serializes (features_json only); card.breaker_shadow NEVER serializes
    # (test_breaker_shadow_never_serialized). `top` is non-null whenever
    # narrated is (compose_narration's invariant, pinned in tests) — the
    # unguarded index is deliberate: a violation must fail loudly in tests.
    _bk = getattr(card, "breaker", None)
    if isinstance(_bk, dict) and _bk.get("narrated"):
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
    code, a non-narratable code, or any missing evidence key the template
    renders — and a present-but-NULL value in such a key counts as missing
    (a null `age` must return None, never render "None-year-old"; never
    guesses, never substitutes; a template that renders no evidence fields
    is unaffected by nulls). Raises nothing (any internal error → None; the caller
    stamps suppressed="template_error", §5.5 E-15). Pure; no flag reads, no
    knob reads — eligibility lives in trade_breaker.compose_narration, the
    flag at the server seam. Inherits the positional-honesty covenant
    (trade_narrative.py:119-126).
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
`FLAGS.trade_breaker_narrative` — the `trade_likes_you` precedent). `trade.breaker_narrative`
alone does nothing (the narration call sits inside the `FLAGS.trade_breaker` block — the
requires-relationship is structural, not checked twice).

### 1.8 Mobile — the hesitation element

`mobile/src/components/TradeCard.tsx`, mounted after the FB-47 partner-fit line row
(`:452-458`) and before the consensus-note block (`:460-478`) — the same muted, hint-tier
band of the card:

```tsx
{/* Counterparty breaker — "their likely hesitation" (flag
    trade.breaker_narrative; the server serializes `breaker` only for
    narrated cards, so payload presence IS the gate — a client-side flag
    check would add a second gate that can only disagree, fit precedent).
    Chalkline: type tokens + flare for the informational dot (ADR-005) —
    no new colors, no emoji, radius within spec. */}
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
  `trade-card-breaker-hesitation` is superseded by the repo idiom — flagged §9 Q-8.)
- The client never switches on `code` (cross-client-invariants row stays "n/a in v1") and
  contains no string-literal sentence — server-composed copy only (structural guard §7.5).
- The TS card-payload type (the type carrying `real_opponent` / `fitPremium`) gains
  `breaker?: { code: string; severity: number; sentence: string }` — additive, optional.
  Older builds ignore unknown keys (fit precedent); no minimum-version gate needed.
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
    "evidence": {…}                //   (a selection, not a score — D-4);
  },                               //   ties broken by TIEBREAK_PRIORITY (M-6)
  "objections": [                  // list — EVERY v1 class exactly once, pass
    {"code": "fit_outlook",        // order §3.4; below-floor classes still
     "severity": 0.82,             // listed (the §6.4 counterfactual needs the
     "evidence": {…}},             // full vector); envelope-gapped classes
    {"code": "fit_duplicate",      // carry severity null + skip marker:
     "severity": 0.0, "evidence": {…}},
    {"code": "fit_new_weakness",
     "severity": null, "skipped": "format_gap", "evidence": {}},
    …                              // severity: float 0–1 rounded to 3 dp | null
  ],                               // skipped ∈ "format_gap"|"budget"|
                                   //   "not_applicable"|"partner_snapshot"|
                                   //   "predicate_error" (E-14: this class's
                                   //   predicate crashed — durable, so the
                                   //   §8 degraded-share readout can count
                                   //   unattributable crashes from data)
  "them": 41.3,                    // float|null — card.fit_diag them-score
                                   // PASSTHROUGH (D-3); null on organic decks
                                   // and likes-you-injected cards
  "narrated": null,                // str|null — the hesitation sentence
  "suppressed": null,              // null | "repetition" | "below_floor" |
                                   //   "class_ineligible" | "format_gap" |
                                   //   "template_error" (§5.5 E-15)
  "outlook_src": "legacy",         // "declared" | "legacy" | "composite"
  "outlook_pair": {                // BOTH sources retained (D-8 agreement rule)
    "declared": null,              //   str|null — private; stamps only, never
    "inferred": "rebuilder",       //   narrated from (item 14)
    "score": -0.041                //   float — infer_team_outlook score
  },
  "board_auth": "consensus",       // "board" | "board_suspect" | "consensus"
  "value_mode": "market",          // M-5 provenance — the stud-tax mode pinned
                                   // around every breaker valuation (§3.0);
                                   // constant "market" in v1, stamped so a
                                   // future mode change is visible in data
  "identity_src": "owner_id",      // §2.3 co-owner ruling marker
  "format_gap": null,              // null | ["fit_new_weakness", …] (§3.7)
  "degraded": null,                // null | rung marker (§5.1)
  "skipped": null,                 // null | {"classes": [...], "reason": "budget"}
  "ms": 4.1                        // float, 1 dp — evaluation wall-ms,
                                   // diagnostics only, never an input
}
```

**Minimal marker** (every degraded/exception path at rungs 3–5; never a bare null; exactly
three keys so it is constructible anywhere, including the server-local rung-5 handler with no
breaker state; the attribute/key is absent only when the flag is off):

```jsonc
{ "ver": "brk-1", "degraded": "exception_outer", "objections": null }
```

**Synthetic log-time marker** (M-2 — written by §1.4 only, when the flag reads on at log time
but the card carries no attribute; `ver` null because no module version can honestly be
claimed at that site):

```jsonc
{ "ver": null, "degraded": "flag_flip_or_unstamped", "objections": null }
```

Markers carry `top`/`narrated` absent (not null); consumers use `.get`. Severity rounds to
3 dp and `ms` to 1 dp — part of determinism (float-repr noise breaks byte-identity tests)
AND of the §2.7 size budget.

### 2.2 `PartnerContext` + the two bulk readers (M-4; HLD erratum E-C)

```python
@dataclass
class PartnerContext:
    """One counterparty's present-state snapshot. Built lazily, once per
    target_user_id per stamp_breaker call, ONLY for partners appearing in
    the served deck. All reads are state the job already holds PLUS the two
    per-job bulk reads below (partner prefs + declared outlooks are NOT
    pre-loaded by the job — HLD erratum E-C)."""
    user_id: str                      # LeagueMember.user_id (league identity —
                                      # primary-owner keyed, server.py:16970-16975)
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
    prefs: dict                       # from the bulk asset-prefs read —
                                      # untouchables/targets/not_interested
                                      # (§2.3 identity ruling: owner-id only)
    format_gap: list[str]             # ENVELOPE_CLASSES gapped for this league/
                                      # roster (§3.7); [] when fully modeled
    identity_src: str = "owner_id"
    degraded: str | None = None       # "partner_snapshot" when construction
                                      # failed (rung 1)
```

**Bulk reads, not per-partner queries (M-4).** Two new thin **read-only** helpers in
`database.py` — no schema change, one `IN (...)` select each, called once per
`stamp_breaker` call for the distinct partner set (≤ league size):

```python
def load_asset_preferences_bulk(user_ids: list[str], league_id: str) -> dict[str, dict]:
    """{user_id: {list_type: [asset_ids]}} for every user in user_ids that has
    rows; absent users simply missing. Read-only; ASSET_PREF_LISTS shapes
    (database.py:8657) identical to load_asset_preferences (:8660)."""

def load_league_preferences_bulk(user_ids: list[str], league_id: str) -> dict[str, dict]:
    """{user_id: prefs_row_dict} (incl. team_outlook) from league_preferences
    (database.py:987-991). Read-only."""
```

Per-partner fallback loops would add up to ~2 × 11 queries per deck on the job thread; two
queries fetch the same data. DB failure on either bulk read degrades **all** partners'
affected fields (prefs → empty + `other_player_keep` stamps `skipped: "not_applicable"`;
declared outlook → None, resolution falls to inferred) — stamped rung 0 with the field-level
skip markers, **NOT rung 1**, which is reserved for a partner's snapshot build failing
(roster/strengths/board): prefs absence is a legitimate common state and marking it "degraded"
would swamp the rung metrics. Sibling-collision note: negmem may want equivalent readers —
whichever plan lands first owns them, the other reuses (§9 Q-11).

The **viewer context** for the shadow run is the same dataclass built from `viewer_roster` /
`viewer_elo` / `viewer_outlook` / the viewer's own prefs (included in the bulk read's id set),
`outlook_src="declared"` when `viewer_outlook` came from prefs (the seam can't distinguish
declared from #8-seeded; stamped `"declared"` either way with the pair recording both —
acceptable for a never-serialized shadow, noted §9 Q-9).

### 2.3 Identity ruling — co-owners (M-7; deviation from HLD §3.4, ruled)

HLD §3.4 rules "resolve over `{owner_id} ∪ co_owner_ids(roster)` via `sleeper_roster`". At the
seam **no raw Sleeper roster dict exists**: `League`/`LeagueMember`
(`trade_service.py:3613/:3753`) carry no `co_owners`, the `league_members` DB rows are keyed
on the **primary owner's id** (`server.py:16970-16975`), and nothing persists the co-owner
list server-side — `co_owner_ids` (`sleeper_roster.py:34`) is only ever fed by live Sleeper
fetches. Fetching live inside the trade job would add a network call to every deck
(NFR-2/NFR-4 violation). **Ruling (M-7):** counterparty state resolves under `member.user_id`
alone; every stamp carries `identity_src: "owner_id"`; the co-owner fixture test (§7.1) pins
that a co-owner's prefs stored under a *different* account id are NOT read (documented
limitation, not silent wrongness) — this satisfies HLD §3.4's degrade-and-mark intent. **The
union variant is an explicit non-goal pending a data-path change** (persisting `co_owners` at
league-sync time — §9 Q-3, a named v1.1 candidate with its own tiny scope block).
`board_src` conflict handling (two boards) is thereby moot in v1: at most one board exists per
league identity. `PartnerContext` caching stays keyed by `target_user_id` (no
`canonical_owner_id` at this seam).

### 2.4 Evidence key enums (closed, per code — the whitelist's mechanical form)

Values are ids, numbers, and enum strings ONLY — no free text, no player names
(names resolve from ids at template time). `hesitation_line` may read only these keys, and
the vocabulary-closure test checks **evidence keys too, not just codes** — an unlisted key is
how a private-state leak sneaks past the whitelist (§7.1).

| code | evidence keys (all mandatory when scored) |
|---|---|
| `fit_outlook` | `outlook` (enum), `lean` (float, §3.3 quantity), `asset` (pid of the highest-consensus-value incoming player driving the lean; null for all-pick packages), `age` (int\|null), `pos` (enum\|null) |
| `fit_new_weakness` | `pos` (enum), `before` (int), `after` (int), `need` (int), `asset` (pid of the highest-value outgoing player at `pos`), `tier_basis` ("positional"\|"absolute" for `pos` — distinguishes production positional bands from the `_POS_TIER_MIN_POOL` absolute-cut fallback, `trade_service.py:2086/:2266`; fallback rows must be distinguishable in data) |
| `fit_duplicate` | `pos` (enum), `bench_n` (int), `value_share` (float), `asset` (pid of the highest-value incoming player at `pos`), `tier_basis` (same as `fit_new_weakness`) |
| `value_giving` | `basis` ("board"\|"consensus"), `margin` (float, their-seat surplus), `n_give` (int), `n_recv` (int) — **board-basis rows stamp dark; the margin still stamps for calibration** |
| `other_player_keep` | `asset` (pid), `list` ("untouchable") — **private; stamps dark, never renders (D-6)** |
| `roster_crunch` | `extra` (int), `slot_cost` (float), `pileup` (list of pos enums, possibly empty) |

### 2.5 `card.breaker_shadow`

Same schema as §2.1 evaluated from the **viewer's** seat (no give/receive swap), with
`narrated`/`suppressed`/`tmpl_ver` permanently null and `them` null (the fit them-score is a
partner quantity). Present on every card of a flag-on deck when `breaker_shadow_run ≥ 1`
(minimal marker on degraded paths — unlabeled shadow missingness would corrupt the §8 primary
calibration population exactly as breaker missingness would); permitted null only when the
shadow knob is off — with one exception: the rung-5 seam handler stamps a shadow minimal
marker unconditionally (it cannot read the knob at failure time, §1.2), so a shadow-off deck
that hits rung 5 carries markers; harmless, readouts treat markers as degraded either way. One
accepted asymmetry rides that handler (§1.2): the rung-5 primary marker OVERWRITES any existing
`breaker` stamp while an existing `breaker_shadow` stamp is PRESERVED, which mildly decorrelates
primary/shadow coverage on rung-5 decks — accepted; readouts treat markers as degraded on both
sides. Shadow evaluation is **interleaved per card after the primary stamp**,
never a second loop — budget exhaustion degrades primary and shadow *together*, keeping their
coverage correlated, which R-3's proxy-population argument needs (uncorrelated shadow
missingness would bias the viewer-seat calibration cut). **Never serialized**
(`test_breaker_shadow_never_serialized`).

### 2.6 Schema deltas

None. No tables, no columns, no routes. `deck_impressions.features_json` gains the two keys
(data-dictionary rows at build: `features_json.breaker` — §2.1 shape | §2.1 minimal marker |
§2.1 synthetic log-time marker, present on every row of a flag-on deck;
`features_json.breaker_shadow` — same | null).

### 2.7 Size budget (measured obligation, not vibes)

Realistic rung-0 stamp ≈ 6 objections × ~90–130 B + markers + top + sentence ≈ **0.9–1.4 KB**;
shadow doubles it ⇒ ~2–3 KB added per `features_json` (baseline ~0.7–1.0 KB). At the
**60-card** bake-off deck limit (erratum E-B): ~120–180 KB per deck insert. No column limit
bites (TEXT in both dialects; executemany fine at this scale), but it is a **pinned test**:
`test_stamp_size_budget` (§7.1) serializes a worst-case fixture stamp and asserts
`len(json.dumps(stamp)) < 4096` per card — a tripwire against evidence-shape creep, because
`features_json` rows are read back by every readout query and 10× growth is a query-cost
regression nobody would otherwise notice. The §2.1 rounding rules are part of this budget.

---

## 3. Core Logic

### 3.0 Per-job config snapshot + value-mode pin (M-5)

`stamp_breaker` begins with
`cfg = {k: ts._c(k) for k in _BREAKER_KNOB_KEYS + _SHARED_ENGINE_KNOB_KEYS}` — the 25
§4-registered `breaker_*` keys ∪ the shared engine list (`waiver_slot_cost`, already an engine
registration; §1.1) — and reads **only `cfg`** thereafter, both passes AND `compose_narration`
(which receives the same dict via the `BreakerJob` per-job holder, §1.1 — never a re-read; the
holder also carries the `BreakerReport`, which `compose_narration` updates). Three verified
hazards this kills:

1. **Hot knob flip mid-job**: `PUT /api/admin/config` → `reload_config()`
   (`trade_service.py:969`) mutates `_cfg` in place; without the snapshot, pass 1 and pass 2 —
   or two cards in one pass — could read different values ⇒ intra-deck nondeterminism
   invisible to `ver`. One job, one knob-state; `model_config_changes` censors the readout
   window (M1 rail).
2. **`_cfg_override` overlays / arm profiles**: verified inactive at the post-F9 seam — the
   thread-local overlay is a contextmanager (`trade_service.py:995`) that exits when each
   arm's generate call returns. The snapshot makes the breaker structurally indifferent to
   whether a future caller (v2 in-generation) sits inside an overlay. The binding-sabotage
   test (§7.1) pins that module-import discipline still propagates knob changes across
   *calls* (snapshot boundary is per-call, not per-process).
3. **Stud-tax thread-local**: unpinned at the post-F9 seam, so any `package_value_v2` call
   there silently uses the `'market'` default. The breaker makes this **explicit and
   deterministic**: every breaker valuation call is wrapped in
   `ts.stud_tax_override("market")` (`trade_service.py:1089`), and the mode is **stamped in
   provenance** (`value_mode: "market"`, §2.1). Design decision (recorded per M-5): the
   partner's own stud-tax setting is per-user private state — a DB read per partner, and
   using it would make the same card's severity depend on a partner's UI toggle, a
   calibration confounder; the partner's mode is unknowable in principle from the breaker's
   seat, and determinism wins. The consensus-default `'market'` is the one mode every seat
   shares.

### 3.1 Card mirroring (D-10)

Evaluation swaps give/receive **as a view at evaluation time**, never as data:

```python
@dataclass
class _CardView:                      # partner seat
    give_ids: list[str]               # = card.receive_player_ids (they send these)
    recv_ids: list[str]               # = card.give_player_ids  (they receive these)
```

No partner-frame shape labels are minted (taxonomy §2.1); the shadow run uses the unswapped
view. Value accessors, built once per call inside the §3.0 stud-tax pin:
`cval(pid) = ts.elo_to_value(seed_elo.get(pid, 1500.0))`; per-partner
`oval(pid) = ts.elo_to_value(pctx.board.get(pid, 1500.0))` iff boarded. Raw maps throughout
(T3).

### 3.2 Window resolution — mirrored from the engine, verbatim shape

`PartnerContext` resolves exactly the declared-else-inferred shape the engine uses at
`trade_service.py:4948-4956` / `trade_gen_v2.py:982-989`:

```python
declared = (declared_outlooks or {}).get(member.user_id)
if declared is None and not declared_outlooks:
    # trade.outlook_infer off ⇒ the job built no declared map; the breaker
    # reads the same source itself — via the §2.2 BULK reader (one query for
    # the whole partner set, never per-partner).
    declared = (bulk_league_prefs.get(member.user_id) or {}).get("team_outlook")
inferred, score, signals = ts.infer_team_outlook(
    member.roster, players,
    (pick_shares or {}).get(member.user_id, 0.0),
    num_teams)          # num_teams = len(league.members) + 1 — re-verify at
                        # build against trade_service._num_teams's source (Q-1)
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

> **⚠ FLAGGED FOR CROSS-REVIEW — NOT SETTLED (M-8).** The scalar choice below (unweighted
> `_give_side_now_lean` mean) is A's ruling and stands in this candidate, but M-8 explicitly
> reserves it for cross-review adjudication. The tradeoff it accepts: the mean **ignores
> value weighting** — a package of one 29-y/o stud plus three young throw-ins reads as mildly
> young even though the value overwhelmingly leans old; `ts.signed_lane_shift` (value-weighted)
> would capture that but would break the provable-coherence property below. Cross-review must
> either confirm the unweighted mean or propose a weighted quantity WITH a replacement
> coherence proof against `_opponent_frame`.

**Quantity:** `lean` = arithmetic mean of `ts._now_lean(pos, age)` (`trade_service.py:2648`)
over the assets the partner would **receive** (`view.recv_ids` = the viewer's give side) —
byte-parallel to `trade_narrative._give_side_now_lean` (`trade_narrative.py:71-83`),
deliberately NOT the value-weighted `ts.signed_lane_shift`. Picks stay **IN** the mean at
`_now_lean`'s PICK short-circuit constant −0.25 (`trade_service.py:2648-2656`) — exactly as
`_give_side_now_lean` counts them, which is what keeps the parity below byte-provable; an
all-pick incoming side therefore means lean = −0.25, never a skip (§3.10). Why the unweighted
mean: `_opponent_frame`
(`trade_narrative.py:86-100`) asserts window-FIT from exactly this quantity at |lean| ≥ 0.05;
computing the breaker's window-PUSH from the same number with mirrored thresholds makes the
§7.1 coherence test a *proof* (the two writers cannot disagree about the same scalar) instead
of a hope. Equality of the two computations is itself pinned (`test_lean_quantity_parity`);
any future threshold or quantity change lands breaker-side (HLD §2.4).

**Fire condition and severity:**

```python
o = pctx.outlook
if o in ("rebuilder", "jets"):      push = max(0.0,  lean - 0.05)   # aging
elif o in ("contender", "championship"): push = max(0.0, -lean - 0.05)  # youth/picks
else:                               push = 0.0                       # not_sure
sev = min(1.0, push / 0.35)                       # 0.40 lean ⇒ 1.0; constants
                                                  # pinned under BREAKER_VERSION (M-6)
if pctx.outlook_src == "legacy":
    sev *= cfg["breaker_outlook_haircut_legacy"]                     # D-8
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
value space, byte-parallel to the fit `_surplus` shape (fit LLD §1.7), inside the §3.0
stud-tax pin:

```python
def _net_player_bodies(view: "_CardView", players: dict) -> int:
    """Net PLAYER bodies the partner absorbs (recv − give), picks excluded
    (ts.is_pick_asset, trade_service.py:1764 — takes the player OBJECT, not
    the pid, hence the players.get lookup — Sleeper picks occupy no
    roster slot). The ONE computation behind both value_giving's waiver-slot
    adjustment and roster_crunch's `extra` (§3.5): shared so the two can
    never diverge."""
    recv = sum(1 for p in view.recv_ids if not ts.is_pick_asset(players.get(p)))
    give = sum(1 for p in view.give_ids if not ts.is_pick_asset(players.get(p)))
    return recv - give

rvals = [val(p) for p in view.recv_ids]; gvals = [val(p) for p in view.give_ids]
v_max = max(rvals + gvals)
recvd = ts.package_value_v2(rvals, v_max, n_other=len(gvals), other_values=gvals)
sent  = ts.package_value_v2(gvals, v_max, n_other=len(rvals), other_values=rvals)
extra = _net_player_bodies(view, players)
if extra > 0: recvd -= cfg["waiver_slot_cost"] * extra
margin = recvd - sent
sev = min(1.0, max(0.0, -margin) / cfg["breaker_value_scale"])
```

`val` = `oval` when `pctx.board_auth == "board"`, else `cval` (board_suspect and unboarded
both fall to consensus optics — PLAN F-3 — with `board_auth` recording why);
`basis` = "board"/"consensus" accordingly in evidence. `fit_diag` never feeds this number
(passthrough only, D-3). The class's **argmax floor is basis-dependent** — the §3.9 FINALIZE
top selection reads `breaker_floor_value_giving` on the board basis and
`breaker_floor_value_giving_consensus` on the consensus basis (the same split §3.8 step 5
applies at narration time).

> **Read the sketch above as POST-fix semantics (PLAN §10 A-1, amended text authoritative).**
> As shipped today, `'market'` mode **ignores `v_max` and `n_other`** — they are dead
> parameters "kept for signature compatibility" (`package_value_v2` docstring,
> `trade_service.py:1298`) — and the depth discount benchmarks each package against its OWN
> best asset; the sketch's `v_max` argument reads as `'heavy'`-mode math and has no effect in
> v1's pinned `'market'` mode. The operator-approved `fix/package-benchmark-sweetener` branch
> (merge held for the Monday window boundary) changes exactly that benchmarked quantity: the
> depth discount re-benchmarks to the **trade's best asset** (the "4-mids-for-a-stud scored
> fair" defect, `docs/reviews/2026-08-21-market-curve-comparison.md`). Breaker severities
> inherit the fix automatically through the module-level `ts.package_value_v2` call — no
> breaker code change. Sequencing: the pre-flag-on dry run, the calibration cohort (§8), and
> the arm-A golden re-capture (PLAN A-1(c)) all start **at/after** that Monday merge — nothing
> breaker-side cites the pre-fix golden SHA or pools severities across the merge.

**`other_player_keep`.** `hits = set(view.give_ids) ∩ set(pctx.prefs["untouchables"])`
(what they'd send away ∩ their untouchable list — `ASSET_PREF_LISTS`, `database.py:8657`).
`sev = 0.0` if none; else `0.9`, `+0.1` when a hit is the package-wide max-`cval` asset.
Permanently dark (D-6); evidence stamps the hit pid for calibration. (Whether prefs rows can
reference pick ids: verify at build — §9 Q-12.)

**Board authenticity (F-3 heuristic, `board_auth`).** Computed at context build when a board
exists: `divergent = |{pid ∈ board : |board[pid] − seed_elo.get(pid, board[pid])| ≥
cfg["breaker_board_div_min"]}|`; `board_auth = "board"` iff `divergent ≥
cfg["breaker_board_min_divergent"]`, else `"board_suspect"`; no board ⇒ `"consensus"`.
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
# severity table (written as plain if/elif at build; the table IS the spec):
#   worst_slack < 0  ⇒ 1.0   — infeasible: the mirror of the K3 kill the
#                              served card may never have been tested against
#                              (only the v3 path runs _feasible_after for both)
#   worst_slack == 0 ⇒ 0.60
#   worst_slack == 1 ⇒ 0.30
#   worst_slack ≥ 2  ⇒ 0.0
```

Only positions they actually send from can fire (`out_d > 0`) — receiving can't open a hole.

**`roster_crunch`** (extension code, `producer=breaker`; new logic ⇒ conservative maturity,
D-6/HLD §2.7). Fires from slot math + positional pile-up — bench size is NOT modeled
(`_feasible_after` docstring, `trade_optimizer.py:165-172`), so the "forced drop of a player
they demonstrably value" limb from the PLAN's definition is **not computable in v1** and is
recorded as an evidence gap (§9 Q-4), not approximated:

```python
extra = _net_player_bodies(view, players)   # §3.4's shared helper — net PLAYER
                                            # bodies they absorb, picks excluded;
                                            # one computation for both classes
if extra <= 0: sev = 0.0
else:
    pileup = [pos for pos in incoming_positions
              if pctx.profile["tier_depth"][pos]["bench"] >= 3]
    sev = min(1.0, (extra * cfg["waiver_slot_cost"])
                    / cfg["breaker_crunch_scale"]
                   + 0.15 * min(len(pileup), 2))
```

Default scales: one extra body ⇒ 425/850 = 0.50; two ⇒ 1.0 (capped). Sleeper picks occupy no
roster slot, so only player assets count toward `extra` — and the v1 envelope is Sleeper-only
(§3.7), which moots per-platform pick-slot semantics; the PRD says so explicitly (§9 Q-13).

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
   (`trade_service.py:2069-2077`; the function takes no size parameter).
3. `scoring_format` ∈ {`"1qb_ppr"`} ∪ {any `sf*`} (the two `_starters_at` regimes; superflex
   is IN envelope via `_POS_TIER_CUTS_SF_QB`, `trade_service.py:2078`; TEP is in envelope —
   TE premium changes values, not slot structure). Standard 1-K/1-DEF lineups are IN envelope
   with those positions excluded from depth math; true IDP leagues are OUT.
4. No asset on the partner's roster prices 0.0 while holding a non-QB/RB/WR/TE/PICK position
   (the G-026 IDP/K corruption test — one pass over the roster).

`fit_outlook`, `value_giving`, `other_player_keep` score everywhere (age/value/list math is
format-independent) — except the G-026 zero-value hazard: a zero-priced PLAYER asset in the
package inflates the partner's apparent give-side margin, so in a non-envelope league
`value_giving` also stamps `format_gap` when the package carries one (§3.10 table). A 14-team
or IDP league gets fewer named hesitations, not wrong ones;
share-of-decks-with-≥1-gapped-class rides `BreakerReport` (the case for/against widening in
v2).

### 3.8 `compose_narration` — eligibility chain + repetition suppression

Deck-level, deterministic, in served order. For each card with a scored vector
(rungs 0–2; marker-only cards are skipped — nothing to narrate):

1. `top` must be non-null; let `obj = top`, `code = obj["code"]`.
2. **Class switch:** `cfg[f"breaker_narrate_{code}"] >= 1.0` — else
   `suppressed = "class_ineligible"`.
3. **Whitelist:** `code ∈ NARRATABLE_CLASSES` (blocks `other_player_keep` regardless of
   switch); `value_giving` additionally requires `evidence["basis"] == "consensus"` —
   board-basis is ineligible OUTRIGHT (D-7; the switch governs the consensus basis only).
4. **Envelope:** `code ∉ breaker["format_gap"]` — else `suppressed = "format_gap"`.
5. **Floors:** `severity ≥ max(class floor per §4, cfg["breaker_min_severity"])` — else
   `suppressed = "below_floor"`. (`value_giving` consensus basis reads
   `breaker_floor_value_giving_consensus`.)
6. **Outlook narration margin (D-8, `fit_outlook` only):** when `outlook_src == "legacy"`,
   require `|outlook_pair["score"] − cut| ≥ cfg["breaker_outlook_narrate_margin"]` where
   `cut` is the crossed threshold (`infer_contender_cut` / `infer_rebuilder_cut`,
   `trade_service.py:3313-3318`) — the narration bar sits above the stamp bar. When a
   declared outlook exists it may only RAISE confidence on agreement: declared ≠ inferred ⇒
   not narrated for this card (`suppressed = "class_ineligible"`); the stamp records both
   (item 14 default).
7. Survivors are grouped by `(card.target_user_id, code)`. Within a group larger than
   `ceil(cfg["breaker_max_repeat_frac"] × cards_for_that_partner)`, only the max-severity
   card (tie: first in served order) narrates; the rest set
   `suppressed = "repetition"` (D-7).
8. For each remaining card: `sentence = trade_narrative.hesitation_line(obj, players)`;
   `narrated = sentence` (None ⇒ stays null — a template refusal is honest silence);
   `tmpl_ver = trade_narrative.HESITATION_TMPL_VERSION`. Any per-card internal exception ⇒
   `narrated: null, suppressed: "template_error"`, counted, never raised (§5.5 E-15).

Shadow payloads are never visited. The function mutates only
`narrated`/`suppressed`/`tmpl_ver`. Returns the narrated count (the M-1 republish condition).

### 3.9 Two-pass budget evaluation (NFR-2, HLD §2.6, M-9)

Clock: `time.monotonic()` (never `time.time()` — wall-clock steps under NTP would make rung
transitions nondeterministic relative to load; monotonic is what the job timeout uses).
Boundary comparisons are strict `>` (never `>=`): exactly-at-budget runs on — pinned so the
boundary is testable, not because it matters.

```
t0 = time.monotonic(); budget = cfg["breaker_ms_budget"] / 1000.0
if budget <= 0: every card gets the minimal marker {ver, degraded:
    "budget_exhausted", objections: null}; return          # documented disable
PASS 1 — for each card in served order: build/fetch PartnerContext (rung 1 on
    failure); evaluate PASS_1_CLASSES, then the shadow pass-1 for the same
    card when the shadow knob is on (interleaved — §2.5); per-class exception
    ⇒ that class alone stamps skipped: "predicate_error" + predicate_errors
    counter (§5.5 E-14); per-card context exception ⇒ rung-4 marker for that
    card. If elapsed() > budget mid-pass: every REMAINING card gets the
    minimal marker (rung 3 — rank-correlated by construction, therefore
    labeled; readouts exclude the deck).
CHECKPOINT — if elapsed() > cfg["breaker_budget_checkpoint_frac"] * budget:
    pass 2 is DROPPED WHOLE: every card appends the two skip entries and
    stamps skipped = {"classes": ["fit_new_weakness", "roster_crunch"],
    "reason": "budget"} (rung 2 — deck-uniform, unbiased-by-rank).
PASS 2 — else evaluate PASS_2_CLASSES for every card (+ interleaved shadow),
    BUFFERING results; pass 2 is ATOMIC (M-9): if elapsed() > budget
    mid-pass, the buffered pass-2 results are DISCARDED for the whole deck
    and every card stamps the rung-2-shaped skip marker with reason
    "budget_exhausted" + degraded: "budget_exhausted" — pass-1 scores are
    KEPT (labeled, deck-uniform missingness; the HLD's anti-rank-bias
    principle outranks its rung-3 table cell).
FINALIZE — top selection (argmax over per-class floors, post-haircut; ties by
    TIEBREAK_PRIORITY, M-6), them passthrough, provenance markers
    (outlook_src/board_auth/value_mode/identity_src/format_gap), ms.
```

Cost envelope (**60-card basis — erratum E-B**): ≤11 PartnerContexts ×
(`analyze_roster_strengths` + `infer_team_outlook`) ≈ ≤1 ms each, plus the two bulk reads
(§2.2, once per job); per-card work is dict arithmetic + `package_value_v2` — expected
20–200 ms/deck at 60 cards with the shadow on (≤2× per-card cost, same budget envelope)
against the 250 ms default budget and the 60 s job timeout. The pre-flag-on dry run (fit W0
precedent) hands the operator the measured number **on 60-card decks** before `trade.breaker`
lights.

### 3.10 Per-class degenerate-input contract (M-7 — B's table, normative)

Every class returns one of: scored `{severity, evidence}`, or `skipped: "not_applicable"` /
`"format_gap"` — never raises, never silently omits (M4: absence impossible). Parametrized
test per cell (§7.1).

| Class | All-picks give side (partner sends picks) | All-picks receive side (partner gets picks) | Partner roster empty | K/DEF/IDP asset in package (G-026: prices 0.0) |
|---|---|---|---|---|
| `fit_outlook` | scored — lean evaluates the incoming side only; what the partner sends never enters the mean | scored — picks stay **IN** the mean at `ts._now_lean`'s PICK constant −0.25 (`trade_service.py:2648-2656`, byte-parallel to `_give_side_now_lean` — §3.3; the parity test covers pick-carrying cards); all-pick incoming ⇒ lean = −0.25 with `asset`/`age`/`pos` null: the contender/championship branch CAN fire (its template renders no evidence fields, §1.6), the rebuilder/jets branch cannot fire on a negative lean (push zeroes) so the null asset never renders; `not_applicable` ONLY when no incoming asset resolves at all | scored (outlook still inferable — pick share + empty-roster vet/youth shares; evidence shows the inputs) | zero-priced assets carry ages and stay in the unweighted mean (M-8 scalar is value-blind); scored even when every incoming asset is zero-priced — `not_applicable` stays reserved for the no-incoming-asset-resolves case |
| `fit_new_weakness` | `not_applicable` (a pick leaving opens no lineup hole) | n/a — evaluates what the partner SENDS (their give side) | `not_applicable` (no lineup to break) | K/DEF/IDP positions are outside `_POS_TIER_CUTS` ⇒ invisible to slot math; if the vacated slot IS such a position ⇒ `format_gap` |
| `fit_duplicate` | n/a (evaluates what the partner RECEIVES) | `not_applicable` (picks stack no position) | `not_applicable` (nothing to duplicate against) | incoming K/IDP ⇒ excluded; mixed package uses priced players only; all-excluded ⇒ `not_applicable` |
| `value_giving` | scored — picks price via pick values on both bases | scored | scored (board/consensus math is roster-free) | **hazard**: zero-priced assets make the partner's give side look free ⇒ margin inflates. Rule: any zero-`cval` PLAYER asset on either side in a non-envelope league ⇒ `format_gap` (§3.7 item 4); in-envelope leagues cannot hit it (no such rosters pass item 4) |
| `other_player_keep` | prefs are id-matching; pick ids not in prefs ⇒ no hit ⇒ 0.0 (verify pick-id storage at build, Q-12) | n/a (evaluates the partner's GIVE side only) | still scored (prefs exist independent of roster; a pref for an unrostered player ⇒ no match ⇒ 0.0) | scored normally (prefs are id-matching, value-free) |
| `roster_crunch` | picks incoming occupy no Sleeper roster slot ⇒ only player assets count toward `extra` | same | `not_applicable` | slot math counts the asset (a K occupies a spot); pile-up positions limited to `_POS_TIER_CUTS` keys; a K/DEF-carrying roster inside the envelope contributes no pile-up rows |

Also normative: **empty give or receive side** (defensive) ⇒ classes score 0.0 or
`not_applicable` per their column, no exception. **Pick shape at this seam:** card-side picks
are the owned-pick pseudo-player shape (`position == "PICK"`, injected by
`server._owned_pick_assets`) — the shape that hits `ts._now_lean`'s PICK branch
(`trade_service.py:2652`); universal-pool generic picks (real position, `team == "PICK"`)
never reach the trade-job seam. **Self-trade guard**: a card whose
`target_user_id == viewer_user_id` (data corruption upstream — the phantom-13th-team bug
class, `server.py:16970-16975` comment) stamps `degraded: "self_partner"` and is skipped; not
constructible today, guarded anyway (§5.5 E-7).

---

## 4. Knob table — 25 keys (final count; M-5: A's table stands)

Count derivation: 6 narration switches + 7 floors (6 classes + the separate consensus-basis
`value_giving` floor D-7 demands) + 12 singletons = **25**. Every key follows the
five-registration rule **in the consumer's commit** (discipline comment
`trade_service.py:888-899`): `trade_service._DEFAULT_CFG` (tail) ·
`database._MODEL_CONFIG_DEFAULTS` (`database.py:2188`; without the row `set_config` KeyErrors,
`:4191`, and the rollback ladder is theater) · `_PINNED_KNOBS`
(`test_bakeoff_arm_a_golden.py:471`; inventory guard `:546-547` fails BY NAME) · the
disposition sentence in `docs/plans/three-model-bakeoff/scope-phase2.md` · the
`docs/config-reference.md` row. All 25 are read exclusively through the §3.0 per-job snapshot,
whose key set is these 25 ∪ `_SHARED_ENGINE_KNOB_KEYS` (`waiver_slot_cost` — an existing
engine registration, needing NO five-registration here and not counted in the 25; §1.1).

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
| `breaker_narrate_roster_crunch` | 0.0 | 0 | 〃 (new-logic class: last to graduate, HLD §2.7) |

`_MODEL_CONFIG_DEFAULTS` descriptions ≤90 chars each, e.g.
`("breaker_ms_budget", 250.0, "breaker: per-deck eval budget ms; 0 disables (minimal markers)")`.
Severity-curve constants baked into predicates (the 0.05/0.35 lean window, the slack table,
the 0.40/0.40/0.20 duplicate weights, the 0.9/1.0 keep severities, `TIEBREAK_PRIORITY`) are
deliberately NOT knobs — **`BREAKER_VERSION`-pinned semantics (ruled, M-6)**; re-leveling
across classes is what the floor knobs are for (D-4). The board-authenticity thresholds ARE
knobs (above) but their *semantics* are version-pinned: calibration must not chase a moving
authenticity definition, so a threshold change worth making is a `ver`-bump conversation
first. That warning sentence is carried **verbatim** into the `docs/config-reference.md` rows
for `breaker_board_div_min` and `breaker_board_min_divergent`.

---

## 5. Error Handling & Edge Cases

### 5.1 Degradation ladder (HLD §2.6, made exact)

Bare null is never stamped; an absent key means flag-off, nothing else. Marker shapes in §2.1.

| Rung | Trigger | Stamp on affected cards | Scope |
|---|---|---|---|
| 0 | normal | full §2.1 payload | all |
| 0 (field-level) | one class's predicate raises (E-14, erratum E-D) or a bulk read fails (§2.2) | scored vector; a raising predicate stamps its class alone `severity: null, skipped: "predicate_error"` (durable — §8 counts it), `predicate_errors` counted; a failed bulk read stamps the dependent class(es) `skipped: "not_applicable"` (prefs absence is a legitimate state, not an error) | that class, that card (or all cards for a bulk-read failure) |
| 1 | PartnerContext build fails (G-045 pruned partner, unknown `target_user_id`, profile exception) | scored vector for computable classes; classes needing the failed input stamp `severity: null, skipped: "partner_snapshot"`; whole-context failure ⇒ minimal marker `degraded: "partner_snapshot"` | that partner's cards |
| 2 | checkpoint trips after pass 1 | pass-1 vector + `skipped: {"classes": ["fit_new_weakness","roster_crunch"], "reason": "budget"}` | every card (deck-uniform) |
| 3 | budget exhausted mid-pass-1 | minimal marker `degraded: "budget_exhausted"` | remaining cards (rank-correlated ⇒ labeled; readouts exclude the deck). Mid-pass-2 exhaustion: §3.9 atomic-discard (M-9) — pass-1 kept, deck-uniform skip marker + `degraded: "budget_exhausted"` |
| 4 | per-card exception outside any class predicate (context assembly, finalize) | minimal marker `degraded: "exception_card"` (or `"self_partner"` for the §3.10 guard); logged + counted | that card |
| 5 | outer exception (incl. import failure) | seam handler stamps minimal markers on EVERY card — BOTH `breaker` and `breaker_shadow`, `degraded: "exception_outer"`, no knob read (§1.2) + warning log | all |
| log-time | flag on at log time, attribute absent (M-2) | §1.4 synthetic marker `{ver: null, degraded: "flag_flip_or_unstamped", objections: null}` — written by the impressions block, not the module | that row |

The per-class containment refinement (E-14, from B): one flaky predicate must not zero the
coverage metric for all six classes — whole-card rung 4 is reserved for failures outside any
class. This narrows the HLD §2.6 rung-4 row's population; it is a **declared HLD erratum —
E-D in the §0.2 registry** (the LLD's binding rule permits contradicting the HLD only via
that registry).

### 5.2 Input-wrongness table (degrade-and-mark is normative — HLD §3.5)

| Input defect | Behavior | Marker |
|---|---|---|
| Partner absent from `league.members` | rung 1 | `degraded: "partner_snapshot"` |
| Board bulk-seeded / clone (F-3) | consensus basis for `value_giving` | `board_auth: "board_suspect"` |
| Unboarded partner (the 84.5% normal case — rung 0, not a defect) | consensus basis | `board_auth: "consensus"` |
| Co-owned roster, prefs under co-owner account id | not read (ruling §2.3) | `identity_src: "owner_id"` |
| 14-team / non-Sleeper / IDP roster | depth classes skip + narration-ineligible | `format_gap: [...]`, per-class `skipped: "format_gap"` |
| Zero-priced player asset in package, non-envelope league (G-026) | `value_giving` also gaps (§3.10) | `format_gap` incl. `value_giving` |
| `not_sure` window | `fit_outlook` scores 0.0 | evidence carries `outlook: "not_sure"` |
| Likes-you-injected card (no `fit_diag`) | `them: null`; everything else scores normally | — |
| Board staleness | NOT handled in v1 (Q-2/A-6 open) | — |
| Empty give or receive side / all-picks sides / empty roster | §3.10 table; no exception | per-class `not_applicable` |
| `target_user_id == viewer` | skipped (§3.10 guard) | `degraded: "self_partner"` |

### 5.3 Job-level containment

The seam block is the only caller; `stamp_breaker` itself raises nothing (rung 4/5 markers
built internally), and the seam try/except is the belt-and-braces envelope for the import line
and marker-path bugs. The breaker never raises across the seam. The §1.4 impression copy can
no longer crash on a missing attribute (M-2 synthetic marker) — the failure mode the HLD's
bare read would have had (one AttributeError ⇒ whole deck's impressions lost to `:6129`) is
designed out; a seam bug that leaves flag-on cards unstamped now surfaces as
`flag_flip_or_unstamped` rows cratering the coverage metric and tripping the NFR-6 tripwire —
known, not discovered.

### 5.4 Determinism (NFR-4)

No RNG, no LLM, no wall-clock in any verdict (`ms` and the budget affect *which rung* stamps
— labeled — never a score; the clock is `time.monotonic()`, §3.9). Iteration orders: cards in
served order; classes in `ALL_CLASSES` order; positions in `pctx.counts` insertion order
(`_STARTER_NEED` fixed); argmax ties by `TIEBREAK_PRIORITY` (M-6), then pid ascending, then
served order. Knobs frozen per job (§3.0). Rounding fixed (§2.1).
`test_breaker_deterministic` runs the same fixture twice and asserts deep equality of every
payload.

### 5.5 Concurrency & mid-job-change contract (first-class, from draft B)

Every row is a contract; §7 maps each to a test.

| # | Case | Contract |
|---|---|---|
| E-1 | Deck of 0 cards (F3 can empty one; `_log_deck_signal_impressions` early-returns `:4060-4061`) | `stamp_breaker`/`compose_narration` no-op; report `cards_seen=0`; no republish; no crash |
| E-8 | Hot flag reload mid-job (`POST /api/feature-flags/reload` between seam and impression block) | Stamp site reads both breaker flags ONCE, into locals at the top of the seam block (§1.2). Impression copy is attribute-gated with the M-2 synthetic marker (§1.4). Flip on→off mid-job: stamps land in `features_json` (correct — they existed at serve); serializer re-reads nothing (narration already composed). Flip off→on: no stamp ⇒ synthetic marker rows, no crash. **Honesty note:** flag AND knob reads at call time INSIDE engine helpers are NOT covered by the §3.0 knob snapshot — the snapshot governs only the breaker's own `cfg` reads. Examples: `trade_crown_asset` flag in `_package_value_market` (`trade_service.py:1357/:1409`); `_package_value_market` reads `_c("package_adj_gamma_market")`/`_c("package_discount_cap")` live (`:1402/:1406`); `elo_to_value` reads the `elo_value_*` keys live (`:1280-1281`). §3.0's "one job, one knob-state" is therefore exact-with-stated-residual — an accepted intra-deck determinism hole shared with the whole engine, not breaker-specific; mitigated by the M1 rail (knob changes are logged in `model_config_changes` and censor readout windows) |
| E-9 | Hot KNOB change mid-job (`PUT /api/admin/config`) | §3.0 snapshot: one job, one knob-state (the breaker's own `cfg` reads only — flag AND knob reads inside engine helpers are the E-8 residual); `model_config_changes` censors the readout window (M1) |
| E-10 | `_cfg_override` overlay / bake-off arm profile | Verified inactive at the post-F9 seam (contextmanager exits with the arm's `with` block, `trade_service.py:995`); §3.0 snapshot makes it moot; binding-sabotage test pins module-import discipline across calls |
| E-11 | Stud-tax thread-local unpinned at seam | Explicit `ts.stud_tax_override("market")` around all breaker valuations, `value_mode` stamped (§3.0, M-5) |
| E-12 | Two concurrent jobs, same league, different viewers | No shared mutable state: `PartnerContext` cache is per-call (local dict); knob reads are snapshot-per-call; report is per-call. Nothing to lock |
| E-13 | Superseded jobs (`force_supersedes_running`) | The seam block SKIPS them (`not _job_superseded(job_id)` — T-1 ruling, §1.2 point 4 / §9 Q-10): pure wasted-compute avoidance, no correctness dependency either way. Belt regardless: superseded jobs skip the signal block (`:6092-6093`) so no rows are written, and every publish is `_job_live`-blocked so no render occurs. A supersede landing DURING the block is the mid-run case — §1.3's superseded row |
| E-14 | Exception inside ONE class's predicate | Per-CLASS try/except in the per-card loop: that class stamps `skipped: "predicate_error"` (durable in `features_json` — the §8 degraded-share readout counts it), `predicate_errors` counted in the ephemeral report; the CARD stays rung 0 with the other classes scored (§5.1, erratum E-D) |
| E-15 | Exception inside `compose_narration` after stamps landed | Caught per card: `narrated: null, suppressed: "template_error"`; stamps untouched; counted. `hesitation_line` itself returns None on any internal error (§1.6) |
| E-16 | Exception in the outer server block (incl. the import line) | Inline rung-5 marker with no breaker-module dependency (§1.2 point 3) |
| E-17 | Budget exactly at a boundary | Strict `>` comparisons (§3.9): exactly-at-checkpoint runs pass 2; exactly-at-budget finishes the card. Pinned so the boundary is testable |
| E-18 | Snapshot republish under every flag combination | §1.3 matrix; `_n_narrated > 0` ⇒ seam republish (works with `deck.signal_v2` off, streaming either state); signal_v2 on ⇒ `:6115` re-serialization preserves the sentence and adds iids; superseded ⇒ `_job_live` blocks |
| E-19 | `imp_by_card` falsy with narration on (impressions insert failed) | Sentence already published by the seam republish; measurement lost for that deck (existing failure class), exposure NOT lost; A/B readout excludes such decks (no outcome rows to join) |
| E-20 | Likes-you-injected cards | Present at the seam (injected `:5747`, before F9) — stamped like any card; `them` null (no `fit_diag`, D-3); no special path |
| E-21 | Ghost rows (robustness only — M-12 says none exist) | The impression loop iterates ghost entries (`:4120-4122`); the attribute-gated copy stamps them uniformly; every breaker readout filters `is_ghost = 0` regardless |
| E-22 | Multi-format sessions (`sess["trade_svcs"]`, `server.py:5438-5440`) | The job's `active_format` is the ONLY format the breaker sees (`scoring_format` into `analyze_roster_strengths`; `seed_map` is already per-format). The per-format `TradeService` INSTANCE is irrelevant — the breaker uses module-level `ts` helpers + explicit args, never instance state (and the rung-5 handler makes no module reference at all, §1.2 — the local `trade_service` name IS that instance). Format flips between jobs produce per-job-consistent stamps keyed to the format their deck served under |
| E-23 | Auto-sweetened cards (`fix/package-benchmark-sweetener`, PLAN A-1(b)) | Ordinary cards at the seam: present pre-ghost-split, stamped like any card — the breaker evaluates the sweetened package as-is. The sweetener's `features_json` key and the `breaker`/`breaker_shadow` keys coexist without collision (distinct keys in one JSON object). §8 gains an optional readout cut on the sweetened key |

(E-2..E-7 — partner-absent, co-owner, degenerate packages, K/DEF, self-partner — are the §3.10
and §5.2 rows; numbering kept sparse to match draft B's ledger for cross-review diffing.)

---

## 6. Backward Compat & Migration

- **No migrations — verified.** No `Table()` additions, no new columns, no routes, no env
  vars. `features_json` and payload changes are JSON-internal. `breaker_` prefix stays
  reserved-unused (a grep test in §7.4 pins that no `breaker_` table exists). The two §2.2
  bulk readers are read-only helpers over existing tables.
- **Flag-off byte identity (NFR-3), proof obligations:** module never imported
  (`sys.modules` check); no card attribute; no `features_json` key; no payload key; no
  publish-count change (the seam republish is inside the flag guard). Rows and payloads
  byte-identical to today (`test_flag_off_features_json_byte_identical`,
  `test_flag_off_payload_byte_identical`).
- **Dark window compat:** `trade.breaker` on alone changes exactly two things —
  `features_json` gains the two keys, and job wall time gains the measured stamp cost.
  Payloads AND the publish stream stay byte-identical (§1.3 rows 2 and 5; `_n_narrated == 0`
  ⇒ zero added publishes).
- **Client compat:** the payload key is additive; web/extension ignore it; mobile renders
  only when present. Old mobile builds ignore unknown keys (fit precedent); no
  minimum-version gate.
- **Draft-path compat:** the stamp is draft-agnostic (`compose_deck` and `team_draft`,
  `group_size ∈ {0, N}` — fit F-6 trap) — parametrized in §7.4.
- **Rollback ladder (HLD §5.3):** narrative flag off (hot) → `breaker_min_severity 1.1` or
  per-class switch to 0 (`set_knob`, logged) → `trade.breaker` off (compute gone, key gone)
  → revert commit. Nothing persisted needs cleanup: old `features_json.breaker` blobs are
  version-stamped inert serve-time facts — never re-stamped, never backfilled.
- **Version discipline:** any predicate/threshold/evidence-shape/tie-break/envelope change
  bumps `BREAKER_VERSION`; any template change bumps `HESITATION_TMPL_VERSION`; readouts
  filter `ver` (calibration) and (`ver`, `tmpl_ver`) (narration A/B) and refuse cross-version
  pooling (fit M2 precedent). A bump mid-dark-window starts a new calibration cohort; the §8
  spec states the cohort's `ver` before `trade.breaker` lights.

---

## 7. Testing

### 7.0 Fixture realism — the #366 lesson, made a precondition (M-10)

`_POS_TIER_MIN_POOL = 40` (`trade_service.py:2086`): below 40 ranked players at a position,
`analyze_roster_strengths` silently falls back to absolute cuts (`tier_basis` reports it,
`:2266`). Engine fixtures are smaller than that — **a green depth-class test on a small
fixture proves the fallback mode, not production behavior.** Therefore the shared fixture
module is **`backend/tests/fixtures/breaker_league.py`** (reusing the fit W0 replay board
where it fits): a 12-team league (11 members + viewer) with **≥40 priced players per
`_POS_TIER_CUTS` position** (QB/RB/WR/TE); partners `_OPP_REBUILDER` (young roster, boarded
with ≥10 divergent rows), `_OPP_CONTENDER` (vet-heavy, clone board — 3 divergent rows),
`_OPP_UNBOARDED`, `_OPP_THIN_TE` (exactly `_starters_at` TEs); one superflex variant; one
14-team variant (envelope-out); one co-owned roster; one K/DEF-carrying roster; a mirrored
card pair; a served deck of ~8 cards across 3 partners. **Every depth/tier predicate test
asserts `tier_basis == "positional"` in its preconditions** — a fixture shrink that flips the
mode fails loudly instead of testing the wrong bands. Fixture idiom otherwise per
`test_bakeoff_challenger.py` (local `_Player`, literal Elo maps, inline
`LeagueMember`/`League`).

### 7.1 `backend/tests/test_trade_breaker.py` (new) — names ARE the spec (M-11: union, deduped)

| Test | Asserts |
|---|---|
| `test_breaker_deterministic` | two identical runs ⇒ deep-equal payloads, every card, incl. rounding rules (NFR-4) |
| `test_breaker_vocabulary_closure` | every emitted `code` ∈ the 9 coded `PASS_REASON_LAYER2` codes ∪ {`roster_crunch`}; **`other_text` never emitted**; `shape_aversion` never emitted in any field (producer-column enforcement, D-2); codes cross-checked against `database.PASS_REASON_LAYER2` by import, not by copy; **every evidence key ⊆ the §2.4 enums per code** (an unlisted key is how a private-state leak sneaks past the whitelist) |
| `test_fit_outlook_predicate` | rebuilder receiving a 29-y/o RB fires with the §3.3 severity; contender receiving picks fires (all-pick incoming ⇒ lean = −0.25 via the `_now_lean` PICK constant — satisfiable per the §3.10 F1 cell; evidence `asset`/`age`/`pos` null, template renders no evidence fields); `not_sure` ⇒ 0.0; legacy haircut applied (knob override moves it) |
| `test_fit_new_weakness_predicate` | `_OPP_THIN_TE` sending its only startable TE ⇒ 1.0 with `{pos:"TE", before, after, need}`; slack-1 fixture ⇒ 0.30; receive-side can't fire; precondition `tier_basis == "positional"` |
| `test_fit_duplicate_predicate` | surplus-position incoming fires with `value_share`/`bench_n` per §3.4; non-surplus ⇒ 0.0; precondition `tier_basis == "positional"` |
| `test_value_giving_one_code_path` | boarded-authentic partner ⇒ `basis:"board"` margin from `oval`; unboarded AND clone-board ⇒ `basis:"consensus"` from `cval`; the severity function is the same object on both paths (one helper, asserted by call) |
| `test_other_player_keep_predicate` | untouchable in their give side ⇒ 0.9/1.0; targets/not_interested lists never fire it |
| `test_roster_crunch_predicate` | 1-for-2 from their seat ⇒ extra=1, sev 0.50 at defaults; pile-up bonus caps at +0.30; extra ≤ 0 ⇒ 0.0; picks occupy no slot |
| `test_degenerate_inputs_per_class` | one parametrized case per §3.10 cell: all-picks × each class, empty roster, empty sides, K/DEF assets — every cell returns its contracted scored/`not_applicable`/`format_gap` result, never raises |
| `test_board_auth_heuristic` | divergent-row counts on both sides of `breaker_board_min_divergent` ⇒ `board`/`board_suspect`; no board ⇒ `consensus` |
| `test_lean_quantity_parity` | breaker lean == `trade_narrative._give_side_now_lean` for shared fixtures **including pick-carrying and all-pick packages** (picks in the mean at −0.25 — F1; coherence precondition — M-8 flagged). Fixture pin: pick fixtures use `position == "PICK"` — the owned-pick pseudo-player shape, the only pick shape at the trade-job seam (§3.10) |
| `test_opponent_frame_breaker_coherence` (characterization) | over a fixture grid (outlook × lean ∈ {−0.2, −0.05, 0, +0.05, +0.2}): never both `_opponent_frame` non-None and breaker `fit_outlook` fired for the same (card, outlook value); pins today's `:96-99` thresholds; asserts both writers consumed the same outlook value or fails (HLD §2.4 precondition) |
| `test_mirrored_card_cross_seat_coherence` (HLD §2.7) | mirrored fixture: high breaker `fit_new_weakness` from seat B ⟺ B's own viewer-seat `need_gate_ok`/feasibility view flags the mirror |
| `test_breaker_binding_sabotage` (sabotage) | monkeypatch a `ts` knob (e.g. `waiver_slot_cost`) ⇒ the NEXT `stamp_breaker` call's verdict moves (T1 discipline + §3.0 per-call snapshot boundary); module-attribute monkeypatch of `ts.package_value_v2` to a sentinel ⇒ verdicts move — value-binding would no-op and fail |
| `test_knob_snapshot_frozen_within_job` | mutate `ts._cfg` between pass 1 and pass 2 (monkeypatch hook) ⇒ stamps unchanged within the job (§3.0) |
| `test_them_is_passthrough` | sentinel `fit_diag.them` rides through untouched; absent `fit_diag` ⇒ `them` null (likes-you fixture) |
| `test_partner_snapshot_rung1` | unknown `target_user_id` ⇒ rung-1 marker, other partners' cards unaffected |
| `test_bulk_reader_failure_field_level` | sabotaged bulk prefs read ⇒ `other_player_keep` stamps `not_applicable` on every card, rung stays 0 (§2.2 — not rung 1) |
| `test_per_class_exception_contained` (sabotage) | one predicate raising ⇒ that class stamps `skipped: "predicate_error"` (durable, in `features_json`), other 5 scored, card rung 0, `predicate_errors` counted (E-14, erratum E-D) |
| `test_budget_ladder_labeling` (sabotage) | tiny `breaker_ms_budget` + a slowed predicate: checkpoint trip ⇒ deck-uniform rung-2 skips; mid-pass-1 exhaust ⇒ rung-3 markers on remaining cards only; **mid-pass-2 exhaust ⇒ buffered pass-2 DISCARDED, deck-uniform skip + `budget_exhausted`, pass-1 kept (M-9)**; `breaker_ms_budget=0` ⇒ minimal markers everywhere; E-17 strict-`>` boundary |
| `test_exception_rungs` (sabotage) | context-assembly raise ⇒ rung-4 marker for that card, rung 0 elsewhere; `stamp_breaker` monkeypatched to raise at the seam ⇒ rung-5 marker on EVERY card (server-level fixture) |
| `test_rung5_marker_version_pinned` | the seam literal == `trade_breaker.BREAKER_VERSION` |
| `test_self_partner_marker` | `target_user_id == viewer` fixture ⇒ `degraded: "self_partner"`, skipped (E-7) |
| `test_empty_deck_noop` | empty `cards` ⇒ no-op, zeroed report, no republish (E-1) |
| `test_co_owner_prefs_not_read` | co-owner fixture: prefs stored under a different account id are not consulted; `identity_src == "owner_id"` (§2.3 pin) |
| `test_format_envelope` | 14-team league / IDP roster / non-sleeper platform ⇒ depth classes `skipped: "format_gap"` + narration-ineligible; superflex scored via SF cuts; `fit_outlook`/`value_giving` still score (G-026 gap row excepted) |
| `test_objections_vector_complete` | every scored payload lists all 6 classes exactly once, pass order, incl. below-floor, `not_applicable`, and gapped entries (M4) |
| `test_top_tiebreak_priority` | two classes at equal rounded severity above floor ⇒ `top` follows `TIEBREAK_PRIORITY` (M-6) |
| `test_stamp_size_budget` | worst-case fixture stamp serializes < 4096 B per card (§2.7) |
| `test_stud_tax_pinned_market` | an ambient `stud_tax_override("balanced")` around the call does NOT move breaker valuations; `value_mode == "market"` stamped (§3.0, M-5) |
| `test_shadow_run` | knob on ⇒ `breaker_shadow` §2.5 shape on every card, viewer-seat verdicts (unswapped fixture check); knob off ⇒ attribute absent/None; shadow `narrated` always null; budget exhaustion degrades primary and shadow together (interleave pin) |
| `test_outlook_declared_vs_inferred` | declared present ⇒ `outlook_src "declared"`, pair records both; declared absent ⇒ `legacy`; resolution shape asserted against `trade_service.py:4948-4956` semantics (declared wins); bulk-reader path exercised when `declared_outlooks` is empty |
| `test_default_knob_ordering` | the shipped §4 defaults respect the D-8 "narration bar above stamp bar" ordering: for every class (both `value_giving` bases), the effective narration threshold `max(class floor, breaker_min_severity)` per §3.8 step 5 exceeds that class's top-selection floor whenever `breaker_min_severity` sits above it — concretely, `breaker_min_severity` (0.60) is pinned ≥ every default floor except the deliberately-higher `breaker_floor_value_giving_consensus` (0.75), which is pinned ≥ `breaker_min_severity` — the testable half of §7.6 item 4 |

### 7.2 Narration + composition

| Test | Asserts |
|---|---|
| `test_narration_switch_ladder` | all switches 0 ⇒ zero narrated on a hot deck (flag-on renders NOTHING by design); flipping one class narrates only that class; return value == count narrated |
| `test_narration_whitelist_dark_classes` | `other_player_keep` top + its switch forced 1 ⇒ still never narrated; board-basis `value_giving` never narrated with its switch on (consensus basis narrates) |
| `test_narration_floors_and_min_severity` | below class floor / below `breaker_min_severity` ⇒ `suppressed: "below_floor"` |
| `test_narration_outlook_margin` | legacy-source `fit_outlook` inside the margin ⇒ not narrated, stamp untouched; declared≠inferred ⇒ not narrated, pair stamped |
| `test_repetition_suppression` | 5 same-(partner, code) candidates on one deck at frac 0.34 ⇒ only max-severity card narrates, rest `suppressed: "repetition"` |
| `test_narration_template_error_contained` | `hesitation_line` monkeypatched to raise ⇒ `suppressed: "template_error"`, stamps untouched, no exception (E-15) |
| `test_hesitation_templates_snapshot` | every §1.6 template string pinned; `HESITATION_TMPL_VERSION` pinned |
| `test_hesitation_line_honesty` | missing evidence key ⇒ None; **present-but-null evidence value in a rendered key ⇒ None** (never "None-year-old" — §1.6); unknown code ⇒ None; rendered names resolve from evidence ids only (D-053); no template contains "FTF" or an unhedged mental-state verb |
| `test_tmpl_ver_stamped` | narrated card carries `tmpl_ver == "brt-1"`; un-narrated carries null |

### 7.3 Impressions (server-level; M-2 rows)

| Test | Asserts |
|---|---|
| `test_impressions_breaker_uniform_keys` (extends `test_impressions_uniform_columns`) | flag-on deck, mixed rungs: every row's `features_json` decodes with `breaker` non-null (scored, marker, or synthetic) and `breaker_shadow` present; organic AND bake-off rows both carry them (outside-the-guard placement pinned) |
| `test_midjob_flag_flip_no_crash` | flip the flag between stamp and log (monkeypatch FLAGS): off→on ⇒ impressions still written, every row carries the synthetic `flag_flip_or_unstamped` marker, fit keys intact; on→off ⇒ stamped payloads ride through (attribute-gated); **never a bare null, never a lost deck** — the row that would have failed the HLD §3.3 sketch (erratum E-A) |
| `test_flag_off_features_json_byte_identical` | flag off at both sites ⇒ impressions rows byte-identical (no key) |

### 7.4 Seam, serving, and serialization (server-level)

| Test | Asserts |
|---|---|
| `test_breaker_zero_ordering_effect` (sabotage; **parametrized `bakeoff_group_size ∈ {0, N}` + organic**) | served deck (trade ids in order) byte-identical with `trade.breaker` on vs off, both draft paths and organic; the fit `test_fit_diag_inert` delete-attribute variant: stripping `breaker` from every card changes nothing served |
| `test_breaker_inert_seam_creep_guard` (D-11) | grep-guard: no module outside `server.py` (seam + features + serialization) and `trade_breaker.py` reads `card.breaker`/`breaker_shadow`; `inspect.getsource(trade_service)` and each generator contain no `trade_breaker` reference |
| `test_flag_off_never_imports_breaker` | flag off + full job ⇒ `"backend.trade_breaker" not in sys.modules` |
| `test_flag_off_payload_byte_identical` | flag off ⇒ `trade_card_to_dict` output byte-identical |
| `test_breaker_payload_absent_during_dark_window` | stamped card, narrative flag off ⇒ `trade_card_to_dict` output has NO `breaker` key |
| `test_breaker_shadow_never_serialized` | shadow-stamped card, all flags on ⇒ no `breaker_shadow` key in any payload; serialized `breaker` object has exactly `{code, severity, sentence}`; `narrated ⇒ top non-null` invariant exercised |
| `test_narrated_payload_reaches_snapshot_all_flag_combos` (subsumes drafts' republish-matrix tests; M-1) | **parametrized over `deck.signal_v2 ∈ {on, off}` × streaming state × narrated ∈ {0, ≥1} × job live/superseded**: the stored `j["cards"]` snapshot carries `breaker.sentence` for narrated cards iff narrated ∧ live (§1.3 matrix, incl. the signal-v2-off row where the seam republish is the only carrier); dark/zero-narrated decks add ZERO publishes and their snapshots are byte-identical to flag-off |
| `test_likes_you_card_stamped` | injected card carries a scored stamp with `them` null |
| `test_no_breaker_tables` | no table in `database.metadata` matches `breaker_%` (prefix reserved-unused) |

### 7.5 Structural guard — `mobile/tests/check-breaker-card.js`

House idiom (regex + brace matcher, no simulator — see `check-analytics-297-302.js` header).
Assertions:

1. `TradeCard.tsx` contains testIDs `trade-card.breaker-hesitation` and
   `trade-card.breaker-hesitation.body`.
2. The element render is conditional on `data.breaker?.sentence` (regex pins the guard
   expression — no unconditional render path; absent key ⇒ no render).
3. The rendered text node interpolates `data.breaker.sentence` and contains no string-literal
   sentence and no switching on `data.breaker.code` (server-composed copy only).
4. The new styles block references token identifiers only (no `#`-hex literals, no
   `borderRadius` > 8).
5. The card-payload TS type declares optional `breaker` with `code`/`severity`/`sentence`.
6. No mobile file references `breaker_shadow` (client never sees the shadow).
7. `testid-lint.sh` passes on the tree (CI already runs it).

### 7.6 Evidence beyond pytest (D-056) + non-mechanically-testable invariants

**Code-walk proof at build:** a file:line-cited walk of both seams (stamp block placement
relative to F9/ghost split/impression call; features block placement outside the bakeoff
guard) — the §0.3 table re-cited at the build sha. **TestFlight checklist** before
`trade.breaker_narrative` lights (launch step 4, HLD §5.1): (1) narrated card shows the
hesitation element with the expected sentence; (2) a suppressed/below-floor card shows
nothing; (3) dark-window build shows nothing anywhere; (4) element styling matches Chalkline
reference screens; (5) pass flow still files decline reasons normally. Logged in TEST_LEDGER.

Four HLD invariants that are not mechanically testable as stated, and their testable forms:

1. **NFR-1 publish-stream byte-identity** — pinned by §7.4's flag-combo matrix
   (publish-count + snapshot-content equality for dark decks).
2. **NFR-6 coverage ≥99%** — a production metric; the testable surrogate is
   `test_impressions_breaker_uniform_keys` (absence impossible per deck) + the readout SQL
   committed as a **`scripts/`-style artifact** (fit `bakeoff_readout.sql` precedent) so the
   graduation query is code-reviewed, not composed ad hoc at readout time — required by §8.
3. **§2.7 "same predicate shape, seat-swapped"** — the testable form is the mirrored-fixture
   biconditional (`test_mirrored_card_cross_seat_coherence`) + binding sabotage (a knob move
   moves both seats together).
4. **D-8 "narration bar above stamp bar"** — knobs are floats with no cross-key validation
   machinery; the shipped *defaults* respect the ordering (test-pinned:
   `test_default_knob_ordering`, §7.1) and the §8 readout asserts it at readout time.
   Residual: an operator can mis-set knobs; the answer is `model_config_changes` attribution,
   not prevention.

---

## 8. Calibration-readout spec skeleton (the preregistered artifact — committed before `trade.breaker` first lights; M-12: TBD cells are the operator's)

This section IS the artifact the HLD D-6 commits to; the TBD cells are filled by the operator
+ build session **before flag-on**, then frozen (changes require a new `ver` window). The
graduation SQL ships as a reviewed `scripts/` artifact (§7.6 item 2).

**Populations.** (a) Counterparty-seat: mirrored card served to the counterparty within the
A-5 window AND a coded pass reason filed — long-horizon accumulator, never a launch gate
(n≈0 today). (b) Viewer-seat shadow (`features_json.breaker_shadow.top` vs the viewer's own
filed layer-2 code) — the PRIMARY population, labeled proxy validation with its selection
caveat. (c) The HLD §2.7 cross-seat consistency check — population-independent third signal.

**Join.** `deck_impressions.features_json` ⨝ `trade_pass_reasons` on `impression_id`;
`ver` filter mandatory (`ver: null` synthetic rows are degraded, never covered, never
joined); filed `other_text` rows are unmatched-by-construction and excluded from every
per-class precision denominator (D-1). Boundaries restated verbatim from PLAN §6/§10 A-1:
**no ghost rows ever** (M-12; ended 2026-08-21 00:43Z; `is_ghost = 0` filter regardless);
D-091 window (2026-08-16→08-19) excluded; QB value-optics not comparable across **either**
1QB repricing seam — `qb_1qb_cap_elo` 1785→1644 @04:46Z **and** 1644→1717 @11:48Z;
`model_config_changes` censors windows (M1). **Plus one NAMED code-ship boundary:** the
`fix/package-benchmark-sweetener` Monday merge (§3.4 note — the package-benchmark re-fix that
moves `value_giving` severities). It is a code deploy, **invisible to
`model_config_changes` — the M1 rail will NOT censor it**; the readout censors at its deploy
timestamp explicitly, and per the §3.4 sequencing sentence the calibration cohort starts
at/after it (pre-merge severities are never pooled with post-merge ones).

**Per-class gate table (all classes; a class graduates only from its own row):**

| Class | min n (cell) | required margin over majority-class baseline (40% `value_giving`, n=208 — re-derive at readout) | required margin over stratified-random baseline | Notes |
|---|---|---|---|---|
| fit_outlook | TBD-operator | TBD-operator | TBD-operator | reported per `outlook_src` stratum separately |
| fit_new_weakness | TBD-operator | TBD-operator | TBD-operator | envelope rows only |
| fit_duplicate | TBD-operator | TBD-operator | TBD-operator | envelope rows only |
| value_giving | TBD-operator | TBD-operator | TBD-operator | reported per basis stratum; consensus stratum flagged near-tautological (R-4) |
| other_player_keep | TBD-operator | TBD-operator | TBD-operator | dark class — calibration only, no graduation target in v1 |
| roster_crunch | TBD-operator | TBD-operator | TBD-operator | extension code: no filed-reason anchor exists; precision measured against `other_text` free-text hand-coding is FORBIDDEN (other_text excluded); its row may remain unpassable in v1 — stated, not hidden |

**Stratification (minimum, pinned):** `outlook_src` × board basis (`board` /
`board_suspect` / `consensus`); every reported precision carries its cell n; cells below
min-n print "insufficient" — never pooled silently. **Coverage criteria restated (NFR-6):**
scored coverage ≥99% of served impressions AND rung-1..3 share < `breaker_degraded_share_max`
— rung-marked and `ver: null` rows are never "covered". **Also reported, never a gate:**
class-entropy of `top.code` (D-7 red line before any narration graduation), per-class fire
rate, degraded share by rung (incl. `flag_flip_or_unstamped`) and per-class
`skipped: "predicate_error"` share (F6 — durable, countable from `features_json`), `ms`
p50/p95, mirrored-serve narration-divergence count (R-6 monitor), and an optional cut on the
auto-sweetener's `features_json.gap_sweetener` key (name confirmed 2026-08-21, sibling tip
`0e04d30`; present on every row, null when absent) (PLAN A-1(b) / §5.5 E-23 — sweetened vs unsweetened
cards reported separately when the operator asks).

---

## 9. Open Questions (for cross-review + operator; none block the scaffold)

Settled by rulings and closed here: draft A's Q-5 (atomic pass-2 — adopted, M-9), Q-6
(7 floors / 25 knobs — adopted, M-5), Q-7 (version-pinned severity constants — adopted, M-6);
draft B's stud-tax question (ruled `'market'` + provenance stamp, M-5) and dead-switch
question (registered-dark per A's table, M-5).

| # | Question | Merged-candidate position |
|---|---|---|
| Q-1 | `num_teams` source at the seam (§3.2) — `len(league.members)+1` vs the job's own value | re-verify at build against `trade_service._num_teams`'s source, **including the `league.members` inclusion convention** — the demo builder (`server.py:362-431`) constructs `members` WITHOUT the viewer (the `+1` assumes that shape); confirm every platform's league sync follows it before trusting the formula. A wrong count only shifts the pick-centering term |
| Q-2 | Board staleness (A-6): is last-ranked-at recoverable? | not handled in v1; `board_auth` does not encode staleness (inherited open item) |
| Q-3 | Co-owner union (§2.3): HLD §3.4's union is unimplementable without persisting `co_owners` at sync | ruled (M-7): v1 = owner-id-only + `identity_src` marker + fixture pin; union is an explicit non-goal pending a data-path change — a named v1.1 candidate needing its own (tiny) scope block |
| Q-4 | `roster_crunch` forced-drop limb needs a bench-size model that doesn't exist | omitted, not approximated; evidence gap documented; class stays last in the maturity ladder |
| Q-8 | testID spelling: repo dot-idiom `trade-card.breaker-hesitation` vs scope.md's hyphen example | dot idiom; scope example treated as illustrative |
| Q-9 | Shadow `outlook_src` cannot distinguish declared from #8-seeded viewer outlook (§2.2) | stamped "declared" either way; shadow is never serialized and the §8 readout notes it |
| Q-10 | **CLOSED — T-1 orchestrator ruling (lenses split; both positions logged).** Should the §1.2 block skip `league_demo` and/or `_job_superseded` jobs? | **Both skips ADDED** (§1.2). Lens for: the demo skip matches every neighboring mutation layer (`server.py:5631-:5981`) and the demo-guarded impressions calls (`:6066`/`:6092`), and a narrated sentence about a synthetic demo partner is a product absurdity; the superseded skip is pure wasted-compute avoidance. Lens against: neither skip is correctness-load-bearing (§5.5 E-13 — no wrong rows, no wrong renders were possible without them), and demo narration could be deliberate demo material. Disposition: skips ship; a PRD open question records the "narrate on demo as demo material" lift option as a product call |
| Q-11 | §2.2 bulk readers: negmem may want equivalents — shared-reader ownership | whichever plan lands first owns them; the other reuses (sibling reconciliation note) |
| Q-12 | Can `asset_preferences` rows reference pick ids? (`other_player_keep` §3.10 row) | verify at build; table stores player ids today — pick ids simply never match |
| Q-13 | Roster-spot semantics of incoming picks on MFL/ESPN (both platforms are live) | mooted by the Sleeper-only §3.7 envelope — but the PRD says so explicitly |

Also flagged, not settled: **M-8, §3.3** — the `fit_outlook` scalar choice carries its own
FLAGGED FOR CROSS-REVIEW box inline.

---

*End of merged LLD candidate. Structure and skeleton from draft A; the republish contract,
attribute-gated impression copy, config/stud-tax snapshot, degenerate-input table,
concurrency contract, and fixture-realism precondition from draft B — merged under rulings
M-1..M-12. Every §0.3 anchor re-verified this checkout 2026-08-21 during synthesis; line
drift expected at build — re-cite everything (PLAN A-3).*
