# Code-walk proof — counterparty breaker (waves 1 + 2)

**Why this document exists.** [D-056](../../../living-memory/DECISIONS.md) (2026-08-15) retired Maestro
and the simulator entirely. Where a simulator capture used to go, the evidence is now a written,
**file:line-cited** trace through the landed code. This is that trace, per
[scope.md](scope.md) §3 and [LLD](LLD.md) §7.6.

**Walked at:** branch `claude/counterparty-breaker-plan`, tip **`fdd1683`** (waves 1 + 2 merged).
Every line below was **re-read in this checkout on 2026-08-21**, not carried over from the plan
docs — the LLD's own §0.3 anchor table warns that line numbers drift and must be re-cited at build.

**Files in scope:**

| File | Region |
|---|---|
| `backend/trade_breaker.py` | whole module (1,187 lines) |
| `backend/server.py` | `:4007-4010` (sentinel) · `:4213-4239` (features copy) · `:6063-6143` (the seam) · `:11176-11190` (serialization) |
| `backend/trade_narrative.py` | `:171-330` (the additive hesitation surface) |
| `mobile/src/components/TradeCard.tsx` | `:460-479` (element) · `:839-852` (styles) |
| `mobile/src/shared/types.ts` | `:219-228` (wire type) |

---

## (a) The seam: where it is, and why deck order cannot move

### a.1 Placement

`_run_trade_job` is defined at **`server.py:5445`**. The breaker block is **`:6063-6143`**, and its
position is bounded on both sides by landed code:

- **Above it (`:6023-6061`)** — the last mutation layer, F9 first-session shaping. That block is the
  one that can still *reorder and drop* cards: `:6029-6034` replaces `final_cards` with `shaped` and
  `:6035-6044` rebuilds and republishes the snapshot. It also owns the `board_refresh` header
  (`:6052-6061`). **By `:6063`, `final_cards` is final.**
- **Below it (`:6145-6161`)** — the ghost split. `served_final = final_cards` at **`:6149`**, and the
  split loop at `:6151-6158` runs only `if ghost_on`. Under the no-ghost ruling
  (`ghost_holdout_one_in = 0` since 2026-08-21 00:43:32Z) this is **inert**: `served_final IS
  final_cards`. The breaker therefore sees exactly the list the impression writers see.
- **Further below (`:6180-6184`)** — `log_trade_impressions`, and **`:6206-6243`** — the
  `deck.signal_v2` block that calls `_log_deck_signal_impressions` (defined `:4026`) with
  `cards = served_final` at **`:6220`**.

That ordering is the whole reason the seam sits where it does: **post-mutation-stack,
pre-ghost-split**. Any earlier and a later layer could reorder cards the breaker had already scored
against their neighbours; any later and the impression rows would be written before the stamp
existed.

### a.2 Why order is unaffected — three independent reasons

1. **The block writes nothing but the two new attributes.** Across `:6063-6143` the only assignments
   to card state are `_bc.breaker` (`:6141`) and `_bc.breaker_shadow` (`:6143`) in the failure
   handler; the success path's writes all live inside `trade_breaker` and are likewise attribute-only
   (`trade_breaker.py:742-744`, `:877-879`, `:896-898`, `:908-910`, `:919-921`, `:961`, `:966-968`).
   `final_cards` is never re-bound, sorted, filtered, appended to, or truncated anywhere in the block
   — contrast `:6029-6034` immediately above, which is what a layer that *does* change the deck looks
   like.
2. **Nothing downstream reads the stamp to make a decision.** The only readers of `card.breaker` in
   the entire tree are the three server sites (`:4231`, `:11184`) and the module itself — pinned by
   the D-11 grep guard `test_breaker_inert_seam_creep_guard`, which also asserts that
   `inspect.getsource(trade_service)` and each generator contain no `trade_breaker` reference.
3. **The module is not even importable-by-accident when the flag is off.** The import at **`:6083`**
   is *inside* the `if` at **`:6080-6081`**, so a flag-off job leaves `backend.trade_breaker` absent
   from `sys.modules` (`test_flag_off_never_imports_breaker`), and a module that was never imported
   cannot have side effects.

Directly test-pinned by `test_breaker_zero_ordering_effect` (parametrized `bakeoff_group_size ∈
{0, N}` + organic; served trade-ids compared byte-for-byte, flag on vs off) and by the
delete-attribute variant borrowed from the fit arm's `test_fit_diag_inert`.

### a.3 The two skips, and the one flag read

**`:6078-6079`** reads both flags **once**, into `_bk_on` / `_bk_narr`, before any work — so the whole
block acts on one coherent pair even if a hot reload lands mid-job (§5.5 E-8). The guard at
**`:6080-6081`** adds two skips:

- `league_id != "league_demo"` — consistent with every neighbouring mutation layer and with the
  demo-guarded impressions calls at `:6181` and `:6207`; narrating about a synthetic demo partner is
  a product absurdity.
- `not _job_superseded(job_id)` (predicate at `:2917`) — pure wasted-compute avoidance; a superseded
  job publishes no snapshot and writes no `deck_impressions` rows, so neither skip is
  correctness-load-bearing. Both were ruled in (LLD §9 Q-10) with the "against" lens logged.

---

## (b) The stamp path, including every marker fallback

### b.1 Absence is impossible by construction

`stamp_breaker` (**`trade_breaker.py:714-765`**) states the contract in its docstring at `:724-729`:
every card leaves carrying the attribute — a scored payload or a labeled minimal marker — and the
function **raises nothing**. The mechanics:

| Path | Line | Result |
|---|---|---|
| Empty deck | `:735-736` | no-op, zeroed report, **no republish** (E-1) |
| Knob snapshot | `:730` → `_knob_snapshot` `:220-233` | all 25 `breaker_*` keys + `waiver_slot_cost` resolved **once** via the module-level `ts._c` (T1), falling back to the §4 default only while a key is unregistered |
| `breaker_ms_budget = 0` | `:747-751` | documented disable — every card marked `budget_exhausted`, rung 3 |
| Deck-level exception | `:760-764` | any card still unstamped gets `exception_card`, rung 4 |

The marker itself is `_marker(reason)` at **`:236-238`** — exactly three keys,
`{"ver": BREAKER_VERSION, "degraded": reason, "objections": None}` — deliberately constructible
anywhere, with no dependency on evaluation state. `_stamp_marker` (**`:741-745`**) applies it to
`card.breaker` and, when the shadow knob is on, to `card.breaker_shadow`, and increments the rung
counter.

### b.2 The rung ladder inside `_run`

| Rung | Reason | Line | Scope |
|---|---|---|---|
| 0 | scored | `:961` (`w.card.breaker = payload`), rung recorded `:973-974` | per card |
| 0 (contained) | `skipped: "predicate_error"` | `:859-864` | per **class**; the card stays covered and `report.predicate_errors` increments (E-14) |
| 1 | `partner_snapshot` — partner context unbuildable | `:896-899` | per card; other partners' cards unaffected |
| 2 | pass-2 skipped (budget checkpoint) | `:929-930`, rung at `:973` | **deck-uniform** |
| 3 | `budget_exhausted` | `:919-922`, `:946` | remaining cards (mid-pass-1) / deck-uniform with pass-2 buffered work **discarded** (mid-pass-2, M-9) |
| 4 | `self_partner` / `exception_card` | `:877-880`, `:908-911` | per card |
| 5 | `exception_outer` | `server.py:6130-6143` | **every** card |

Field-level degradation is deliberately *not* a rung: a failed bulk-prefs read
(`_obj_other_player_keep` **`:583-588`**, and `_bulk_prefs` at `:355-369`) marks `other_player_keep` `not_applicable` and leaves
the card at rung 0, because "this partner stored no preferences" is a common legitimate state and
counting it as degradation would swamp the ladder.

### b.3 Rung 5 — the outermost fallback, built from nothing

**`server.py:6123-6143`.** The `except` catches everything the seam can raise **including the import
itself** at `:6083`. That constrains what the handler may touch, and the landed code respects it:

- the marker at `:6130-6131` is a **literal**: `{"ver": "brk-1", "degraded": "exception_outer",
  "objections": None}`. It cannot reference `trade_breaker.BREAKER_VERSION` — the module may not
  exist — so the two are kept equal by `test_rung5_marker_version_pinned` instead;
- **no knob is read** (`:6132-6136`): in `_run_trade_job` the local `trade_service` is the per-format
  *instance* (no `_c`), and a live knob read at failure time would violate the §3.0
  one-job-one-knob-state rule anyway;
- `:6140-6143` stamps `breaker` on every card and `breaker_shadow` **only when it is currently
  `None`**, so an existing shadow stamp survives.

### b.4 The copy into `features_json`

**`server.py:4213-4239`**, inside `_log_deck_signal_impressions` (`:4026`). Four properties, each
load-bearing:

1. **Outside the bake-off guard.** The fit keys at `:4211-4212` sit inside `bakeoff_run is not None`;
   the breaker's copy does not — organic decks stamp too (ruling M-2).
2. **Attribute-gated, not flag-gated.** `_bk = getattr(card, "breaker", _BK_SENTINEL)` at `:4231`,
   against the module-level sentinel defined at **`:4007-4010`** — a fresh `object()`, never `None`,
   so "no attribute" stays distinguishable from a stamped null. A mid-job hot flip cannot make this
   site act on a flag state the stamp site never saw, and this loop has **no per-row try/except**: one
   `AttributeError` here would lose the whole deck's impressions, fit keys included.
3. **Never a bare null on a flag-on row.** `:4235-4239` — when the attribute is missing but the flag
   reads on at log time, a synthetic `{"ver": None, "degraded": "flag_flip_or_unstamped",
   "objections": None}` is written. Its `ver` is null **by construction**: at log time the module may
   never have been imported, so no version literal can honestly be claimed.
4. **Both keys ride inside `features_json`** (one column), so `save_deck_impressions`' executemany
   first-row-keys trap cannot drop them.

Pinned by `test_impressions_breaker_uniform_keys` (mixed rungs, organic **and** bake-off rows),
`test_midjob_flag_flip_no_crash` (both flip directions), and
`test_flag_off_features_json_carries_no_breaker_key`.

---

## (c) The narration gate chain — switches → floors → whitelist → template

`compose_narration` (**`trade_breaker.py:1073-1169`**) is a separate deck-level pass, called from the
seam at `server.py:6101-6104` **only** when `_bk_narr` is true. It returns the count narrated.

### c.1 Per-card eligibility (in landed order)

| # | Gate | Line | Effect |
|---|---|---|---|
| 0 | marker-only card | `:1095-1097` | `continue` — nothing to narrate, no suppression reason recorded |
| 0b | fields reset | `:1098-1100` | `narrated` / `suppressed` / `tmpl_ver` set to `None` first ⇒ **idempotent** |
| 1 | no `top` | `:1102-1104` | nothing cleared a floor at stamp time |
| 2 | **per-class switch** | `:1106-1108` | `cfg["breaker_narrate_<code>"] < 1.0` ⇒ `class_ineligible`. All six default **0.0** (`:118-123`) — flag-on with default knobs renders **nothing**, by design |
| 3 | **whitelist** | `:1109-1111` | `code ∉ NARRATABLE_CLASSES` (`:64-66`) ⇒ `class_ineligible`. `other_player_keep` is absent from that set, so it can never narrate even with its switch forced to 1 |
| 4 | **basis restriction** | `:1113-1115` | `value_giving` narrates on the `consensus` basis only; the board basis is ineligible outright (D-7) |
| 5 | format envelope | `:1116-1118` | code in `payload["format_gap"]` ⇒ `format_gap` |
| 6 | **floors** | `:1119-1122` | `top.severity < max(class floor, breaker_min_severity)` ⇒ `below_floor`. `_class_floor` (`:699-707`) makes `value_giving`'s floor basis-dependent — `consensus` uses the deliberately-higher `breaker_floor_value_giving_consensus` (0.75 vs 0.30) |
| 7 | outlook agreement + margin | `:1123-1125` → `_outlook_narratable` `:1172-1187` | declared ≠ inferred ⇒ refuse; `legacy` source inside `breaker_outlook_narrate_margin` of the cut ⇒ refuse |
| — | any exception in the chain | `:1127-1129` | `template_error`, contained |

The **narration bar sits above the stamp bar** by construction of step 6 (`max(...)` of the
class floor and the global minimum), with the shipped defaults pinned in that order by
`test_default_knob_ordering`.

### c.2 Deck-level repetition suppression

**`:1131-1148`.** Survivors are grouped by `(target_user_id, code)`; the per-partner limit is
`ceil(breaker_max_repeat_frac × partner_card_counts[uid])` (`:1139-1140`). Over the limit, only the
max-severity card survives (`:1144`, ties broken by original index) and the rest are stamped
`suppressed: "repetition"` (`:1146-1148`).

### c.3 The template call

**`:1150-1166`.** Only group winners reach `trade_narrative.hesitation_line(payload["top"], players)`
at **`:1156`**; a raise is contained as `template_error` (`:1157-1160`). Two subtleties in the landed
code:

- **A template refusal is honest silence, not a suppression** (`:1161-1163`): a falsy return leaves
  both `narrated` and `suppressed` null. The refusal itself lives in `trade_narrative` —
  `HESITATION_DARK_CODES` (`trade_narrative.py:195`) has no template for `other_player_keep`, and the
  honesty rule returns `None` on a missing **or present-but-null** evidence value rather than
  rendering "None-year-old".
- `tmpl_ver` is read from `trade_narrative.HESITATION_TMPL_VERSION` (`:1151`, defined
  `trade_narrative.py:184` = `"brt-1"`) and stamped **only on narrated cards** (`:1165`), so the A/B
  join key `(ver, tmpl_ver)` is null wherever nothing rendered.

Direction of dependency is one-way and stated at `trade_narrative.py:171-175`: the breaker calls
**down** into the narrative module; nothing there imports `trade_breaker`, reads a flag, or reads a
knob.

---

## (d) The dark-window payload guarantee

**`server.py:11176-11190`**, inside `trade_card_to_dict` (`:11091`).

```
_bk = getattr(card, "breaker", None)                    # :11184
if isinstance(_bk, dict) and _bk.get("narrated"):       # :11185
    out["breaker"] = {"code": ..., "severity": ..., "sentence": _bk["narrated"]}   # :11186-11190
```

The gate is **`narrated`**, not the flag and not the presence of a stamp. Consequences, each of which
is the guarantee:

- **Dark-stamp window** (`trade.breaker` on, `trade.breaker_narrative` off): `compose_narration` never
  ran, so `narrated` is null on every card and the payload carries **no `breaker` key at all**. Dark
  classes cannot ship as inspectable structured data even to a curious client
  (`test_breaker_payload_absent_during_dark_window`).
- **The full objection vector never serializes** — only three fields — and **`card.breaker_shadow`
  never appears in any payload** (`test_breaker_shadow_never_serialized`).
- The unguarded `_bk["top"]["code"]` index at `:11187` is deliberate: `narrated ⇒ top non-null` is
  `compose_narration`'s invariant, and a violation must fail loudly in tests rather than degrade.
- Flag fully off ⇒ output byte-identical (`test_flag_off_payload_byte_identical`).

**The client half.** `mobile/src/components/TradeCard.tsx:472` gates the element on
`data.breaker?.sentence`; `:473-478` render the sentence **verbatim** with testIDs
`trade-card.breaker-hesitation` / `.body`, no `code` read and no client-side copy — the "Their likely
hesitation:" lead-in is part of the server string (`trade_narrative.py:187-190`). Styles at `:843-852`
are token-only (`flare.base` dot, `space.sm` gap; no hex literals, no radius). The wire type at
`mobile/src/shared/types.ts:228` declares `breaker?` optional with exactly `{code, severity,
sentence}`. **Payload presence IS the gate** — the client reads no flag, so it cannot drift from the
server's eligibility rules. All twelve of these facts are asserted by
`mobile/tests/check-breaker-card.js`; run in this checkout: **12 passed, 0 failed**.

---

## (e) The republish path, per flag combination

The client is served `j["cards"]` — a snapshot rebuilt by whichever layer last published. The
breaker's own republish is **`server.py:6105-6122`**, conditional on `_n_narrated` being non-zero,
and uses the standard idiom: `_served_cards(...)` (`:4013`) → `trade_card_to_dict` → `real_opponent` /
`outlook` decoration → `_trade_jobs_lock` → `_job_live(j)` guard (`:2902`).

| `trade.breaker` | `trade.breaker_narrative` | narrated | `deck.signal_v2` | What the client gets |
|---|---|---|---|---|
| off | — | — | either | Module never imported. No attribute, no `features_json` key, no payload key, **no extra publish** — byte-identical to pre-feature |
| on | off | 0 by construction | either | Stamps written; `features_json` carries `breaker` + `breaker_shadow`; **payload has no breaker key**; `_n_narrated == 0` ⇒ `:6105` is false ⇒ **zero extra publishes**, snapshot byte-identical to flag-off |
| on | on | 0 (floors / switches / suppression) | either | Same as above — the republish is gated on the **count**, not on the flag, so a hot deck that narrates nothing costs nothing |
| on | on | ≥1 | **on** | The `:6113-6122` republish carries the sentences; the later signal-v2 republish at `:6230-6243` rebuilds the same cards **plus** `impression_id`, and re-serializes `breaker` from the same attributes — the two agree because both call `trade_card_to_dict` |
| on | on | ≥1 | **off** | `:6207` is false, so the signal-v2 republish never runs. **The seam republish at `:6113-6122` is the ONLY carrier** — this row is precisely why the M-1 contract makes the breaker publish for itself instead of relying on a neighbour |
| any | any | any | any, **job superseded** | `:6081` skips the block entirely; and even if it did not, `_job_live(j)` at `:6121` refuses the write. A superseded job publishes nothing |

Pinned by `test_narrated_payload_reaches_snapshot_all_flag_combos`, parametrized over
`deck.signal_v2 ∈ {on, off}` × streaming state × narrated ∈ {0, ≥1} × job live/superseded — including
the assertion that dark and zero-narrated decks add **zero** publishes and produce snapshots
byte-identical to flag-off.

---

## What this walk does NOT prove

Stated plainly, because a code-walk that implies runtime coverage is worse than none:

- **No runtime evidence exists for this feature.** Nothing here has run on a device. The PRD §8.3
  **19-step manual TestFlight checklist** is the only runtime evidence the mobile half will get
  (D-056), and it is **UNRUN** — it needs a build containing the element, which does not exist.
- **`tsc --noEmit` was not run locally** (`mobile/node_modules` is absent in this worktree); it is
  covered by CI's `mobile-typecheck` job on the pushed sha.
- Coverage, cost and calibration are **production** measurements. Their surrogates are the uniform-key
  tests and the preregistered [calibration-readout-spec.md](calibration-readout-spec.md); no number in
  that spec has been observed yet.
