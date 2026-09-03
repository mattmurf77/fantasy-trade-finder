# Feature Scope — G-413: Send in Sleeper handles draft picks (#413)

<!-- Copied from docs/templates/feature-scope.md (revision without the retired Maestro /
     simulator-tier sections, D-056). Every section is answered; nothing is waived. -->

**Date:** 2026-09-02
**Entry point:** feedback #413 (mattmurf77, v1.16.12 build 140, screen `TradesHome`) — group G-413, batch [plan.md](plan.md)
**Builder:** Phase 2 build agents (backend first, mobile second) on a branch cut from a freshly fetched `origin/main`; planning worktree `9145d22f`
**Operator sign-off on waivers:** **not needed — there are no waivers.** Two things are *stated* rather than waived and are surfaced here so they are read as decisions: (a) no feature flag (§2), (b) the field-1 encoding question is carried as an open question with a device proof, not a spike (§3).
**PRD:** [prd.md](prd.md) · **HLD delta:** [hld-delta.md](hld-delta.md) · **LLD delta:** [lld-delta.md](lld-delta.md) · **Plan:** [plan-g413.md](plan-g413.md)

**Bright-line notice (CLAUDE.md § Feature gates):** this change touches an **API contract** (two
new 422 codes on `POST /api/trades/propose`, two new warning codes on `/api/trades/validate`, a
new 400 reason) and an **analytics enum** (`sleeper_send_failed.error_code`). It is therefore
not express-eligible; full gates apply and no express was declared.

---

## 1. Analytics scope

- [ ] **(a) New events specced** — **no new events.**
- [x] **(b) Existing events cover it — with one closed-enum extension and one semantic
      correction, both specced here as taxonomy changes (not waivers):**

| Event | Change | Question it answers |
|---|---|---|
| `sleeper_send_failed` (client) | **`error_code` closed enum: 15 → 17 values.** Fires with the new codes on fielded builds too (the `body?.error` read predates this change). Adds `sleeper_pick_unmapped`, `sleeper_pick_not_owned`. No emitter change — `SendInSleeperButton.tsx:254-264` already sends `body?.error`. `CLIENT_EVENT_PROPS` constrains keys, not values, so no ingest change; `WAT_LIVE` already lists the event (`backend/analytics_queries.py:53-55`); `NON_INTENT_EVENTS` untouched (it is not an impression/navigation event). Four comment sites must agree on "17": `backend/analytics_taxonomy.py:1055-1058`, `SendInSleeperButton.tsx:252-253`, `docs/business/analytics/2026-08-11-p0-7-addendum.md:64-67`, `docs/cross-client-invariants.md:825` (gains the enum listing — the only place send-event enums are pinned). | How often a pick send is refused, and why — the pre-fix signal for #413 was `sleeper_write_failed` from Sleeper's GraphQL rejection; post-fix the two new codes replace it for pick problems. **Reader warning:** `sleeper_write_failed` rows before this deploy include pick-caused failures; do not read the drop as a Sleeper-side improvement. |
| `sleeper_send_succeeded` (server) | **Semantic correction, no key change.** `give_n`/`receive_n` counted picks as players and `pick_n` was always 0 (`server.py:16274-16278` passed the raw arrays and an empty `picks`). Post-fix: players only / encoded picks. Dated note in the addendum. | Pick share of confirmed sends — a number that was structurally 0 before this date. |
| `sleeper_send_attempted` (client) | Unchanged. Its `give_n`/`receive_n` still count mixed arrays (client-side, pre-split) — **stated**, not fixed: the attempt leg cannot know the split without duplicating server logic, and the succeeded leg is the one WAT/funnel read. | Attempt volume. |
| `deck_outcomes` `propose` label (F1) | Unchanged; only reachable after a successful write (`server.py:16264`). PRD T-11 proves refusals do not label. | — |

- [ ] **(c) WAIVED** — n/a, (b) applies.

Follow-through: `docs/data-dictionary.md` n/a (nothing new is stored); the addendum and the
invariants doc are updated per §4.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** The route *reads* `draft_picks` (existing, populated by
  the `session_init` sync daemon — `docs/architecture.md:152`) with `load_draft_picks`'s default
  platform-only source. No write, no column, no migration. `docs/data-dictionary.md` untouched.
- **New/changed feature flags: none — a stated decision, not a waiver.** The change lives
  entirely inside `trade.send_in_sleeper` (and the validate route's `send_in_sleeper || send_in_mfl`
  gate). A pick-free send is byte-identical (same arrays, no extra fetch — PRD R-4/R-12, T-10/V-6).
  The only new behaviors are (i) a send that today fails with a 502 now either succeeds or fails
  with a specific 422, and (ii) a validate that today lies now tells the truth. A
  `trade.sleeper_pick_send` flag would gate a *fix*, adding a second way to keep pick sends broken.
  Rollback is a code revert of an additive contract; the existing `trade.send_in_sleeper` kill
  switch still removes the whole surface deploy-free. `config/features.json`,
  `backend/feature_flags.py` `FLAG_KEYS`, `docs/config-reference.md` unchanged.
- **New env vars / `model_config` keys: none.** No tunable. `docs/config-reference.md` n/a.
- **Ship-the-knob:** deploy-free lever = `trade.send_in_sleeper` → `false` via
  `POST /api/feature-flags/reload` (removes the button everywhere, as today).

## 3. Evidence scope

<!-- D-056: no Maestro, no simulator, no screens/ captures. -->

- [x] **Structural guard:** `mobile/tests/check-send-button-platform.js` **extended** (no new file;
      `npm run test:send-button-platform` exists at `mobile/package.json:80`) with checks **7–8**
      (LLD §8.3, PRD §7.4): the `doPropose` catch's if/else-if chain contains
      `code === 'sleeper_pick_unmapped'` and `code === 'sleeper_pick_not_owned'` branches that call
      `Alert.alert`, do not reference `goConnect`, sit **before** the catch-all `else`, and the
      catch-all's copy survives. Sabotages (each proven RED): delete a branch; append it after the
      catch-all; route not-owned into the reconnect branch. Dependency-free beyond the project's own
      `typescript`, like the existing six blocks.
- [x] **Unit tests:** backend pytest — the primary evidence.
      - `backend/tests/test_sleeper_write.py` +2 (T-1 `encode_draft_pick` shape; T-2 pick-only body).
      - `backend/tests/test_sleeper_write_route.py` +12 new (T-3b the positive spine assertion,
        T-4…T-13, T-14 the unmapped-before-not-owned ordering) and **T-3 = the `:288` fixture
        fixed** — today it sends `"draft_picks": ["2027_1"]`, a string the adapter would reject,
        and passes only because `propose_trade` is mocked (false confidence, flagged in
        investigation.md). Stubs: `server.load_draft_picks`, `server._fetch_sleeper_traded_picks`
        patched directly — the seven existing `_sleeper_get` single-`return_value` stubs would hand
        the rosters list back as traded picks if the route fetched unconditionally (LLD §7.1).
      - `backend/tests/test_trade_send_validate.py` +6 (V-1 is the #413 repro: an owned pick on the
        give side yields zero `player_moved`; V-5 proves roster-limit math excludes picks).
      - Expected suite delta **+20** on the 2026-08-31b baseline (4483 / 1 skipped → 4503 / 1). Every
        test names its sabotage in PRD §7 (23 named sabotages across T-/V-); each is run RED before
        acceptance. Two of them guard fielded builds directly: dropping `detail` from a 422 (T-7/T-9)
        and deleting the propose-label call (T-3b).
- [x] **Code-walk proof:** `docs/feedback/items/413-sleeper-send-draft-picks/code-walk.md`, five
      targets W-1…W-5 (PRD §9): the four mounts still send mixed arrays; the catch → new branches →
      copy; `confirmSend` renders the new warnings with no client change; comment sites agree with
      the wire contract; the 422 reaches `sleeper_send_failed.error_code` through the existing
      `body?.error` read.
- [x] **Manual TestFlight checklist:** PRD §10, **7 steps** — TF-1/2/4/7 mandatory, TF-3
      conditional (legal outcome: "not run — Q-037 stays open"), TF-5/6 opportunistic (their proof
      of record is T-9/V-3 and T-7/V-2; the states are not buildable on demand) — run by the
      operator on a real Sleeper league (every proposal cancelled in Sleeper afterwards). Runtime
      proof genuinely matters here for one reason that no test can substitute: **step 3 is the
      field-1 proof** — the pick string's
      first field is captured as the original-owner roster id on two live examples but unconfirmed on
      a pick that has changed hands, and there is no Sleeper dry run (`FTF_TEST_MODE` fail-closes the
      route, `server.py:16167-16171`). Steps 1–2 close the two halves of the report; 4 checks the
      receive orientation; 5–6 the two refusals; 7 the byte-identical player-only path. Outcome of
      step 3 closes **Q-037** either way (pass → close; fail → capture `detail`, flip field 1 to the
      current holder — one argument in `encode_draft_pick`).
- [ ] **WAIVED because:** nothing.
- **`testID`s added/renamed: none.** The alerts are `Alert.alert`, not JSX. `mobile/scripts/testid-lint.sh`
  exposure: none; must stay green.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **updated — required** | `:405` propose row: arrays are MIXED; server splits and encodes against the `draft_picks` grid + live `traded_picks`; `draft_picks?[]` removed from the body and noted as rejected-if-non-empty; `pick_n`/`give_n` honesty note. `:408-420` error table: add 422 `sleeper_pick_unmapped` (+`picks[]`) and 422 `sleeper_pick_not_owned` (+`picks[]`); `:419` 400 row gains the `draft_picks` reason. `:421` "v1 scope" line replaced (picks are now encoded server-side; FAAB still out). `:406` validate row: Sleeper codes gain `asset_unmapped`, `pick_moved`; `player_moved`/`roster_limit` are players-only; "Body mirrors propose (players only)" → "(mixed arrays)". `:432` MFL validate row untouched. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **updated** | New topical H2 + TOC row (LLD §10): pick assets ride the mixed arrays on every propose route; the server splits/encodes against its own ground truth; any unresolvable pick refuses the whole send; no route accepts a client-encoded pick string. Sleeper / MFL / ESPN named. |
| `docs/architecture.md` (module wiring / data flow changed) | **updated** | § Components → Backend: `sleeper_write.py` currently has **no row** (only a parenthetical at `:152`); add one (adapter for the captured `propose_trade` mutation; `encode_draft_pick`; flag; token handling) — and note the propose route's two pick-time reads (`draft_picks` grid + live `traded_picks`). § Data flow: the `DB → SRV` edge for `draft_picks` on the propose path (HLD §2). |
| `living-memory/HLD.md` (architecture genuinely shifted) | **updated — one line** | The Sleeper write path gains the same pick step MFL/ESPN have (mirror of the `docs/architecture.md` row); no new module/client/flow. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **updated — required** | § Client analytics event contract, beside the `surface` enum at `:825`: `sleeper_send_failed.error_code` is a closed 17-value enum — list all 17 (the 14 server codes of `/api/trades/propose` incl. the two new ones + `network` \| `timeout` \| `unknown`). Also the validate `code` vocabulary (`league_archived`, `player_moved`, `roster_limit`, `roster_not_found`, `asset_unmapped`, `pick_moved`) if not already pinned there. |
| `docs/glossary.md` (new domain term) | **n/a** | No new term. "owned pick", "generic rung", "pick grid", "traded picks" are existing vocabulary. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **updated — required** | `living-memory/DECISIONS.md` gains **D-176** (verbatim in PRD §12; next id — `D-171` is the current max, verified 2026-09-02) + the matching row in the Decision index at `:438`. Records: server-owned encoding; two ground truths; whole-send refusal; `draft_picks` key rejected; no flag; the `traded_picks`-flake residual. No ADR — it is an instance of an established pattern, not a new architectural rule. |

**Additional doc rows this change owes, beyond the template's list:**

| Doc | Updated? | Section / reason |
|---|---|---|
| `docs/integrations/sleeper.md` | **updated** | `:62` op 15 `propose_trade`: "now emits non-empty `draft_picks`, produced by `server._sleeper_encode_ftf_picks` → `sleeper_write.encode_draft_pick`". `:43`/`:187-188` `traded_picks`: gains two consumers (propose + validate, pick sends only). §3.3 `:197-204`: the element shape `"orig,season,round,from,to"` with the field-1 caveat (Q-037), from/to orientation per side. |
| `docs/business/analytics/2026-08-11-p0-7-addendum.md` | **updated** | `:64-67`: 14 server codes, 17 values, the two new spellings. New dated bullet under the `sleeper_send_succeeded` row `:57`: `pick_n`/`give_n` semantic correction as of the deploy date — rows before it counted picks as players and `pick_n` was structurally 0. |
| `docs/config-reference.md` | **n/a** | No flag, env var, or `model_config` key. |
| `docs/data-dictionary.md` | **n/a** | No schema change; `draft_picks` is read with its existing contract. |
| `living-memory/OPEN_QUESTIONS.md` | **updated** | **Q-037** — field 1 of the Sleeper pick string on a previously-traded pick (Q-016 format: why it matters / action to unblock = TestFlight step 3 / workaround = none needed, failure is visible / owner = operator / asked 2026-09-02). |
| `backend/sleeper_write.py` header `:22` + `:230` | **updated** | Server-side production of `draft_picks`; field-1 caveat pointing at Q-037. (Code comment, same commit — listed because the module header is the doc of record for the captured shape.) |
| `mobile/src/components/CLAUDE.md:33` | **updated** | `SendInSleeperButton` row: one clause — the two `sleeper_pick_*` refusal branches; pick ids ride the mixed arrays verbatim, the server encodes. |
| `mobile/src/api/CLAUDE.md:32` | **updated** | `sendInSleeper.ts` row: one clause — propose arrays are mixed; validate's Sleeper codes now include `asset_unmapped` / `pick_moved`. |
| `living-memory/CHANGELOG.md` | **updated at ship** | Dated H2 for the merge. |
| `living-memory/TEST_LEDGER.md` | **updated at ship + after TestFlight** | Suite counts (+20), the 21 named sabotages proven RED, the structural checks 7–8, the code-walk, and the 7-step checklist with **step 3's outcome logged explicitly**. |
| `living-memory/NEXT.md` | **updated at ship** | #413 closed; if TF-3 fails, a one-line follow-up (flip field 1) is queued. |
| `docs/feedback/items/413-sleeper-send-draft-picks/status.md` | **updated at ship** | → shipped, with the sha and build. |
| `docs/plans/sleeper-write-capture-runbook.md:159` | **n/a — deliberately not edited** | It is the capture record. Its "confirm on a multi-owner pick" sentence stays true until TF-3 is logged; the resolution is recorded in Q-037 and `integrations/sleeper.md`, not by rewriting history. |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests` (`pytest backend/tests`, expected 4503 passed / 1
  skipped on the 2026-08-31b baseline — the build agent records the actual numbers) +
  `mobile-typecheck` (`npx tsc --noEmit`, which also runs the `check-*.js` suites incl. the extended
  `check-send-button-platform.js`) + `maestro-testid-lint` (`mobile/scripts/testid-lint.sh`; no
  testIDs added).
- **Evidence recorded** in `living-memory/TEST_LEDGER.md`: the three pytest files and their deltas,
  every named sabotage (T-1…T-13, V-1…V-6, C-7/7b/7c/8) proven RED, the code-walk W-1…W-5, and the
  TestFlight checklist as the runtime evidence.
- **TestFlight verification:** a checklist **was** written (§3), so it is run by the operator and
  each step's outcome — **step 3 above all**, including "not run" — is logged in TEST_LEDGER.
  **Build honesty (same statement as PRD §1 and §10):** all seven steps run on any build ≥ 1.16.12
  once Render deploys, because the request contract is unchanged and both 422s carry `detail`,
  which the fielded catch-all renders; the new build changes only the refusal alert's wording.
- **Pre-push hook:** `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056; the note records the
  pytest + structural + code-walk + checklist as the evidence run instead. Hooks installed once per
  clone via `git config core.hooksPath githooks`.
- **Express lane declared by the operator?** **No.** Full gates. And per the bright line, this
  change would not have been express-eligible without an explicit confirming yes: it changes an API
  contract and an analytics enum.
- **Branch hygiene:** branch cut from a freshly fetched `origin/main`; on ship, verified by content
  against `origin/main`, tip sha ledgered in `docs/recovery/`, worktree removed.
