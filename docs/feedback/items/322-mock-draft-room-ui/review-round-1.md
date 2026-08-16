# G2 review — round 1 (critic)

> Critic pass over `prd.md` (R-1–R-16) + `scope.md`, 2026-08-16. Every claim
> below re-checked against `origin/main` @ `d3fe3ac` and against G3's plan
> (`../328-mock-draft-pick-assignment/plan.md`). Verdict: the PRD is
> substantially sound — ticker coverage, the `picks[].tier` null/absent
> contract, the gesture posture, and the sabotage set all hold up. Two
> blocking objections, both cheap to fix; six non-blocking.

## Author's three corrections — assessed

1. **`SCHEMA` not `MOCK_DRAFT_SCHEMA` — confirmed.** `SCHEMA = 1` at
   `backend/mock_draft_service.py:57`; `MOCK_DRAFT_SCHEMA` is the *mobile*
   constant (`mobile/src/api/mockDraft.ts:26`). PRD §2 states it correctly.
2. **`type.bodySm` = 13px — confirmed.** `chalkline.ts`: `bodySm` fontSize 13
   (:135–137), `label` fontSize 11 (:115–117). R-8's token usage is correct
   and nothing lands below the 11px floor.
3. **The `ranking_service` import — checked hardest, and it is sound.**
   - *Layering/cycle:* `ranking_service.py`'s import block is stdlib-only
     (`dataclasses`, `typing`, `datetime`, `pathlib`, `json`, `random` —
     :15–20; no `from . import` anywhere). It imports nothing from the
     backend package, so `mock_draft_service → ranking_service` cannot form
     a cycle, and the edge points the right way per `docs/architecture.md`'s
     module table (ranking_service is a leaf math module, :128).
   - *Board state:* `tier_for_elo` is a **`@classmethod`**
     (`ranking_service.py:1271–1272`), pure over `TIER_CONFIG` (loaded once
     at module import from the checked-in `tier_config.json`, :30–39) — no
     instance, no DB, no user-board state needed. It guards `elo is None`
     and returns `None` below the waivers floor, exactly as PRD §2's
     nullability row states.
   - *INV-10:* the only I/O is the config-file read at `ranking_service`
     import time — a module `server.py` already imports at boot, so no new
     import-time work in practice and zero platform egress ever.
     `mock_draft_service`'s own header claim (":43 — imports no HTTP client
     and performs no I/O of any kind") stays literally true. See NB-5.

## BLOCKING

### B-1 — PRD §3's G2/G3 boundary is factually wrong against G3's actual plan

PRD §3 claims "G3's pick-ownership work lives in the settings/ownership
resolution functions … G2 touches ONLY `state_payload()` … the functions are
disjoint." G3's plan (`328-mock-draft-pick-assignment/plan.md` §4, §7) says
otherwise:

- **G3 edits `state_payload()` itself** — the `settings_echo.ownership_source`
  echo ("Echoed in `settings_echo.ownership_source`
  (`mock_draft_service.state_payload`, alongside `order_source`)", §4). The
  exact function §3 declares exclusively G2's appears in both touch lists —
  the thing the batch's disjointness rule exists to catch.
- **G3 also touches both of G2's mobile files:** `mobile/src/api/mockDraft.ts`
  (the `MockOwnershipSource` type) and `mobile/src/screens/MockDraftScreen.tsx`
  (the ownership disclosure caption) — G3 plan §7. G2's plan §5 "sole owner
  this wave" claim for the screen is therefore also stale.
- Shared as well: `backend/tests/test_mock_draft.py`, `docs/api-reference.md`
  (same payload block), `docs/cross-client-invariants.md`.

The edits are non-overlapping *regions* (G2: the pick-dict loop + import
block; G3: the `settings_echo` dict + `build_settings` param), so the merge
is mechanical — but the PRD may not ship asserting function-level
disjointness that doesn't exist. **Fix:** rewrite §3 to name the true
five-file overlap and the within-function split, and hand the orchestrator an
explicit Phase-2 serialization (either order works; the second lander rebases
`state_payload`, `mockDraft.ts`, `MockDraftScreen.tsx`, the test file, and
the two docs). The batch disjointness table needs the corrected rows.

### B-2 — T-S9 contradicts code the PRD leaves untouched (`sinceUserPick`)

T-S9 asserts "no `by ===` comparison in **any** my-team predicate" in the
screen. But `sinceUserPick` — which computes the `newest` value R-1 feeds
into `tickerWindow` — keys on `p.by === 'user'`
(`MockDraftScreen.tsx:410` @ d3fe3ac), and no requirement changes it. As
written the suite cannot go green: either the assertion flags this line, or
"my-team predicate" is left undefined and the test is unfalsifiable. Two
coherent resolutions; the PRD must pick one:

- **(a) Scope T-S9** to the tint/chip/sheet predicates and explicitly accept
  `sinceUserPick`'s `by` keying, with the manual-mode consequence stated: in
  manual mode every pick is `by: 'user'`, so `newest` is always 0 — header
  reads "Just picked", no rows tint. Defensible (the user was never away),
  but it must be *said*, and T-F8's expectation ("ticker 'mine' tint tracks
  the user's own team") should note that the *new-pick* tint is structurally
  absent in manual mode.
- **(b) Re-derive `sinceUserPick`** from `picked_by_user_id === userOwnerId`
  (the #305-consistent reading: "since your *team's* last pick"), which makes
  manual-mode turns taken for other teams count as "since your last pick" and
  is arguably the truer semantics — then extend T-U1/T-F8 to cover it. This
  is a small behavior change beyond the six items' literal text, so it needs
  the author to claim it deliberately (surgical-change principle), not
  inherit it from a test assertion.

Either answer is one paragraph; the current state (assertion vs. untouched
code) is the only unacceptable one.

## NON-BLOCKING

- **NB-1 — State basis-independence of `picks[].tier` explicitly.** §2
  computes tier from `ctx.consensus_elo` always; the payload is built
  per-`basis`, and a build agent could plausibly wire `board_elo` in for
  `basis=my_board`. Add one row: tier is consensus-based and
  **basis-independent**; accepted consequence — a row the user saw badged
  under My board (client walk over the user's board Elo, the room's #277
  path) may show a *different* tier on the chip after drafting. Deliberate,
  because chip tiers must be stable across basis toggles; say so.
- **NB-2 — R-1's no-sort rests on an unpinned ordering assumption.**
  "`picks[]` arrives in pick order" is true today by construction
  (`next_pick` walks slots sequentially), but nothing pins it. Either add a
  defensive `sort by pick_no` inside `tickerWindow` (pure, one line) or a
  T-P addition asserting `state_payload()` emits `picks[]` ascending by
  `pick_no`. Otherwise a future backend reorder silently breaks the window.
- **NB-3 — Make the filter+search composition a pure helper.** T-S6's
  "search applied to that subset" is fragile as an AST assertion over inline
  screen code. Put the composition in the helper T-U2 already tests (e.g.
  `filterPool(rows, position, query)`), and let T-S6 assert the screen's
  undrafted render source is that helper's output. Same tests, far sturdier.
- **NB-4 — Citation nit:** `tier_for_elo`'s def is at
  `ranking_service.py:1271–1272`; R-5 cites :1286 (mid-docstring). Harmless;
  fix in passing.
- **NB-5 — Module-header honesty:** when the build adds the import, extend
  `mock_draft_service.py`'s own header note (:43) the same way scope.md §4
  amends the architecture.md row — the claim stays true, but the header is
  where the next reader looks first.
- **NB-6 — R-8's `minHeight ≥ 44`:** 44pt is the touch-target rule and the
  chips are non-interactive. Fine to keep for vertical rhythm, but either say
  that's why or let content drive the height — as written it reads like a
  tap-target requirement on a non-tappable element.

## Confirmed sound (no objection)

- Ticker R-coverage: <8 picks (R-2, T-U1 0/3 cases), exactly 8 (T-U1),
  steady-state top-drop (R-3), highlight re-derivation incl. `newest = 0`
  and `newest > rows.length` (R-4, T-U1). Out-of-order manual picks are
  structurally impossible today (see NB-2 for the pin).
- `picks[].tier` contract: null-vs-absent split is explicit (§2), and the
  `my_picks` inheritance is stated *and* separately tested (T-P3 — correct,
  since a future `my_picks` rebuild could drop the key even though today the
  entries are the same dicts, :1413).
- Sabotages: each named sabotage breaks its own test and nothing subtler
  (T-P2's "default missing Elo to waivers" is exactly the fabrication class
  the null rule bans; T-U2's compose-over-full-pool sabotage makes the
  RB-filter/QB-name case return non-empty, which is the assertion).
- Gesture class: no new recognizers anywhere in the spec; T-S10 pins the
  absence of `PanResponder`/`react-native-gesture-handler`; the chip grid
  explicitly wraps instead of scrolling; the SectionList lives inside a
  Modal, not nested in the screen ScrollView. Consistent with the
  2026-07-12 lesson.
- Reset semantics: keyed on `on_the_clock?.pick_no`, which only advances via
  the user's own mutation response (CPU tail arrives in the same response),
  so no mid-interaction reset is observable; basis switches reuse the same
  `pick_no` and correctly do not reset. Completion (`on_the_clock → null`)
  fires one harmless reset.
- R-15 analytics: not reviewed per coordinator instruction (operator queue).
- scope.md: docs table rows check out (architecture amendment honest,
  LLD/HLD n/a justified, data-dictionary correctly untouched); D-056
  waivers are decision-backed, not agent-selected.

---

# ROUND 2: SIGNED OFF

All eight round-1 dispositions verified present in the round-2 `prd.md`/`scope.md`
text, not just claimed in the reconciliation log. B-1: §3 now carries the
file → region → owner table and the binding G3-first serialization; cross-checked
once more against G3's `prd.md` §4 — the two PRDs describe the **same boundary**
(constants block :67–68, `build_settings` :995, `state_payload`'s
`settings_echo` dict vs G2's pick loop :1373–:1400 + import block; the
`settings_echo` cite differs cosmetically — G2 ":1414 block", G3 ":1418" — the
dict actually opens at :1416 @ d3fe3ac; same region, immaterial). B-2: T-S9 is
scoped with `sinceUserPick` (:408–:413) explicitly excluded, R-4 states the
manual-mode consequence (`newest` always 0 ⇒ "Just picked", no new-pick tint),
T-F8 marks it expected, and the alternative is a named deferral in §4. NB-1
(§2 basis-independence row incl. the "must NOT wire `board_elo`" instruction),
NB-2 (defensive sort in R-1 + T-U1 shuffled case with the drop-the-sort
sabotage), NB-3 (`filterPool` in `mobile/src/utils/mockPool.ts`, R-11/R-13 +
T-U2 empty-query case + T-S6 render-source assertion), NB-4 (:1272
classmethod), NB-5 (header-note instruction in R-5), NB-6 (R-8 rhythm
rationale) — all incorporated as logged. **One NON-BLOCKING handoff note for
the orchestrator, not a G2 defect:** the reconciliation log's closing claim
that "both PRDs now state [the G3-first serialization] in the same terms" is
not quite true — G3's `prd.md` §4 still says "merge-order coordination is the
orchestrator's call" rather than recording the G3-first decision. G2's PRD
binds the agent that must act on the order (G2's builder branches after G3's
merge), so nothing breaks; but either stamp the decision into G3's §4 or
soften the log sentence so the record is consistent. With that noted, G2's
PRD + scope are build-ready.
