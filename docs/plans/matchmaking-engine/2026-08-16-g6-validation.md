# G6 presentment-rules spec vs matchmaking-engine phase 1 — validation verdict

> Requested 2026-08-16 by the feedback-wave orchestrator session (G6 = items #304 #336 #339
> #340 #341, spec at `docs/feedback/items/304-positional-need-filter/` on
> `feedback-2026-08-16-specs` @ `997f0db`). Reviewed against this session's shipped work:
> `suggestion.telemetry` + `trade_gen.v2` (both dark), research corpus
> (`docs/research/matchmaking/`), presentation mockup. Claims below are code-verified against
> the merged ship branch, not memory.

## Loud items first (surface before the G6 build merges)

1. **Rebase before building — main has moved past G6's fork.** G6 branched off `2c67ea0`;
   main now carries the dynasty_nerds flag graduation (`d6de017`) **plus this session's two
   squash merges** (suggestion.telemetry, trade_gen.v2). G6's build touches
   `trade_service.py` `_DEFAULT_CFG` (7 knobs), `server.py`, `config/features.json`, and the
   flag fixtures — all four now carry new content from this ship. Expect adjacent-insertion
   conflicts in `_DEFAULT_CFG`'s tail (telemetry block + gen2 block now live there) and
   keep-both resolutions in the three flag-parity fixtures (which now include
   `suggestion.telemetry` and `trade_gen.v2`). All trivial, but a build agent that doesn't
   rebase first will produce a broken auto-merge.
2. **Tripwire math interaction (spec-level, one line to add):** G6's empty-deck bound
   (worst-case 4.6% vs the 5% bar) and the `served + Σkills > 15` tripwire were measured on
   the D-055 corpus **without ghost withholding**. When `suggestion.telemetry` lights, a
   deterministic ~1-in-10 of organic guided-deck cards are withheld at serve (logged
   `is_ghost=1`, never rendered; likes-you/wildcard/retest/pinned exempt —
   `server.py:3629`). Ghost-withheld cards are neither served nor rule-killed, so: (a) the
   tripwire should count ghosts on the served side (or exclude them from the audit), and
   (b) the empty-deck worst case shifts by ~the ghost rate. Recommend the G6 spec state
   which count feeds the tripwire. No change needed if G6 computes on post-ghost served
   cards — but say so explicitly.
3. **Scope boundary line the G6 spec should carry:** presentment rules apply to the **v1
   construction path**. `trade_gen.v2` (dark, separate module `backend/trade_gen_v2.py`,
   checked before the v1 branch in `_generate_trades_impl`) carries its own gate stack
   (dual-board ε on consolidation-discounted packages, ±15% consensus band, composition
   hygiene). Whether presentment rules ALSO run on gen-v2 output is a reconciliation
   decision owed at gen-v2 lighting — not implicitly inherited. Recommend one sentence in
   the G6 spec: "Applies to v1 deck construction; trade_gen.v2 reconciliation deferred to
   its lighting checklist."

## Conflict check (the three things the operator flagged)

- **Filters/reorders likes-you or incoming offers:** none. Ghost withholding explicitly
  exempts likes-you/wildcard/fatigue-retest at the serve gate; gen-v2 doesn't touch the
  likes-you injector. Consistent with G6's "likes-you gets #336 dedup only."
- **Client-passable targeting/bypass state:** none. Everything shipped is backend-only;
  gen-v2's `max_per_opponent` is a server-side caller parameter; tier metadata is
  presentation data, not bypass state. Consistent with G6's server-side bypass derivation.
- **Reorder-instead-of-filter at presentment:** no conflict, one nuance worth recording.
  Gen-v2's exposure cap demotes cap-overflow cards below the list head instead of dropping
  them — but this ordering applies only to cards that already **passed every hard gate**
  (quality violations are killed, not buried, same as G6's stance). The demotion exists
  because of the operator's uncapped-list decision (2026-08-16): full ranked survivor set,
  scarcity only at the endorsement tier. G6's filter-not-reorder principle and gen-v2's
  head-shaping are compatible: filter on rule violations, order among survivors.

## Overlap map

| G6 rule | This session's equivalent | Verdict |
|---|---|---|
| #340 max-overpay ceiling | gen-v2 dual-board ε + ±15% band (its own pipeline) | Parallel, not superseded either way — G6 patches v1 now; gen-v2 self-gates. Reconcile at gen-v2 lighting. |
| #341 net ±1 player/position | gen-v2 composition-hygiene + roster feasibility | Same intent; G6's exact net-rule is worth porting into gen-v2's hygiene gate later (S). |
| #339 pick-not-the-gap band | gen-v2 consolidation discount + MESO pick variants | Check at gen-v2 lighting that the pick-heavy MESO variant passes #339's two-sided band; the discount likely subsumes it but is not the same test. |
| #304 positional-need gate | gen-v2 divergence + marginal-lineup valuation | #304 is v1-only patching; gen-v2 makes it redundant-by-construction on its own output. |
| #336 windowless already-matched exclusion | gen-v2 consumes `past_decision_keys` | **Synergy:** G6's windowless loader fix automatically benefits gen-v2 (same kwarg). One future caveat: the round-3 counter-offer research (decline→revise→re-offer, `round-3/01`) will need an explicit carve-out policy so windowless exclusion of matched/awaiting never grows to cover *declined* — declines must stay re-approachable with a modified package. |

## Additional-work list

| Item | Tag | Reason |
|---|---|---|
| Light `suggestion.telemetry` | build-now (independent) | Only collects; no G6 interaction except tripwire note above. |
| G6 spec: tripwire/ghost counting sentence | build-now (G6-side, pre-merge) | One line; avoids a silent measurement drift later. |
| G6 spec: v1-scope sentence | build-now (G6-side, pre-merge) | One line; prevents implicit inheritance onto gen-v2. |
| Light `trade_gen.v2` | after-G6-ships | Wants telemetry accept-stats anyway; reconciliation decision (which G6 rules also run on gen-v2 output) belongs on its lighting checklist. |
| Port #341's net-rule into gen-v2 hygiene | after-G6-ships | Small; keeps the two pipelines' floors aligned. |
| Mobile pyramid UI (mockup → app) | build-now (parallel-safe) | Presents deck contents; orthogonal to which rules shaped them. Full gates, real Maestro flows. |
| Decline→re-offer loop (round-3/01 state machine) | after-G6-ships | Must be designed against #336's exclusion semantics; needs the carve-out noted above. |
| Drop-as-superseded | none | Nothing this session built is superseded by G6; nothing in G6 is superseded by this session. The two are complementary layers (G6 = guardrails on today's v1 decks; this session = measurement + the successor generator + presentation). |
