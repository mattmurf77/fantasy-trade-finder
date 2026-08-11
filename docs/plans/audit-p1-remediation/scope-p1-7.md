# Feature Scope — P1-7 · Pick Anchors unlock + label reconciliation (audit A-16)

<!--
Copied from docs/templates/feature-scope.md per CLAUDE.md § Feature gates.
Every section is answered or explicitly WAIVED with a reason. Silence is not a waiver.
Companion plan: docs/plans/audit-p1-remediation/plan-p1-7.md
-->

**Date:** 2026-08-11
**Entry point:** 2026-08-09 mobile UX audit — finding **A-16 / P1-7** (`04-priority-backlog.md` P1 table, `06-resolutions.md` row A-16)
**Builder:** planning agent, worktree `ftf-p1-remediation`, branch `p1-remediation-2026-08-11` (off `origin/main @ ab9368f`)
**Operator sign-off on waivers:** **required — 3 waivers + 7 checkpoints below are unanswered**

**Express lane:** **not declared.** No operator express declaration was made at flow start, so the full gates apply. Independently, this change alters an API value domain and a cross-client display vocabulary, which the root `CLAUDE.md` bright line excludes from "quick fix" anyway. An agent never self-selects express.

**Hard dependency:** **P0-1 merges to `main` before this builds.** P0-1 adds `set_ranking_method_if_unset` and writes `ranking_method = 'anchor'` from `/api/anchor/save` when `via == 'anchors'` (excluding `via == 'draft_room'`). That write is what routes users into the branch this item fixes — and, until this item lands, P0-1 *widens* the permanently-locked cohort. See plan §Design 2 and risk R1.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new event name is introduced, and none is removed or retyped.

  | Existing event | Where | Question it answers for this change |
  |---|---|---|
  | `anchor_answered` (`backend/server.py:7519-7531`, props `player_id`, `pick_value`, `skipped`, `via`) | fired by `POST /api/anchor/save`, both hosts | How many anchors a user has answered, and from which surface (`via: anchors` vs `draft_room`) — the behavioural series behind the new unlock rule. **Untouched by this change**, including `via`. |
  | `ranking_complete_first_time` (`backend/server.py:6228-6238`) | fired once on the first unlock transition per format | Whether the anchor cohort now reaches unlock at all — the acceptance metric. |

- [ ] **(a) New events specced:** none. Deliberate: the fix removes a wrong answer rather than adding a surface, and the server taxonomy is default-deny (`backend/analytics_taxonomy.py`), so adding a name would be work with no consumer.
- **Flagged, not waived — derived-series impact.** `ranking_complete_first_time` will begin firing for anchor-method users, and the `league_member_unlocked_trades` push fans out to their leaguemates on the same transition (`server.py:6241-6265`). Both are correct (those users genuinely became unlocked) but constitute a step change in a shipped series and a burst of notifications. **P0-1 raises the identical question as its Q5 for the Quick Set cohort — the two answers must match.** → plan checkpoint **C1**.
- **No new analytics dimension.** `ranking_method` is already a registered experiment-targeting attribute (`backend/experiments.py:59`); P0-1 owns that risk (its Q4). P1-7 does not change which users hold which method — only what `'anchor'` means at the unlock gate.
- → follow-through: no `docs/data-dictionary.md` change (nothing new stored); no taxonomy edit.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** The evidence store (`users.tier_overrides`, `backend/database.py:182-183`) and the method column (`users.ranking_method`, `:181`) both already exist and are unchanged in shape and semantics. No migration, no index, no type change. **No backfill either** — a legacy `'anchor'` user with zero anchors correctly stays locked until they anchor, so there is nothing to repair retroactively. → `docs/data-dictionary.md` **n/a**. *(P0-1 separately corrects the stale enum comment on `database.py:181`; do not duplicate that edit — re-diff first.)*
- **New/changed feature flags: none.** The Pick Anchor wizard is unflagged (reachable from the Rank Home chooser and the Rank tab action sheet with no gate). The second host, `AnchorSheet`, rides the existing `draft.rank_inline`, which is **`true`** in both `config/features.json:158` and `backend/tests/fixtures/flags/release.json:158`. No flag added, none re-defaulted, no `FLAG_KEYS` entry. **Explicit rationale for adding none:** per root `CLAUDE.md`, no bright line demands one here, and a flag over this fix would ship a knob whose OFF position is a known bug (the same argument P0-1 makes in its Q2). → `docs/config-reference.md` **n/a**.
- **New env vars / `model_config` keys: none.** `ANCHOR_UNLOCK_MIN = 40` ships as a Python class constant on `RankingService`, beside `POSITION_THRESHOLDS`. **If the operator wants a deploy-free tuning lever** (plan checkpoint **C2**), it becomes a `model_config` key and this row flips to a `docs/config-reference.md` update — decide before build, not after.
- **Ship-the-knob / rollback lever:** the honest lever is `git revert`. The backend change is ~15 lines in one function plus one new method; the mobile change is one derived constant and two fallback substitutions. Nothing is persisted that a revert would strand — `unlocked_formats` rows written during the window are monotonic by contract (`server.py:6191-6213`) and simply keep those users unlocked, which is the desired end state anyway.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/p1-7-anchor-labels.yaml` — signs in (`qa_standard`, `standard` profile, `release` flags), reaches the wizard via `rank.more-ways` → `rankmenu.more-toggle` → `rankmenu.anchors`, asserts all five changed rung labels **scoped to their new testIDs**, then taps `anchors.rung.no_value` and asserts the confirmation line reads the **same word** as the button. That round-trip is the fix; it fails pre-fix ("No value" vs FA).
- [x] **Extended flow:** `mobile/.maestro/capture/anchors.yaml` — no step edits needed (its anchors are label-independent: `".*in draft capital.*"` at `:175-178`, `".*Pull down to refresh.*"` at `:93-96`), but `screens/manifest.json:55` lists `mobile/src/utils/anchorRows.ts` as a freshness source for the `anchors` screen, so all three captures (`error`, `loading`, `question`) are re-taken and one header line is added recording that rungs now render `TIER_LABEL`-derived text.
- [x] **New flow, conditional:** `mobile/.maestro/flows/p1-7-anchor-unlock.yaml` — **gated on checkpoint C6** (the `anchors-done` seed profile). Depends on P0-1's `rank.unlocked-banner` testID (`RankScreen.tsx:686`).
- [ ] **WAIVED (1 of 3) — on-device proof of the unlock, if C6 is declined.** Reason: no seed profile can currently produce a `ranking_method='anchor'` user with a populated board. `app_user.anchors` is reserved in every profile JSON and implemented by nothing (`seed_ui_test_db.py` has no handler; verified by grep). Substitute proof if declined: pytest T-3/T-7/T-14/T-15/T-17 (which assert the raw `unlocked` boolean and the P0-1 composition directly) plus the manual pass in plan §Test plan 4. **Operator sign-off required.**
- [ ] **WAIVED (2 of 3) — the iOS push-permission dialog is not asserted.** Reason: it is a SpringBoard alert outside the app hierarchy and Maestro cannot assert it reliably; `usePushNotifications` also short-circuits when permission was already granted on the device. Same waiver P0-1 records. Proxy: `rank.unlocked-banner` ⇔ `progress.unlocked` ⇔ `pushEnabled` (`RootNav.tsx:266-267`).
- [ ] **WAIVED (3 of 3) — no web or extension test delta.** Reason: neither client has an anchor surface (`grep -rl "anchor/save|anchorRows|pick anchor" web/ extension/` → empty), and both already render `TIER_LABEL`, which is unchanged. Nothing to test.
- **`testID`s added/renamed:** `anchors.rung.<key>` × 8, added to the wizard's rung buttons (`PickAnchorScreen.tsx:344-353`, which have **no** testIDs today). Template-literal id, so it needs a `anchors.rung*` glob in `mobile/scripts/testid-lint-allow.txt` beside the existing `anchors.scope*` entry (`:44-45`), plus registration in `mobile/src/screens/CLAUDE.md`. Must pass `mobile/scripts/testid-lint.sh` (exit 0). **No id renamed or removed** — `AnchorSheet`'s existing `anchor-sheet.rung.${key}` (`AnchorSheet.tsx:128`) is key-based and therefore immune to the label change.
- **Capture delta:** `anchors` (all three states; the `question` capture is where the pixels move). Run `mobile/scripts/screen-capture.sh --screen anchors`, and `mobile/scripts/screen-freshness.sh` to confirm nothing else is flagged. Re-check whether any Draft Room capture photographs an open `AnchorSheet` at build time — none was found, but `draft.rank_inline` is on, so re-verify rather than assume.
- **Smoke-suite impact:** crossing surfaces are `flows/smoke/04-tiers.yaml` (tier labels — same constant, unchanged), `09-league.yaml` (the progress ring), `06-trades-deck.yaml` (unlock-gated deck), and any Draft Room flow that can open the anchor sheet. Expected green and unchanged: **no smoke profile has `ranking_method='anchor'`**, so no smoke path enters the new branch. Verify, do not assume.
- **Backend: pytest files added/updated:**
  - `backend/tests/test_anchor_unlock.py` **(new)** — 17 cases: the unlock rule (T-1…T-7), no-leak-into-other-branches (T-8…T-13), P0-1 composition including the `draft_room` anti-double-count (T-14…T-16), and the durability test that is the executable form of the Option-2 rejection (T-17).
  - `backend/tests/test_pick_anchor.py` **(extended)** — one case pinning that `/api/anchor/save` still writes **no** `tiers_saved` entry and **no** rank swipe (T-18), i.e. the anchor lane stays the anchor lane (`docs/cross-client-invariants.md:344`).
  - `mobile/tests/check-anchor-labels.js` **(new)** — AST structural check in the style of `check-member-entered-marker.js`: fails if any rung label is a string literal or if `ANCHOR_TIER` does not cover every `AnchorKey`. **This is what makes the fix permanent** rather than a one-time patch.
  - Must stay green: `test_tier_occupancy.py` (incl. `test_anchor_rungs_land_in_matching_tiers`), `test_draft_extensions_w1.py`, `test_seed_ui_test_db.py`, `test_test_users.py`, `test_trio_cross_position.py`, `test_rookie_scope.py`, and P0-1's `test_ranking_method_point_of_use.py`.
  - `cd mobile && npx tsc --noEmit` clean.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **Updated** | `GET /api/rankings/progress` — document the new `'anchor'` unlock rule (≥ `ANCHOR_UNLOCK_MIN` board overrides in the active format, OR the tiers rule) and the additive `anchor_count` / `anchor_required` keys **if checkpoint C5 is approved**. No route added, renamed or removed; no request field changes. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **Updated** | Two conventions shift: (1) unlock rules are per-method and now include an **evidence-count** rule keyed on `users.tier_overrides` rather than on the trio interaction counter; (2) display labels for a shared vocabulary are **derived from one constant** and enforced by a structural test. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No module wiring or data-flow change — same routes, same services, same store, same client→server sequence. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No new module, client or major flow. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **Updated — the load-bearing row** | (a) **§Pick anchor keys button-label table (`:329-339`)**: five labels change (`4 1sts`→`4+ 1sts`, `1 2nd`→`2nd`, `1 3rd`→`3rd`, `1 4th`→`4th`, `No value`→`FA`) plus a sentence stating labels are **derived** from `TIER_LABEL` via `ANCHOR_TIER` (`mobile/src/utils/anchorRows.ts`) and must never be authored independently. (b) **§"Tier labels ARE pick terms" (`:358`)**: today it asserts every anchor answer lands in "the tier that carries its name" while `:331` gives those tiers *different* names — resolve that self-contradiction. (c) Add the **display-tier vs pin-Elo** sentence for `no_value` (pins at Elo 1100, below the `waivers` floor of 1150; backend returns `tier: null`; mobile's floor-less `tierForElo` shows FA) and note the mobile/backend banding gap as a known issue → checkpoint **C4**. **Keys, Elo bands and colors are unchanged.** |
| `docs/glossary.md` (new domain term) | **Updated** | No *new* term, but the **Tier band** entry (`:26`) is the canonical label list and the wizard now shares it verbatim — add one clause. Confirm at build time whether a "Pick Anchors" entry exists; if not, add one (it is a domain term across four screens and two docs). |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **Updated — `DECISIONS.md` D-012** *(verify next free id; P0-1 claims D-011)* | Records: (1) why **Option 3** over the audit's Option 1 (inert — the tiers branch reads `tiers_saved`, which the anchor lane never writes and is forbidden from writing) and Option 2 (`_interactions` is rebuilt from rank swipes at every session build, so an in-memory bump evaporates; and a counter on the shared `apply_anchor` lane would grant unlock credit to the `via:'draft_room'` action P0-1 deliberately excludes); (2) why `TIER_LABEL` is canonical over `ANCHOR_ROWS` (~11 locations across four clients vs 1); (3) why `no_value` displays as FA; (4) why `ANCHOR_UNLOCK_MIN = 40` and is **not** per-position (the wizard's default scope is one cross-position value-descending queue). **ADR n/a** — no decision of ADR weight; nothing architectural moves. |
| `docs/data-dictionary.md` | **n/a** | No schema change (see §2). |
| `docs/config-reference.md` | **n/a** *(conditional)* | No env var, flag or `model_config` key — **unless** checkpoint **C2** makes `ANCHOR_UNLOCK_MIN` a `model_config` key, in which case this row becomes **Updated**. |
| `docs/runbook.md` | **n/a** | No new operational procedure, migration or backfill. |
| `docs/design/design-system.md` / `components.md` | **n/a** | No new component and no token change; the rungs stay the specced compact `Button`. Re-read `components.md:117` at build time — it discusses the ladder's top/bottom labels in prose and should be corrected only if it names an anchor label. |
| `living-memory/CHANGELOG.md` | **Updated** | Dated H2 at ship. |
| `living-memory/TEST_LEDGER.md` | **Updated** | pytest + `tsc` + `testid-lint.sh` + `check-anchor-labels.js` + the Tier-1 sim run. |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if the build loses >30 min to something new. Strong candidate: "`RankingService._interactions` is **rebuilt from persisted rank swipes** on every session build (`ranking_service.py:770-783`) — anything that increments it in memory silently evaporates on the next cold start." |
| `living-memory/DEPENDENCIES.md` | **n/a** | No dependency added, bumped or removed. |
| `screens/manifest.json` + `screens/CLAUDE.md` | **Updated** | The `anchors` screen's three captures are re-taken (its freshness source `anchorRows.ts` changed); manifest hashes update as a side effect of `screen-capture.sh`. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | Dated artifact — record the outcome in `CHANGELOG.md`, do not rewrite the audit. The drift found during re-verification (5 label mismatches, not 2; Option 1 is inert as written) is recorded in `plan-p1-7.md` § Verified current state → Drift from audit. |

## 5. Ship gate declaration

- **Simulator-gate tier** (per the matrix in `docs/runbook.md` § Pre-ship simulator gate):
  **Tier 1 — Mobile screen / navigation / state change.** Justification: five button labels change on two live mobile surfaces (`PickAnchorScreen`, `AnchorSheet` behind the already-on `draft.rank_inline`), which is a visual change, not logic-only. Required before merge to `main`: **full smoke suite (11 flows) + `p1-7-anchor-labels.yaml`** (+ `p1-7-anchor-unlock.yaml` if **C6** is approved) **+ `mobile/scripts/screen-capture.sh --screen anchors`** for every state whose visuals changed, with `screen-freshness.sh` run to catch anything else.
  *(The backend half alone would be Tier 3; the stricter tier governs.)*
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written after the run. `githooks/pre-push` enforces locally (`git config core.hooksPath githooks`).
- **Operator deviation from the matrix (if any) and why:** none proposed.

---

## Open items requiring operator input before build

Full detail and recommendations in `plan-p1-7.md` § Operator checkpoints.

| # | Question | Recommendation | Blocks |
|---|---|---|---|
| **C1** | Suppress the first-unlock push fan-out for the newly-unlocked anchor cohort? | Match whatever P0-1 decides for its Q5 — the two deploys must not each produce a burst | Merge |
| **C2** | Confirm `ANCHOR_UNLOCK_MIN = 40`; constant or `model_config` key? | 40, as a constant (a key flips the `config-reference.md` row to YES) | Build |
| **C3** | Confirm label direction: `ANCHOR_ROWS` conforms to `TIER_LABEL` | Yes — ~11 locations vs 1, and the chooser already sells tiers in that vocabulary | Build |
| **C4** | `no_value` displays "FA", or stays a ninth vocabulary item? | "FA" now; log the mobile `tierForElo` 1150-floor gap as a separate backlog item | Build |
| **C5** | Ship the visible progress hint (`anchor_count` / `anchor_required` + wizard copy)? | Yes, but cleanly severable — declining it means **zero** API shape change | Build (severable) |
| **C6** | Implement the reserved `app_user.anchors` seeder key + `anchors-done` profile? | Yes — otherwise the on-device unlock proof is waived (waiver 1 of 3) | Build |
| **C7** | Sequencing with P1-8 (A-17), which edits the same unlock ladder | One session for both, or P1-7 first (it extracts the `_tiers_rule` seam P1-8 wants) | Build |
