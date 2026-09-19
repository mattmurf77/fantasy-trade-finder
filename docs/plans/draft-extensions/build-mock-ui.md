# Build status — W2 mobile: mock draft UI (placement C)

**Date:** 2026-08-06 · **Wave:** draft-extensions W2 (mobile) · **Flag:** `draft.mock` (registered, **ships OFF** — not flipped)
**Scope owned:** `mobile/` only. No backend file was touched; the mock engine, its routes and the calibration work belong to the parallel agent.
**Design input:** `mockups/polish-lab-2026-08/mock-draft-placement.html` · **Plan:** `docs/plans/rookie-draft/mock-draft-plan.md` §4–9 · **Host:** `mobile/src/screens/DraftRoomScreen.tsx`

---

## 1. What was decided, and the obligation it created

The design pass recommended **option B** (a state-promoted card in the room) and argued explicitly **against option C** (a `Real draft | Mock` segmented control) on one serious ground:

> The Draft Room prints its own no-platform-writes guarantee — *"Picks are made on the platform — Fantasy Trade Finder never drafts for you"* (D9) — on itself. A mode switch above that sentence makes it ambiguous on the one screen where mistaking a simulation for the real draft costs a real draft pick.

**The operator chose C.** That choice is honoured here, and so is the objection. Mode-marking is therefore built as a structural property with a test behind it, not as styling:

| Obligation | How it is met | Where it is enforced |
|---|---|---|
| The mock surface is unmistakable **from any scroll position** | `MockRail` (flare wash + full-width flare bottom edge, label `MOCK DRAFT` + "not your league's real draft") renders **outside** the ScrollView on both surfaces — via the Draft Room `Shell`'s new pinned `header` prop, and above the ScrollView on `MockDraftScreen` | `check-mock-mode-marker.js`: rail is outside the ScrollView, and precedes it in document order |
| The marker renders in **every** mock sub-state | `MockDraftScreen` has exactly **ONE** top-level `return`, and the rail sits above the state branch — so loading, error, each typed-empty refusal, the live board, the confirm step and the recap all inherit it. There is no early return to escape through | `check-mock-mode-marker.js`: exactly one top-level return; rail is not inside any `?:` or `&&`; the six sub-state testIDs are enumerated |
| **Platform-adjacent affordances are absent in mock mode** | In Mock mode the room does not render the StatusBar/Refresh (they describe the *real* draft), the `draft-room.deep-link` CTA, or the "never drafts for you" note. `MockDraftScreen` never prints that sentence at all | `check-mock-mode-marker.js`: the deep-link + guarantee text live in the `mockMode ? … : …` **false** branch; the mock screen's *rendered* strings (JSX text + string literals, not comments) contain no "never drafts" |
| Flag off ⇒ nothing | `mockMode = mockOn && mode === 'mock'`; the toggle, the mock query and every mock branch are gated on it | `check-mock-mode-marker.js` asserts both the `useFlag('draft.mock')` read and the `mockMode = mockOn &&` derivation |

The test is **AST-based, not grep-based** (it parses the real TSX with the project's own TypeScript and walks the JSX tree), because a grep would pass on a rail that had been quietly moved inside a branch — the exact regression worth catching. Mutation-verified: moving the rail into `{state ? … : null}` fails the run.

Run: `node tests/check-mock-mode-marker.js` (or `npm run test:mock-mode-marker`, registered in `mobile/package.json`).

---

## 2. What shipped

### New files

| File | What |
|---|---|
| `mobile/src/api/mockDraft.ts` | The four `/api/mock-draft` routes; the two response shapes with an `isMockEmpty` branch; `MockEmptyReason` typed **open** per plan D10; `DraftSchemaError` reused from `draft.ts` |
| `mobile/src/components/draft/DraftRows.tsx` | The shared Draft-surface pieces: `draftRow` styles, `BasisChip`, `positionOf`, `slotLabel`, and the two fallback strings |
| `mobile/src/components/draft/MockChrome.tsx` | `MockRail` + `DraftModeToggle` |
| `mobile/src/components/draft/MockEntryPanel.tsx` | The Mock side of the room's switch, incl. every honest refusal; exports `MOCK_MIN_TEAMS` |
| `mobile/src/components/draft/MockSetupSheet.tsx` | The setup sheet (confirm, don't interrogate) |
| `mobile/src/screens/MockDraftScreen.tsx` | The session: on-the-clock card, pick ticker, your-picks chips, undrafted list, confirm bar, recap |
| `mobile/tests/check-mock-mode-marker.js` | The structural mode-marking test |

### Changed files

- `mobile/src/screens/DraftRoomScreen.tsx` — the segmented control + Mock mode; `Shell` gained a pinned `header` slot; `UndraftedRowView` is now **exported** and gained three mock-only optional props (`onPress`, `selected`, `actionLabel`) plus a `testID` override; the row/chip styles and copy moved to `DraftRows`.
- `mobile/src/navigation/RootNav.tsx` — `MockDraft` root-stack route, registered per the `FreeAgents` pattern **including** `headerBackVisible: false` + the custom `HeaderBack` control (#151 / RNS#3294), plus the route type.
- `mobile/package.json` — `test:mock-mode-marker` script.
- Registries: `mobile/src/api/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md` (component rows + a full testID tranche).

### Reused vs invented

**Reused verbatim** — `UndraftedRowView` (imported by the mock from the room, *not* copied), the `Consensus | My board` `BasisChip` pair and its fallback copy, the order-row styles, `PlayerContextMenu` + W1's `AnchorSheet` (still behind W1's own `draft.rank_inline` flag — the mock does not ship W1 behaviour unflagged), `TickLabel`, `Toast`, `Button`, `FeedbackFAB`, the `readErrorCopy` error vocabulary, the `FreeAgents` route registration incl. its iOS-26 back-control workaround, and the `staleTime`/no-refetch idiom.

**Invented** (named so it can be specced later) — `MockRail`, `DraftModeToggle`, `MockEntryPanel`, `MockSetupSheet`, `OnTheClockCard`, `PickTicker`, and the `MockPickConfirm` bar. The confirm is a **bar, not a menu**: one commitment with one alternative, and it exists because the CPU tail resolves instantly and v1 has no undo (plan O-M3 — restart is the escape hatch).

### Honest states

All four required states render **in the room**, never after a push into a dead end:

| State | Source of truth | Note |
|---|---|---|
| Bots not validated (`cpu_model_unvalidated`) — **today's real state** | POST response | Only reachable after the tap; see gap **G2** |
| Mock already running | `GET` returns an active row | Resume (`mock-entry.resume`) vs Start over — the latter is ONE `POST`, because create abandons the prior active row in the same transaction |
| No rookie class loaded | derived from the **board's** `class_not_loaded` notice | The room's "Show last year's class" toggle deliberately does **not** arm the card — the mock pool has no season override (**G7**) |
| League too small | client-side `MOCK_MIN_TEAMS = 6` | The engine has no floor (**G5**) |

Plus two refusals the design pass argued for as *correctness*, kept here even though placement C cannot hide the toggle: `live` (a mock started mid-draft can never catch up — pool snapshotted at creation, INV-10 forbids later platform reads) and `complete` (a drafted class is the rejected replay mode). And `startup_draft`, since mocks only cover rookie classes.

---

## 3. Where the backend contract did not support the designed UI

`docs/plans/draft-extensions/build-w2d.md` did **not exist** at build time, so this was coded against `backend/mock_draft_service.py` + the four routes in `backend/server.py` as they stand on this branch. The design pass's gap list (G1–G9) was re-verified against that source; **all nine still hold**. Client-side consequences:

| Gap | Still open? | What the client does about it |
|---|---|---|
| **G1** — create passes no `order`, `ownership` or `personas` | **Yes** (`server.py` calls `build_settings(ctx, owners=…, user_owner_id=…, rounds=…, draft_type=…, rng=…)` and nothing else) | Every mock is `order_source: "randomized"` even when the real order is assigned; **traded picks are ignored**; every CPU team is `{outlook:"not_sure", source:"default"}`. So the setup sheet's order notice shows almost always, the "from <manager>" provenance the design drew on `my_picks` chips will be absent, and the persona sub-line on the on-the-clock card will read `no clear lean` for every team. The UI is wired for all three and will light up the moment the create path is |
| **G2** — no capability probe (`class_not_loaded` / `cpu_model_unvalidated` are POST-only) | **Yes** | The refusal necessarily arrives *after* the user taps Start. Mitigated as far as the contract allows: `class_not_loaded` is pre-empted from the board's own notice, and the POST refusal is remembered in `postRefusal` so the card mutes without a second request. **A `can_create: {ok, reason}` block on GET would remove the one interaction the honest-state rule exists to prevent** |
| **G3** — `picks[]` carries no `consensus_rank`/`value` | **Yes** | **The recap's "+3 / −1 vs consensus" delta column is NOT rendered.** It cannot be computed — the drafted players are gone from `undrafted[]` before first render — and a fabricated delta is worse than none. This is the one place the built UI is smaller than the design, and it is a deliberate subtraction |
| **G4** — `on_the_clock` has no name or persona | **Yes** | Two client-side joins per render (`roster_id` → `order[]` for the username, → `settings_echo.personas` for the outlook). Works; slightly wasteful |
| **G5** — no `league_too_small` refusal | **Yes** | `MOCK_MIN_TEAMS = 6` is a magic number in `MockEntryPanel`. Delete it if the typed-empty vocabulary gains the reason |
| **G6** — board payload has no draft `type` | **Yes** | The setup sheet defaults to linear **and says so** in a hint line rather than implying it read the league |
| **G7** — no last-year path for the mock pool | **Yes** | Documented and enforced: the mock card ignores `showLastYear` |
| **G8** — `picked_at` always `null` | **Yes** | Nothing depends on it; no timeline was designed |
| **G9** — route's rounds default is a flat 4 | **Yes** | The client passes `rounds` from the board payload in the create body |

**One additional finding, not in the design pass's list:**

- **G10 — `settings_echo` does not echo `user_owner_id`.** The screen needs the session user's owner id to tint their own ticker/recap rows and to build the "Your picks" chips from `order[]`. It is recovered indirectly (`on_the_clock.is_user` on an active mock — `advance_cpu` always stops at the user's turn — else `my_picks[0].picked_by_user_id`). That holds for every state the engine can produce today, but it is inference, not contract: **echoing `user_owner_id` in `settings_echo` would make it a read.** One line.

**G11 — no analytics vocabulary for the mock.** `backend/analytics_taxonomy.py` is default-deny and registers no `mock_*` (or `draft_room_mode_switched`) event, and registering one is a backend edit this wave may not make. Rather than ship `track()` calls that read like live instrumentation and are dropped on ingest, **the mock surfaces fire no events at all**, with a comment at each site saying why. The natural set is `draft_room_mode_switched {mode}` · `mock_draft_started {league_id, rounds, type, order_source}` · `mock_draft_pick_made {pick_no, basis, valued}` · `mock_draft_completed {picks}` · `mock_draft_abandoned {pick_no}` — register those and the calls are a few lines. (The room's existing W1 events are untouched.)

**One place the build bent around a non-backend constraint:** `backend/tests/test_draft_extensions_w1.py` pins W1's kill switch (`if (!onMenu) {`) and its per-player testID literal to `DraftRoomScreen.tsx` **by source text**. The clean refactor was to move `UndraftedRowView` into `components/draft/DraftRows` with the rest; that would have failed two green tests this wave may not edit. The row therefore stays in `DraftRoomScreen.tsx`, exported, and the mock imports it — one row, one implementation, a slightly wrong address. If a later wave may touch that test, move the row and update the two assertions to point at `DraftRows`.

---

## 4. Gates

| Gate | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | **clean** (0 errors) |
| `python3 -m pytest backend/tests -q` | **1867 passed, 1 skipped** — the stated baseline, unchanged |
| `node tests/check-mock-mode-marker.js` | 28 checks pass; mutation-verified to fail when the rail moves into a branch |
| `node tests/check-session-rerank.js`, `node tests/check-feedback-badge.js` | pass (unchanged) |
| Files touched outside `mobile/` | none, apart from this status doc |

**Not covered:** no Maestro flow was added. `draft.mock` is OFF and `CPU_MODEL_VALIDATED` is `False`, so an end-to-end flow would today only be able to assert the muted `mock-entry.blocked.cpu_model_unvalidated` card — the ids it would need (`draft-room.mode.mock`, `mock-draft.rail`, `mock-draft.confirm.draft`) are registered and ready for one once the bots validate.

---

## 5. Suggested next steps (for whoever owns the backend next)

1. **G2** and **G1**, in that order — G2 makes the room's disabled states honest *before* a tap; G1 makes traded picks and personas real, which is what several rendered lines are currently waiting on.
2. **G3** — add `consensus_rank` to `state_payload()`'s `picks[]` and the recap's delta column can be un-subtracted with no layout change.
3. **G10** — echo `user_owner_id` in `settings_echo`.
4. Then a Maestro flow: Mock toggle → setup → three user picks → recap, with `mock-draft.rail` asserted on **every** frame.
