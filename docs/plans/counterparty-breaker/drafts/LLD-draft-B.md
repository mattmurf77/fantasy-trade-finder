# LLD — Counterparty breaker (draft B, reviewer lens)

**Date:** 2026-08-21 · **Author:** Agent B (independent draft; foregrounds under-specified
interfaces, unhandled error paths, edge cases, testability).
**Binds under:** [PLAN.md](../PLAN.md) → [HLD.md](../HLD.md) (CONVERGED — not contradicted here)
→ this LLD. Precedent studied: [../../fit-challenger/LLD.md](../../fit-challenger/LLD.md),
PRD-build §6 trap table.
**Every line number below re-verified against this checkout 2026-08-21** (worktree
`trading-engine-eval-8ab7bc`, branch `claude/counterparty-breaker-plan` docs). Line drift
expected at build; re-cite per PLAN A-3.
**Operator ruling honored throughout: NO ghost cards, full stop.** Nothing below creates,
consumes, or measures ghost impressions; the ghost-split code path is treated as an inert code
location only.

---

## 0. Reviewer's verification ledger

The HLD deferred the republish question and cited sites "drift expected." I re-walked all of
them. Corrections and confirmations the rest of this draft builds on:

| Claim | Verified state in this checkout |
|---|---|
| Seam location | F9 block ends at `server.py:6028`; `served_final = final_cards` at `:6034`; ghost split `:6036-6046`. The breaker block inserts **between `:6028` and `:6030`** (before the telemetry-split comment block). |
| Publish sites (ALL of them) | Streaming `on_opponent_done` callback `server.py:2984-3006`; F7 split republish `:5726-5736`; likes-you republish `:5768-5777`; F3 suppression republish `:5815-5827`; `_order_deck` republish `:5911-5922`; F7 wildcard republish `:5953-5963`; F9 first-deck republish `:6002-6011`; final impression-id republish `:6115-6128`. **Every one is conditional** — each fires only if its layer changed the deck, and the final one fires only when `deck.signal_v2` is on AND `imp_by_card` is truthy AND the job is not superseded (`:6092-6093`, `:6115`). The completion comment (`:6145-6146`) says the "final card snapshot was already published by the last on_opponent_done invocation" — i.e. **with `deck.signal_v2` off there is NO unconditional post-mutation publish at all.** §2.3 below is built on this. |
| `_job_live` / supersede | `_job_live` def `:2902-2914` (running AND not superseded); `_job_superseded` `:2917-2925`; superseded jobs run to completion but skip the signal-impression block (`:6087-6093`) and all publishes (every publish site checks `_job_live`). Legacy `log_trade_impressions` (`:6067`) is **not** supersede-gated (pre-existing; no features_json there, no breaker exposure). |
| `_served_cards` | def `:4007-4018` — the render gate every publish loops through. A breaker republish must use it too. |
| `_log_deck_signal_impressions` | def `:4020`; empty-deck early return `:4060-4061`; the per-row loop `:4122` iterates served **and ghost** entries (`:4120-4121`); features assembly `:4135-4212`; `bakeoff_run` guard `:4193`; fit keys `:4205-4206`. **No per-row try/except** — one exception in the loop aborts the entire deck's impressions (outer catch at the callsite `:6129`). |
| `save_deck_impressions` | `database.py:5503-5516` — thin executemany; first-row-keys trap real, defused by riding inside `features_json` (one column). |
| `PASS_REASON_LAYER2` | `database.py:5579-5583` — 10 layer-2 codes across 3 layer-1 keys, incl. `other_text`. |
| `trade_card_to_dict` | def `server.py:10976`; fit additive block `:11055-11057` (`out["fit"]`). |
| `_run_trade_job` | def `server.py:5412`; `trade_service = trade_svcs.get(active_format)` `:5438-5440` — the SESSION's per-format TradeService instance, distinct from the `ts` module the breaker imports. |
| `_cfg_override` / `_c` | `trade_service.py:995-1010` (thread-local overlay, contextmanager — **exits when each arm's generate call returns**), `_c` accessor `:1003-1010`. At the post-F9 seam no arm profile overlay is active. But `_c` reads live `_cfg`, mutable mid-job by `PUT /api/admin/config` → `reload_config()` (`:969-982`). |
| Stud-tax thread-local | `trade_service.py:1062-1105` — pinned by generation entry points "for the duration of their math"; **unpinned at the post-F9 seam**, so any `package_value_v2` call there silently uses `'market'` default regardless of anyone's setting (`:1346`). |
| `analyze_roster_strengths` | `trade_service.py:2211`; `_POS_TIER_CUTS` `:2071-2077` (12-team assumed, per its own comment `:2069-2070`); SF QB cuts `:2078`; `_POS_TIER_MIN_POOL = 40` `:2086` with `tier_basis` fallback reporting `:2266`. |
| `infer_team_outlook` | `trade_service.py:3084`; composite applies only when a caller supplies `starter_signal` (`:3235`, INV-372b) — no deck-path caller does. |
| `_opponent_frame` | `trade_narrative.py:86-101`; thresholds ±0.05 at `:97/:99`; reads `match_context["opponent_outlook"]["value"]`. `build_narrative` `:103`. |
| `stamp_fit_diag` | `trade_gen_fit.py:857`; per-card try/except with `card.fit_diag = None` on unscorable cards; MODULE-import discipline `:35-36`; organic-isolation covenant `:23-24`. |
| Mobile narrative claim | Confirmed: only a comment at `mobile/src/components/TradeCard.tsx:437` mentions `narrative`; nothing renders it. Client mapping is additive-key-tolerant (fit precedent). |
| `asset_preferences` / declared outlook are **NOT pre-loaded for partners** | The job loads only the VIEWER's untouchables (`server.py:5546-5556`). Partner prefs (`database.load_asset_preferences`, `:8660`) and declared outlooks (`league_preferences_table`, `database.py:987-991`) require **new per-partner DB reads at the seam** — the HLD's "over data the job already loaded" is true for rosters/boards, false for these two. §4.2 makes this a bulk load. |
| Deck size | `bakeoff_deck_limit` was raised 30→60 at the A-1 boundary (PLAN §10). The HLD cost envelope (§5.4, "~30 served cards") is a 2× undercount for bake-off decks. Budget math and the W0-style dry run must use **60**. |

---

## 1. Scope

Per HLD §1: `backend/trade_breaker.py` (new) + `trade_narrative.hesitation_line` (new pure
function) + one guarded block in `server._run_trade_job` + one attribute-gated copy in
`_log_deck_signal_impressions` + one narration-gated block in `trade_card_to_dict` + the mobile
hesitation element. Two flags (`trade.breaker`, `trade.breaker_narrative`), knob family §4.4,
zero tables, zero routes, zero ordering effect. Not in scope: everything in HLD §1.4.

---

## 2. Interfaces

### 2.1 `backend/trade_breaker.py` — public surface (complete; anything else is private)

```python
BREAKER_VERSION = "brk-1"          # bump on ANY predicate/threshold/evidence-shape change

# The full closed knob list, read ONCE per job into a frozen snapshot (§4.1):
_BREAKER_KNOB_KEYS: tuple[str, ...]  # enumerated in §4.4

def stamp_breaker(
    cards: list,                    # the post-F9 final_cards list — NEVER reordered/mutated
    *,
    league,                         # ts.League — g_league
    players: dict,                  # players_dict
    seed_elo: dict[str, float],     # seed_map
    scoring_format: str,            # active_format
    viewer_user_id: str,            # g_user_id — needed by the shadow run + self-trade guard
    shadow: bool = False,           # operator decision 5 — also stamp card.breaker_shadow
) -> "BreakerReport": ...

def compose_narration(cards: list, *, players: dict) -> int:
    """Populate card.breaker['narrated'] / ['suppressed'] per D-6/D-7.
    Returns count narrated (0 is normal). Reads ONLY card.breaker set by
    stamp_breaker in the same job; never re-evaluates predicates."""

@dataclass
class BreakerReport:               # FitReport precedent — per-job diagnostics, no DB
    cards_seen: int; stamped: int
    degraded_by_rung: dict[int, int]
    narrated: int; suppressed_by_reason: dict[str, int]
    class_fires: dict[str, int]    # top.code histogram
    format_gapped_decks: int       # 0/1 — this deck had ≥1 gapped class
    partner_ctx_built: int; partner_ctx_failed: int
    ms_total: float; ms_p50_card: float; ms_p95_card: float
    pass2_ran: bool                # False ⇒ rung-2 fired
```

Import discipline (HLD §2.2, binding): `from . import trade_service as ts`,
`from . import trade_optimizer as topt`, `from . import trade_narrative` — module imports only
(T1). Never imports `trade_gen_fit`, `server`, `bakeoff_runner`. `database` imports limited to
the two bulk readers in §4.2. `trade_service` never imports `trade_breaker`.

**Interface contracts the HLD left unstated, now pinned:**

- `stamp_breaker` **returns the report and raises nothing.** Every exception is absorbed into
  rung 4/5 markers internally; the server-side try/except (HLD §2.3 sketch) is belt-and-braces
  for the import line and a bug in the marker path itself. Rationale: the outer handler cannot
  build per-card markers if the module half-died; the module can.
- `stamp_breaker` is **idempotent**: a second call overwrites `card.breaker` wholesale
  (deterministic inputs ⇒ identical result). No accumulation, no append.
- `compose_narration` is idempotent and **must be called after** `stamp_breaker` in the same
  job; called on a card without `card.breaker` it stamps nothing and counts it (defensive —
  reachable only via a bug, surfaced in the report, never an exception).
- `cards` may be **empty** (deck of 0 — F3 suppression can empty a deck): both functions are
  no-ops returning a zeroed report / 0. Test-pinned.
- **Self-trade guard:** a card whose `target_user_id` resolves (via the §3.4 co-owner union) to
  the viewer is stamped with the rung-4 marker `degraded: "self_partner"` and skipped — it is a
  data corruption upstream, not a valid evaluation target. (Not constructible today; guard
  exists because `league_members` corruption was the phantom-13th-team bug class,
  `backend/CLAUDE.md` §Identity.)

### 2.2 `trade_narrative.hesitation_line` — pure template function

```python
def hesitation_line(objection: dict, players: dict) -> str | None:
    """Deterministic template render of ONE objection. Returns None iff the
    objection's code has no template or a REQUIRED evidence id fails to
    resolve (D-053: never renders a fallback name, never guesses). Reads
    ONLY objection['code'] / ['evidence']; ids resolve to names here and
    only here. Raises nothing (any internal error → None; the caller
    stamps suppressed='template_error' — see §5 row E-14)."""
```

Inherits the positional-honesty covenant (`trade_narrative.py:120-126` comment block).
`build_narrative` (`:103`) untouched. `TMPL_VERSION = "brt-1"` lives beside the templates in
`trade_narrative.py`; `compose_narration` copies it into the stamp as `tmpl_ver`.

### 2.3 The server seam — insertion AND the republish contract (the part the HLD deferred)

**Insertion:** `server.py`, after the F9 block closes (`:6028`), before the
`suggestion.telemetry` split comment (`:6030`). Everything needed is in scope at that line
(verified: `final_cards`, `g_league`, `players_dict`, `seed_map`, `active_format`, `g_user_id`,
`real_user_ids`, `outlook_value`, `league_id`, `ghost_on`, `job_id`).

**The republish finding (ledger row 2):** with `deck.signal_v2` OFF, no publish runs after the
mutation stack — the client's snapshot is whatever the last *conditional* republish (or the last
streaming callback) produced. A narrated sentence stamped post-F9 would exist in
`features_json` and **never reach any client** on that flag combination. With `deck.signal_v2`
ON, the `:6115-6128` republish re-serializes every card and would carry it — but only when
`imp_by_card` is truthy (impressions succeeded) and the job isn't superseded. Therefore:

```python
        # ── breaker (v1) — evaluate + stamp + (flag 2) compose + republish ──
        # Post-F9 (:6028), pre-telemetry-split (:6030). Attribute-only,
        # fail-open, zero ordering effect (test-enforced). Flags are read
        # ONCE here into locals — §5 row E-8 (mid-job hot reload).
        _breaker_on  = bool(getattr(FLAGS, "trade_breaker", False))
        _narrate_on  = _breaker_on and bool(
            getattr(FLAGS, "trade_breaker_narrative", False))
        if _breaker_on and league_id != "league_demo" and not _job_superseded(job_id):
            try:
                from .trade_breaker import stamp_breaker, compose_narration  # lazy
                _bk_report = stamp_breaker(
                    final_cards, league=g_league, players=players_dict,
                    seed_elo=seed_map, scoring_format=active_format,
                    viewer_user_id=g_user_id,
                    shadow=_breaker_shadow_enabled(),
                )
                _n_narrated = 0
                if _narrate_on:
                    _n_narrated = compose_narration(final_cards,
                                                    players=players_dict)
                if _n_narrated:
                    # Republish so the sentence reaches the snapshot on EVERY
                    # flag combination (deck.signal_v2 off included). Same
                    # decoration as every other publish site; the :6115
                    # republish (signal_v2 on) re-serializes and keeps it.
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
                _stamp_breaker_outer_marker(final_cards)   # §5 row E-13
```

Contract points a reviewer should hold the build to:

1. **Republish only when `_n_narrated > 0`.** A dark-stamp deck (`trade.breaker_narrative`
   off, or on with zero narrated) publishes nothing new — flag-1-only byte-identity of the
   *payload stream* is preserved (NFR-1/NFR-3 extended to publish traffic).
2. The republish precedes impression logging, so it never carries `impression_id`; the
   `:6115` republish restores that when `deck.signal_v2` is on. Ordering is: breaker republish
   (sentence, no iids) → impressions → final republish (sentence + iids). Clients tolerate the
   intermediate state — it is the same state every mutation-layer republish already produces.
3. **Skip conditions match the impression block, not the mutation layers:** `league_demo`
   (impressions never log there — a stamp would be unmeasurable compute; a narrated sentence
   about a synthetic demo partner is also a product absurdity) and superseded jobs (nobody
   will see the cards; stamping them wastes the budget and — worse — the invariant "every
   *logged* impression carries the key" is unaffected because superseded jobs skip the signal
   block at `:6093`). The supersede re-check inside `_log_deck_signal_impressions`' caller
   remains the authoritative gate; the seam check is a cost optimization with a benign race
   (superseded-after-stamp ⇒ stamped cards, no rows, no publish — harmless).
4. `_stamp_breaker_outer_marker(cards)` is a **server-local 4-liner** setting the §5 minimal
   marker `{"ver": "brk-1", "degraded": "exception_outer", "objections": None}` on every card
   — deliberately not imported from `trade_breaker`, because the import itself is one of the
   failure modes it must cover (HLD NFR-2's "constructible with no breaker state" made
   literal: it must not even need the module).

### 2.4 `_log_deck_signal_impressions` — the copy is ATTRIBUTE-gated, not flag-gated

Beside — outside — the `bakeoff_run` guard (`:4193`), after the fit keys (`:4205-4206`):

```python
        # Counterparty breaker — key present iff the stamp ran (attribute-
        # gated, NOT flag-gated: a mid-job flag flip must not make this
        # block see a flag state the stamp site never saw — §5 row E-8).
        # Ghost rows (inert under the no-ghost ruling) take the same copy;
        # readouts filter is_ghost=0 regardless.
        _bk = getattr(card, "breaker", _SENTINEL)
        if _bk is not _SENTINEL:
            features["breaker"] = _bk
            features["breaker_shadow"] = getattr(card, "breaker_shadow", None)
```

**This deliberately amends the HLD §3.3 sketch** (`if flags.trade_breaker: features["breaker"]
= card.breaker`, "no getattr default"). The HLD's version has a live crash path: flag flipped
ON between the seam and the impression block (hot reload is a route,
`POST /api/feature-flags/reload`) ⇒ `card.breaker` AttributeError ⇒ and because the row loop
has **no per-row try/except** (ledger row 5), the entire deck's impressions — fit keys,
telemetry, everything — are lost to the outer catch at `:6129`. Attribute-gating makes the copy
a pure function of what the stamp site actually did. The HLD's real invariant — "absent key on
a flag-on row is a defect" — is enforced where it belongs, in tests (§7 T-9) and the coverage
tripwire, not by a runtime KeyError with deck-wide blast radius. Uniformity per deck still
holds: the stamp site stamps every card or none (its outer marker covers every card), so
within one job the key is present on all rows or absent on all rows.

### 2.5 `trade_card_to_dict` — narration-gated additive block

After the fit block (`:11055-11057`):

```python
    _bk = getattr(card, "breaker", None)
    if isinstance(_bk, dict) and _bk.get("narrated"):
        out["breaker"] = {
            "code":     _bk["top"]["code"],      # top is non-null whenever narrated is
            "severity": round(float(_bk["top"]["severity"]), 3),
            "sentence": _bk["narrated"],
        }
```

Dark window ⇒ no key (HLD §3.6). `breaker_shadow` never serialized. Full objection vector never
serialized. Invariant `narrated ⇒ top is not None` is compose_narration's to maintain and §7
T-12's to enforce — the serializer indexes `top` unguarded on purpose (a violation should fail
loudly in tests, and the whole block is inside callers' existing serialization path which the
inertness suite covers).

### 2.6 Mobile — `mobile/src/components/TradeCard.tsx`

One conditional element after the header-badge block (`:441-449` region): renders
`data.breaker.sentence` iff `data.breaker?.sentence` is a non-empty string. Chalkline tokens
(`flare` accent = informational, per ADR-005 — this is an informational highlight, not an
action), `testID="trade-card-breaker-hesitation"`. No switching on `code` (cross-client
invariant row stays "n/a in v1"). The client does **not** check the flag — the server already
gates by omitting the key; a client-side flag check would add a second gate that can only
disagree (fit precedent: payload presence IS the gate). Older builds: mapping is
additive-tolerant (ledger row 12) — unknown `breaker` key ignored. Structural guard
`mobile/tests/check-breaker-card.js` pins: element present in source, gated on payload key,
absent-key ⇒ no render, testID present, no `code`-switching.

---

## 3. Data

### 3.1 `card.breaker` — exact types (tightening HLD §3.1's sketch)

```jsonc
{
  "ver":      "brk-1",            // str, = BREAKER_VERSION
  "tmpl_ver": "brt-1",            // str | null — null until compose_narration runs (dark window)
  "top":      {...} | null,       // argmax objection above per-class floor, or null
  "objections": [                 // ALWAYS length == |v1 classes| (6) on rung 0;
    {                             //   rung 2 lists 4 scored + 2 skipped entries
      "code": "fit_outlook",      // str, closed set (§4.3)
      "severity": 0.82,           // float 0..1, rounded 4 places (JSON size + determinism)
      "evidence": {...},          // per-code enum keys ONLY (§3.2); ids/numbers/enums, no names
      "skipped": "format_gap"     // OPTIONAL enum: "format_gap"|"budget"|"not_applicable"
    }                             //   — a skipped entry has severity null, evidence {}
  ] | null,                       // null ONLY inside a degradation marker (rungs 3-5)
  "them": 41.3 | null,            // fit_diag passthrough (D-3); null organic/likes-you/absent
  "narrated": str | null,
  "suppressed": null | "repetition" | "below_floor" | "class_ineligible"
              | "format_gap" | "template_error",
  "outlook_src": "declared" | "legacy" | "composite",
  "outlook_pair": {"declared": str|null, "inferred": str},   // D-8 needs both retained
  "board_auth": "board" | "board_suspect" | "consensus",
  "format_gap": ["fit_new_weakness", ...] | null,
  "degraded": null | "partner_snapshot" | "budget_exhausted" | "exception_card"
            | "exception_outer" | "self_partner",
  "ms": 4.1                       // float, per-card wall ms, 1 decimal
}
```

Minimal marker (rungs 3–5 and the server-local outer stamp): exactly
`{"ver", "degraded", "objections": null}` — three keys, nothing else, so it is constructible
anywhere. `top`/`narrated` absent (not null) on markers; consumers use `.get`.

### 3.2 Evidence key enums (per code — `hesitation_line` may render ONLY these)

| Code | Evidence keys (all optional unless starred) | Notes |
|---|---|---|
| `fit_outlook` | `outlook`* (enum), `asset`* (pid), `age` (int), `pos` (enum), `lean` (float) | outlook = the §4.2 resolved value; asset = worst-fitting give-side asset |
| `fit_new_weakness` | `pos`* (enum), `slot_deficit`* (int), `asset` (pid) | mirrored R5 lineup math |
| `fit_duplicate` | `pos`* (enum), `depth_at_pos`* (int), `tier_basis` (enum) | from partner `analyze_roster_strengths` |
| `value_giving` | `basis`* ("board"\|"consensus"), `margin`* (float), `pkg_delta` (float) | board basis narration-ineligible outright (D-7) |
| `other_player_keep` | `asset`* (pid), `list`* ("untouchable") | ALWAYS dark in v1 (D-6) |
| `roster_crunch` | `drops_forced`* (int), `pos_pileup` (enum), `slots_over` (int) | new logic; stamp-only maturity |

No key not in this table may appear (vocabulary-closure test §7 T-3 checks evidence keys too,
not just codes — an unlisted key is how a private-state leak sneaks past the whitelist).

### 3.3 Size budget (measured obligation, not vibes)

Realistic rung-0 stamp ≈ 6 objections × ~90–130 B + markers + top + sentence ≈ **0.9–1.4 KB**;
shadow doubles it ⇒ ~2–3 KB added per `features_json` (today's baseline ~0.7–1.0 KB). At the
**60-card** bake-off deck limit (ledger row 15): ~120–180 KB per deck insert. No column limit
bites (TEXT both dialects; executemany fine at this scale), but the LLD makes it a **pinned
test**: §7 T-16 serializes a worst-case fixture stamp and asserts `len(json.dumps(stamp)) <
4096` per card — a tripwire against evidence-shape creep, because features_json rows are read
back by every readout query and 10× growth is a query-cost regression nobody will otherwise
notice. Severity rounding (4 places) and ms rounding (1 place) are part of this budget AND of
determinism (float repr noise breaks byte-identity tests).

### 3.4 Identity resolution (co-owner)

Per HLD §3.4, via `backend/sleeper_roster.py` (`co_owner_ids`, `canonical_owner_id`) — the ONE
predicate. `PartnerContext` is cached by **`canonical_owner_id(roster)`**, not by
`card.target_user_id` — two cards targeting the same roster through different co-owner aliases
must hit one cache entry (correctness, not just cost: two entries could resolve different
boards). Prefs union / board selection per HLD; `board_src` recorded when co-owner boards
diverge.

---

## 4. Core Logic

### 4.1 Config snapshot — one read, frozen, stamped implicitly by `ver`

`stamp_breaker` begins with `cfg = {k: ts._c(k) for k in _BREAKER_KNOB_KEYS}` and reads **only
`cfg`** thereafter (both passes, compose_narration receives the same dict via the report or a
module-level per-job holder — NOT a re-read). Three hazards this kills, all live (ledger rows
13–14):

1. **Hot knob flip mid-job** (`PUT /api/admin/config` → `reload_config()` updates `_cfg`
   in-place): without the snapshot, pass 1 and pass 2 — or two cards in one pass — read
   different values ⇒ intra-deck nondeterminism invisible to `ver`.
2. **`_cfg_override` overlays**: none is active at the post-F9 seam (arm contexts exit with
   their `with` blocks — verified `trade_service.py:995-1001`), but the relaxed-pass and
   arm-profile machinery exists on this thread; snapshotting at entry makes the breaker's
   reads structurally indifferent to whether a future caller (v2 in-generation) sits inside
   an overlay. The **binding-sabotage test** (§7 T-6) monkeypatches a `ts` knob and asserts
   the verdict moves on the NEXT `stamp_breaker` call — module-import discipline preserved,
   snapshot boundary documented.
3. **Stud-tax thread-local** (ledger row 8): at the seam, no pin is active ⇒
   `package_value_v2` runs in `'market'` mode. The breaker makes this **explicit and
   deterministic**: every breaker valuation call is wrapped in
   `ts.stud_tax_override("market")` (the existing contextmanager, `trade_service.py:1089`).
   Rationale: the partner's own stud-tax setting is per-user private state (a DB read per
   partner, and using it would make the same card's severity depend on a partner's UI toggle
   — a calibration confounder); consensus-default 'market' is the one mode every seat shares.
   Recorded as a D-level decision for cross-review — the alternative (partner's own mode) is
   defensible and someone should argue it.

### 4.2 `PartnerContext` — fields, build order, bulk reads

```python
@dataclass(frozen=True)
class PartnerContext:
    partner_key: str                  # canonical_owner_id
    roster_ids: tuple[str, ...]
    strengths: dict                   # ts.analyze_roster_strengths(roster, players, scoring_format)
    outlook_declared: str | None      # from bulk league_preferences read
    outlook_inferred: str             # ts.infer_team_outlook(...) — engine-served signal set ONLY
    outlook_resolved: str             # declared or inferred per D-8
    outlook_src: str
    board: dict[str, float] | None    # member.elo_ratings RAW (T3 — never _shrink_user_elo)
    board_auth: str                   # F-3 divergence heuristic vs seed_elo
    prefs_untouchable: frozenset[str] # union over co-owners
    prefs_not_interested: frozenset[str]
    starter_slots: dict               # league roster_positions → slot map
    format_ok: bool                   # §4.5 envelope verdict (12-team, non-IDP, priced pool)
    format_gap: tuple[str, ...]       # classes gapped for this league/partner
```

**Bulk reads, not per-partner queries** (ledger row 14): two new thin readers in
`database.py` — `load_asset_preferences_bulk(user_ids, league_id)` and
`load_league_preferences_bulk(user_ids, league_id)` — one `IN (...)` select each, called once
per job for the distinct partner set (≤ league size). Per-partner fallback loops would add up
to ~2 × 11 × 2 (co-owners) queries per deck on the job thread; two queries is the same data.
DB failure on either bulk read degrades **all** partners' affected fields (prefs → empty +
`other_player_keep` skipped `not_applicable`; declared outlook → None with `outlook_src`
unchanged semantics), stamped rung 0 with the field-level markers — NOT rung 1, which is
reserved for a partner's snapshot build failing (roster/strengths/board), because prefs
absence is a legitimate common state and marking it "degraded" would swamp the rung metrics.

`infer_team_outlook` is called with exactly the signal set the engine's deck path supplies
(no `starter_signal`, no `first_round_ledger` — INV-372b/INV-365b verified): the breaker
inherits the legacy vector by construction and `outlook_src="legacy"` until the engine itself
graduates the composite.

### 4.3 Class predicates — per-class degenerate-input contract

The closed v1 set: `fit_outlook`, `fit_new_weakness`, `fit_duplicate`, `value_giving`,
`other_player_keep`, `roster_crunch`. Exact arithmetic per class is build-time work bound by
HLD §2.7 (mirror the live predicate shape via `ts`/`topt`); what THIS draft pins is the
degenerate-input behavior the HLD never enumerated — **every class must return one of:
scored `{severity, evidence}`, or `skipped: "not_applicable"` / `"format_gap"` — never raise,
never silently omit** (M4: absence impossible):

| Class | All-picks give side | All-picks receive side | Partner roster empty | K/DEF/IDP asset in package (G-026: prices 0.0) |
|---|---|---|---|---|
| `fit_outlook` | picks lean youth: lean computed over receive-side assets partner GETS; picks contribute rebuild-lean via pick_values ages n/a → pick lean constant | same | scored (outlook still inferable from picks share; roster [] ⇒ inferred "rebuilder" by vet/youth shares = 0 — acceptable, evidence shows the inputs) | scored; zero-priced assets excluded from lean weights (weight 0 = excluded); if ALL assets zero-priced → `not_applicable` |
| `fit_new_weakness` | no player leaves partner roster ⇒ `not_applicable` (a pick can't open a lineup hole) | n/a — evaluates what partner SENDS (their give = card receive side) | `not_applicable` (no lineup to break) | position outside `_POS_TIER_CUTS` (K/DEF/IDP) ⇒ that asset invisible to slot math; if the vacated slot IS such a position ⇒ `format_gap` |
| `fit_duplicate` | `not_applicable` (picks stack no position) | evaluates what partner RECEIVES = card give side; all-picks ⇒ `not_applicable` | `not_applicable` (nothing to duplicate against) | incoming K/IDP ⇒ `not_applicable` for that asset; mixed package uses priced players only |
| `value_giving` | scored — picks price via `pick_values` on both bases | scored | scored (board/consensus math is roster-free) | **hazard**: zero-priced assets make the partner's give side look free ⇒ margin inflates. Rule: any zero-`dynasty_value` PLAYER asset on either side ⇒ severity computed but `evidence.margin` flagged via envelope — in a non-envelope league (§4.5) the class stamps `format_gap` |
| `other_player_keep` | asset_preferences may pin pick ids? (verify at build: prefs store player ids today) — pick ids not in prefs ⇒ `not_applicable` | n/a (evaluates partner's GIVE side only) | still scored (prefs exist independent of roster; a pref for a player no longer rostered ⇒ no match ⇒ severity 0) | scored normally (prefs are id-matching, value-free) |
| `roster_crunch` | consolidation ask with picks incoming ⇒ no roster-spot pressure from picks (Sleeper picks occupy no roster slot — verify per-platform at build; MFL/ESPN differ) ⇒ count player assets only | same | `not_applicable` | slot math counts the asset (a K occupies a spot) but pile-up positions limited to `_POS_TIER_CUTS` keys; else `format_gap` |

Severity = per-class 0–1 from existing margins (D-4); `top` = argmax over scored entries above
their `breaker_floor_<class>`; ties broken by a **pinned class-priority order** (declared as a
module constant, part of `ver`) — the HLD never said what argmax does on a tie, and an
unpinned dict-order tie-break is a determinism bug waiting for a Python version bump.

### 4.4 Knob table (the closed list; five registrations each, same commit as consumer)

| Key | Default | Disable value | Consumer |
|---|---:|---:|---|
| `breaker_ms_budget` | 250.0 | 0 (skip evaluation → every card gets rung-3 marker; flag off is the real kill) | `stamp_breaker` |
| `breaker_budget_checkpoint_frac` | 0.6 | 1.0 (checkpoint never trips early) | pass-2 gate |
| `breaker_min_severity` | 0.55 | 1.1 | `compose_narration` |
| `breaker_narrate_fit_outlook` | 0.0 | 0.0 | `compose_narration` (per-class switch ×6 — one key per class) |
| `breaker_narrate_fit_new_weakness` / `_fit_duplicate` / `_value_giving` / `_other_player_keep` / `_roster_crunch` | 0.0 | 0.0 | same (D-6; `_value_giving` governs consensus basis only, D-7; `_other_player_keep` exists but is a dead switch in v1 — registered so the ladder is uniform, documented dark) |
| `breaker_floor_fit_outlook` … ×6 | per class (LLD-build; consensus `value_giving` floor materially higher, D-7) | 1.1 (class never tops) | top-selection |
| `breaker_max_repeat_frac` | 0.34 | 1.0 | repetition suppression |
| `breaker_outlook_haircut` | 0.7 | 1.0 (no haircut) | D-8 legacy-source discount |
| `breaker_degraded_share_max` | 0.05 | 1.0 | graduation readout only |
| `breaker_shadow` | 1.0 | 0.0 | shadow-run gate (operator decision 5; a knob not a flag so `set_knob` logging censors readout windows when it flips) |

Count: **17** (1+1+1+6+6+1+1+... recount at build; the knob-inventory guard pins by name).
Registration sites per fit precedent (`trade_service.py:895-916` discipline):
`trade_service._DEFAULT_CFG`, `database._MODEL_CONFIG_DEFAULTS`, `_PINNED_KNOBS` golden,
disposition sentence (this folder's scope-breaker.md), `docs/config-reference.md`.
Disposition sentence family: *"Breaker evaluation knob — read only by `backend/trade_breaker.py`
at the post-F9 stamp seam; no generator or reranker can observe it."*

### 4.5 Format envelope (enumerated, per HLD §3.5)

`format_ok` iff ALL of: Sleeper-platform league · `league.num_teams == 12` (the
`_POS_TIER_CUTS` assumption is 12-team and takes no size parameter — ledger row 9) · no
IDP/K/DEF starting slots in `roster_positions` beyond 1 K/1 DEF... **(build decision: standard
1-K/1-DEF lineups are IN envelope with those positions excluded from depth math; true IDP
leagues are OUT)** · scoring_format resolvable to a priced pool (superflex IS in envelope via
`_POS_TIER_CUTS_SF_QB`, `trade_service.py:2078`; TEP is in envelope — TE premium changes
values, not slot structure). Outside: depth classes (`fit_new_weakness`, `fit_duplicate`,
`roster_crunch`) stamp `skipped: "format_gap"`, narration-ineligible; `fit_outlook` and
`value_giving` additionally gap when the G-026 zero-value condition holds for package assets
(§4.3 table). `format_gap` share rides `BreakerReport`.

### 4.6 Budget ladder mechanics

Clock: `time.monotonic()` (never `time.time()` — wall-clock steps under NTP would make rung
transitions nondeterministic relative to load; monotonic is what the job timeout uses).
Checkpoint after pass 1: `elapsed > cfg[breaker_ms_budget] * cfg[breaker_budget_checkpoint_frac]`
⇒ pass 2 dropped whole, every card's two feasibility-tier entries get
`skipped: "budget"` (rung 2, deck-uniform). Mid-pass exhaustion (`elapsed > budget` checked
per card): remaining cards in THAT pass get the minimal rung-3 marker; already-scored cards
keep their stamps (labeled rank-correlated missingness — readouts exclude rung-3 decks). The
shadow run shares the same budget envelope (it is the same per-card cost ×2, HLD §5.4): shadow
evaluation runs interleaved per card AFTER the primary stamp, so exhaustion degrades shadow
first only if implemented as a second loop — **it is NOT**; interleaving keeps primary and
shadow coverage correlated, which R-3's proxy-population argument needs (uncorrelated shadow
missingness would bias the viewer-seat calibration cut).

---

## 5. Errors & Edge Cases (the normative table)

Every row is a contract; §7 maps each to a test. "Marker" = §3.1 minimal marker.

| # | Case | Contract |
|---|---|---|
| E-1 | Deck of 0 cards (F3 can empty one; `_log_deck_signal_impressions` early-returns at `:4060`) | `stamp_breaker`/`compose_narration` no-op; report `cards_seen=0`; no republish; no crash |
| E-2 | Partner absent from `{m.user_id: m}` members map (G-045 pool prune; orphan roster) | rung-1 for that partner's cards: `degraded: "partner_snapshot"`; other partners unaffected |
| E-3 | Partner roster empty / co-owned resolution (§3.4) | per-class column in §4.3; cache keyed by canonical owner |
| E-4 | All-picks give, all-picks receive, mixed | §4.3 per-class table; a card where EVERY class returns `not_applicable`/`format_gap` stamps rung 0 with `top: null` — that is a valid "no objection found" stamp, NOT a degradation |
| E-5 | K/DEF/IDP assets (G-026 zero-values) | §4.3 + §4.5; never silently compute on 0.0 prices |
| E-6 | League ≠ 12 teams; IDP formats; superflex; TEP | §4.5 envelope; superflex + TEP in, others gap depth classes |
| E-7 | `partner == viewer` (self-trade) | `degraded: "self_partner"` skip (§2.1) |
| E-8 | Hot flag reload mid-job (`POST /api/feature-flags/reload` between seam and impression block) | Flags read ONCE into locals at the seam (§2.3); impression copy attribute-gated (§2.4). Flip on→off mid-job: stamps land in features_json (correct — they existed at serve); payload gate re-reads nothing (narration already composed). Flip off→on: no stamp, no key, no crash |
| E-9 | Hot KNOB change mid-job (`PUT /api/admin/config`) | §4.1 snapshot: one job, one knob-state; `model_config_changes` timestamp censors the readout window (M1) |
| E-10 | `_cfg_override` overlay / bake-off arm profile | Inactive at the seam (verified); snapshot makes it moot; sabotage test T-6 pins module-import binding |
| E-11 | Stud-tax thread-local unpinned at seam | Explicit `stud_tax_override("market")` around breaker valuations (§4.1.3) |
| E-12 | Two concurrent jobs, same league, different viewers | No shared mutable state: `PartnerContext` cache is per-call (local dict); `ts._c` reads are snapshot-per-job; report is per-call. Nothing to lock |
| E-13 | Superseded jobs (`force_supersedes_running`) | Seam skips stamping (`_job_superseded` check, §2.3.3); benign race documented; superseded jobs already skip the signal block (`:6093`) so no unstamped impressions are possible; publishes blocked by `_job_live` everywhere |
| E-14 | Exception inside ONE class's predicate | Per-CLASS try/except inside the per-card loop: that class gets `skipped: "not_applicable"` + a `predicate_error` count in the report; the CARD stays rung 0 with the other classes scored. (Whole-card rung-4 is reserved for failures outside any class — per-card context assembly.) Rationale: one flaky predicate must not zero the coverage metric for all six classes |
| E-15 | Exception inside `compose_narration` after stamps landed | Caught inside `compose_narration` per card: that card gets `narrated: null, suppressed: "template_error"`; stamps untouched; count in report. `hesitation_line` itself returns None on any internal error (§2.2) |
| E-16 | Exception in the outer server block (incl. the import line) | Server-local `_stamp_breaker_outer_marker` — no breaker-module dependency (§2.3.4) |
| E-17 | Budget exhausted exactly at the checkpoint | `>` comparison (not `>=`): exactly-at-budget runs pass 2. Pinned so the boundary is testable, not so it matters |
| E-18 | Snapshot republish under every flag combination | §2.3: narrated>0 ⇒ breaker republish (works with `deck.signal_v2` OFF and streaming either state); signal_v2 ON ⇒ `:6115` re-serialization preserves the sentence and adds iids; superseded ⇒ `_job_live` blocks; demo ⇒ seam skipped |
| E-19 | `imp_by_card` falsy with narration on (impressions insert failed) | Sentence already published by the breaker republish; measurement lost for that deck (existing failure class), exposure NOT lost — exposure-without-impression decks are identifiable by job diagnostics, and the A/B readout excludes them (they have no outcome rows to join anyway) |
| E-20 | Likes-you-injected cards | Present at the seam (injected `:5747`, before F9) — stamped like any card; `them` null (no fit_diag, HLD D-3); no special path |
| E-21 | Ghost rows (robustness only — ruling says none exist) | The impression loop iterates ghost entries (`:4120-4122`); attribute-gated copy stamps them uniformly; every breaker readout filters `is_ghost = 0` regardless (belt under the ruling's braces) |
| E-22 | Multi-format sessions (`sess["trade_svcs"]`, `:5438-5440`) | The job's `active_format` is the ONLY format the breaker sees: `scoring_format=active_format` into `analyze_roster_strengths`, `seed_map` is already per-format. The per-format TradeService INSTANCE is irrelevant — the breaker uses module-level `ts` helpers + explicit args, never instance state. Format flips between jobs produce per-job-consistent stamps keyed by the format their deck served under |
| E-23 | Unranked partner (no `member.elo_ratings`) | `board: None`, `board_auth: "consensus"`, `value_giving` basis consensus — the 84.5% normal case, rung 0 |
| E-24 | Clone/bulk-seeded board (F-3) | divergence-count heuristic vs `seed_elo`; `board_auth: "board_suspect"`; severity confidence discount; threshold is a module constant under `ver`, not a knob (calibration must not chase a moving authenticity definition) |

---

## 6. Compat & Migration

- **Zero migrations — verified.** No `Table()` additions, no `migration_cols` rows, no new
  columns. `features_json` and payload changes are JSON-internal. `breaker_` prefix reserved
  and unused. Rollback = HLD §5.3 ladder; revert commit needs no data work.
- **Flag-off byte identity, proof obligations:** (a) `trade.breaker` off ⇒ module absent from
  `sys.modules` (T-1), no `breaker` key in any `features_json` (T-2), no payload key, no
  publish-count change (the breaker republish is inside the flag guard); (b) flag ON,
  narrative OFF ⇒ deck order/composition byte-identical (T-4), payload byte-identical
  (narration-gated serializer), publish stream byte-identical (`_n_narrated == 0` ⇒ no
  republish); (c) knobs at disable values with flags on ⇒ stamps exist but rung/skip-labeled,
  nothing narrated.
- **Older mobile builds:** additive unknown key, ignored (ledger row 12). No minimum-version
  gate needed. Web/extension: never read the key in v1.
- **`BREAKER_VERSION` bump vs historical rows:** stamped rows are immutable serve-time facts —
  never re-stamped, never backfilled. Readouts filter `ver` (calibration) and (`ver`,
  `tmpl_ver`) (narration A/B) and refuse cross-version pools (fit M2 precedent). A bump
  mid-dark-window simply starts a new calibration cohort; the preregistered readout spec (D-6)
  must state the cohort's `ver` before `trade.breaker` lights.
- **api-reference contract:** one row — `trade_card_to_dict` response gains optional
  `breaker: {code, severity, sentence}`, present only when narrated (never during the dark
  window); `features_json.breaker`/`breaker_shadow` documented in the data-dictionary's
  deck_impressions entry.

---

## 7. Testing

### 7.1 Fixture realism — the #366 lesson, made a precondition

`_POS_TIER_MIN_POOL = 40` (`trade_service.py:2086`): below 40 ranked players at a position,
`analyze_roster_strengths` silently falls back to absolute cuts (`tier_basis` reports it).
Engine fixtures are smaller than that — **a green depth-class test on a small fixture proves
the fallback mode, not production behavior.** Therefore: `backend/tests/fixtures/` gains (or
reuses the fit W0 replay board for) a **breaker league fixture** with ≥40 priced players per
`_POS_TIER_CUTS` position (QB/RB/WR/TE), 12 teams, one superflex variant, one 14-team variant
(envelope-out), one co-owned roster, one unboarded partner, one clone board (seed-copied), one
partner with a K/DEF-carrying roster. Every per-class predicate test asserts
`tier_basis == "positional"` in its preconditions — a fixture shrink that flips the mode fails
loudly instead of testing the wrong bands.

### 7.2 Test list (`backend/tests/test_trade_breaker.py` + extensions)

| # | Test | Pins |
|---|---|---|
| T-1 | `test_flag_off_never_imports_breaker` | NFR-3; `test_organic_never_imports_fit` shape (`test_trade_gen_fit.py:883` precedent) |
| T-2 | `test_flag_off_features_json_byte_identical` | no `breaker` key, rows byte-equal |
| T-3 | `test_vocabulary_closure` | every emitted code ∈ 9 anchor codes + `roster_crunch`; NO `producer=negmem` code; **evidence keys ⊆ §3.2 enums per code** |
| T-4 | `test_breaker_inert_both_draft_paths` | delete `card.breaker` from every card ⇒ served output identical (`test_fit_diag_inert` pattern, `:681`); parametrized `group_size ∈ {0, N}` + organic |
| T-5 | `test_determinism` | two runs, same inputs ⇒ byte-equal stamps (incl. rounding rules §3.3) |
| T-6 | `test_breaker_binding_sabotage` | monkeypatch a `ts` knob → next stamp_breaker verdict moves (T1 discipline + §4.1 snapshot boundary) |
| T-7 | `test_per_class_predicates` | §4.3 table, one parametrized case per cell incl. all-picks × each class, empty roster, K/DEF |
| T-8 | `test_degradation_ladder` | each rung constructible; rung-2 deck-uniform (no card has partial pass-2); markers exactly 3 keys; E-17 boundary |
| T-9 | `test_impressions_uniform_keys_flag_on` | extends `test_impressions_uniform_columns` (`test_bakeoff_serving.py:1170`): every row of a flag-on deck carries `breaker` (scored or marker) — the invariant §2.4 moved out of runtime |
| T-10 | `test_midjob_flag_flip_no_crash` | flip flag between stamp and log (monkeypatch FLAGS) ⇒ impressions still written, key presence matches stamp-site state (E-8 — the row that would have failed the HLD §3.3 sketch) |
| T-11 | `test_per_class_exception_contained` | sabotage one predicate to raise ⇒ other 5 classes scored, card rung 0, `predicate_error` counted (E-14) |
| T-12 | `test_payload_gating` | dark window ⇒ no `breaker` key; narrated ⇒ exactly `{code,severity,sentence}`; `narrated ⇒ top non-null`; `test_breaker_shadow_never_serialized` |
| T-13 | `test_republish_matrix` | parametrize (`deck.signal_v2` × narrated>0 × superseded): sentence present in final `j["cards"]` iff narrated ∧ live; dark decks add zero publishes (E-18) — **this is the test the HLD's deferred republish question resolves into** |
| T-14 | `test_narrative_honesty_and_whitelist` | sentence names only §3.2-enum-resolvable facts; board-basis `value_giving` and `other_player_keep` never narrate under any switch state; snapshot suite pins templates + `tmpl_ver` |
| T-15 | `test_cross_seat_coherence` + `test_opponent_frame_characterization` | HLD §2.4/§2.7: mirrored fixture card, high partner-seat severity ⟺ viewer-seat gate flags the mirror; `_opponent_frame` (±0.05 thresholds, `trade_narrative.py:97/:99`) cannot assert the opposite window fact from the same outlook value; asserts both writers consume one value or fails |
| T-16 | `test_stamp_size_budget` | worst-case stamp < 4 KB serialized (§3.3) |
| T-17 | `test_repetition_suppression` | > `breaker_max_repeat_frac` same (partner, code) ⇒ top-severity card only, rest `suppressed: "repetition"` |
| T-18 | `test_co_owner_context_single_cache_entry` | two aliases, one PartnerContext; union prefs; board_src |
| T-19 | `test_format_envelope` | 14-team / IDP fixtures ⇒ depth classes `format_gap`, narration-ineligible; superflex scored via SF cuts |
| T-20 | `test_knob_inventory` | all §4.4 keys × five registrations, by name |
| T-21 | grep-guard (D-11) | no module outside `server.py` seam sites reads `card.breaker` |
| T-22 | `test_empty_deck_noop` (E-1), `test_self_partner_marker` (E-7), `test_superseded_job_no_stamp_no_rows` (E-13) | |

Structural: `mobile/tests/check-breaker-card.js` (§2.6) + `testid-lint`. Code-walk proof at
build re-cites §0's ledger. Manual TestFlight checklist (PRD) before `trade.breaker_narrative`
lights.

### 7.3 HLD invariants NOT mechanically testable as stated — and the fix

1. **NFR-1 "byte-identical deck order and composition"** — order is testable (T-4), but
   "byte-identity" of the *publish stream* was unstated; T-13 pins publish-count and
   snapshot-content equality for dark decks.
2. **NFR-6 "coverage ≥99%"** — a production metric, not a test; the testable surrogate is T-9
   (absence impossible per deck) + the readout SQL committed in the preregistered spec, which
   this LLD requires as a `scripts/`-style artifact (fit `bakeoff_readout.sql` precedent) so
   the graduation query is code-reviewed, not composed ad hoc at readout time.
3. **§2.7 "same predicate shape, seat-swapped"** — "shape" is not mechanically checkable; the
   testable form is T-15's biconditional on a mirrored fixture plus T-6's binding sabotage
   (knob moves ⇒ both seats move together).
4. **D-8 "narration margin bar higher than stamp bar"** — two knobs can be set to violate it;
   add a startup/`set_knob` refusal? No — knobs are floats with no cross-key validation
   machinery; instead T-14 pins the *shipped defaults* respect the ordering and the readout
   spec asserts it at readout time. Flagged as a residual (an operator can mis-set knobs; the
   ladder's answer is `model_config_changes` attribution, not prevention).

---

## 8. Open Questions (for cross-review; none blocks the scaffold)

1. **Stud-tax mode for breaker valuations** (§4.1.3): consensus `'market'` chosen for
   determinism and seat-symmetry; the partner's-own-mode alternative deserves an argument.
2. **Demo-league skip** (§2.3.3): this draft skips `league_demo` entirely (matching F3/
   likes-you/impressions); if the operator wants the hesitation line demonstrable in the demo
   deck, the skip moves to the impression copy only — one-line change, decide at PRD.
3. **`load_asset_preferences_bulk` / `load_league_preferences_bulk`** (§4.2): two new
   `database.py` readers — confirm siblings aren't adding equivalents (negmem reads prefs too?
   taxonomy of shared readers belongs to whichever plan lands first).
4. **Pick ids in `asset_preferences`** (§4.3 `other_player_keep` row): verify at build whether
   prefs rows can reference pick assets; the table stores player ids today.
5. **Roster-spot semantics of incoming picks per platform** (§4.3 `roster_crunch`): Sleeper
   picks occupy no roster slot; MFL/ESPN league support is live — v1 envelope is
   Sleeper-only (§4.5), which moots it, but say so explicitly in the PRD.
6. **`breaker_narrate_other_player_keep` dead switch** (§4.4): registered-but-dark keeps the
   ladder uniform; a reviewer may prefer not registering it until D-6's register item 8 is
   answered. Either is defensible; pick one and write the disposition sentence accordingly.

---

*End of draft B. The republish contract (§2.3), the attribute-gated impression copy (§2.4),
the config/stud-tax snapshot (§4.1), the per-class degenerate-input table (§4.3), and the
fixture-realism precondition (§7.1) are the load-bearing deltas over the HLD's sketches —
each traces to a verified line in §0.*
