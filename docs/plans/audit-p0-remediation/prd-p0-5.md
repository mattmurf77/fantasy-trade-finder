# PRD — P0-5: Apple account-only sign-in reaches a platform/league choice

> Product requirements for audit finding **P0-5**, built by `W1-P05` in wave 1
> (commits **6** and **7**). Implementation detail lives in
> [`lld-p0-5.md`](lld-p0-5.md); the binding batch design is [`hld.md`](hld.md);
> source plan [`plan-p0-5.md`](plan-p0-5.md), scope block [`scope-p0-5.md`](scope-p0-5.md).
>
> **Audit acceptance criterion (verbatim):** *a brand-new Apple sign-in reaches a
> platform/league choice without visiting Settings.*
>
> **Express lane: not declared. Full gates apply** (root `CLAUDE.md` — agents never
> self-select express; HLD S-46).

## Contents

- [1. Problem](#1-problem)
- [2. Users and scope of impact](#2-users-and-scope-of-impact)
- [3. Requirements](#3-requirements)
- [4. Acceptance criteria](#4-acceptance-criteria)
- [5. Non-goals](#5-non-goals)
- [6. The P0-3 hand-off contract](#6-the-p0-3-hand-off-contract)
- [7. Measurement](#7-measurement)
- [8. Docs impact](#8-docs-impact)
- [9. Rollback](#9-rollback)
- [10. Open items carried to the operator](#10-open-items-carried-to-the-operator)

---

## 1. Problem

A user who signs in with Apple and has no linked Sleeper account gets a **real, verified
session** with a **sentinel league** — `league_id = "no_league"`, name *"No league
linked"* — minted by `_mint_account_only_session` on the server. The client pins both and
then routes straight to the tabs.

Every league surface behind those tabs is empty, and nothing on any of them says why or
what to do. The only escape is Settings → Account → "Link your Sleeper username" (or the
ESPN / MFL rows), which a first-time user has no reason to open. Under `release` flags
(`onboarding.landing: false`) the official Apple button is the **primary** control on the
sign-in screen, so this is not a corner: it is the front door.

Two things the audit did not surface, both found during planning and both part of the
fix:

1. **Relaunch.** The routing predicate treats the sentinel as a real league, so a cold
   start after the first bad run lands on the tabs again. A one-line routing fix would
   have repaired the first sign-in only — and would have left every already-stranded
   TestFlight user stranded.
2. **The picker produces a false error for these users.** It asks Sleeper about the
   synthetic `acct_<id>` key: live that returns nothing ("No 2026 NFL leagues found for
   this account"), and under the hermetic test harness it 503s ("Couldn't reach Sleeper —
   try again shortly"). Routing users there without changing it trades *empty tabs* for
   *blaming Sleeper*.

## 2. Users and scope of impact

- **Affected:** sessions with `account_only === true` **or** a pinned `no_league`
  sentinel — Apple sign-ins with no bound Sleeper source. 100% of them are broken today.
- **Not affected:** Sleeper-keyed sessions, demo sessions (they pin a real synthetic
  league), and account-only users who have already linked an ESPN/MFL league (their
  league is real, so nothing about their routing changes).
- **Visible change for existing testers:** anyone currently sitting on empty tabs with a
  sentinel league lands on the picker at their next launch. That is the fix working, and
  it gets a release-notes line (HLD §8 R10).

## 3. Requirements

### Functional

| # | Requirement | Rationale / authority |
|---|---|---|
| **FR-1** | An account-only sign-in routes to **LeaguePicker**, not `Main`, via `replace` (no back edge to a spent sign-in screen). | The acceptance criterion; HLD §1.3. |
| **FR-2** | Post-auth routing on **every launch** keys off `league.league_id === NO_LEAGUE_ID`, **never** off `user.account_only`. | **S-22.** `account_only` stays true after an ESPN/MFL link, so an `account_only` predicate would trap a well-provisioned user in the picker forever. |
| **FR-3** | A session holding the sentinel lands on LeaguePicker at cold start, and stops doing so the moment a real league is pinned. | Makes the fix retroactive for already-stranded users; `setLeague(real)` overwrites the sentinel and the guard retires itself. |
| **FR-4** | The picker **never** calls `GET /api/sleeper/leagues/<id>` for an account-only user; the ESPN/MFL/Fleaflicker merges still run. | Removes the false 503 / "no leagues found". The merges must run — an account-only user who linked ESPN from Settings has leagues to list. |
| **FR-5** | With an account-only session and zero leagues, the picker renders a **companion state**: header "Connect a League", body *"Connect Sleeper, ESPN or MFL to see your leagues."*, and one button per available platform (Sleeper, ESPN, MFL, Fleaflicker-when-flagged). | The handoff copy; HLD §1.3. |
| **FR-6** | The ESPN / MFL / Fleaflicker buttons open the **existing** `EspnLinkSheet` / `PlatformLinkSheet` through the **existing** handlers. No link flow is rebuilt. | Those flows are audit-graded A−/B+; the finding is about reachability, not about linking. |
| **FR-7** | Sleeper is offered **on the picker**, not by bouncing the user to Settings — via a `LinkSleeperSheet` extracted from `SettingsScreen` and shared by both screens. | **S-20.** The alternative ships copy that offers Sleeper and then routes to the screen this finding is about. |
| **FR-8** | The extraction is **verbatim**, including the 409 `merge_choice_required` two-boards Alert and the `sleeper_already_claimed` case; Settings' behaviour after it is identical (same copy, same Alert, same `replace('LeaguePicker')`). | HLD §8 **R8** — the moved code's failure mode is *deleting the wrong ranking board*. |
| **FR-9** | The footer link row is suppressed **in the companion state only**; loading, error and list states render it exactly as today. | Otherwise the same three buttons render twice on one screen; and no existing capture or flow may move. |
| **FR-10** | The **non-account-only** empty state is unchanged, character for character. | `capture/leagues@fresh.yaml` asserts its literal sentence and is a must-pass-unmodified control (HLD §6 row 13). |
| **FR-11** | After an ESPN/MFL link the user reaches `Main` with the league active; after a Sleeper-username link the picker repaints in place with the real league list. | Uses the existing `onLeagueLinked → pickLeague → setLeague → replace('Main')` wiring and the existing `[user?.user_id]` effect; **no new post-link plumbing**. |
| **FR-12** | The picker's companion state accepts **optional** `invitedBy` / `invitedLeagueName` and forks its body copy when they are present. Nothing supplies them in wave 1. | **S-17** — this is P0-3's landing surface; P0-5 must ship the seam even though it is unused until commit 12. |
| **FR-13** | A Maestro flow drives a brand-new Apple sign-in end to end, via a harness seam whose only gates are the two pre-existing production kills (`FTF_TEST_MODE` server-side, `IS_TEST_BUILD` client-side). No new route, no new flag, no new env var. | **S-21 / waiver W-1.** A real Apple sign-in is undrivable by Maestro; everything after the credential substitution is production code under test. |

### Non-functional

- **NFR-1 — no new feature flag** (waiver **W-3**). This is a bug fix on a branch broken
  for 100% of its users; a flag's OFF position would be the known bug. Per-platform
  rollback stays where it already is (`espn.link`, `mfl.link`, `fleaflicker.link`).
- **NFR-2 — no new analytics event.** The taxonomy is default-deny and commit 1 registers
  nothing for P0-5; the funnel is already bracketed (§7).
- **NFR-3 — no schema, no API contract, no server product code.** The only backend change
  in P0-5's name is the harness seam, which is `FTF_TEST_MODE`-only and is built by
  `W1-BE`.
- **NFR-4 — the production diff of the harness seam is provably empty.** `TEST_APPLE_SUB`
  is `null` in every non-test bundle, and a pytest asserts the server half **401s** with
  `FTF_TEST_MODE` unset.
- **NFR-5 — no dependency added, bumped, or removed** (`mobile/node_modules` is a
  symlink; `npm install` is unavailable to this build).

## 4. Acceptance criteria

**A-1 (the audit's, unstubbed).** A brand-new Apple sign-in reaches a platform/league
choice **without visiting Settings**. Automated by
`mobile/.maestro/flows/p0-5-account-only-picker.yaml` legs 1-2 (`signin.apple-btn` →
`leagues.empty.link-espn` + `leagues.empty.link-sleeper` + `leagues.empty.link-mfl` +
`.*Connect Sleeper, ESPN or MFL.*`); confirmed on a real Apple ID in the TestFlight pass.

**A-2 (relaunch).** Force-quit and relaunch **before** linking anything lands on the
picker, not on the tabs. Flow leg 4 (`clearState: false`); `assertNotVisible tab.trades`.

**A-3 (already-stranded users are rescued).** A session that already holds the `no_league`
sentinel from a previous launch is routed to the picker on its next cold start with no
sign-out, reinstall, or migration. Same evidence as A-2 (the relaunch leg boots from
persisted state); confirmed manually against an existing TestFlight account-only account.

**A-4 (no false error).** The companion state is asserted from both sides: no
`leagues.row.*`, no *"No 2026 NFL leagues found"*, no *"Couldn't reach Sleeper"*, and no
`tab.trades`.

**A-5 (Settings is unbroken after the extraction).** `capture/settings.yaml` passes
unmodified; Settings' Sleeper card renders identically; linking from Settings still ends
on the picker; and the **409 two-boards Alert works from both entry points** — Settings
and the picker — with both choices behaving identically. (Manual; this is R8's only real
exposure.)

**A-6 (nothing else moved).** `capture/leagues@fresh.yaml`, `flows/smoke/01-signin.yaml`
and `flows/smoke/02-league-pick.yaml` pass **unmodified**, and the full 11-flow smoke
suite is green at tier 1.

**A-7 (post-link continuity).** After linking ESPN from the companion state the user
reaches `Main` with tabs populated and a **writable** board — i.e. `/api/session/init`
reused the session token and preserved `verified` / `verified_via='apple'`. Pinned by
`test_account_only_harness.py` and verified once on device.

## 5. Non-goals

- **Fixing the tabs' empty states.** After this fix no user reaches them by any normal
  path; the empty league surfaces stay exactly as they are.
- **A skip affordance.** Explicitly rejected — "Skip for now" rebuilds the stranding one
  tap further in. The header's existing **Sign out** is the only exit.
- **A non-dismissible sheet over `Main`** (the resolutions doc's alternative). Rejected:
  it puts an inescapable modal in front of a first-time user, over a tab bar whose
  emptiness it does not fix, using the exact iOS RN modal-stacking mechanism that has
  already wedged this screen once.
- **Landing-page platform selection before an account exists.** Not buildable:
  `/api/espn/link` and `/api/mfl/link` both 401 without a session.
- **Pinning an invited Sleeper league for an account-only user.** Not possible as built —
  an `acct_` user has no roster in that league (§6).
- **Automating the link→`Main` completion leg.** Waiver **W-2**: live ESPN/MFL egress is
  forbidden by the hermetic rails audit and no fixture exists. Manual TestFlight covers it.
- **New instrumentation.** `platform_link_started {platform, entry}` is the event worth
  having and is deferred to P0-7's backlog — register the name server-side first.
- **Hardening the notification-tap door into `Main`.** It would be dead code with no way
  to test it (every push is league- or match-scoped; these users have neither).
- **Touching `useSession.ts`, `LeagueScreen.tsx`, `deepLinks.ts`, the analytics
  registries, or any `docs/` / `living-memory/` file.** Other agents own them.

## 6. The P0-3 hand-off contract

P0-3 (invite loop) lands **after** P0-5 and rebases onto it (**S-19**). These are the
invariants P0-5's landed code guarantees, stated so neither agent assumes the other
handled it.

**C-1 — Sentinel semantics are the routing contract.** Post-auth routing keys off
`league.league_id === NO_LEAGUE_ID` and nothing else. Consequences for P0-3:

- An invited league must be pinned through **`setLeague()`**, which overwrites the
  sentinel. **P0-3 must not introduce a parallel "invited league" field** that marks a
  user as provisioned without clearing the sentinel — such a user would be bounced back
  to the picker on every cold start, forever.
- Conversely, P0-5's guard will never fight a correctly pinned league: once `setLeague`
  holds a real id, `initialRoute` resolves to `Main` on every launch.

**C-2 — The companion state is P0-3's landing surface, and it already exists.**
`LeaguePickerScreen` accepts optional `invitedBy?: string | null` and
`invitedLeagueName?: string | null`. When `invitedBy` is present the body copy becomes
*"@matt invited you to Lakeview Dynasty. Connect Sleeper, ESPN or MFL to join."*, and
degrades to *"their league"* when the league name is unavailable — so the invite banner
is correct **without** `GET /api/league/invite-meta` succeeding.

**C-3 — The wiring is already in place; P0-3 only navigates.** `RootNav`'s `AuthStack`
types `LeaguePicker: { espnLink?: boolean; invitedBy?: string; invitedLeagueName?: string
} | undefined`, and the `LeaguePicker` screen element already passes both params into the
screen. P0-3's case D is therefore one call:
`navigation.replace('LeaguePicker', { invitedBy, invitedLeagueName })`.

**C-4 — Do not attempt to pin an invited Sleeper league for an `acct_` user.** An
account-only user has no Sleeper user id and is not a member of that league;
`buildSessionInitBody`'s Sleeper branch would find no roster and produce an empty
`user_player_ids`. Case D is: hold the intent, route to the companion state, let the
invite become the strongest copy on the screen. If the user then links Sleeper and is
genuinely in that league, P0-3's auto-pin effect (keyed on `cached`) fires on the
refreshed list **with no extra code** — because P0-5's Sleeper-link handler deliberately
re-populates `cached` in place rather than navigating away.

**C-5 — The harness seam is shared and already landed.** `testRouteEntry.ts` exports
`IS_TEST_BUILD`, `testLaunchArg(name)` and an allowlist-driven
`applyTestRouteEntry(ref, { authed })`. P0-3's signed-out `LeagueJoin` entry (M12) is
**already allowlisted** and becomes live the moment commit 12 registers the route. P0-3
adds no gate, no launch-argument accessor, and no `/__test__` route.

**C-6 — File hand-over.** `RootNav.tsx`, `LeaguePickerScreen.tsx` and `SignInScreen.tsx`
belong to `W1-P05` in wave 1 and to `W2-P03` in wave 2. P0-3 re-greps its anchors after
the rebase; every P0-5 edit is small and well-separated from P0-3's regions (the route
table, the sign-in banner, the auto-pin effect).

## 7. Measurement

No new events. The stranded population is measurable identically before and after, as
the gap between two events that already fire:

| Event | Where | Question |
|---|---|---|
| `signin_succeeded {method:'apple'}` | `SignInScreen`, inside the account-only branch itself | how many users enter this branch |
| `league_selected {league_index, league_count, auto, league_type}` | `LeaguePickerScreen.pickLeague` — fires for **imported** ESPN/MFL leagues too, via `onLeagueLinked → pickLeague` | how many end up with a real league |

Post-ship read: the apple `signin_succeeded` → `league_selected` conversion should rise.
`screen_viewed` already fires for every route including `LeaguePicker` (HLD §10.1), so
the "reached the choice" step is readable today without any new instrumentation.

Deferred: `platform_link_started {platform, entry: 'picker_empty' | 'settings'}` would
separate *never saw the choice* from *saw it and declined* — the one thing the gap metric
cannot do. Owner: P0-7's backlog; **register the name in `analytics_taxonomy.py` before
wiring any call.**

## 8. Docs impact

Every row is owned by **`W3-DOCS`** (wave 3); P0-5 supplies content. Full table in
[`lld-p0-5.md` §12](lld-p0-5.md#12-docs-rows-supplied-to-w3-docs).

| Doc | Updated? | Why / why not |
|---|---|---|
| `docs/cross-client-invariants.md` | **yes (small)** | `no_league` is a cross-client constant (server emits, mobile consumes, now load-bearing in routing) and is documented nowhere. |
| `docs/glossary.md` | **yes** | **account-only session** — the term is used throughout backend and mobile and appears in no glossary. |
| `docs/runbook.md` | **yes** | The `FTFTestAppleSub` / `ftf-test-apple:<sub>` seam and both production gates, under the mobile UI-test harness section. |
| `living-memory/LLD.md` | **yes** | Sentinel-not-flag routing convention; `LinkSleeperSheet` as the single owner of the Sleeper-link form. |
| `living-memory/DECISIONS.md` | **yes — `D-028`** | Not `D-011`: root `CLAUDE.md`'s next-id column is stale (HLD §10.4). |
| `screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md` | **yes** | New capture + frame; new component row; five new `leagues.empty.*` testIDs. |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md` | **yes, at ship** | Behaviour change users will notice + tier-1 sim evidence. |
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed; the harness seam is unreachable in any deployed build → runbook instead. |
| `docs/architecture.md`, `living-memory/HLD.md` | **n/a** | No module wiring or data-flow change. |
| `docs/data-dictionary.md`, `docs/config-reference.md`, `living-memory/DEPENDENCIES.md` | **n/a** | No schema, no flag, no dependency. |

## 9. Rollback

**P0-5 ships unflagged (NFR-1 / waiver W-3), so rollback is `git revert` of the commit —
there is no runtime switch and deliberately so.**

| Scenario | Action | Blast radius |
|---|---|---|
| The fix itself is wrong | **`git revert` commit 7** ("P0-5: account-only routes to LeaguePicker; …"). Restores `replace('Main')`, the sentinel-blind predicate, the unconditional Sleeper fetch, today's empty state, and the inline Settings form. | Returns to the known bug. Commit 6 (harness) can stay — it is inert without commit 7. **Must be reverted before commit 12** (P0-3) or that commit's companion-state props lose their target; after wave 2 a revert is a manual conflict resolution, which is the honest cost of an unflagged fix. |
| Only the extraction is wrong | Revert the `SettingsScreen` / `LinkSleeperSheet` hunks and point the picker's Sleeper button at Settings' account section (~5 lines, the plan's D-1 fallback). Keeps FR-1…FR-6 and FR-9…FR-11. | Ships copy that offers Sleeper and then bounces the user — degraded, not broken. |
| A single platform's link flow misbehaves | **No revert.** Turn off `espn.link` / `mfl.link` / `fleaflicker.link`; that platform's button disappears from both the companion state and the footer. | Per-platform, deploy-free — the rollback lever the design deliberately keeps. |
| The harness seam is implicated in anything | **`git revert` commit 6** (and W1-BE's commit 4 for the server half). The only cost is losing automated coverage of A-1/A-2; the fix itself is untouched. | Zero — both halves are inert in production by construction. |

**Not offered:** an `auth.account_only_picker` kill switch (scope §6 **D-2**,
recommendation *no*). Its OFF position is the bug, and shipping a flag whose off-state is
a known defect adds a way to reintroduce it. If the operator wants one anyway, the only
coherent shape is default-**ON**, gating **only** the two `RootNav` routing changes —
that is the sole pair with a definable "old behaviour", and it must be requested before
build, not retrofitted.

## 10. Open items carried to the operator

1. **D-1 (decided, recorded):** extract `LinkSleeperSheet` vs. route to Settings — HLD
   **S-20** approves the extraction. Restated here only because it is the one place where
   "surgical changes" and the acceptance criterion pull in opposite directions.
2. **W-1 / W-2 / W-3** (harness seam / unautomated completion leg / no new flag) are
   approved in the HLD and carried in the final report's waiver list.
3. **Severity is flag-dependent.** With `onboarding.landing: false` (release today) the
   Apple button is the sign-in screen's primary control, which is what makes this branch
   high-traffic. If that flag is ever flipped on — live P0-9 territory — the Apple entry
   degrades to a text link framed *"Already have an account?"*, so the branch becomes
   rarer for new users and simultaneously **harder to discover** for the returning ones
   who need it. The fix is correct either way; the *priority* is not flag-independent,
   and the audit did not record this.
4. **Release note required:** existing account-only testers will land on the league
   picker at their next launch instead of on the tabs.
