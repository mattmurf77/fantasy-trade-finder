# FB-328 — PRD: mock drafts use the league's real assigned/traded picks

> Author-round deliverable for group **G3** (2026-08-16 wave). Base
> `origin/main` @ `d3fe3ac`. Companions: [`plan.md`](plan.md),
> [`hld-delta.md`](hld-delta.md), [`lld-delta.md`](lld-delta.md),
> [`scope.md`](scope.md). QA regime: **D-056** (Maestro/simulator retired) —
> evidence is pytest + structural `check-*.js` + a written operator
> TestFlight checklist.

## 1. Problem

**#328 (mattmurf77, v1.13.3):** "Mock drafts aren't using the actual assigned
draft picks (for example in Newton I got all four picks to slot 8 rather than
my actual assigned/traded picks)." Newton is an **ESPN** league; the mock's
create path resolves real order/ownership for Sleeper only
(`backend/server.py:12110`) and falls back **silently** to slot-order
drafting for everything else. The user's real picks live in the manual
pick-assignment tool and were ignored.

## 2. Requirements

Every requirement maps to #328; each names ≥1 test from §6.

| ID | Requirement | Tests |
|---|---|---|
| R-1 | An ESPN league with a seeded, ordered assignment grid (`picks.assign` ON) gets its mock **order** from the grid's stored round-1 order (`order_source: "assigned"`) — never a shuffle. | T-1 |
| R-2 | Every user-asserted traded pick in that grid lands in the mock's ownership overlay: at the traded `(round, slot)` the **acquiring** team is on the clock, in cpu mode. `settings_echo.ownership_source == "user"`. | T-1 |
| R-3 | R-2 holds identically in **manual** mode: at the traded slot, `next_pick`/`on_the_clock` names the acquiring team with `is_user: true` ("picking for" chip). No mode-specific resolution code exists — both modes read one snapshot. | T-2 |
| R-4 | An MFL league with traded rows in the normalized `draft_picks` store gets an ownership overlay anchored to the **original owner's** slot in the (still randomized) order; `ownership_source == "platform"`, `order_source == "randomized"` — the order is never invented (KD-6). | T-3 |
| R-5 | For a fixed `rng_seed`, an MFL mock's resolved order is deterministic and equal to the pre-change internal shuffle's permutation (pre-shuffle recipe parity, lld §2.4). | T-3 |
| R-6 | Identity guard: an overlay row whose `original_user_id` or `owner_user_id` is not in the resolved order is dropped (logged, counted). Drop-**all** degrades `ownership_source` to `"none"`; a partial drop applies what matched and labels `"partial"`; a fully-matching row set must yield neither (two-sided). A dropped row never crashes and never misassigns. | T-4 |
| R-7 | Honest fallback, labeled: unseeded/unordered ESPN grid, `picks.assign` OFF, Fleaflicker/unknown platform, and empty MFL store all produce today's slot-order behavior with `ownership_source == "none"` — never an error, never a platform read. | T-5, T-6 |
| R-8 | A league whose ownership data was consulted, **covers every slot of the mock**, and contains zero traded picks labels `"platform"`/`"user"` (empty overlay is a fact, not a fallback). | T-9 |
| R-9 | Sleeper is byte-identical to 1.13.4 except the new label: existing W2d/G1 order/overlay tests pass unchanged; a resolved full-coverage Sleeper board labels `"platform"`. | T-7 |
| R-10 | Rows persisted before this change echo `settings_echo.ownership_source: null` — the key **present**, value `null` — and are otherwise byte-identical (T-305-05 style). The create request body, capability probe, `/pick`, `/abandon`, and all error shapes are unchanged. | T-8 |
| R-11 | The mobile mock screen renders one disclosure caption from `settings_echo.ownership_source` only — "Real pick ownership applied" (`platform`; `user` adds "· entered by your league") / "Some real pick ownership applied — other slots use draft order" (`partial`) / "Traded picks unavailable — each team drafts its own slot" (`none`) / nothing (`null` or unknown) — in both the active clock card and the recap card. | S-1 (structural), TF-1/TF-5 |
| R-12 | `mock_started` carries `ownership_source` read off the resolved `settings_echo`, and the taxonomy admits it. | T-10, S-2 |
| R-13 | ESPN mocks default their linear/snake `type` from the assignment grid's numbering (`body.type` still wins), so mock numbering matches the PickAssignment tool. | T-1 |
| R-14 | **Partial coverage is labeled, never silently full** (review OBJ-2): when ownership data is applied but does not cover every `(round, slot)` of the mock — a contested/orphaned ESPN slot at round ≥ 2, mock `rounds` deeper than the grid/board/store, or an identity-dropped row — `ownership_source == "partial"` and the applied rows still apply. Round-**1** holes drop the whole resolution to `"none"` (existing order rule); the asymmetry is deliberate and pinned. | T-12 |

## 3. Success criteria

1. The exact #328 repro is dead: in Newton (ESPN, picks assigned incl.
   trades), the operator's on-the-clock picks in a fresh auto mock match the
   assignment grid — not four picks at one slot (TF-2).
2. No silent fallback remains on any platform: every mock state payload
   discloses `ownership_source`, and the mobile screen renders it (R-7,
   R-11).
3. Zero regressions on Sleeper (R-9) and zero new platform egress anywhere on
   the create path (asserted in T-5's no-egress check).

## 4. Out of scope

- **G2's mock-draft room UI work (#322–#327).** G2 also touches
  `backend/mock_draft_service.py` and `mobile/src/screens/MockDraftScreen.tsx`
  — five shared files, one shared function, non-overlapping *regions* (G2
  PRD §3's boundary table is the authoritative mirror of this list). **G3
  touches exactly these regions in `mock_draft_service.py`: the module
  constants block (`ORDER_SOURCE_*`/new `OWNERSHIP_SOURCE_*`, `:67-68`),
  `build_settings` (`:995`), and `state_payload`'s `settings_echo` dict
  (`:1414` block).** G2 must not modify those three regions; G3 touches
  nothing else in that file. On `MockDraftScreen.tsx` G3 adds only the
  caption helper + two mounts (lld §4.2). **Serialization (decided,
  orchestrator, Phase-2 — binding on both build agents): G3 builds and
  merges to the group branch first; G2's build agent branches after G3's
  merge and rebases its regions on G3's edits.** G2's PRD §3 carries the
  same decision in the same terms.
- Fleaflicker pick ingestion (no data exists; honest `"none"` is the
  contract).
- Deriving an MFL slot **order** (KD-6; MFL has no sequence to read).
- Any change to the Draft Room board routes/payloads, the assignment tool, or
  `draft.mfl` board behavior.
- Relabeling/backfilling mocks persisted before this change (`null` = unknown).
- Reflecting mid-mock grid changes (ownership is snapshotted at create —
  existing invariant, `mock_draft_service.py:973-976`).

## 5. Guardrails

- **Bright line:** this changes an API payload contract — full gates, no
  express (plan §5.6).
- Zero platform egress on the new paths: ESPN reads the DB grid, MFL reads
  the DB store; neither path may construct a fetcher with `sleeper_get` or
  any MFL opener.
- Closed vocabulary server-side, open + nullable client-side (lld §1.2/§4.1).
- Resolution failures degrade to labeled fallback; they never 4xx/5xx and
  never block mock creation.
- No schema migration; no new flags; no new routes.

## 6. Test plan (D-056)

### 6.1 pytest — behavioral, each with a named sabotage

Location: `backend/tests/test_mock_draft.py` additions, or new
`backend/tests/test_mock_pick_ownership.py` if size warrants. Every test
below must be **proven to fail** under its named sabotage before the build
lands (2026-08-10 rule); the sabotage set:

- **SAB-A** — re-add the 1.13.4 early return `if platform != dbs.SLEEPER or
  not is_enabled("draft.room"): return out` at the top of `_mock_real_draft`.
- **SAB-B** — in `_mock_owned_pick_overlay`, skip the identity-guard filter
  (keep all traded rows).
- **SAB-C** — hardcode `ownership_source=OWNERSHIP_SOURCE_PLATFORM` in
  `build_settings`' returned dict. (Breaks tests expecting `"none"` — never
  name it for a test that *expects* `"platform"`.)
- **SAB-D** — in `_mock_owned_pick_overlay`, replace the anchoring
  `slot_of[str(r["original_user_id"])]` with the franchise-fid ordinal:
  `slot = int(str(r.get("original_roster_id") or "0").lstrip("0") or 0)`
  (slot-number keying — the exact wrong-anchor bug class; concrete per
  review OBJ-4 so two builders implement one sabotage).
- **SAB-E** — remove the `ownership_source` line from `state_payload`'s
  `settings_echo` (the key becomes *absent*, not `null`).
- **SAB-F** — hardcode `ownership_source=OWNERSHIP_SOURCE_NONE` in
  `build_settings`' returned dict (the mirror of SAB-C, for tests expecting
  a positive label).
- **SAB-G** — skip the coverage checks: in `_mock_real_draft` drop the
  `expected <= covered` test (always label the source value once the order
  resolves) and in `_mock_owned_pick_overlay` force `complete = True` and
  ignore `drops` in the label.
- **SAB-H** — in `_mock_real_draft`'s row-reading loop, treat a partial
  round-1 slot map as an order: replace the `set(by_slot) ==
  set(range(1, len(by_slot) + 1))` completeness check with `bool(by_slot)`
  (the "a partial slot map is not an order" rule deleted).

**Self-satisfaction audit (review OBJ-1):** the matrix below was re-audited
row-by-row after the T-7 remap. Rule applied: a sabotage may never *produce*
the value its test expects. Prior violations found and fixed: T-7 (expected
`"platform"`, was mapped to SAB-C which hardcodes `"platform"`) and T-9's
MFL half (same pattern); both now map to SAB-F. T-8 carries an explicit
key-**presence** assertion precisely so SAB-E (key absent) cannot satisfy
its `null` expectation via `.get()`.

| Test | Asserts | Proven-to-fail by |
|---|---|---|
| T-1 (R-1, R-2, R-13) | ESPN league, seeded full-coverage grid fixture (one round-2 traded pick): create returns order == stored round-1 order, `order_source == "assigned"`, acquiring team on the clock at the traded `(round, slot)` via `owner_of`, `settings_echo.ownership_source == "user"`, `settings_echo.type` == grid `order_type` | SAB-A (whole test), SAB-F (label half) |
| T-2 (R-3) | Same fixture, `mode: "manual"`: at the traded slot `on_the_clock` carries the acquiring team's id and `is_user: true` | SAB-A |
| T-3 (R-4, R-5) | MFL store rows (synthetic `mfl:<league>.f<fid>` ids, one traded): overlay lands at the original owner's shuffled slot; `ownership_source == "platform"`, `order_source == "randomized"`; same pinned `rng_seed` twice → identical order, equal to `random.Random(seed).shuffle` over `[str(o) for o in owners]`; two **distinct** pinned seeds → different orders (de-vacuous). **Precondition assertion (OBJ-4):** for the pinned seed, each traded row's correct shuffled slot ≠ its SAB-D franchise-ordinal slot — pinned in the fixture so a seed collision can never record a false green under SAB-D | SAB-D (anchoring — also proves the route's MFL block is live: SAB-A does NOT reach it, the block is in the create route), SAB-F (label half) |
| T-4 (R-6) | One traded row's `owner_user_id` outside the resolved order → row dropped, remaining rows applied, label `"partial"`; ALL rows unknown → `"none"` and empty overlay; fully-matching rows (full census) must yield `"platform"`, not `"partial"`/`"none"` | SAB-B |
| T-5 (R-7) | ESPN unseeded grid, and separately `picks.assign` OFF → create succeeds, slot-order drafting, `ownership_source == "none"`, no crash; fetch-spy asserts zero platform calls on the whole create | SAB-C |
| T-6 (R-7) | Fleaflicker/unknown platform → `"none"` (the labeled version of 1.13.4's behavior) | SAB-C |
| T-7 (R-9) | Existing W2d/G1 Sleeper order/overlay tests pass **unchanged**; a resolved full-coverage Sleeper board create labels `"platform"` | SAB-F (label half); the unchanged half is regression, not sabotage |
| T-8 (R-10) | A persisted pre-change `mock_drafts` row (settings JSON without the key): `GET` echoes `settings_echo` with the `ownership_source` **key present** and value `null` (assert `"ownership_source" in payload["settings_echo"]` AND `is None` — never `.get()` alone), payload otherwise byte-identical to a 1.13.4 golden; capability probe payload byte-identical | SAB-E |
| T-9 (R-8) | ESPN grid seeded+ordered, full coverage, zero trades → `"user"`, empty overlay; MFL store with a full-census season, none traded → `"platform"`, empty overlay | SAB-F |
| T-10 (R-12) | `analytics_taxonomy` admits `ownership_source` on `mock_started` (prop-set membership) | — (structural-in-pytest) |
| T-11 | Backend structural pin: `_mock_real_draft`'s ESPN branch and the board route both call `_assignment_grid` (source inspection) | — |
| T-12 (R-14) | Partial coverage labels `"partial"` with the applied rows still applied: (a) ESPN grid with a round-**2** contested slot (grid-excluded) → order intact, other traded rows applied, `"partial"`; (b) 4-round ESPN mock over a 3-round grid → `"partial"`; (c) MFL store shallower than mock `rounds` → `"partial"`; (d) asymmetry pin: a round-**1** contested/missing slot → `"none"` (whole resolution drops) | SAB-G ((a)–(c) — produces the source label where `"partial"` is expected); SAB-H ((d) — the deleted completeness rule makes (d) fail hard, via a wrong label or the order-build `KeyError` on the gapped slot map, never `"none"`; SAB-A/SAB-G also yield `"none"` here and are deliberately NOT named for (d)) |

### 6.2 Structural checks (client-visible ⇒ required)

- **S-1** NEW `mobile/tests/check-mock-ownership-caption.js` — caption reads
  only `settings_echo.ownership_source`; four known strings + render-nothing
  default; both mounts' testIDs present; `MockSettingsEcho.ownership_source`
  typed (lld §7).
- **S-2** extend `mobile/tests/check-mock-draft-modes.js` — `mock_started`
  resolved-echo props pin grows to include `ownership_source`.
- **S-3** `tsc` clean; `mobile/scripts/testid-lint.sh` passes.

### 6.3 Operator TestFlight checklist (the runtime net)

1. **Newton (ESPN) — assignment applied:** in PickAssignment, confirm (or
   set) the pick grid incl. at least one traded pick. Start an **auto** mock:
   the draft order matches the grid's round-1 order; your on-the-clock turns
   arrive at your assigned slots; at the traded slot the acquiring team picks;
   the clock card reads "Real pick ownership applied · entered by your
   league".
2. **Newton — the exact #328 repro:** with your real picks NOT all at one
   slot, verify you do NOT get all four picks at a single slot. Complete or
   end the mock; the recap card shows the same caption.
3. **Newton — manual mode:** repeat step 1 in manual mode; at the traded slot
   the "You're picking for <acquiring team>" chip names the acquirer.
4. **MFL league:** start a mock: at least one known traded pick lands with
   the acquiring team (relative to wherever its original owner drafted);
   caption reads "Real pick ownership applied"; order is disclosed as
   randomized (existing disclosure), and picks are NOT all at one slot for a
   team that traded one away.
5. **Sleeper (ffv3) regression:** a mock behaves exactly as on 1.13.4, plus
   the "Real pick ownership applied" caption.
6. **No-data league** (any league with no pick data, e.g. ESPN before
   seeding): mock still starts; caption reads "Traded picks unavailable —
   each team drafts its own slot"; an old in-flight/recap mock created on
   1.13.4 shows **no** caption.
7. **Partial coverage** (Newton works: set the assignment grid to 3 rounds,
   start a 4-round mock): rounds 1–3 follow the grid, round 4 drafts at slot
   order, caption reads "Some real pick ownership applied — other slots use
   draft order".

## 7. Rollback

No flag of its own (operator-reviewed in scope.md §2): rollback is a code
revert. The change is additive on the wire (nullable field) and additive in
persisted JSON, so reverting the server strands no client and corrupts no
row; mocks created while the fix was live keep their (correct) snapshotted
ownership.
