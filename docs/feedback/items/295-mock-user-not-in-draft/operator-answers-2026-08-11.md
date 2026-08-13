# #295/#296 — Operator answers to the scope block's open items, 2026-08-11

> Delivered by the `/feedback` orchestrator session that ran triage, not by the
> session that authored [`scope.md`](scope.md) / [`prd.md`](prd.md). Answers
> §7's O-1…O-4 and the two waivers. **One answer disputes a factual premise —
> read O-1 before building.**

---

## Waivers — both ACCEPTED

- **§1 Analytics — waiver accepted**, on the stated condition: the mock event
  family (`mock_started` / `mock_pick_made` / `mock_completed` /
  `mock_abandoned` / `mock_create_refused`) is **spun out as its own item**,
  not folded in. That work has been handed to a separate session and is
  already in flight. Do not add `track()` calls to this fix.
- **§3 Maestro — partial waiver accepted** via O-3 below.

## O-1 — DISPUTED. The premise is wrong; re-verify before designing around it.

The scope block states ffv3's roster 6 carries `owner_id: null`, making the
post-fix mock an **11-team draft in a 12-roster league**, and recommends
leaving it at 11.

**The operator says the league has 12 owners.** They are the league's member
and the reporter; treat this as authoritative over the analysis.

Corroborating evidence — there are **two ffv3 league rows**, and they disagree:

| `sleeper_league_id` | opponents stored | + caller | = members |
|---|---|---|---|
| `1312140920132497408` | 10 | 1 | **11** |
| `1181674778942836736` | 11 | 1 | **12** |

The 12-member row includes a manager (`smozhgani`) absent from the 11-member
row. **A plausible reading is that the ownerless-roster finding was measured
against the wrong league row.** Before the "leave it at 11" recommendation is
implemented or disclosed to the user via `order_source: "randomized"`:

1. Re-resolve which ffv3 id the fix's repro actually used.
2. Re-check `owner_id` on the **live Sleeper API** rosters array for that id,
   not against a stored snapshot.
3. If 12 owners resolve, the O-1 recommendation and its disclosure copy are
   both moot and should be deleted rather than softened.

## O-2 — Accept the analytics waiver

**Accepted** ("asked and answered"). See the waivers section above.

## O-3 — Sim-gate deviation

**Accepted — skip the sim.** The operator's explicit call, made after being
shown the uncomfortable framing (that this would be the second consecutive
batch on this feature to ship without a simulator run, and that the first one
is why the bug exists). Record it as an operator decision in the scope block's
§5 and in `TEST_LEDGER.md`, with the deviation named rather than implied.

## O-4 — The `docs/api-reference.md` edits: PARTIALLY APPLIED, by the orchestrator

Operator ruling: "let's pick it up here." Applied on branch
**`docs-api-reference-mock-status` @ `8c7b807`**, cut from `origin/main`.

- **Edit (1) — `:426` blockquote: APPLIED.** It read *"the CPU-bot mock is
  CUT"* with `CPU_MODEL_VALIDATED` `False`; the constant has been `True` since
  `6caca35` (`mock_draft_service.py:300`). Replaced with the true-today status
  (LIVE by operator override, statistical verdict still FAILED and pinned by
  `test_w2_16_calibration_gate`).
- **Edits (2) and (3) — `:441` four-rung ladder, `:448` `user_not_in_draft`
  reason: DELIBERATELY NOT APPLIED.** Both describe **post-fix** behaviour.
  Applying them before the fix ships would replace stale-in-one-direction drift
  with stale-in-the-other, in the same document, for the same reason. **They
  belong in the fix's own commit** — please carry them.
- The proposed replacement text in `prd.md` §6 R10 also contains a
  *"**Fixed 2026-08-10 (#295/#296)**"* clause. That was **omitted** for the
  same reason; restore it when the fix lands.
