# PRD — P0-1: the default ranking path never completes its own progression

> Requirements and acceptance for finding **P0-1** of the 2026-08-09 mobile UX audit.
> **Build agent:** `W1-BE`. **Commit:** 2 of 15. **Design:** `lld-p0-1.md`.
> **Bound by** `hld.md` §2 S-01…S-07 · §3 commit 2 · §4 W1-BE · §6 rows 1, 8 · §7 ·
> §8 R7 · §9 LLD-1.
>
> **Express lane:** **not declared.** Full gates apply (`scope-p0-1.md`, `hld.md`
> S-46). Agents never self-select express.

## Contents

- [1. Problem](#1-problem)
- [2. Requirements](#2-requirements)
- [3. Acceptance criteria](#3-acceptance-criteria)
- [4. Non-goals](#4-non-goals)
- [5. Docs rows W3-DOCS executes](#5-docs-rows-w3-docs-executes)
- [6. Rollback](#6-rollback)
- [7. Pre-merge checklist](#7-pre-merge-checklist)
- [8. Known, accepted consequences](#8-known-accepted-consequences)

---

## 1. Problem

A user who ranks the way the app routes them by default — Rank tab → Quick Set
Tiers (`TabNav.tsx:195-215`, `#244` launch routing) — never passes through the
ranking-method chooser, which is the **only** production writer of
`users.ranking_method` (`POST /api/ranking-method`, `server.py:6288`;
`RankHomeScreen.tsx:58-61` and `SettingsScreen.tsx:229-238`). The column stays NULL.

`GET /api/rankings/progress` branches on that column (`server.py:6155-6175`). NULL
falls to the trio branch, which requires 10 interactions × 4 positions — and a tier
save writes Elo overrides without ever touching the interaction counter. So the user
finishes a complete board and the endpoint answers `unlocked: false`, permanently.

The contradiction is visible on one screen. `LeagueScreen.tsx:326-334` counts a
position ranked when `progress[p] >= threshold` **or** `tiersSaved.includes(p)`, so
the ring reads **4/4** — beside an account that is locked. Everything keyed to the
unlock stays dark:

| Surface | Gate |
|---|---|
| **The push primer never fires** | `pushEnabled = everUnlockedRef.current \|\| data?.unlocked === true` (`RootNav.tsx:266-267`), the third argument to `usePushNotifications` (`:279-283`). This is the highest-cost symptom: the user is never even asked. |
| The payoff banner never renders | `RankScreen.tsx:356, 685-697` |
| Leaguemates see "in progress" forever | `LeagueScreen.tsx:826-836` (mobile), `web/js/app.js:5165-5177` (web) |

**Who is affected:** every user with a tier-based board and no chooser visit —
i.e. the default path. The monotonic `unlocked_formats` floor (`server.py:6177-6187`)
cannot rescue them: it only carries a user who was *once* computed unlocked.

**Evidence in-repo:** `backend/tests/fixtures/profiles/quickset-done.json` exists
solely to reproduce this state (capture request #8), `seed_ui_test_db.py`
`_validate_quickset` actively refuses profiles that would un-reproduce it, and
`mobile/.maestro/capture/league@quickset-done.yaml` photographs it as
`league__progress-ring--4-4-locked`.

---

## 2. Requirements

### Functional

| # | Requirement | Verified by |
|---|---|---|
| **FR-1** | `users.ranking_method` is written at the **point of use** by the four ranking save handlers — `/api/tiers/save` → `via` (`'tiers'`\|`'quickset'`), `/api/rank3` → `'trio'`, `/api/rankings/reorder` → `'manual'`, `/api/anchor/save` → `'anchor'`. | T-1…T-5b |
| **FR-2** | **First use wins.** An existing non-empty method is never overwritten. | T-9, T-10, T-H2 |
| **FR-3** | **One exception:** a completeness-marking tiers/quickset save may overwrite `'anchor'`, and only `'anchor'`. No other method string is ever overwritten by anything. | T-11, T-11b, T-11c, T-H4 |
| **FR-4** | Three exclusions write nothing: rookie-scope tier saves (`scope == 'rookie'`), `via: 'rookie_ranks'` reorders, `via: 'draft_room'` anchors. | T-6, T-7, T-7b, T-8 |
| **FR-5** | The write is **race-free** — a single conditional `UPDATE`, no read-then-write window. | Design (`lld-p0-1.md` §2.1); no concurrency test is claimed |
| **FR-6** | The write **can never fail a save.** A DB error is logged and swallowed; a save that 4xx/5xxs leaves the column untouched. | T-14, T-14b; `_note_ranking_method`'s never-raises contract |
| **FR-7** | On an actual write only, the 60 s league-members cache is dropped so leaguemates' `has_ranking_method` badge is not stale. A no-op write does not pay that cost. | T-13 |
| **FR-8** | A **startup backfill** in `_migrate_db()` repairs already-stuck users: `ranking_method` unset **and** `tiers_saved` complete for ≥1 scoring format → `'quickset'`. | T-18, T-18b, T-18c |
| **FR-9** | The backfill cohort is **narrow and strictly improving**: a partial tier board is never tagged (it could re-lock a mixed-method user), and an existing method is never overwritten. | T-19, T-20, T-23 |
| **FR-10** | The backfill is **idempotent**, safe on every boot, tolerant of malformed `tiers_saved`, and can never break boot. | T-21, T-22, T-22b |
| **FR-11** | The backfill **suppresses the retroactive first-unlock fan-out** — no `ranking_complete_first_time` event and no `league_member_unlocked_trades` push burst — by pre-seeding `unlocked_formats` with the qualifying formats in the same `UPDATE` that writes the method. | **T-24** (+ control **T-24b**) |
| **FR-12** | The backfill **logs the affected user ids** so the scoped SQL undo in §6 is expressible. | Boot-log line, checked in the sim run |
| **FR-13** | The unlock ladder itself is unchanged. | T-16, T-23; diff review |

### Non-functional

| # | Requirement |
|---|---|
| **NFR-1** | **No schema change.** `users.ranking_method` already exists (`database.py:181`, migration entry `:1861`). No DDL, no index, no type change. |
| **NFR-2** | **No API shape change.** No route added, removed or renamed; no request field; no response key. The *value domain* of `/api/rankings/progress` moves (`ranking_method` non-null far more often; `unlocked` flips false→true for the Quick Set cohort) — that is the fix. |
| **NFR-3** | **No feature flag** and no flag default change (S-04, `hld.md` S-44). |
| **NFR-4** | **No new analytics event**, and no existing event repurposed. In particular the implicit writes must **not** fire `ranking_method_changed`, whose meaning is "the user chose a method" (`server.py:6306-6317`). |
| **NFR-5** | **No client behaviour change.** `useSession.rankingMethodPref` is a device-local AsyncStorage routing pref (`useSession.ts:194-220`), never hydrated from the server, so the column cannot perturb launch routing, the chooser, or Settings. The only mobile edit is one `testID`. |
| **NFR-6** | Commit 2 is independently green: `python3 -m pytest backend/tests/ -q`, `cd mobile && npx tsc --noEmit`, `bash mobile/scripts/testid-lint.sh`. **Never run `npm install`** — `mobile/node_modules` is a symlink. |

---

## 3. Acceptance criteria

### A1 — the audit's criterion (new users)

> *A fresh account that only ever uses Quick Set reaches 4/4 on the per-position
> ring **AND** `unlocked: true` **together**, and the push primer fires.*

| Half | Proof | Owner |
|---|---|---|
| `unlocked: true` from Quick Set alone, with **zero** trio interactions | **T-15**: four `POST /api/tiers/save` (QB/RB/WR/TE, `via:'quickset'`) then `GET /api/rankings/progress` → `unlocked is True` **and** `ranking_method == 'quickset'` **and** all four per-position counts still `0` | pytest |
| 4/4 **and** unlocked in **one session on device** | `mobile/.maestro/flows/p0-1-quickset-unlock.yaml`: `".*4 of 4 positions ranked.*"` **and** `assertVisible id: rank.unlocked-banner` in the same run, plus `assertNotVisible id: rank.unlock-payoff` (the locked state's fingerprint). Two flows could each pass on different sessions and never prove simultaneity — hence one flow. | Maestro |
| The push primer fires | **Proxy, waived (W-1):** `rank.unlocked-banner` ⇔ `progress.unlocked` ⇔ `pushEnabled` (`RootNav.tsx:267`) — the same boolean gates both. The iOS permission dialog is a SpringBoard alert outside the app hierarchy and is not reliably Maestro-assertable; `usePushNotifications` additionally short-circuits when permission was already granted. **Direct check:** manual, on a permission-reset simulator (`xcrun simctl privacy <udid> reset all <bundle>`), recorded in `TEST_LEDGER.md` with which method was used. | proxy + manual |
| Not over-unlocked | **T-16**: a three-position board stays locked | pytest |
| Nobody loses an unlock | **T-9 / T-19 / T-20 / T-23** | pytest |
| **The bug was actually observed** | **Pre-fix control run** (R5): the same flow against the pre-fix build with the pre-inversion fixture must **fail** at the banner assertion. A test that never observed the bug proves nothing. | Maestro |

### A2 — the backfill's criterion (existing users)

> *Users already stuck unlock on their next progress read, **without** a push
> fan-out.*

| Half | Proof |
|---|---|
| Stuck users unlock | **T-18/T-18b/T-18c** (the row is tagged and the floor seeded) + **T-24** (the next `GET /api/rankings/progress` answers `unlocked: True`) |
| **No** push fan-out, **no** `ranking_complete_first_time` | **T-24**: `_send_typed_push` never called and zero `ranking_complete_first_time` rows in `user_events`; **T-24b** is the control proving the fan-out is not merely dead |
| Nobody is re-locked or re-labelled | **T-19** (partial board untouched), **T-20** (existing method wins), **T-23** (the monotonic floor still carries a trio user) |
| Safe to run on every boot | **T-21** (second run writes nothing), **T-22/T-22b** (malformed / legacy `tiers_saved` shapes) |
| Cohort is knowable | **FR-12** boot log names the ids; the confirming query is `SELECT count(*) FROM users WHERE ranking_method IS NULL AND tiers_saved IS NOT NULL` (§5 runbook row) |

### A3 — the fixture/seeder/capture inversion (S-06)

- `backend/tests/fixtures/profiles/quickset-done.json` describes the **fixed** state
  and the seeder accepts it (`lld-p0-1.md` §5.2, §5.3).
- The seeder now **refuses** the incoherent post-fix profile — an all-four-position
  Quick Set board claiming `unlocked:false` — regardless of `ranking_method`.
- `mobile/.maestro/capture/league@quickset-done.yaml` is renamed
  `progress-ring--4-4-unlocked`, its header re-argued, and the frame **re-captured**
  (S-07 — history lives in git, not in a screen-library frame whose name asserts a
  bug that no longer exists).
- The two `test_seed_ui_test_db.py` tests that encode the bug are inverted in the
  same commit (`lld-p0-1.md` §5.4).

### A4 — sim gate

Tier **1** for the batch as a whole (`hld.md` §4 W3-QA, §10.5 — the batch contains
navigation and screen changes, so the strictest class governs; P0-1's own scope
block declared tier 2 and is superseded). One tier-1 run covers all seven findings.
P0-1's crossing surfaces to watch: `flows/smoke/04-tiers.yaml` (tier-save path),
`06-trades-deck.yaml` (unlock-gated deck), `09-league.yaml` (the ring) — all
expected unchanged and green, **verified not assumed**. Evidence:
`living-memory/TEST_LEDGER.md` + `qa/sim-runs/last-sim-run.json`.

---

## 4. Non-goals

| Not doing | Why |
|---|---|
| **A-16 — `'anchor'` never unlocks.** The wizard writes `'anchor'`, which is unhandled by the ladder and falls to the trio branch, so an anchors-only user can never unlock. | Out of scope by `hld.md` §9 LLD-1 ("must not … fix A-16/A-17"). P0-1's `allow_over=("anchor",)` exception makes the *ordering* harm impossible (an anchor answered before Quick Set no longer pins the user), but an anchors-only board still does not unlock. Belongs on `NEXT.md`, not here. |
| **A-17 — `'manual'` unlocks unconditionally**, with no evidence requirement. | Same. Widening or narrowing the ladder is a behaviour change to every method, not a bug fix to one. |
| Any other change to the unlock ladder (`server.py:6163-6175`). | The fix removes a wrong *input* to the ladder; touching the ladder itself would make the blast radius every user rather than the stuck cohort. |
| A feature flag / rollback knob over the point-of-use writes. | Its OFF position is the known bug (S-04). §6 has the honest levers. |
| A new analytics event for implicit writes. | NFR-4. If `an-data-architect` wants an implicit-write signal it needs a **new** name registered server-side first (default-deny taxonomy) — and this batch's taxonomy commit (commit 1) is already closed by S-36. |
| Onboarding sub-flags. | P0-9, operator's call. |
| Preserving the pre-fix `4/4-locked` capture as a `--historic` frame (`plan-p0-1.md` Q6). | S-07 settles it: re-captured, not preserved. |
| Backfilling *which method a user actually used*. | Unknowable retroactively. The `'quickset'` label is an explicit recorded assumption (§8). |

---

## 5. Docs rows W3-DOCS executes

No build agent edits `docs/**` or `living-memory/**` (`hld.md` §4 Wave 3). These are
P0-1's rows of the §7 rollup, supplied here as the source of content. **Ids are
`hld.md` §10.4's, not the plan's stale `D-011`.**

| Doc | Row |
|---|---|
| `docs/data-dictionary.md` `:105` | `users.ranking_method` — (a) correct the stale value set: it lists `null / 'trio' / 'manual' / 'tiers'` and omits **`'anchor'`** (2026-07-10) and **`'quickset'`** (#119), both shipped and both accepted by `POST /api/ranking-method`; (b) add the write contract: *written implicitly at first use by `/api/tiers/save`, `/api/rank3`, `/api/rankings/reorder`, `/api/anchor/save` — first-use wins, `'anchor'` upgradable by a completeness-marking tiers/quickset save; rookie-scope saves, `via:'rookie_ranks'` reorders and `via:'draft_room'` anchors write nothing*; (c) note the one-time backfill to `'quickset'` for pre-fix all-four tier boards, which also pre-seeds `unlocked_formats`. Column itself unchanged. |
| `docs/api-reference.md` | **Behavioural note, no shape change.** `/api/rankings/progress`: `ranking_method` is now non-null for anyone who has taken a ranking action, and `unlocked` for tier-based users no longer depends on having visited the chooser. Annotate the four save routes (`/api/tiers/save`, `/api/rank3`, `/api/rankings/reorder`, `/api/anchor/save`) with the side effect and its exclusions. State explicitly that no route, request field, or response key was added, removed or renamed. |
| `docs/cross-client-invariants.md` `:205` | Ranking-method strings: the string **set** is unchanged; the **contract** shifts from *"the chooser records the user's preference"* to *"written at the point of use, first-use wins, `'anchor'` upgradable by a completeness-marking tiers/quickset save"*. Both backend and web read this value (`web/js/app.js:866` reads it for truthiness only), which is why it belongs here. |
| `docs/runbook.md` | New operational note: the backfill runs at boot inside `_migrate_db()` (`database.backfill_ranking_method_from_tiers`); what it touches (`ranking_method` + `unlocked_formats`, cohort = unset method **and** all four positions saved in ≥1 format); expected one-time row count; the confirming query `SELECT count(*) FROM users WHERE ranking_method IS NULL AND tiers_saved IS NOT NULL`; the affected ids are printed to the boot log (`[backfill] ranking_method: …`) and that log line is what makes the §6 undo expressible; the reversal SQL; and the **seed-fixture interaction** — it rewrites the seeded `quickset-done` user on every UI-test boot, which is why the fixture ships already in the post-backfill shape. |
| `living-memory/LLD.md` | Two conventions: implicit column writes from save handlers, and the `set_ranking_method_if_unset(…, allow_over=…)` conditional-write idiom (single-statement, race-free, first-use-wins, returns "did I write"). |
| `living-memory/DECISIONS.md` | **D-025** — first-use-wins over last-use-wins (the re-lock hazard already documented at `server.py:6177-6183`); the single `'anchor'` → tiers/quickset upgrade and why it is strictly improving; the rookie-scope / `rookie_ranks` / `draft_room` exclusions; backfilling to `'quickset'` rather than `'tiers'` and the labelling assumption that carries; startup migration over lazy on-read repair or a one-shot script; and the **suppressed fan-out** with its permanent consequence (§8). |
| `screens/CLAUDE.md` | Index entry follows the capture rename `league__progress-ring--4-4-locked` → `--4-4-unlocked`. |
| `mobile/src/components/CLAUDE.md` | Register `rank.unlocked-banner` in the testID registry. **Documentation only** — `testid-lint.sh` greps `mobile/src` and never opens this file (`hld.md` §10.3), so it is not a build-time dependency. |
| `living-memory/CHANGELOG.md` | Batch entry names the user-visible change: *Quick Set users now unlock the Trade Finder when their board is complete — including retroactively, without a notification burst.* |
| `living-memory/TEST_LEDGER.md` | The tier-1 run, the **pre-fix control run**, and which push-primer check was used (permission-reset simulator vs. the `unlocked:true` network proxy). |
| `docs/architecture.md`, `living-memory/HLD.md`, `docs/glossary.md`, `docs/config-reference.md`, `living-memory/DEPENDENCIES.md` | **n/a** — no module wiring or data-flow change; no new module/client/major flow; no new domain term; no env var, `config/features.json` key or `model_config` key; no dependency added, bumped or removed. |
| `living-memory/GOTCHAS.md` | **Conditional** — only if the build loses >30 min to something new. The known trap (a startup backfill mutating seeded UI-test fixtures) is covered by the runbook row. Next free id is **G-027**, and `hld.md` §7 already assigns G-027…G-029 to P0-2/P0-6/P0-8-9, so W3-DOCS allocates any P0-1 entry after those. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** — the audit is a dated artifact. Record the outcome in `CHANGELOG.md`; do not rewrite it. |
| Root `CLAUDE.md` | Correct the stale "next ID" columns (`D-011`/`G-013`) — `hld.md` §10.4. Five plans copied the wrong ids from it; the next batch of parallel agents will make the identical mistake otherwise. |

---

## 6. Rollback

**There is no flag, by design.** A flag over the point-of-use writes would ship a
knob whose OFF position is the known bug (S-04). The levers, in order of preference:

1. **`git revert` the commit.** Commit 2 is deliberately not squashed with commit 1
   (`hld.md` §3) precisely so it is separately revertible. The point-of-use writes
   stop on the next Render deploy. **Rows already written are correct data, not
   damage** — every one of them records a ranking action the user genuinely took,
   and after a revert they simply behave as they did before the fix for the
   *chooser* path (the ladder is unchanged).

2. **A scoped SQL undo for the backfill only.** The backfill is **one-way and
   idempotent**: it writes `ranking_method` and appends to `unlocked_formats`, and
   nothing in this design ever unsets either. That is acceptable because:
   - Every row it touches is one for which the tiers branch returns `True`, so the
     unlock it produces is `≥` whatever the pre-fix answer was. It cannot subtract.
   - `unlocked_formats` is **monotonic by contract** already
     (`mark_format_unlocked`, `database.py:3862-3864`) — the backfill writes it the
     same way every unlock does, so it introduces no new class of state.
   - It is idempotent by predicate, so a re-deploy, a restart loop, or a rollback
     followed by a roll-forward all converge on the same rows.

   If it must be undone, the boot log's cohort list (**FR-12**) makes it a single
   scoped statement:

   ```sql
   UPDATE users SET ranking_method = NULL
    WHERE ranking_method = 'quickset'
      AND sleeper_user_id IN (<ids from the [backfill] ranking_method log line>);
   ```

   `unlocked_formats` is deliberately **not** reversed: removing a format would
   break the monotonic contract that `get_rankings_progress` relies on, and leaving
   it is harmless (it only ever prevents a *duplicate* unlock transition).

3. **If the operator wants a knob anyway** (`plan-p0-1.md` Q2), the honest one is
   over the *backfill*, not the writes: a `model_config` key
   `migrations.ranking_method_backfill_enabled` read inside
   `backfill_ranking_method_from_tiers`. **Not built** — recommendation is no knob,
   and this is the operator's call to reopen.

**What a revert does NOT undo:** rows already tagged (see lever 2), and the
`ranking_complete_first_time` gap for the backfilled cohort (§8) — `was_first` is
spent per user and cannot be un-spent.

---

## 7. Pre-merge checklist

Operator/orchestrator items. None is a build task; **the first is blocking.**

| # | Item | Blocking? |
|---|---|---|
| **1** | **Confirm no live experiment targets `ranking_method`.** It is a registered account-scope targeting attribute (`backend/experiments.py:59`, hydrated at `:258`), and this change plus the backfill collapses most of the NULL bucket into `'quickset'` — an experiment targeting it would see its eligible population move mid-flight. One authenticated prod call: `GET /api/admin/experiments` with the `CRON_SECRET` from `secrets.local.env` (never pasted into chat); confirm no definition's targeting references `ranking_method`. **S-05 closed the known case** — the only live experiment is `onboarding_v2_rollout`, which is **device-unit** and therefore structurally cannot target an account-scope attribute (FR-33b) — so this is cheap insurance against a new experiment being started mid-build. | **Yes** |
| 2 | **Dry-run the backfill cohort against a prod replica** and eyeball a handful of affected users: import `backfill_ranking_method_from_tiers` in a REPL pointed at a replica, or run `SELECT count(*) FROM users WHERE ranking_method IS NULL AND tiers_saved IS NOT NULL`. Records the expected one-time row count before it happens in prod (R7). | No — recommended |
| 3 | **Pre-fix control run** recorded: the new Maestro flow fails on the unfixed tree (R5). | Yes |
| 4 | Push-primer manual check on a permission-reset simulator, or the recorded proxy, in `TEST_LEDGER.md` (waiver W-1). | No — needs the ledger line |
| 5 | Operator sign-off on the waiver register in `scope-p0-1.md` (W-1…W-5). Q1 (`'anchor'` upgrade) is **settled** by S-01; Q5 (fan-out suppression) is **settled** by S-03; Q6 (preserve the historic capture) is **settled** by S-07. Q2 (no knob) and Q3 (no event) remain recommendations. | No |

---

## 8. Known, accepted consequences

| # | Consequence | Disposition |
|---|---|---|
| **C-1** | **The backfilled cohort never emits `ranking_complete_first_time`** — not now (suppressed) and not later, because `was_first` is `len(unlocked_formats) == 0` and the pre-seed spends it permanently, including for a genuine later unlock in the user's second scoring format. | Accepted price of S-03. Anyone reading that event as an unlock funnel must exclude the backfilled cohort; the boot log names its ids and D-025 records it. |
| **C-2** | **Analytics discontinuity.** Method-segmented series show a step change across the deploy boundary: the NULL bucket collapses and `'quickset'` jumps. | `hld.md` R16. CHANGELOG + D-025. There is no way to backfill "which method did they actually use" retroactively. |
| **C-3** | **The `'quickset'` label is an assumption.** `'quickset'` and `'tiers'` are behaviourally identical at the ladder (`server.py:6165`); the label is chosen because the default route lands on QuickSetTiers, so the overwhelming majority of NULL-method tier boards were built there. | Recorded in D-025 (waiver W-5). |
| **C-4** | **Retroactive unlock is user-visible without warning**: stuck users find the push primer, the payoff banner, and an `Unlocked` badge waiting at their next launch. | That is the fix working. Named in the CHANGELOG rather than discovered. |
| **C-5** | **Residual re-lock risk, effectively unreachable.** A pre-fix NULL-method user with 40 trio interactions who then does a full Quick Set save is tagged `'quickset'` and re-evaluated on the tiers branch. The monotonic floor (`:6177-6187`) carries them — *unless* they never once polled `/api/rankings/progress` while qualified, so the floor was never persisted. `RootNav` polls that endpoint at the root of the authed tree, so this requires never having had the app open while qualified. | Covered by T-23; noted in the ledger. |
| **C-6** | **Incidental web-client changes, benign.** `web/js/app.js:856-870` stops offering the ranking-method chooser to a user who already has a method (more correct); `:5173` shows `Signed up · ranking` for backfilled leaguemates (more accurate, and usually superseded by the `Unlocked` branch). | No action. |
| **C-7** | **`board_data_summary.any`** (`backend/accounts.py:484-511`) is computed partly from `ranking_method` and drives the link-Sleeper merge-choice prompt. Every user this change touches already had `swipes`/`tiers_saved`/`tier_overrides` set — the action that writes the method also wrote board data — so `any` was already `True`. | No behaviour change expected. One assertion in `test_accounts.py` if it is cheap; otherwise verified by that suite staying green. |
| **C-8** | **The seeded UI-test backend gains `member_rankings` rows for `qa_quickset`** as a side effect of the fixture's `unlocked: true` (`seed_ui_test_db.py:1093-1099`). | Deliberate and more faithful — production `/api/tiers/save` publishes `member_rankings` on every save. No test asserts that count for this profile. Eyeballed in the mandatory capture re-run. |
