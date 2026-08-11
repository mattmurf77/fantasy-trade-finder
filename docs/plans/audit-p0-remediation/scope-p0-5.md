# Feature Scope — P0-5: Apple account-only sign-in reaches a platform/league choice

<!--
Copied from docs/templates/feature-scope.md. Every section answered or explicitly waived.
Companion plan: docs/plans/audit-p0-remediation/plan-p0-5.md
-->

**Date:** 2026-08-10
**Entry point:** mobile UX audit finding **P0-5** (`docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-5)
**Builder:** planning agent, worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10` (base `origin/main @ ab9368f`)
**Operator sign-off on waivers:** **required — 3 waivers + 2 decisions pending** (see §6)

**One-line summary:** account-only (Apple, no Sleeper) sessions currently route straight to the tabs
with a `no_league` sentinel and every league surface empty; route them to `LeaguePicker` instead and
give that screen a companion state that leads with "Connect Sleeper, ESPN or MFL".

**Express lane:** **not declared.** Full gates apply. (Per CLAUDE.md, agents never self-select express.)

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it** — the funnel is already bracketed end-to-end:

  | Event | Where it fires | Question it answers |
  |---|---|---|
  | `signin_succeeded` `{method:'apple'}` | `mobile/src/screens/SignInScreen.tsx:183` (the account-only branch itself) | How many users enter this branch at all. |
  | `league_selected` `{league_index, league_count, auto, league_type}` | `mobile/src/screens/LeaguePickerScreen.tsx:232-250` — fires for **imported** ESPN/MFL leagues too, via `onLeagueLinked` → `pickLeague` | How many of them end up with a real league. |

  **The stranded population = (apple `signin_succeeded`) − (their subsequent `league_selected`),
  measurable identically before and after the change**, which is what makes this fix readable
  without new instrumentation.

- [ ] **(c) WAIVED — no analytics needed because:** n/a (covered by (b)).

**Deliberately deferred:** `platform_link_started {platform, entry}` would separate "never saw the
choice" from "saw it and declined". Not added now — `backend/analytics_taxonomy.py`
(`ALLOWED_CLIENT_EVENTS`) is **default-deny**, and the handoff's trap list records prior art of a
client event fired and silently dropped for exactly this reason. If P0-7 proceeds, register the name
server-side **first**. Follow-through owner: P0-7.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No `backend/database.py` change; `docs/data-dictionary.md` needs no edit.
- **New/changed feature flags:** **none — deliberate.**
  - Rationale: this is a bug fix on a branch that is broken for **100% of its users**. There is no
    working prior behaviour for a flag to preserve, so an off-state would only be a way to ship the
    bug back. Blast radius is already bounded by data: only sessions with `account_only === true` or
    `league.league_id === 'no_league'` can enter any new branch — no Sleeper-keyed or demo session can.
  - Existing flags still gate each platform button independently and remain the per-platform
    rollback lever: `espn.link` (ON), `mfl.link` (ON), `fleaflicker.link` (OFF), `auth.accounts` (ON).
  - **Ship-the-knob:** if the operator wants a deploy-free kill anyway, the honest shape is
    `auth.account_only_picker` (default **ON**) gating *only* the two `RootNav.tsx` routing changes —
    that is the only pair with a coherent "old behaviour". **Operator decision, §6 D-2.**
- **New env vars / `model_config` keys:** **none.** The Maestro seam reuses the existing
  `FTF_TEST_MODE` (backend, already the gate for the whole `/__test__` blueprint at
  `backend/server.py:2015`) and the existing build-time `extra.testMode` constant (client,
  `mobile/src/utils/testRouteEntry.ts:51-56`, set only by `mobile/scripts/sim-build.sh`). No new
  knob, and nothing new that could be set in Render.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/p0-5-account-only-picker.yaml` — covers: brand-new Apple
  sign-in → **LeaguePicker companion state** (the acceptance criterion), asserts `tab.trades` is
  *not* visible (did not route to `Main`), asserts the old false "No 2026 NFL leagues found" /
  Sleeper-error copy is gone, then a **relaunch leg** (`clearState: false`) proving the sentinel-aware
  `initialRoute` holds across a cold start, then an MFL-sheet-opens leg. Full flow spec in
  `plan-p0-5.md` §5.
- [x] **New capture:** `mobile/.maestro/capture/leagues@account-only.yaml` — new visual state of an
  existing screen, one screenshot, same launch-argument entry.
- [x] **Extended flow:** none extended. `mobile/.maestro/capture/leagues@fresh.yaml` is
  **asserted unchanged** — it signs in as the Sleeper-keyed `qa_no_leagues` and asserts the literal
  *"No 2026 NFL leagues found for this account."*; it must still pass, proving the companion state
  did not leak into the non-account-only empty state.
- [ ] **WAIVED because:** n/a.

- **`testID`s added:** `leagues.empty.link-sleeper`, `leagues.empty.link-espn`,
  `leagues.empty.link-mfl`, `leagues.empty.link-fleaflicker`, `leagues.empty.body`.
  All static string literals → no `scripts/testid-lint-allow.txt` entry needed.
  **`testID`s moved (not renamed):** `settings.link-sleeper-input` travels with the extracted
  `LinkSleeperSheet` component so `capture/settings.yaml` and `testid-lint.sh` keep resolving.

- **Harness seam required (W-1, see §6).** The harness **cannot** perform a real Apple sign-in:
  `AppleAuthentication.signInAsync` raises an undrivable system sheet requiring a real Apple ID +
  password, and `/api/auth/apple` verifies against Apple's live JWKS (`backend/accounts.py:214-221`).
  `backend/test_support.py` has no auth-shaped route and no seeder profile
  (`backend/tests/fixtures/profiles/*.json`) produces an account-only user. Minimum seam:
  1. Backend, `FTF_TEST_MODE=1` only: accept `identity_token = "ftf-test-apple:<sub>"` and synthesise
     the claims instead of calling `verify_apple_token`. Everything downstream is the real path.
  2. Client, `IS_TEST_BUILD` + launch argument `FTFTestAppleSub` only: substitute the credential for
     the SDK call and render the Apple button when `isAvailableAsync()` is false. **Every line after
     that is production code under test** (`SignInScreen.tsx:167-185` → `onAccountSignedIn`).
  Both gates are pre-existing and independently audited; a pytest asserts the backend seam **401s**
  with `FTF_TEST_MODE` unset.

- **Capture delta:** `leagues` (new companion state + unchanged existing states), `settings`
  (post-`LinkSleeperSheet` extraction). Run `mobile/scripts/screen-capture.sh --screen leagues`
  and `--screen settings`.

- **Smoke-suite impact:** Tier-1 change class → **all 11 flows run**. The two that cross this surface
  directly are `flows/smoke/01-signin.yaml` and `flows/smoke/02-league-pick.yaml` (Sleeper sign-in →
  picker → `Main`); they are the guard on the `initialRoute` edit and must stay green **unchanged**.

- **Backend pytest added/updated:**
  - `backend/tests/test_account_first.py` — **unchanged, must stay green** (contract for
    `account_only`, the sentinel, `verified_via` persistence).
  - New: `/api/auth/apple` with `identity_token="ftf-test-apple:x"` and `FTF_TEST_MODE` unset → **401
    `invalid_token`** (asserts the production gate on the harness seam).
  - New: an account-only session can `POST /api/espn/link` (preview leg) with no Sleeper identity —
    pins the claim the whole design rests on.
  - New: `/api/session/init` with an `acct_` user id + the existing `X-Session-Token` **reuses the
    token and preserves `verified`/`verified_via`** (`server.py:14626-14638`). Without this, the
    P2.5 read gate would 403 these users out of their own board the moment they link a league.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (route added/renamed/removed/contract-changed) | **n/a** | No route change. `/api/espn/link`, `/api/mfl/link`, `/api/account/link-sleeper`, `/api/session/init` are all called with existing contracts from existing call sites. The `FTF_TEST_MODE` token seam in `/api/auth/apple` is harness-only and unreachable in any deployed build → documented in `docs/runbook.md`, not in the public API reference. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **yes** | New convention: **post-auth routing keys off the `no_league` sentinel, never off `user.account_only`** — `account_only` stays true after an ESPN/MFL link (it is cleared only by linking a *Sleeper username*, `SettingsScreen.tsx:432-437`), so an `account_only` predicate would trap a well-provisioned user in the picker permanently. Second entry: `LinkSleeperSheet` is the single owner of the Sleeper-identity-link form (Settings + LeaguePicker consume it). |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No module wiring or data-flow change — one prop value and one branch inside an existing screen; no new client↔server path. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No new module, client, or major flow. An existing flow (platform linking) is being connected to an existing screen (LeaguePicker) that already hosts both of its sheets. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **yes (small)** | `no_league` is a cross-client string constant — emitted by `backend/server.py:17956` (`ACCOUNT_NO_LEAGUE_ID`), consumed by `mobile/src/state/useSession.ts:56` (`NO_LEAGUE_ID`) and now load-bearing in RootNav's routing predicate. It is currently documented nowhere; add it to the shared-enum table. |
| `docs/glossary.md` (new domain term) | **yes** | Add **account-only session** — an Apple/Google identity with no bound Sleeper source; working key `acct_<account_id>`; sentinel league `no_league`. The term is used throughout backend and mobile code and appears in no glossary. |
| `docs/runbook.md` | **yes** | Under the mobile UI-test harness section: the `FTFTestAppleSub` launch argument + `ftf-test-apple:<sub>` token seam, stating both production gates explicitly. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **yes — `D-011`** | "Account-only sessions route to LeaguePicker; the **sentinel league**, not the `account_only` flag, is the routing predicate." Records: the rejected non-dismissible-sheet-over-`Main` alternative and why; the no-new-flag call; the `LinkSleeperSheet` extraction. Full-ADR not warranted (no architectural shift) — a DECISIONS entry is the right altitude. |
| `living-memory/CHANGELOG.md` | **yes, at ship** | New dated H2. |
| `living-memory/TEST_LEDGER.md` | **yes, at ship** | Sim-run tier, flows run, result. |
| `living-memory/GOTCHAS.md` | **yes, if the seam bites** | Candidate `G-013`: "`GET /api/sleeper/leagues/acct_<id>` proxies a synthetic id to Sleeper and returns a **503 `sleeper_unavailable`** under the VCR harness — an account-only user must never trigger the Sleeper league fetch." |

### 4.1 Execution record — W3-DOCS, commit 14 (2026-08-11)

> Row-by-row closure of the table above, per the feature-gate contract. **IDs are `hld.md` §7 / §10.4's**, which supersede any `D-011` / `G-013` written above — root `CLAUDE.md`'s next-ID columns were stale when these scope blocks were authored (they have since been changed to "max existing + 1 — grep first", so the trap is closed at the source).

| Row | Status | Where it landed |
|---|---|---|
| `docs/cross-client-invariants.md` | **updated** | New § *`no_league` — the account-only league sentinel*: emitter/consumer sites, the sentinel-not-flag routing rule, the never-proxy-to-a-platform-API rule, and the change-together list. |
| `docs/glossary.md` | **updated** | **account-only session**. |
| `docs/runbook.md` | **updated** | New § *Mobile UI-test identity seam — `FTFTestAppleSub`*, with both production gates and why neither alone is sufficient. Verified against `SignInScreen.tsx:35/195` and `server.py:_TEST_APPLE_TOKEN_PREFIX`. |
| `living-memory/LLD.md` | **updated** | Sentinel-not-flag routing; root-stack rule; `LinkSleeperSheet` as single owner. |
| `living-memory/DECISIONS.md` | **updated — D-029** (not D-011) | Incl. the rejected non-dismissible-sheet-over-`Main` alternative. |
| `living-memory/GOTCHAS.md` | **updated — G-032** | The LLD's candidate promoted to a real entry: an account-only session must never trigger the Sleeper league fetch (503 under the harness, misleading "No 2026 NFL leagues found" live). |
| `mobile/src/components/CLAUDE.md` | **updated** | New `LinkSleeperSheet` row, naming the 409 alert as the reason it must not be reimplemented. The five `leagues.empty.*` testIDs are screen-level (`LeaguePickerScreen.tsx`) and were verified present rather than added to the component map. |
| `living-memory/CHANGELOG.md` | **updated** | Batch H2 — the retroactive route flip is named as a user-visible change. |
| `screens/CLAUDE.md` | **deferred** | See below. |
| `docs/api-reference.md` · `docs/architecture.md` · `living-memory/HLD.md` · `docs/data-dictionary.md` · `docs/config-reference.md` · `living-memory/DEPENDENCIES.md` | **n/a — confirmed** | As stated above. |

**Not executed, and why:** `screens/CLAUDE.md` + `screens/manifest.json` re-capture rows are **deferred** — the renamed/new frames require a run of `mobile/scripts/screen-capture.sh` against the simulator, which `W3-QA` holds for the sim gate. Writing index entries for PNGs that do not exist would make the manifest lie. Tracked for the capture pass. `living-memory/TEST_LEDGER.md` is owned by `W3-QA` and is deliberately untouched here.

## 5. Ship gate declaration

- **Simulator-gate tier** (matrix in `docs/runbook.md` § Pre-ship simulator gate): **Tier 1** —
  "Mobile screen / navigation / state change". This edits navigation routing (`RootNav.tsx`), a
  screen's rendered states (`LeaguePickerScreen.tsx`), and extracts a component out of
  `SettingsScreen.tsx`. Required: **full smoke suite (11 flows) + the new
  `p0-5-account-only-picker.yaml` flow**, plus `mobile/scripts/screen-capture.sh --screen leagues`
  and `--screen settings` for the changed visuals.
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written after
  the run. Enforced locally by `githooks/pre-push` (`git config core.hooksPath githooks`).
- **Also required before merge:** `python3 -m pytest backend/tests/ -q`,
  `cd mobile && npx tsc --noEmit`, `mobile/scripts/testid-lint.sh`.
- **Operator deviation from the matrix:** none requested.
- **Bright line (CLAUDE.md §Conventions):** this change touches **no** schema, **no** API contract,
  **no** feature-flag surface, and **no** analytics event. It is *not* on the bright line — but it is
  also **not** an express-lane candidate, because the Tier-1 sim run is the only thing that can
  demonstrate the acceptance criterion (a routing change is invisible to pytest and `tsc`).

## 6. Waivers and decisions requiring operator sign-off

| # | Kind | Item | Ask |
|---|---|---|---|
| **W-1** | Waiver | **New production code exists solely to make the flow testable** — the `FTF_TEST_MODE` token seam and the `IS_TEST_BUILD` credential substitution (§3). Justification: a real Apple sign-in is undrivable by Maestro and would require automating a password entry; stubbing any higher up would test the harness instead of the fixed branch. Both gates are pre-existing and a pytest asserts the backend seam 401s in production configuration. | Approve the seam, or accept **no automated coverage** of the acceptance criterion (manual TestFlight only). |
| **W-2** | Waiver | **The link→`Main` completion leg is not automated.** Completing an MFL or ESPN import needs live third-party egress, which the hermetic harness forbids (rails audit) and for which no fixture exists. The flow stops at "sheet opened"; completion is covered by manual TestFlight tests 11 and 14 in `plan-p0-5.md` §7. | Accept. |
| **W-3** | Waiver | **No new feature flag** (§2). | Accept, or ask for `auth.account_only_picker` (D-2). |
| **D-1** | Decision | **The Sleeper option.** The handoff's copy names Sleeper first, but Sleeper linking is a Settings-only form today. Plan commits to **extracting `LinkSleeperSheet`** (~110 moved lines, consumed by both screens). Fallback: a button that navigates to Settings (~5 lines, zero refactor) — but that re-creates the dead end this finding is about, and the highest-consequence code being moved is the 409 two-boards Alert whose failure mode is *deleting the wrong ranking board*. **Recommendation: extract.** | Confirm extract vs route-to-Settings. |
| **D-2** | Decision | Ship the optional `auth.account_only_picker` kill switch (default ON, gating only the two routing lines)? **Recommendation: no.** | Confirm. |

## 7. Cross-finding dependency — P0-3 (flag for the HLD)

**P0-3 is adding a deep-link route that pins an invited league as active after auth. The
intersection case is an account-only Apple user tapping an invite, and it is not currently
buildable as specified.**

1. **Ordering.** If P0-3's post-auth pin runs *after* P0-5's `replace('LeaguePicker')`, the user sits
   on "Connect your league" while the app already knows which league they were invited to.
2. **Predicate coupling.** P0-5's relaunch guard sends any session with `league_id === 'no_league'`
   to the picker. **P0-3 must pin the invited league via `setLeague()` (which overwrites the
   sentinel), not carry it in a parallel field** — otherwise the user bounces back to the picker on
   next launch.
3. **The blocking half.** An invited league is a **Sleeper** league; an account-only user has **no
   Sleeper user id** and is therefore not a member. `buildSessionInitBody`'s Sleeper branch
   (`mobile/src/api/auth.ts:453-471`) would find no roster for `acct_<id>` and produce empty
   `user_player_ids`. Pinning an invited Sleeper league for an account-only user **cannot work as
   built**. Proposed resolution: keep the invite in `useSession.setInvitedBy` (already survives,
   `useSession.ts:158-162`, already consumed by `session_init`), route to the picker, and have the
   companion state **name the inviter and league** — "Ryan invited you to Dynasty Warriors — connect
   Sleeper to join". That turns the collision into the strongest copy on the screen.

**Recommendation: land P0-5 first** (smaller, and it gives P0-3 a real destination to pin against),
and make "invited + account-only" a first-class case owned by P0-3's HLD. Both plans touch
`mobile/src/navigation/RootNav.tsx` — P0-5 at `:297-301` and `:410`, P0-3 at the `:303-325` route
table. Sequence the merges; do not parallelise the edits.
