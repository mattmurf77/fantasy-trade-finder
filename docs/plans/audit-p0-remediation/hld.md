# HLD — P0 remediation batch (2026-08-09 mobile UX audit)

> High-level design binding the seven per-finding plans in this directory into **one
> buildable branch**. Authored against worktree `ftf-p0-remediation`, branch
> `p0-remediation-2026-08-10`, off `origin/main @ ab9368f`.
>
> **This document is the authority on:** batch composition, settled decisions, commit
> order, build-agent file ownership, the shared harness seam, the Maestro/doc rollups,
> and what each downstream LLD agent may and may not touch. Where a per-finding plan
> disagrees with this document, **this document wins** — the plans were written in
> parallel and several of them make claims about shared files that do not survive
> reconciliation (§10 lists every one).
>
> **Source plans:** `plan-p0-1.md`, `plan-p0-2.md`, `plan-p0-3.md`, `plan-p0-5.md`,
> `plan-p0-6.md`, `plan-p0-7.md`, `plan-p0-8-9.md` + the seven `scope-*.md` twins.
> **Source brief:** `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md`.
> **Conventions:** root `CLAUDE.md` (full gates — no express declared), `docs/CLAUDE.md`,
> `mobile/.maestro/README.md` flow-authoring laws 1-23, `docs/runbook.md` § Pre-ship
> simulator gate.

## Contents

- [1. Batch architecture](#1-batch-architecture)
- [2. Settled decisions](#2-settled-decisions)
- [3. Commit sequencing](#3-commit-sequencing)
- [4. Build-wave partition — exclusive file ownership](#4-build-wave-partition--exclusive-file-ownership)
- [5. The unified harness seam](#5-the-unified-harness-seam)
- [6. Maestro delta inventory](#6-maestro-delta-inventory)
- [7. Docs impact rollup](#7-docs-impact-rollup)
- [8. Risk register](#8-risk-register)
- [9. LLD assignments](#9-lld-assignments)
- [10. Conflicts resolved here, and plan errors found by spot-check](#10-conflicts-resolved-here-and-plan-errors-found-by-spot-check)

---

## 1. Batch architecture

### 1.1 What the eight fixes actually are

Seven audit findings, eight units of work (P0-8 and P0-9 travel together but are a
build and a validation pass respectively).

| # | Finding | Layer | Blast radius | Flagged? |
|---|---|---|---|---|
| P0-1 | Quick Set never unlocks | Backend only (+1 mobile `testID`) | Every user with a tier board | No |
| P0-2 | Failed trade search ≡ never searched | Mobile, one screen + `Toast` | Trades deck slot | No |
| P0-3 | Invite loop broken at both ends | Backend routes + mobile routing/state | Deep-link + sign-in surface | Emitter only (`growth.invite_join_link`, default OFF) |
| P0-5 | Apple account-only strands users | Mobile routing + one screen + one extraction | `account_only` sessions only | No |
| P0-6 | Matched ESPN users have no action | Mobile component + 4 mounts | Non-Sleeper leagues only | Rides `trade.send_in_sleeper` |
| P0-7 | Analytics blindness | Server taxonomy + mobile instrumentation | Metric definitions, zero UI | Rides `analytics.client_events` + `analytics.ingest` |
| P0-8 | Tour signs off before teaching | Mobile, 2 files | Guided-avatar path | No |
| P0-9 | First-session test prep | Validation + 2 client defect fixes (D1/D2) | Nothing shipped; no flag defaults change | No |

Three of the eight are **pure backend** or **pure server-registry** work (P0-1, P0-7's
taxonomy half, P0-3's route half). Five are mobile. That split is what makes a
three-wave partition possible at all.

### 1.2 The two shared subsystems

Everything in this batch composes cleanly **except** where it crosses one of two spines.
These are the only places where two findings can corrupt each other's semantics rather
than merely each other's diff.

#### Spine A — the auth / routing spine (P0-3 + P0-5, with P0-1 downstream)

```
SignInScreen ──► RootNav.initialRoute ──► LeaguePicker ──► Main (TabNav)
     ▲                    ▲                    ▲
     │                    │                    │
 P0-3 M10            P0-5 (b) sentinel     P0-5 (c) companion state
 invited banner      predicate             P0-3 M9 auto-pin effect
     │                    │
 P0-5 harness         P0-3 M8 LeagueJoin
 (FTFTestAppleSub)    root-stack registration + M12 signed-out entry
```

Three shared files: `RootNav.tsx`, `LeaguePickerScreen.tsx`, `SignInScreen.tsx`
(plus `useSession.ts`, which only P0-3 writes to).

The **semantic** contract between them — not just the textual one — is:

1. **P0-5 owns the routing predicate.** It keys off `league.league_id === NO_LEAGUE_ID`,
   never off `user.account_only`. P0-3 must never introduce a parallel "invited league"
   field that pins a league without going through `setLeague()`; if it did, P0-5's
   relaunch guard would bounce the user back to the picker forever.
2. **P0-3 owns the invite intent, and it must be persisted.** `LeaguePickerScreen`'s
   auto-pin effect keys on `cached`, so it re-fires the moment a platform link
   populates the list. That is what makes the account-only + invited intersection work
   without either fix knowing about the other — *provided* the intent survives the
   several launches an account-only user may take before linking. Hence the
   `ftf_invite_intent` AsyncStorage blob with a 14-day TTL.
3. **P0-5's companion state is P0-3's landing surface.** An account-only session that
   arrives via `LeagueJoin` does not get the generic picker: it gets P0-5's companion
   state carrying inviter + league context ("**@matt** invited you to Lakeview Dynasty —
   connect Sleeper, ESPN or MFL to join"). This is adjudicated and is a *joint*
   deliverable: P0-5 builds the state and accepts optional `invitedBy` / `invitedLeagueName`
   props; P0-3 supplies them.
4. **P0-1 is downstream, read-only.** It reads `RootNav.tsx:267` (`pushEnabled`) as its
   acceptance proxy and edits nothing on this spine.

**Why P0-5 lands first:** its change is smaller, its routing decision is a
*precondition* for P0-3's account-only path being reachable at all, and its companion
state is the surface P0-3 renders into. P0-3 rebases.

#### Spine B — the analytics spine (P0-7 + P0-3's events + P0-8/9's D2)

```
                    backend/analytics_taxonomy.py          ← COMMIT 1, single owner
                    ALLOWED_CLIENT_EVENTS
                    SERVER_FIRED_EVENTS      default-deny; unknown = counted-and-dropped, 200 OK
                    CLIENT_EVENT_PROPS       missing row = ValueError at import = app won't boot
                          │
                    backend/analytics_queries.py           ← COMMIT 1, same owner
                    NON_INTENT_EVENTS (deny-list ⇒ intent-by-default)
                    WAT_LIVE / WAT_DARK / FUNNEL_STAGES / FEATURE_VERTICALS
                          │
        ┌─────────────────┼──────────────────┬───────────────────┐
        │                 │                  │                   │
   P0-7 client       P0-7 server        P0-3 client         P0-8/9 client
   tab_selected      sleeper_send_      invite_shared*      celebration_fired
   league_*          succeeded          invite_link_opened  → celebration_shown
   sleeper_send_     (record_event      invite_league_pinned   (rename at 3 sites;
   attempted/failed   at propose)       invite_pin_failed       target already registered)
   experiment_exposed
   quickset_step_advanced / _abandoned
```

\* `invite_shared` is **already firing and already being dropped** — it has been silently
lost since it shipped. Registering it is a bug fix, not an addition.

The spine's one invariant, and the whole reason commit 1 exists: **register before you
emit.** The taxonomy is default-deny with a 200 response, so an unregistered event name
produces a plausible-looking dashboard with no rows. This repo has prior art of exactly
that failure (the NULL-`platform` incident, and `invite_shared`, and `celebration_fired`
— three instances). Commit 1 is therefore the *first* code commit on the branch and no
other commit may touch either registry file.

Second invariant, easy to miss: `INTENT_EVENTS = (SERVER_FIRED | ALLOWED_CLIENT) −
NON_INTENT_EVENTS`. Taxonomy growth is **intent-by-default**, so a high-frequency
impression event like `tab_selected` would step-change DAU/WAU on ship day and break
every retention series at that seam, permanently and silently. The `NON_INTENT_EVENTS`
additions are mandatory, not a nicety.

### 1.3 Diagram-in-text — the invite / sign-in flow after P0-5 and P0-3 both land

```
                       ┌───────────────────────────────────────────────┐
  Sender taps "Invite" │ buildInviteUrl()  (InviteLeaguematesBanner)    │
                       │  flag growth.invite_join_link read IMPERATIVELY│
                       │   OFF → https://…/?league=<id>&ref=<u>  (today)│
                       │   ON  → https://…/app/league/join/<id>?ref=<u> │
                       └───────────────────────────────────────────────┘
                                          │  (Sleeper chat / iMessage)
                                          ▼
                        ┌──────────────────────────────────┐
                        │  Recipient taps the link         │
                        └──────────────────────────────────┘
                          │                              │
        app INSTALLED (iOS resolves via AASA)      app NOT installed → Safari
                          │                              │
                          │                     GET /app/league/join/<id>?ref=u
                          │                              │  302
                          │                              ▼
                          │                     /?league=<id>&ref=u
                          │                              │
                          │                     web/js/app.js captureReferralFromUrl()
                          │                       → localStorage ftf_invited_league
                          │                       → "Invited by @u" banner
                          │                       → sign in → league auto-selected
                          │                       (UNCHANGED — this half already works)
                          ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │ mobile: App.tsx handleDeepLink  /  RootNav linking config          │
   │   setInvitedBy(ref)                        (existing)              │
   │   setInvitedLeague(leagueId)               (NEW — P0-3)            │
   │     ├─ from path segment  /app/league/join/:leagueId               │
   │     └─ from LEGACY ?league=  ← read ABOVE the bare-path            │
   │        short-circuit at deepLinks.ts:352. THIS ALONE FIXES EVERY   │
   │        LINK EVER SHARED, and it ships UNFLAGGED.                   │
   │   both persisted → AsyncStorage ftf_invite_intent {leagueId,       │
   │   invitedBy, ts}, 14-day TTL, cleared on consume + signOut         │
   └───────────────────────────────────────────────────────────────────┘
                          │
        path-form link ───┴──► LeagueJoinScreen (ROOT stack — reachable signed-out)
        legacy ?league= ──────► (no screen; intent is stashed, routing continues)
                          │
                          ▼
        ┌─────────────────────────────────────────────────────────┐
        │ LeagueJoinScreen decides, by auth state:                │
        │  A. no user               → replace('SignIn')           │
        │  B. Sleeper user, member  → pickLeague(auto) → Main     │
        │  C. Sleeper user, not member → replace('LeaguePicker')  │
        │                              + leaguepicker.invite-notice│
        │  D. ACCOUNT-ONLY session   → replace('LeaguePicker')    │
        │        with invite context → P0-5 COMPANION STATE       │
        └─────────────────────────────────────────────────────────┘
                          │
   ┌──────────────────────┴──────────────────────────────────────────────┐
   │ A. SignIn                                                            │
   │    signin.invited-banner: "@matt invited you to Lakeview Dynasty"    │
   │    (name from GET /api/league/invite-meta, degrades to "their        │
   │     league" on any failure — the acceptance criterion is met without │
   │     the endpoint)                                                    │
   │    renders in BOTH landingOn variants                                │
   │      ├─ Sleeper sign-in ──► LeaguePicker ──► auto-pin effect ──► Main│
   │      └─ Apple sign-in ─────► account_only + no_league sentinel       │
   │             P0-5: onAccountSignedIn → replace('LeaguePicker')  ◄─────┼── the P0-5 fix
   └──────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ LeaguePickerScreen                                                    │
   │  refresh(): account_only ⇒ SKIP GET /api/sleeper/leagues/acct_<id>    │
   │             (else: 503 "Couldn't reach Sleeper" — a false error)      │
   │                                                                       │
   │  ┌─ companion state (account_only && zero leagues) ─────────────────┐ │
   │  │  header "Connect a League"                                        │ │
   │  │  WITH invite context (case D):                                    │ │
   │  │     "@matt invited you to Lakeview Dynasty —                      │ │
   │  │      connect Sleeper, ESPN or MFL to join."                       │ │
   │  │  WITHOUT: "Connect Sleeper, ESPN or MFL to see your leagues."     │ │
   │  │  [Connect Sleeper] → LinkSleeperSheet  (extracted from Settings)  │ │
   │  │  [Connect ESPN]    → EspnLinkSheet     (existing handler)         │ │
   │  │  [Connect MFL]     → PlatformLinkSheet (existing handler)         │ │
   │  │  footer suppressed in this state only                             │ │
   │  └───────────────────────────────────────────────────────────────────┘ │
   │                          │                                             │
   │   link succeeds ─────────┤                                             │
   │     ESPN/MFL → onLeagueLinked → pickLeague() → setLeague(REAL) → Main   │
   │     Sleeper  → setUser(real id) + setLeague(null) → effect on user_id   │
   │                → refresh() now hits Sleeper → real list paints in place │
   │                          │                                             │
   │   list changes ──► AUTO-PIN EFFECT (P0-3, keys on `cached`):           │
   │        invitedLeagueId ∈ cached ? pickLeague(lg,{auto:true}) + consume  │
   │                                 : invite-notice row                    │
   │                          │                                             │
   │                          ▼                                             │
   │                    setLeague(real) OVERWRITES the no_league sentinel    │
   │                    → onLeaguePicked() → replace('Main')                 │
   └──────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
                   Main (tabs) — and because the sentinel is gone,
                   P0-5's relaunch predicate sends them to Main on every
                   subsequent cold start.
```

**The intersection, stated once so no agent assumes the other handled it.** An invited
Apple user with no Sleeper identity is *not a member of the invited Sleeper league* —
`buildSessionInitBody`'s Sleeper branch would find no roster for `acct_<id>`. Pinning it
is not possible as built and must not be attempted. The correct behaviour is exactly
case D above: **hold the intent, route to the companion state, and let the invite become
the strongest copy on the screen.** If the user then links Sleeper and is genuinely in
that league, the auto-pin effect fires on the refreshed `cached` list with no extra code.

### 1.4 Composition beyond the two spines

- **P0-2, P0-6, P0-8/9** compose by file partition alone; they share no semantics.
- **P0-6 → P0-7 is a semantic dependency, not just textual.** After P0-6, a non-Sleeper
  mount renders an affordance that is *not* a send button. Any P0-7 impression event
  firing unconditionally at mount would conflate copy-affordance impressions with send
  impressions and corrupt the send-funnel denominator. P0-7 therefore instruments
  `onPress` / `catch` **only** — never the render path — and P0-6 lands first.
- **P0-1 → P0-7 (none).** P0-1 fires no analytics events by design; `ranking_method_changed`
  means *"the user chose a method"* and firing it from implicit writes would corrupt a
  shipped funnel metric.
- **P0-8's `err.burst` deletion → P0-2.** P0-2 owns the Trades error state in this same
  batch; a mascot bubble competing for the same moment offers strictly less (no error
  name, no retry). Deleting `err.burst` is behaviour-preserving (zero call sites) and
  is confirmed against P0-2's design here.

---

## 2. Settled decisions

Every row below is **adjudicated**. Build and LLD agents design *around* these; none is
reopenable. "Rationale" is the one-line reason of record — the fuller argument lives in
the cited plan section.

| # | Finding | Decision | Rationale |
|---|---|---|---|
| S-01 | P0-1 | The `'anchor' → 'quickset'` upgrade exception is **approved**: a completeness-marking tiers/quickset save may overwrite `'anchor'`, and only `'anchor'`. | `'anchor'` is the one method string whose unlock rule can never succeed; without the exception an anchor-first user is permanently locked purely on ordering — a *new* failure created by the fix. |
| S-02 | P0-1 | Backfill ships as a **startup migration** inside `_migrate_db()`, cohort = `ranking_method IS NULL` **and** all four positions in `tiers_saved` for ≥1 format. | Strictly improving for every row it touches; a one-shot script would lag the auto-deploy that depends on it. |
| S-03 | P0-1 | The backfill's **push fan-out to leaguemates is SUPPRESSED** — pre-seed `unlocked_formats` for the backfilled cohort so `was_first` is already spent. | Suppresses both `ranking_complete_first_time` and the `league_member_unlocked_trades` burst; the unlock is retroactive bookkeeping, not a moment worth notifying about. |
| S-04 | P0-1 | **No new feature flag**, and **no new analytics event**. | The change removes a wrong answer; a flag's OFF position would be the known bug. `ranking_method_changed` means "the user chose" and must not be inflated. |
| S-05 | P0-1 | Q4 closed: the only live experiment is `onboarding_v2_rollout`, which is **device-unit** and therefore cannot target `ranking_method` (an account-scope attribute) per FR-33b. A one-line authenticated prod GET goes on the **pre-merge checklist**, not the build. | The targeting hazard is structurally impossible for the one running experiment; the GET is cheap insurance against a new one being started mid-build. |
| S-06 | P0-1 | The `quickset-done` **fixture / seeder-guard / capture inversion moves with the fix, in the same commit**. | The startup backfill rewrites the seed user at Flask boot; splitting them leaves the seeder refusing the only coherent post-fix profile. |
| S-07 | P0-1 | The old `progress-ring--4-4-locked` capture is **re-captured, not preserved**. History lives in git. | A screen-library frame whose name asserts a bug that no longer exists is worse than no frame. |
| S-08 | P0-2 | First-run auto-start failure **SHOWS the error card**. | The app *did* search on the user's behalf and showed a skeleton; "Hit Find a Trade to start" is a lie either way, and the error card carries a working retry. |
| S-09 | P0-2 | The partial-deck inline note is **deferred**. | Additive, not required by the acceptance criterion; row 7 (`deck.length > 0`) already wins over the failure branch, so partial results still render. |
| S-10 | P0-2 | **Unflagged.** | Its OFF state is the bug. |
| S-11 | P0-2 | Retry label is **"Try again"**. | Majority in-app convention (five Rank screens). |
| S-12 | P0-2 | P0-2 adds **no analytics**. The `find_trades_tapped` empty-prop-allowlist gap is recorded as a **noted defect in P0-7's taxonomy addendum**. | `source` is already silently stripped for the existing `'prefs_changed_strip'` call; fixing it is a taxonomy change and belongs on P0-7's commit, documented either way. |
| S-13 | P0-3 | The **`?league=` reader fix ships UNFLAGGED**. | It repairs every link ever shared and needs no URL change; it is the valuable half of the fix and the low-risk one. |
| S-14 | P0-3 | The new `/app/league/join/<id>` **emitter** ships behind `growth.invite_join_link`, **default OFF**. Server 302 + AASA claim land **unflagged and before** the client emitter can be flipped. | AASA is CDN-cached up to ~24h; shipping the new URL before propagation would send every invite to Safari — a *worse* loop than today. |
| S-15 | P0-3 | `invitedBy` **and** `invitedLeagueId` persist to AsyncStorage under one key with a **14-day TTL**, cleared on consume and sign-out. | Parity with web (`localStorage`); the account-only branch can leave a user league-less for several launches and the intent must outlive them. |
| S-16 | P0-3 | **M12 approved** — the signed-out-boot harness seam, designed jointly with P0-5's (see §5). | `openLink` is unusable in this harness (law 17); without M12 the signed-out invite landing has no automated coverage at all. |
| S-17 | P0-3 | **Account-only intersection:** `LeagueJoin` on an account-only session routes into P0-5's **LeaguePicker companion state carrying inviter + league context**. | Pinning a Sleeper league for an `acct_` user is not possible as built; the companion state turns the collision into the strongest copy on the screen. |
| S-18 | P0-3 | Every event P0-3 emits — **including the currently-dropped `invite_shared`** — is registered in the **taxonomy commit** (commit 1). | Default-deny with a 200 response; `invite_shared` has been lost since it shipped. |
| S-19 | P0-5 | **P0-5 lands BEFORE P0-3; P0-3 rebases.** | Smaller change, and its routing decision is the precondition for P0-3's account-only path existing. |
| S-20 | P0-5 | **`LinkSleeperSheet` extraction approved** (~110 lines out of `SettingsScreen`, shared by Settings and the picker). | The alternative ships copy that offers Sleeper and then bounces the user to the screen this finding is about, or duplicates ~60 lines of merge-conflict handling that will drift. |
| S-21 | P0-5 | **W-1 approved** — the account-only harness seam. Designed as **ONE coherent harness extension** with P0-3's M12: `FTF_TEST_MODE` server-side + `IS_TEST_BUILD` client-side **only**. No new `/__test__` route, no new flag, no third gate. | A real Apple sign-in is undrivable by Maestro; two ad-hoc hacks would double the production-gate surface for one capability. |
| S-22 | P0-5 | Routing predicate keys off **`league.league_id === NO_LEAGUE_ID`**, never `user.account_only`. | `account_only` stays true after an ESPN/MFL link, so that predicate would trap a well-provisioned user in the picker forever. |
| S-23 | P0-6 | **P0-6 lands BEFORE P0-7's instrumentation.** P0-6 owns `SendInSleeperButton`'s render path and prop signature; **P0-7 inserts into `onPress` / `catch` per P0-6's line-range proposal.** | P0-6 is structural, P0-7 additive; the reverse order forces P0-7 to re-instrument a branch that did not exist when it wrote its diff. |
| S-24 | P0-6 | **No new flag** — the copy fallback rides `trade.send_in_sleeper`. | Flag off ⇒ nothing renders on any platform, i.e. exactly today's ESPN behaviour everywhere. A new flag is itself a bright-line surface change. |
| S-25 | P0-6 | The **MFL / Fleaflicker sim-coverage waiver is recorded in the scope block**, compensated by **pure-module unit tests** (`resolveSendPlatform`, `NO_SEND_REASON`, `formatTradeForClipboard`). | No MFL/Fleaflicker seeder profile exists; authoring one inside a P0 bug-fix wave is out of proportion. The whole platform-specific behaviour lives in the pure module. |
| S-26 | P0-6 | `/api/sleeper/propose`'s missing `is_linked_platform_league` guard → **`NEXT.md` item, not this build**. | Backend + API contract = bright line; the client fix is the whole of P0-6's acceptance criterion. |
| S-27 | P0-6 | The compact-mount reason line: **yes**, and it is **verified on sim during QA** (`#276` vertical-cost check on an 852 pt viewport). | Non-Sleeper mounts get zero information today; the cost is 16-32 pt on those mounts only. Verified, not assumed. |
| S-28 | P0-6 | `capture/matches@espn.yaml` gains the **positive copy-affordance assertion** (`assertVisible: id: send-in-sleeper.copy`). | Its existing `assertNotVisible "Send in Sleeper"` passes both before and after the fix — a silent regression detector is no detector. |
| S-29 | P0-6 | The **mobile `setMatchDisposition` wrapper is deleted**. The route and the live `web/js/app.js:4342` caller are **untouched**. Accept/decline UX is **deferred to `NEXT.md`**. | The route is not dead — it carries K-factored ELO consequences and a live web caller. Only the ~13-line unused mobile wrapper is dead, and it reads as "mobile has an accept path" to the next person. |
| S-30 | P0-7 | Adopt the **RESERVED** names `sleeper_send_attempted` / `_succeeded` / `_failed`. | `analytics_queries.WAT_DARK` already reserves them; they light up the north-star send leg, funnel stage 8 and the `send_in_sleeper` vertical for free. New names would leave all four dark one alias away. |
| S-31 | P0-7 | **OPTIONAL-A `league_home_action_tapped` is IN.** | One registry row + ~11 one-line inserts; League Home's exit paths are the only question that screen answers. |
| S-32 | P0-7 | **`NON_INTENT_EVENTS` additions are mandatory** (`tab_selected`, `league_view`, plus `experiment_exposed` and `quickset_abandoned` from §6). | `INTENT` is a deny-list; without them DAU/WAU step-changes to ~app-open count on ship day and every retention series breaks at that seam. |
| S-33 | P0-7 | `is_self` on `league_team_opened` is **omitted**. | Session-user ↔ `PowerRankedTeam.user_id` identity was not proven; never guess a prop. |
| S-34 | P0-7 | `sleeper_send_succeeded` does **not** bump `last_trade_proposed_at`. | That changes notification-gating behaviour, which is out of scope for an instrumentation item. |
| S-35 | P0-7 | The **`_record_send_success` helper is approved** (extract, call from the propose success path, unit-test the helper). | `/api/trades/propose` fail-closes under `FTF_TEST_MODE`, so the route cannot be driven end-to-end; the helper is the honest test seam and keeps the route body to one line. |
| S-36 | P0-7 | **The taxonomy registration is ITS OWN COMMIT and the FIRST code commit on the branch.** | Default-deny + 200 response = silent drop. Three live instances of this failure already exist in the tree. |
| S-37 | P0-7 §6 | Include **F1 `experiment_exposed`** (also fixes the live `FUNNEL_CRITICAL` silent drop), **F3 `quickset_step_advanced` with `seeded_accepted`**, **F4 `quickset_abandoned`**. **Skip F2** (`first_session_started`). | F1 is a live instance of this finding's own trap and every A/B read is exposure-diluted without it. F3/F4 are the per-step drop-off curve the P0-9 question actually turns on. F2's arm attribution is already derivable from `experiments.stamp_for_event`. |
| S-38 | P0-7 / P0-8-9 Q5 | **Wire the `screen_viewed` emission** — *see §10.1: on spot-check this is already live and the directive resolves to a **verification** task, not a build task.* | The adjudication was made on P0-8/9's stale claim; `RootNav.tsx:352` and `:376` already emit `screen_viewed` for every route including tab switches. |
| S-39 | P0-8 | `s8.1` is gated on **beat identity** — `guideSeen['s2.2']` — not on a step count. | `stepsSeenCount` is in-memory and resets on launch; a durable count under-reports real tours and over-reports empty ones; `N` is a magic number that drifts. `s2.2` is the tour's only `advance:'action'` teaching step. |
| S-40 | P0-8 | **`err.burst` is deleted.** | Zero call sites ⇒ deletion is behaviour-preserving; P0-2 owns the Trades error moment in this same batch and offers strictly more. |
| S-41 | P0-9 D2 | **The CLIENT renames `celebration_fired` → `celebration_shown`** at its three call sites. **No alias** is added to the taxonomy. | The taxonomy is the shipped surface and already registers `celebration_shown` with matching props; an alias would enshrine a typo. |
| S-42 | P0-9 D1 | **D1 is IN SCOPE — fix it.** (Like-first swallows `s6.1`, so the tour can never sign off.) | Under the V2 arm the beat is lost permanently, `guideSeen['s6.1']` is never written, and the tour has no ending. One condition. |
| S-43 | P0-9 D3 | **Prove `s5.1` renders** via a flag-pinned capture during validation; fix if broken. | It is the payoff beat carrying the entire trades-first argument and has never rendered in this repo's evidence. Nothing else in the tour is worth testing if it is broken. |
| S-44 | Batch | **NO flag defaults change anywhere in this build.** | P0-9 is test prep, not a rollout; the only flag *added* is `growth.invite_join_link`, default OFF. |
| S-45 | Batch | `tester_allowlist` device-id currency is an **operator checklist item in the final report**, not a build task. | Device pseudo-ids rotate on reinstall; only the operator can confirm the current one. |
| S-46 | Batch | Full gates apply — **no express was declared**. Scope block + Maestro delta + docs table + sim run for every finding. | Root `CLAUDE.md`: agents never self-select express; P0-3 (routes) and P0-7 (analytics) are explicitly over the bright line. |

---

## 3. Commit sequencing

Every commit below must be **independently green**: `python3 -m pytest backend/tests/ -q`
and `cd mobile && npx tsc --noEmit`, plus `bash mobile/scripts/testid-lint.sh` for any
commit that adds a flow or a `testID`. `mobile/node_modules` is a symlink — **never run
`npm install`.**

| # | Commit | Wave / agent | Contents | Green because |
|---|---|---|---|---|
| **1** | `analytics: register P0-remediation taxonomy (P0-7 §3 + P0-3 invite events + F1/F3/F4)` | W0-TAX | `analytics_taxonomy.py` (12 client names + 1 server name + 12 prop rows), `analytics_queries.py` (NON_INTENT, WAT_LIVE/DARK, stale dark caveat), addendum doc, `test_events_api.py`, `test_analytics_p0.py` | Registering a name with no emitter is inert. The two import-time asserts (disjointness; every allowlisted event has a props row) fail *loudly* in CI if half-done. |
| **2** | `P0-1: write ranking_method at the point of use + suppressed startup backfill` | W1-BE | `database.py` (helper, backfill, `_migrate_db` call, column comment), `server.py` (import, `_note_ranking_method`, 4 save handlers, ladder comment), **the fixture/seeder/capture inversion (S-06)**, new pytest file, new Maestro flow, `RankScreen.tsx` testID | Self-contained; the fixture inversion is in the same commit so the seeder never refuses a coherent profile. |
| **3** | `P0-3(server): AASA /app/league/join claim, 302 fallback, invite-meta, growth.invite_join_link (OFF)` | W1-BE | `server.py` (B1/B2/B3), `feature_flags.py`, `config/features.json`, `fixtures/flags/release.json`, `test_invite_links.py` | Additive routes + a default-OFF flag; no client reads it yet. |
| **4** | `harness: FTF_TEST_MODE Apple-identity seam (server half)` | W1-BE | `server.py` `auth_apple` + `_test_mode_identity()`, `test_account_only_harness.py` (asserts **401 when `FTF_TEST_MODE` is unset**) | Inert in every deployed configuration; the production gate is asserted, not assumed. |
| **5** | `P0-7(server): _record_send_success + sleeper_send_succeeded on the propose success path` | W1-BE | `server.py` (helper + one call), unit test on the helper | Name registered in commit 1. |
| **6** | `harness: IS_TEST_BUILD export, signed-out LeagueJoin entry, FTFTestAppleSub (client half)` | W1-P05 | `testRouteEntry.ts`, `RootNav.tsx` (one call-site shape change), `SignInScreen.tsx` (SDK-call substitution only) | Build-time-gated; `LeagueJoin` is not yet a registered route, so the signed-out allowance is a no-op until commit 12. |
| **7** | `P0-5: account-only routes to LeaguePicker; sentinel-aware relaunch; picker companion state; LinkSleeperSheet extraction` | W1-P05 | `RootNav.tsx`, `LeaguePickerScreen.tsx`, `SettingsScreen.tsx`, `LinkSleeperSheet.tsx` (new), flow + capture. Companion state accepts **optional** `invitedBy` / `invitedLeagueName` props (unused until commit 12) | Optional props default to undefined; every existing caller compiles. |
| **8** | `P0-6: platform-generic send gate + copy-trade fallback; delete the dead mobile setMatchDisposition wrapper` | W1-P06 | `SendInSleeperButton.tsx` (gate, render branch, **`surface?: SendSurface` prop declared optional**, name props), `TradeCard.tsx`, `InLeagueCalculator.tsx`, `MatchesScreen.tsx`, `api/trades.ts`, `utils/tradeText.ts` + `utils/clipboard.ts` (new), `mobile/tests/check-trade-text.js`, `package.json`, flow + capture, `fixtures/profiles/espn.json` description | `surface` optional ⇒ the not-yet-plumbed `TradesScreen` mount still compiles. |
| **9** | `P0-7(client): tab_selected + League surface events + OPTIONAL-A` | W2-P07 | `TabNav.tsx`, `LeagueScreen.tsx`, `LeagueSummaryScreen.tsx` | Names registered in commit 1. |
| **10** | `P0-7(client): sleeper_send_attempted/_failed; experiment_exposed; quickset step + abandon` | W2-P07 | `SendInSleeperButton.tsx` (**`onPress` / `catch` inserts only** — no signature or render change), `api/flags.ts`, `state/useFeatureFlags.ts`, `QuickSetTiersScreen.tsx` | P0-6's branches already exist (commit 8). |
| **11** | `P0-2 + P0-8/9: deck failure state, toast offset, s8.1 beat gate, s6.1 swallow fix, celebration_shown rename, send-surface plumbing` | W2-TS | `TradesScreen.tsx` (exclusive), `Toast.tsx`, `analystScript.ts`, three Maestro files | `surface`/name props already accepted (commit 8). |
| **12** | `P0-3(client): legacy ?league= reader, LeagueJoin route + screen, persisted invite intent, invited sign-in banner` | W2-P03 | `deepLinks.ts`, `useSession.ts`, `LeagueJoinScreen.tsx` (new), `RootNav.tsx`, `LeaguePickerScreen.tsx`, `SignInScreen.tsx`, `InviteLeaguematesBanner.tsx`, `api/league.ts`, flow | Server routes + AASA landed in commit 3; harness signed-out entry landed in commit 6; companion-state props landed in commit 7. |
| **13** | `P0-7: make SendInSleeperButton's surface prop required` | W2-P07 (close-out) | one type change | All four mounts plumbed by commits 8 and 11. A missed mount is now a **compile error**, which is the enforcement P0-7 wanted. |
| **14** | `docs: P0-remediation reference + living-memory rollup` | W3-DOCS | §7 in full | Docs only. |
| **15** | `qa: tier-1 sim-run evidence for the P0 remediation batch` | W3-QA | `living-memory/TEST_LEDGER.md`, `qa/sim-runs/last-sim-run.json` | Evidence only. |

**Hard ordering constraints** (everything else may float):
`1 → everything` · `2 before its fixture consumers` · `3 + 6 before 12` · `7 before 12`
· `8 before 10, 11, 13` · `11 before 13`.

**Deliberately *not* squashed:** commits 1 and 2. Commit 1 must be separately revertible
(a taxonomy revert is a metric-definition rollback, nothing else). Commit 2 carries the
backfill and is the only commit in the batch that mutates production data.

---

## 4. Build-wave partition — exclusive file ownership

**Rule: within a wave, no file appears in two agents' lists.** Across waves, sequential
ownership is fine and is used deliberately (`RootNav.tsx`, `LeaguePickerScreen.tsx`,
`SignInScreen.tsx`, `SendInSleeperButton.tsx`, `server.py` all change hands between
waves).

**Four waves.** Three would be possible only by merging the backend agent into the
taxonomy commit, which S-36 forbids.

### Wave 0 — `W0-TAX` (single agent, single commit)

| File | Why |
|---|---|
| `backend/analytics_taxonomy.py` | 12 client names + `sleeper_send_succeeded` + 12 `CLIENT_EVENT_PROPS` rows |
| `backend/analytics_queries.py` | `NON_INTENT_EVENTS`, `WAT_LIVE`/`WAT_DARK`, the stale `:497` dark caveat |
| `backend/tests/test_events_api.py` | acceptance test: `dropped == 0` **and** exact `set(by_type)`; negative test on a misspelled name; prop-stripping test |
| `backend/tests/test_analytics_p0.py` | extend `test_live_taxonomy_is_disjoint`'s membership set |
| `docs/business/analytics/2026-08-11-p0-7-addendum.md` **(new)** | the precondition the registry's own comments demand |

Names registered in this commit, in full:

- **Client** — `tab_selected`, `league_view`, `league_basis_changed`,
  `league_subset_changed`, `league_team_opened`, `league_home_action_tapped` (S-31),
  `sleeper_send_attempted`, `sleeper_send_failed`, `invite_shared` (S-18, fixes a live
  silent drop), `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed`,
  `experiment_exposed` (S-37 F1), `quickset_step_advanced` (S-37 F3),
  `quickset_abandoned` (S-37 F4).
- **Server** — `sleeper_send_succeeded`.
- **`NON_INTENT_EVENTS`** — `tab_selected`, `league_view`, `experiment_exposed`,
  `quickset_abandoned`. (`quickset_step_advanced` stays INTENT — it is real ranking
  intent. The five League interaction events stay INTENT.)
- **Addendum must record:** the `sleeper_send_*` naming decision (S-30); the league-
  `platform`-vs-device-`platform` distinction; the DAU/WAU seam date; the **`find_trades_tapped`
  empty-prop-allowlist defect (S-12)** in the "deliberately NOT here" section; that
  `invite_shared` was firing into a wall since it shipped.

### Wave 1 — three agents in parallel

#### `W1-BE` — backend (P0-1 + P0-3 server + harness server half + P0-7 server)

Sole owner of `backend/server.py` for this wave.

| File | Source | Change |
|---|---|---|
| `backend/database.py` | P0-1 | `set_ranking_method_if_unset`, `backfill_ranking_method_from_tiers` (**with `unlocked_formats` pre-seed per S-03**), `_migrate_db` call, column comment `:181` |
| `backend/server.py` | P0-1 | import, `_note_ranking_method`, inserts in `post_rank3` / `save_tiers_route` / `save_anchor_route` / `reorder_rankings`, ladder comment |
| " | P0-3 B1-B3 | AASA `/app/league/join/*` claim; `GET /app/league/join/<id>` → 302; `GET /api/league/invite-meta` |
| " | P0-5 W-1 | `_test_mode_identity()` + the `auth_apple` branch (§5) |
| " | P0-7 | `_record_send_success()` + the propose-success call |
| `backend/feature_flags.py` | P0-3 B5 | `growth.invite_join_link` in `FLAG_KEYS` |
| `config/features.json` | P0-3 B6 | `growth.invite_join_link: false` + `_comment_` graduation criterion |
| `backend/tests/fixtures/flags/release.json` | P0-3 B6 | same key, false |
| `backend/tests/fixtures/profiles/quickset-done.json` | P0-1 | invert to the fixed state (S-06) |
| `backend/tests/fixtures/seed_ui_test_db.py` | P0-1 | invert `_validate_quickset` |
| `backend/tests/test_ranking_method_point_of_use.py` **(new)** | P0-1 | T-1…T-23 |
| `backend/tests/test_invite_links.py` **(new)** | P0-3 B7 | AASA payload, 302 shape, traversal encoding, invite-meta, flag presence |
| `backend/tests/test_account_only_harness.py` **(new)** | P0-5 | seam 401s with `FTF_TEST_MODE` unset; account-only session can `POST /api/espn/link`; `/api/session/init` reuses the token and preserves `verified` |
| `mobile/src/screens/RankScreen.tsx` | P0-1 | `testID="rank.unlocked-banner"` — one prop |
| `mobile/.maestro/flows/p0-1-quickset-unlock.yaml` **(new)** | P0-1 | |
| `mobile/.maestro/capture/league@quickset-done.yaml` | P0-1 | rename `--4-4-locked` → `--4-4-unlocked` (S-07) |

#### `W1-P05` — P0-5 account-only + the client half of the unified harness

| File | Change |
|---|---|
| `mobile/src/utils/testRouteEntry.ts` | §5 — export the gate, add the launch-arg accessor, add `SIGNED_OUT_ENTRY_ROUTES` |
| `mobile/src/navigation/RootNav.tsx` | `onAccountSignedIn` → `LeaguePicker`; sentinel-aware `initialRoute`; `applyTestRouteEntry` call-site shape |
| `mobile/src/screens/LeaguePickerScreen.tsx` | skip `getLeagues()` for `account_only`; companion state; footer suppression; header copy; mount `LinkSleeperSheet`; **accept optional `invitedBy` / `invitedLeagueName`** |
| `mobile/src/screens/SettingsScreen.tsx` | replace the inline form with `<LinkSleeperSheet>`; keep `testID="settings.link-sleeper-input"` on the moved input |
| `mobile/src/components/LinkSleeperSheet.tsx` **(new)** | verbatim extraction incl. the 409 `merge_choice_required` Alert |
| `mobile/src/screens/SignInScreen.tsx` | **only** the `AppleAuthentication.signInAsync` substitution under `IS_TEST_BUILD` + `FTFTestAppleSub` |
| `mobile/.maestro/flows/p0-5-account-only-picker.yaml` **(new)** | |
| `mobile/.maestro/capture/leagues@account-only.yaml` **(new)** | |

#### `W1-P06` — P0-6 send gate + copy fallback

| File | Change |
|---|---|
| `mobile/src/components/SendInSleeperButton.tsx` | `SendPlatform` resolution replacing `isEspn`; unavailable branch; `Copy trade` + `Copied` flip; **declare `surface?: SendSurface` (optional) and the four name/context props**; header comment rewrite |
| `mobile/src/utils/tradeText.ts` **(new)** | `formatTradeForClipboard`, `resolveSendPlatform`, `NO_SEND_REASON` — pure, no React/RN imports |
| `mobile/src/utils/clipboard.ts` **(new)** | `copyText()` over RN-core `Clipboard` |
| `mobile/src/components/TradeCard.tsx` | both mounts: name props + `leagueName?: string` + `surface={variant === 'match' ? 'match' : 'suggested'}` |
| `mobile/src/components/InLeagueCalculator.tsx` | `:771` name props + `surface="calculator"` |
| `mobile/src/screens/MatchesScreen.tsx` | `leagueName={item.league_name}` |
| `mobile/src/api/trades.ts` | delete `setMatchDisposition`; comment the normalizer (S-29) |
| `mobile/tests/check-trade-text.js` **(new)** + `mobile/package.json` | the S-25 compensating unit tests |
| `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml` **(new)** | |
| `mobile/.maestro/capture/matches@espn.yaml` | + `assertVisible: id: send-in-sleeper.copy` (S-28); comment rewrite |
| `backend/tests/fixtures/profiles/espn.json` | description tail only — the bug is no longer current behaviour |

> **Note the deliberate delegation:** P0-6 declares `surface` on behalf of P0-7 in
> wave 1 so that wave 2's three agents are fully independent of one another.

### Wave 2 — three agents in parallel

#### `W2-TS` — the unified TradesScreen agent (P0-2 + P0-8/9 build + the two inherited one-liners)

Sole owner of `TradesScreen.tsx`. This is the wave's critical path (6 158 lines, four
findings converging).

| File | Change |
|---|---|
| `mobile/src/screens/TradesScreen.tsx` | **P0-2:** `DeckFailure` state + 3 copy constants + `jobErrorCopy`; 7 transition sites; ladder row 4 guard; new row 7b; `deckErrorTitle` style; mode-bar `onLayout` + `topOffset`. **P0-8:** `s8.1` gate `+ ob.guideSeen['s2.2']` at `:2457` + comment rewrite. **P0-9 D1:** mark `celebrationsShown.first_like` only when `requestGuideStep` returned true (`:3133-3139`). **P0-9 D2:** rename `celebration_fired` → `celebration_shown` at `:2547`, `:3135`, `:3153`. **Inherited:** `:4713` — pass P0-6's name/opponent props **and** P0-7's `surface="deck"` |
| `mobile/src/components/Toast.tsx` | optional `topOffset` prop; `top` moved out of `styles.wrap` |
| `mobile/src/components/analystScript.ts` | delete the `err_burst` entry (S-40) |
| `mobile/.maestro/flows/trades-generation-failure.yaml` **(new)** | six legs, Paths A/B/C + retries |
| `mobile/.maestro/flows/guide-no-false-signoff@release.yaml` **(new)** | fails on the unfixed tree, passes on the fixed one |
| `mobile/.maestro/capture/trades.yaml` | **mandatory** — its error leg asserts the bug and breaks the moment the fix lands |
| `mobile/.maestro/capture/onboarding-tour@fresh.yaml` | S8.1 comment + the **D3 `s5.1` validation variant** (S-43) |

#### `W2-P03` — P0-3 client (invite loop)

| File | Change |
|---|---|
| `mobile/src/utils/deepLinks.ts` | `LeagueJoin: 'app/league/join/:leagueId'` in `V2_SCREENS`; **`?league=` capture above the bare-path short-circuit at `:352`** |
| `mobile/src/state/useSession.ts` | `invitedLeagueId` / `setInvitedLeague` / `consumeInvitedLeague`; `ftf_invite_intent` persistence + 14-day TTL; hydrate in `bootstrap`; clear on consume + `signOut` |
| `mobile/src/screens/LeagueJoinScreen.tsx` **(new)** | the four-way interstitial, incl. case D → companion state with context |
| `mobile/src/navigation/RootNav.tsx` | register `<Stack.Screen name="LeagueJoin">`; extend the `AuthStack` param list |
| `mobile/src/screens/LeaguePickerScreen.tsx` | auto-pin effect keyed on `cached`; `leaguepicker.invite-notice`; pass invite context into P0-5's companion state |
| `mobile/src/screens/SignInScreen.tsx` | `InvitedByBanner` in **both** `landingOn` variants |
| `mobile/src/components/InviteLeaguematesBanner.tsx` | `buildInviteUrl` reads `growth.invite_join_link` **imperatively via `useFeatureFlags.getState()`** so both call sites stay byte-identical (§10.2); comment rewrite |
| `mobile/src/api/league.ts` | `fetchInviteMeta(leagueId)` — unauthenticated, short timeout, never throws |
| `mobile/.maestro/flows/league/invite-join.yaml` **(new)** | three blocks incl. the signed-out landing |

> `mobile/src/screens/LeagueScreen.tsx` is **NOT** in this list. See §10.2 — the
> imperative flag read removes P0-3's only reason to touch it, resolving the contention
> with P0-7.

#### `W2-P07` — P0-7 client instrumentation

| File | Change |
|---|---|
| `mobile/src/navigation/TabNav.tsx` | `tab_selected` as the first statement in each of the six existing `tabPress` handlers, **before** `preventDefault()` |
| `mobile/src/screens/LeagueScreen.tsx` | `league_view` mount effect (`firedRef` + `summaryQuery.isFetched`) + OPTIONAL-A on ~11 hub handlers |
| `mobile/src/screens/LeagueSummaryScreen.tsx` | `league_view`; `changeBasis()` helper on both `BasisChip`s; `track` inside `switchSubset`; `openTeam()` at the two `setSelectedId` sites; `source` threaded through `SubsetControl.onSwitch` |
| `mobile/src/components/SendInSleeperButton.tsx` | **`onPress` and `catch` inserts only** — no signature change, no render change (S-23) |
| `mobile/src/api/flags.ts` | record overlay provenance during the `configs[*].flags` merge (which keys came from which experiment) — the raw material for F1 |
| `mobile/src/state/useFeatureFlags.ts` | `experiment_exposed` emitted **deferred** (never during render) on first consumption of an overlaid key |
| `mobile/src/screens/QuickSetTiersScreen.tsx` | F3 `quickset_step_advanced` (incl. `seeded_accepted`), F4 `quickset_abandoned` |
| — | commit 13: flip `surface` to required |

> **Waiver condition (S-46 / P0-7 §7):** `mobile/.maestro/04-tabs-navigation.yaml` and
> `mobile/.maestro/flows/smoke/09-league.yaml` **must pass unmodified**. They are the
> regression proof that stands in for the waived flow. **Any diff to those files
> invalidates the waiver** — W2-P07 does not own them and must not edit them.

### Wave 3 — two agents

#### `W3-DOCS` — every shared doc + living-memory file

Owns all of §7. No build agent edits a `docs/` or `living-memory/` file; each supplies
its rows via its scope block. This removes eight would-be contentions in one move
(`api-reference.md`, `data-dictionary.md`, `cross-client-invariants.md`, `runbook.md`,
`glossary.md`, `DECISIONS.md`, `GOTCHAS.md`, `NEXT.md`).

#### `W3-QA` — the sim gate

Tier **1** for the batch (mobile screen + navigation changes): full smoke suite (11
flows) + all seven new/changed feature flows + `screen-capture.sh` for `trades`,
`matches`, `leagues`, `settings`, `league`, `signin` + `screen-freshness.sh`. Evidence
to `TEST_LEDGER.md` and `qa/sim-runs/last-sim-run.json`. One tier-1 run covers all
seven findings.

### Contention resolution summary

| File | Claimed by | Resolution |
|---|---|---|
| `TradesScreen.tsx` | P0-2, P0-8/9, P0-6 (`:4713`), P0-7 (`:4713`) | **W2-TS owns it exclusively** and applies P0-6's + P0-7's one-liners per their specs. |
| `SendInSleeperButton.tsx` | P0-6 (render path), P0-7 (handlers + prop) | **W1-P06 owns the signature + render path** (declares `surface` optional); **W2-P07 inserts into `onPress`/`catch` only.** |
| `TradeCard.tsx`, `InLeagueCalculator.tsx` | P0-6 (names), P0-7 (`surface`) | **W1-P06 applies both** — same JSX elements, one edit. |
| `RootNav.tsx` | P0-5 (routing + harness gate), P0-3 (route registration) | **Wave 1 = W1-P05, wave 2 = W2-P03.** Sequential. |
| `LeaguePickerScreen.tsx` | P0-5 (companion state), P0-3 (auto-pin) | **Wave 1 = W1-P05, wave 2 = W2-P03.** Sequential. |
| `SignInScreen.tsx` | P0-5 (harness), P0-3 (banner) | **Wave 1 = W1-P05, wave 2 = W2-P03.** Sequential. |
| `server.py` | P0-1, P0-3, P0-5 seam, P0-7 | **W1-BE owns it for the whole build.** Four well-separated regions, one pytest run. |
| `useSession.ts` | P0-3 (writes), P0-5 (reads `NO_LEAGUE_ID` only) | **W2-P03 only.** P0-5's interaction is a read of an existing export. |
| `LeagueScreen.tsx` | P0-3 (`:373`), P0-7 (events) | **W2-P07 only** — §10.2 removes P0-3's edit entirely. |
| `analytics_taxonomy.py` / `analytics_queries.py` | P0-7, P0-3 (B4) | **W0-TAX only.** P0-3's names fold into commit 1. |
| `mobile/src/components/CLAUDE.md` | P0-1, P0-6, +new testIDs | **W3-DOCS.** It is documentation — `testid-lint.sh` greps `mobile/src`, not this file (§10.3). |
| `docs/**`, `living-memory/**` | all seven | **W3-DOCS.** |

---

## 5. The unified harness seam

**One extension, two capabilities.** S-21 forbids two ad-hoc hacks; this is the single
design that serves both P0-5's account-only sign-in and P0-3's signed-out `LeagueJoin`
entry.

### 5.1 Gates — exactly two, both pre-existing and audited

| Gate | Where | Why it cannot leak |
|---|---|---|
| `FTF_TEST_MODE=1` (server) | already mounts the whole `/__test__` blueprint (`server.py:2015`) | never set in Render; the seam's 401-when-unset is **asserted by pytest**, not assumed |
| `IS_TEST_BUILD` (client) | `Constants.expoConfig.extra.testMode`, baked at build time by `app.config.js` from `FTF_ENV=test` | produced solely by `mobile/scripts/sim-build.sh`; `false` in every EAS bundle; there is no runtime path that can set it |

**No third gate, no new `/__test__` route, no new feature flag, no new env var.**

### 5.2 Client — `mobile/src/utils/testRouteEntry.ts` becomes the single harness module

Today the file privately computes `IS_TEST_BUILD` and reads two launch args
(`FTFTestRoute`, `FTFTestRouteParams`). Three additions, all inside the existing gate:

1. **Export the gate.** `export const IS_TEST_BUILD` (or `isTestBuild()`).
   `SignInScreen` imports it rather than re-reading `Constants.expoConfig.extra` — one
   definition of the production gate, greppable in one place.
2. **One accessor for every harness launch argument.**
   ```ts
   /** Returns a launch-argument value ONLY in a test build. null everywhere else. */
   export function testLaunchArg(name: string): string | null
   ```
   `FTFTestRoute`, `FTFTestRouteParams` and the new `FTFTestAppleSub` all go through it.
   Naming convention for anything added later: `FTFTest<Thing>`, query-string values
   only, **never JSON** (the existing `FTFTestRouteParams` contract).
3. **A signed-out entry allowlist.**
   ```ts
   /** Root-stack routes the harness may enter on a SIGNED-OUT boot. */
   const SIGNED_OUT_ENTRY_ROUTES = new Set<string>(['LeagueJoin']);
   export function applyTestRouteEntry(ref, opts: { authed: boolean }): boolean
   ```
   The function itself decides; `RootNav` stops encoding the policy.

`RootNav.tsx:341` changes from
`if (initialRoute === 'Main') applyTestRouteEntry(navigationRef);` to
`applyTestRouteEntry(navigationRef, { authed: initialRoute === 'Main' });`.
Behaviour is byte-identical for every existing flow: a non-authed boot still refuses
every route except the one name on the allowlist. **The allowlist is a set, not a
predicate** — adding a second signed-out route later is a deliberate one-line decision,
not an accident.

`SignInScreen`: gate **only** the SDK call.
```ts
const sub = testLaunchArg('FTFTestAppleSub');            // null in production
const credential = sub
  ? { identityToken: `ftf-test-apple:${sub}` }
  : await AppleAuthentication.signInAsync(...);
```
and render the Apple button even when `isAvailableAsync()` is false, under the same
condition. **Every line after that** — the `account_only` branch, `setUser`, `setLeague`,
`onAccountSignedIn` — is production code under test. Stubbing further up (seeding
`useSession` directly) would test the harness instead of the fixed branch.

### 5.3 Server — one helper in `auth_apple`

```python
def _test_mode_identity(identity_token: str) -> dict | None:
    """Harness only. FTF_TEST_MODE=1 + 'ftf-test-apple:<sub>' -> {'sub': sub}.
    Returns None in every deployed configuration."""
```
Used at exactly one call site, in place of `verify_apple_token`, and only when it returns
non-`None`. Everything downstream — `_provider_auth_response`,
`_mint_account_only_session`, the sentinel league, `verified_via='apple'` — is the real
production path, unmodified.

Pinned by `backend/tests/test_account_only_harness.py`: with `FTF_TEST_MODE` unset,
`POST /api/auth/apple {"identity_token": "ftf-test-apple:x"}` returns **401
`invalid_token`**.

### 5.4 Conformance with the 23 flow-authoring laws

| Law | How this seam satisfies it |
|---|---|
| **17** — `openLink` raises an undismissable SpringBoard confirm on iOS 18 | Deep-link entry is launch-argument-only. Neither new flow calls `openLink`. |
| **6** — the react-query cache is persisted | Both new flows use `clearState: true, clearKeychain: true, stopApp: true` for the first leg; P0-5's relaunch leg deliberately uses `clearState: false` because *persistence* is what it is testing. |
| **10** — assert the typed username before submitting sign-in | P0-3's authed blocks use the retry-hardened preamble verbatim; P0-5's Apple leg types nothing. |
| **8** — tab taps race #244 launch routing | Both flows settle on a surface-owned control before any `tab.*` tap. |
| **1** — text matchers are full-match regex | Every text assertion is wrapped in `.*` (`".*Connect Sleeper, ESPN or MFL.*"`, `".*invited you to.*"`). |
| **4** — template-literal `testID`s are lint-invisible | All new ids are plain string literals (`leaguejoin.*`, `leagues.empty.*`, `signin.invited-banner`, `leaguepicker.invite-notice`). No `testid-lint-allow.txt` entry needed. |
| **5** — `waitForAnimationToEnd` never stabilizes on an ActivityIndicator | `LeagueJoinScreen` renders a spinner; its screenshot is taken immediately after the trigger, never after a wait. |
| **16** — `# flags:` names a resolved fixture under `backend/tests/fixtures/flags/` | Both flows carry `# flags: release`. |
| **19** — kill orphaned backends before a run | Operator step in the sim-gate runbook, not the flow. |
| **23** — eyeball the screenshot | Both flows' shutters are eyeballed during the tier-1 run and the result recorded. |
| banned patterns | No fixed sleeps, no coordinate taps, no `tapOn: text:` — `testid-lint.sh` enforces all three. |

### 5.5 What the seam explicitly does not do

- It does **not** create an account-only seeder profile. The seam mints a *real*
  account-only session through the production path; a fixture profile would test the
  fixture.
- It does **not** cover the link→`Main` completion leg (live ESPN/MFL egress, forbidden
  by the hermetic rails audit) — waiver W-2, covered by manual TestFlight.
- It does **not** read the iOS pasteboard (P0-6's copy string is verified by unit test
  plus one manual paste) or assert the SpringBoard push-permission alert (P0-1's proxy
  is `rank.unlocked-banner` ⇔ `progress.unlocked` ⇔ `pushEnabled`).

---

## 6. Maestro delta inventory

Deduplicated across all seven plans. **7 new files, 5 modified, 3 must-pass-unmodified.**

### New

| # | File | Owner | Proves |
|---|---|---|---|
| 1 | `mobile/.maestro/flows/p0-1-quickset-unlock.yaml` | W1-BE | 4/4 ring **and** `rank.unlocked-banner` in one session (simultaneity is the acceptance criterion) |
| 2 | `mobile/.maestro/flows/p0-5-account-only-picker.yaml` | W1-P05 | brand-new Apple sign-in reaches the platform choice with no Settings visit; relaunch leg; `assertNotVisible tab.trades` |
| 3 | `mobile/.maestro/capture/leagues@account-only.yaml` | W1-P05 | screen-library frame for the new visual state |
| 4 | `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml` | W1-P06 | stated reason **and** useful action on an ESPN match |
| 5 | `mobile/.maestro/flows/trades-generation-failure.yaml` | W2-TS | Paths A/B/C each produce a named persistent state with a working retry |
| 6 | `mobile/.maestro/flows/guide-no-false-signoff@release.yaml` | W2-TS | **fails on the unfixed tree** — the only true regression test in the batch |
| 7 | `mobile/.maestro/flows/league/invite-join.yaml` | W2-P03 | authed pin / authed non-member / signed-out banner (block 3 needs §5) |

### Modified

| # | File | Owner | Why mandatory |
|---|---|---|---|
| 8 | `mobile/.maestro/capture/league@quickset-done.yaml` | W1-BE | its whole header argues the 4/4-but-locked contradiction; rename the capture id and re-justify the `league.works-now` step |
| 9 | `mobile/.maestro/capture/matches@espn.yaml` | W1-P06 | its `assertNotVisible "Send in Sleeper"` passes before **and** after; add the positive assertion (S-28) or lose the detector |
| 10 | `mobile/.maestro/capture/trades.yaml` | W2-TS | its error leg waits for `trades.empty-text` to reappear — it **breaks the moment the fix lands** |
| 11 | `mobile/.maestro/capture/onboarding-tour@fresh.yaml` | W2-TS | S8.1 precondition comment + the **D3 `s5.1` variant walk** (real chip selections so `fresh > 0`) |
| 12 | `backend/tests/fixtures/profiles/espn.json` | W1-P06 | its description states the bug as current behaviour |

### Must pass **unmodified** (regression proof; editing them invalidates a waiver or a control)

| # | File | Guards |
|---|---|---|
| 13 | `mobile/.maestro/capture/leagues@fresh.yaml` | the non-account-only empty state did not move (asserts its literal sentence) |
| 14 | `mobile/.maestro/04-tabs-navigation.yaml` | P0-7's Maestro waiver — drives every `tabPress` handler it edits |
| 15 | `mobile/.maestro/flows/smoke/09-league.yaml` | P0-7's Maestro waiver — mounts both League screens |

Plus the full 11-flow smoke suite, run once for the batch at tier 1. Crossing surfaces to
watch: `04-tiers` (P0-1 save path), `06-trades-deck` (P0-1 unlock gate + P0-2 ladder),
`05-trades-render` (P0-2), `08-matches` (P0-6, Sleeper profile — expected unaffected),
`01-signin` + `02-league-pick` (P0-5's `initialRoute` change), `07-calculator` (P0-7's
`surface` prop).

### New `testID`s (all plain literals; `testid-lint.sh` finds them by source grep)

`rank.unlocked-banner` · `trades.deck-error` · `trades.deck-error.retry` ·
`leagues.empty.link-sleeper` · `leagues.empty.link-espn` · `leagues.empty.link-mfl` ·
`leagues.empty.link-fleaflicker` · `leagues.empty.body` · `send-in-sleeper.unavailable` ·
`send-in-sleeper.copy` · `leaguejoin.root` · `leaguejoin.title` · `leaguejoin.not-member` ·
`leaguejoin.cta` · `signin.invited-banner` · `leaguepicker.invite-notice`

---

## 7. Docs impact rollup

Union of all seven plans' docs tables, deduplicated. **Owner is `W3-DOCS` for every row**;
the "source" column says which build agent supplies the content in its scope block.

| Doc | Rows | Source |
|---|---|---|
| `docs/api-reference.md` | `/api/rankings/progress` — `ranking_method` now written at point of use, `unlocked` no longer depends on the chooser; annotate the four save routes with the side effect. **New row** `GET /api/league/invite-meta`. **New row** `GET /app/league/join/<id>` (302) in the static/share section. **Amend the AASA row at `:587`** — it enumerates claimed paths and goes wrong the moment B1 lands. Optional half-clause: `/api/trades/status` never mentions `error`. | P0-1, P0-3, P0-2(optional) |
| `docs/data-dictionary.md` | `users.ranking_method` `:105` — correct the stale enum (missing `'anchor'`, `'quickset'`) and add the implicit-write + backfill note. `user_events` "Trade:" bullet — add `sleeper_send_succeeded` with its props. | P0-1, P0-7 |
| `docs/cross-client-invariants.md` | Ranking-method strings `:205` — contract shifts from "the chooser records a preference" to "written at the point of use, first-use wins, `'anchor'` upgradable". **New:** `no_league` sentinel is a shared constant (`server.py` emits, `useSession.ts:56` + RootNav's predicate consume) and is documented nowhere today. **New:** the invite-URL format is a two-client contract — record both accepted forms and that the legacy form is parsed forever. §"Client analytics event contract" `:268` — the new names + addendum link, with an explicit note that web and the extension fire none of them. | P0-1, P0-5, P0-3, P0-7 |
| `docs/config-reference.md` | New flag `growth.invite_join_link` — default OFF, what it gates, graduation criterion (AASA propagated + verified on device). | P0-3 |
| `docs/runbook.md` | P0-1 backfill: runs at boot in `_migrate_db`, what it touches, expected one-time row count, the confirming `SELECT`, and the seed-fixture interaction. AASA section `:410-412`: the operational ordering — deploy AASA → wait for CDN → ship the build → **then** flip the flag. Mobile UI-test harness: the `FTFTestAppleSub` + `ftf-test-apple:<sub>` seam and both production gates. New subsection: the operator-only onboarding test (`trades_first_operator_test`) recipe + one-call rollback. | P0-1, P0-3, P0-5, P0-8/9 |
| `docs/glossary.md` | **account-only session** (Apple/Google identity, no bound Sleeper source, `acct_<id>` key, `no_league` sentinel). **invite intent** (the persisted `{leagueId, invitedBy, ts}` blob). | P0-5, P0-3 |
| `docs/design/components.md` | `Toast` gains a public `topOffset` prop — add a row **if** the doc specs Toast's prop surface; n/a if it only specs the visual. Verify at build. | P0-2 |
| `docs/business/analytics/2026-08-11-p0-7-addendum.md` **(new)** | Owned by **W0-TAX**, not W3-DOCS — it is the registry's stated precondition. Contents per §4 Wave 0. | P0-7 |
| `docs/plans/onboarding-conversion/guided-avatar-script.md` | `err.burst` deleted from the implementation; S8.1 now requires the S2.2 beat. | P0-8/9 |
| `screens/CLAUDE.md` | Index entry for the renamed `league@quickset-done` capture; re-captured `matches@espn` frames; new `leagues@account-only`. | P0-1, P0-6, P0-5 |
| `mobile/src/components/CLAUDE.md` | `SendInSleeperButton` row — "self-gates to Sleeper leagues" is now misleading. New `testID` registry entries (§6). New `LinkSleeperSheet` row. | P0-6, P0-1, P0-5, P0-2 |
| `mobile/src/api/CLAUDE.md` | Only if it names `setMatchDisposition` — verify at edit time. | P0-6 |
| `living-memory/LLD.md` | Implicit column writes from save handlers + the `set_ranking_method_if_unset` conditional-write idiom. Deep-link destinations reachable signed-out belong on the **root** stack. Post-auth routing keys off the `no_league` sentinel, never `user.account_only`; `LinkSleeperSheet` is the single owner of the Sleeper-identity-link form. | P0-1, P0-3, P0-5 |
| `living-memory/HLD.md` | **n/a** — every plan agrees: no new module, client, or major architectural flow. This document itself is the batch HLD and lives with the plans. | all |
| `docs/architecture.md` | **n/a** — no module wiring or data-flow change in any of the seven. | all |
| `living-memory/DECISIONS.md` | Last id is **`D-024`** (§10.4). New: **D-026** P0-1 first-use-wins + `'anchor'` exception + `'quickset'` labelling + suppressed fan-out · **D-027** P0-2 named persistent deck failure; `job.error` mapped, never echoed · **D-028** P0-3 legacy `?league=` parsed forever, 302 over a new web page, 14-day persisted intent · **D-029** P0-5 sentinel-not-flag routing predicate, `LinkSleeperSheet` extraction, no new flag · **D-030** P0-6 RN-core `Clipboard` over `expo-clipboard`, delete the mobile disposition wrapper · **D-031** P0-7 reserved `sleeper_send_*` names + the client/server split · **D-032** P0-8 beat-identity gate over step-count gate. | all |
| `living-memory/GOTCHAS.md` | Last id is **`G-026`** (§10.4). **G-029** first-run + four failed polls = a `SkeletonTradeCard` that never resolves · **G-030** MFL/Fleaflicker league ids are numeric, so `league_id.isdigit()` does not exclude them from the Sleeper propose path · **G-031** a client `track()` name absent from `analytics_taxonomy.py` is counted and dropped in silence — third occurrence in this repo. | P0-2, P0-6, P0-8/9 |
| `living-memory/NEXT.md` | Match accept/decline UX (P0-6 option B, with the evaluation) · MFL/Fleaflicker harness profile · `is_linked_platform_league` guard on `/api/sleeper/propose` · `source` prop on `find_trades_tapped`'s allowlist (S-12) · `FUNNEL_CRITICAL` ↔ SDK-mirror drift (`app_opened_first`). | P0-6, P0-2, P0-7 |
| `living-memory/CHANGELOG.md` | One dated H2 for the batch at ship, naming the two behaviour changes users will notice: account-only testers move to the picker at next launch; MFL/Fleaflicker users lose a tappable (always-failing) Send button. | all |
| `living-memory/TEST_LEDGER.md` | Tier-1 sim run + the P0-7 row-landed verification + the P0-6 manual clipboard paste, verbatim. | W3-QA |
| `living-memory/DEPENDENCIES.md` | **n/a** — no dependency added, bumped, or removed. That is the point of P0-6 §1.6. | P0-6 |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** — the audit is a dated artifact. Record the outcome in `CHANGELOG.md`; do not rewrite it. | all |

---

## 8. Risk register

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| **R1** | **Concurrent-session drift.** `CLAUDE.md` warns the working tree mutates; every plan's line numbers were taken at `ab9368f` and several had already drifted from the audit by 100-160 lines. | **High** | Every build agent **re-greps its anchors immediately before editing** and never trusts a line number from a plan. `server.py` and `TradesScreen.tsx` are single-owner per wave precisely so a rebase has one author. Waves are merge points: re-diff `origin/main` between waves. |
| **R2** | **AASA CDN lag (up to ~24h).** Ship the new URL before the claim propagates and every invite opens Safari — a *worse* loop than today. | **High** | S-14: 302 + AASA are unflagged and land in commit 3; the emitter is behind `growth.invite_join_link` default OFF. The runbook encodes the ordering and it is the flag's graduation criterion. The flag is flipped in a **separate session after on-device verification**, never in this build. |
| **R3** | **Client wired before the taxonomy is registered** → every new event counted-and-dropped, 200 responses throughout, and a plausible dashboard with no rows. Three live instances already in the tree. | **High** | S-36: commit 1 is first and owns both registry files exclusively. `test_events_api.py` asserts `dropped == 0` **and** an exact `set(by_type)`; `GET /api/analytics/health` counters are checked flat during the sim run. |
| **R4** | **DAU/WAU step-change on ship day** if `tab_selected` / `league_view` land as INTENT. Every retention and churn series breaks at that seam, silently and permanently. | **High** | S-32: `NON_INTENT_EVENTS` additions are mandatory and in commit 1. Post-ship check: confirm DAU/WAU did not step-change on the ship date. Seam date recorded in the addendum. |
| **R5** | **The fixture inversions.** P0-1 rewrites a fixture and a seeder guard authored days ago *specifically to preserve* this bug; P0-6's `matches@espn` capture and `espn.json` describe the bug in the present tense; P0-2's `trades.yaml` error leg **asserts** the bug and breaks the instant the fix lands. Miss any one and either the seeder refuses coherent profiles or a green flow documents behaviour that no longer exists. | **High** | Each inversion ships **in the same commit as its fix** (S-06, and commits 8 and 11). §6 lists all five as mandatory. The re-capture is unconditional for the renamed frames. Pre-fix control run required for P0-1 and P0-2 — a test that never observed the bug proves nothing. |
| **R6** | **`TradesScreen.tsx` merge complexity.** 6 158 lines, four findings, ~25 distinct edits, on the app's most-trafficked screen. | **High** | Single exclusive owner (`W2-TS`) for the whole wave; **no other agent may open the file**. The agent commits once (commit 11) and may internally stage P0-2 / P0-8-9 / the two inherited one-liners as separate hunks, but they land together so the flows that assert the old behaviour move with them. Tier-1 smoke is the safety net. |
| **R7** | **Backfill blast radius.** The backfill flips `unlocked` for a whole cohort at Flask boot, on every boot, including the seeded UI-test backend. | **High** | Cohort is deliberately narrow (all four positions in ≥1 format) so it is *strictly improving* — for every row it touches the tiers branch returns `True`, which is ≥ whatever the trio branch returned. Idempotent by predicate. Push fan-out **suppressed** by pre-seeding `unlocked_formats` (S-03). Wrapped so it can never break boot. Dry-run count against a prod replica is a **pre-merge checklist item**. T-18…T-22 pin the cohort; T-9/T-19/T-20/T-23 pin "nobody loses an unlock". |
| **R8** | **`LinkSleeperSheet` extraction regression.** The moved code includes the 409 `merge_choice_required` Alert, whose failure mode is *deleting the wrong ranking board*. | Med | Move **verbatim**; keep `testID="settings.link-sleeper-input"` on the extracted input so `capture/settings.yaml` and the lint keep pointing at it; manual test 15 exercises the 409 from the **new** entry point; `capture/settings.yaml` must stay green. |
| **R9** | **P0-6 removes a currently-tappable control on MFL/Fleaflicker.** Not purely additive. | Med | Named in the CHANGELOG rather than discovered. The removed control always 400s today, so no capability is lost. Pinned by the pure-module unit tests (S-25). |
| **R10** | **Retroactive route flip for existing TestFlight account-only users** — anyone sitting on empty tabs finds themselves on the picker at next launch. | Med | That is the fix working. Release-notes line. The predicate keys off the sentinel, so a user who already linked ESPN/MFL is unaffected. |
| **R11** | **`league_view` double-fires** — `LeagueSummaryScreen` runs two parallel queries with `placeholderData`. | Med | `firedRef` guard + `query.isFetched` dependency; verified on sim by counting rows for one visit. |
| **R12** | **P0-7's Maestro waiver is invalidated by an accidental edit** to `04-tabs-navigation.yaml` or `smoke/09-league.yaml`. | Med | Neither file is in any agent's ownership list; §6 lists them as must-pass-unmodified; a diff to either is a review stop. |
| **R13** | **Leg-3 injection leakage** in `trades-generation-failure.yaml` (`count: 4` matching `MAX_POLL_FAILURES` exactly). | Low | Assert `/__test__/whoami`'s `active_injections` is empty between legs, or re-arm. Never call `INJECT_KIND: reset` mid-flow — it clears in-memory sessions and signs the app out. |
| **R14** | **RN-core `Clipboard` is deprecated** and will be removed from react-native. | Low | The whole surface is one function in `mobile/src/utils/clipboard.ts`; migrating to `expo-clipboard` is a one-file edit at the next scheduled native rebuild. `npm install` is unavailable to this build (`mobile/node_modules` is a symlink) and a native module would put a DEPENDENCIES entry and a native-build risk into a *Bug, effort S* item. |
| **R15** | **`platform` cache trustworthiness** — a league row that lost its platform stamp resolves to `'sleeper'` and shows the old always-failing button on MFL. | Low | Pre-existing `#146` fail-open contract; the fix does not widen it, and failing *closed* would hide Send on Sleeper leagues whenever the cache is cold — strictly worse. Named as a known limit. |
| **R16** | **Analytics discontinuity** — method-segmented charts show a step change (NULL collapses, `'quickset'` jumps) across the deploy boundary. | Low | CHANGELOG + DECISIONS entries. There is no way to backfill "which method did they actually use" retroactively; the `'quickset'` label is an explicit, recorded assumption. |
| **R17** | **`s5.1` (D3) turns out to be broken.** It is the payoff beat carrying the entire trades-first argument and has never rendered in this repo's evidence. | Med | S-43 makes proving it a gate on the validation pass. If it does not render, that is the most important defect in the set and it is surfaced to the operator **before** any first-session test is run — a test whose payoff moment is unverified cannot answer the question that was asked. |

---

## 9. LLD assignments

Seven LLD/PRD agents, one per finding. Each is bound by the HLD sections named; **an LLD
may not contradict a §2 row, re-partition §4, or redesign §5.** Where an LLD's finding
plan disagrees with this document, §10 is the reconciliation of record.

### LLD-1 — P0-1 (Quick Set unlock)
**Scope:** point-of-use `ranking_method` writes; the suppressed startup backfill; the
fixture/seeder/capture inversion.
**Files:** `backend/database.py`, `backend/server.py` (four save handlers +
`_note_ranking_method` + import + ladder comment), `backend/tests/fixtures/profiles/quickset-done.json`,
`backend/tests/fixtures/seed_ui_test_db.py`, `backend/tests/test_ranking_method_point_of_use.py`,
`mobile/src/screens/RankScreen.tsx`, `mobile/.maestro/flows/p0-1-quickset-unlock.yaml`,
`mobile/.maestro/capture/league@quickset-done.yaml`.
**Bound by:** §2 S-01…S-07 · §3 commit 2 · §4 W1-BE · §6 rows 1, 8 · §7 (api-reference,
data-dictionary, cross-client-invariants, runbook, LLD.md, D-026) · §8 R7.
**Must specify:** the exact `unlocked_formats` pre-seed that suppresses the fan-out
(S-03) — this is the one part of the backfill the plan describes only as an option;
the `allow_over` signature; the conditional-`UPDATE` SQL; the inverted `_validate_quickset`
guard text. **Must not:** add a flag, add an event, touch the unlock ladder's logic,
or fix A-16/A-17.

### LLD-2 — P0-2 (failed trade search)
**Scope:** the `DeckFailure` state machine, the ladder branch, the toast offset.
**Files:** `mobile/src/screens/TradesScreen.tsx` (P0-2's 15 change-list items),
`mobile/src/components/Toast.tsx`, `mobile/.maestro/flows/trades-generation-failure.yaml`,
`mobile/.maestro/capture/trades.yaml`.
**Bound by:** §2 S-08…S-12 · §3 commit 11 · §4 W2-TS · §6 rows 5, 10 · §8 R6, R13.
**Must specify:** the exact insertion points relative to the *other three* findings
editing the same file, expressed as **grep anchors, not line numbers**; the three copy
constants; the row-4 guard; `jobErrorCopy`'s mapping. **Must not:** echo `job.error`
verbatim (it is `str(e)` of a server-side Python exception); change the existing toast
wording; add a flag or an event.

### LLD-3 — P0-3 (invite loop)
**Scope:** the `?league=` reader, the `LeagueJoin` route + screen, persisted invite
intent, the invited sign-in banner, and the three server routes.
**Files:** server half — `backend/server.py` (B1-B3), `backend/feature_flags.py`,
`config/features.json`, `backend/tests/fixtures/flags/release.json`,
`backend/tests/test_invite_links.py`. Client half — `mobile/src/utils/deepLinks.ts`,
`mobile/src/state/useSession.ts`, `mobile/src/screens/LeagueJoinScreen.tsx` (new),
`mobile/src/navigation/RootNav.tsx`, `mobile/src/screens/LeaguePickerScreen.tsx`,
`mobile/src/screens/SignInScreen.tsx`, `mobile/src/components/InviteLeaguematesBanner.tsx`,
`mobile/src/api/league.ts`, `mobile/.maestro/flows/league/invite-join.yaml`.
**Bound by:** §1.2 Spine A · §1.3 (the flow diagram is normative) · §2 S-13…S-18 ·
§3 commits 3 and 12 · §4 W1-BE + W2-P03 · §5 (the harness is designed, not
re-designed) · §6 row 7 · §7 · §8 R2.
**Must specify:** `LeagueJoinScreen`'s four-way decision incl. **case D** (account-only →
P0-5's companion state with context); the `ftf_invite_intent` blob shape, TTL sweep, and
`bootstrap`/`signOut` interaction; the imperative flag read inside `buildInviteUrl`
(§10.2). **Must not:** touch `LeagueScreen.tsx`; touch `analytics_taxonomy.py` (names
are registered in commit 1); emit any client `track()` call before commit 1 has landed;
pin an invited Sleeper league for an `acct_` user.

### LLD-4 — P0-5 (account-only stranding)
**Scope:** the routing fix, the sentinel-aware relaunch predicate, the picker companion
state, the `LinkSleeperSheet` extraction, and the client half of the harness.
**Files:** `mobile/src/navigation/RootNav.tsx`, `mobile/src/screens/LeaguePickerScreen.tsx`,
`mobile/src/screens/SettingsScreen.tsx`, `mobile/src/components/LinkSleeperSheet.tsx` (new),
`mobile/src/screens/SignInScreen.tsx`, `mobile/src/utils/testRouteEntry.ts`,
`mobile/.maestro/flows/p0-5-account-only-picker.yaml`,
`mobile/.maestro/capture/leagues@account-only.yaml`.
**Bound by:** §1.2 Spine A · §2 S-19…S-22 · §3 commits 6 and 7 · §4 W1-P05 · §5 (owns
the client half) · §6 rows 2, 3, 13 · §7 · §8 R8, R10.
**Must specify:** the companion state's **optional `invitedBy` / `invitedLeagueName`
props and their copy fork** — this is the seam P0-3 renders into and P0-5 must ship it
even though nothing supplies it in wave 1; the verbatim extraction boundary for the 409
Alert; the footer-suppression condition. **Must not:** add a skip affordance; key any
predicate off `user.account_only`; change the non-account-only empty state (an existing
capture asserts its literal sentence).

### LLD-5 — P0-6 (ESPN send fallback)
**Scope:** the platform-generic gate, the unavailable state, the clipboard payload, the
disposition-wrapper deletion, **and the `surface` prop declaration on P0-7's behalf**.
**Files:** `mobile/src/components/SendInSleeperButton.tsx`, `mobile/src/utils/tradeText.ts`
(new), `mobile/src/utils/clipboard.ts` (new), `mobile/src/components/TradeCard.tsx`,
`mobile/src/components/InLeagueCalculator.tsx`, `mobile/src/screens/MatchesScreen.tsx`,
`mobile/src/api/trades.ts`, `mobile/tests/check-trade-text.js`, `mobile/package.json`,
`mobile/.maestro/flows/p0-6-espn-copy-trade.yaml`, `mobile/.maestro/capture/matches@espn.yaml`,
`backend/tests/fixtures/profiles/espn.json`.
**Bound by:** §2 S-23…S-29 · §3 commit 8 · §4 W1-P06 · §6 rows 4, 9, 12 · §7 · §8 R9,
R14, R15.
**Must specify:** the **line-range proposal P0-7 inserts into** — an explicit statement
of which regions of the post-fix file are P0-7's (`onPress`, the `doPropose` catch) and
which are frozen; the `SendSurface` type and the optional `surface?` declaration; the
`resolveSendPlatform` fail-open invariant. **Must not:** fire any `track()` call; add a
flag; touch `TradesScreen.tsx`; touch the propose route.

### LLD-6 — P0-7 (analytics)
**Scope:** the taxonomy registration (commit 1), the server-fired success event, and all
client instrumentation including S-37's F1/F3/F4.
**Files:** `backend/analytics_taxonomy.py`, `backend/analytics_queries.py`,
`backend/tests/test_events_api.py`, `backend/tests/test_analytics_p0.py`,
`docs/business/analytics/2026-08-11-p0-7-addendum.md` (new), `backend/server.py`
(`_record_send_success` + one call), `mobile/src/navigation/TabNav.tsx`,
`mobile/src/screens/LeagueScreen.tsx`, `mobile/src/screens/LeagueSummaryScreen.tsx`,
`mobile/src/components/SendInSleeperButton.tsx` (handlers only),
`mobile/src/api/flags.ts`, `mobile/src/state/useFeatureFlags.ts`,
`mobile/src/screens/QuickSetTiersScreen.tsx`.
**Bound by:** §1.2 Spine B · §2 S-12, S-18, S-23, S-30…S-38 · §3 commits 1, 5, 9, 10,
13 · §4 W0-TAX + W1-BE + W2-P07 · §7 · §8 R3, R4, R11, R12.
**Must specify:** the **`experiment_exposed` emission mechanism** — the plan asserts F1
is needed but never says where it fires. This HLD's design: record overlay provenance
during the `configs[*].flags` merge in `api/flags.ts`, and emit **deferred** (never
during render) from `useFeatureFlags` on the first consumption of an overlaid key, once
per key per session. Also: the F3 `seeded_accepted` derivation; the `error_code`
derivation ladder; the `_record_send_success` signature. **Must not:** touch
`TradesScreen.tsx` (the `surface="deck"` line belongs to LLD-2's agent); add an alias for
`celebration_fired` (S-41); edit `04-tabs-navigation.yaml` or `smoke/09-league.yaml`;
declare `surface` required before commit 13; add `is_self`; bump `last_trade_proposed_at`.

### LLD-7 — P0-8/P0-9 (tour sign-off + first-session test prep)
**Scope:** the `s8.1` beat gate, the `err.burst` deletion, D1, D2, and the P0-9
validation pass.
**Files:** `mobile/src/screens/TradesScreen.tsx` (four regions),
`mobile/src/components/analystScript.ts`,
`mobile/.maestro/flows/guide-no-false-signoff@release.yaml` (new),
`mobile/.maestro/capture/onboarding-tour@fresh.yaml`.
**Bound by:** §2 S-39…S-45 · §3 commit 11 · §4 W2-TS (**shares the agent with LLD-2 —
one author for `TradesScreen.tsx`**) · §6 rows 6, 11 · §7 · §8 R6, R17 · §10.1.
**Must specify:** the D3 variant walk (whether deterministic chip selection is possible,
and the manual fallback if not — **do not fake it**); the exact D1 condition; the three
D2 rename sites. **Must not:** flip any flag default; create the operator experiment
(that is an operator step in the final report); edit `config/tester_allowlist.json`
(S-45); assume `screen_viewed` needs wiring (§10.1).

---

## 10. Conflicts resolved here, and plan errors found by spot-check

Every item below was verified by reading the code in this worktree.

### 10.1 `screen_viewed` is already emitted — the adjudication's premise is false

**The adjudication S-38 says to "wire the registered-but-never-emitted `screen_viewed`
emission (P0-8/9's Q5)". It is already emitted.**

`mobile/src/navigation/RootNav.tsx:352` fires
`track('screen_viewed', { screen: r.name, prev_screen: null }, r.name)` on `onReady`, and
`:376` fires it on every `onStateChange` where the route name changed — which includes
**tab switches**, because `getCurrentRoute()` returns the deepest active route. `:181`
and `:365` fire `screen_left` with a real `dwell_ms`. `screen_viewed` is in
`ALLOWED_CLIENT_EVENTS` (`analytics_taxonomy.py:40`, props
`{screen, prev_screen, tab}`) **and** already in `NON_INTENT_EVENTS`
(`analytics_queries.py:61`), so it neither drops nor inflates DAU.

- **P0-7 §1.1 is correct** ("Live for **every** route, including `LeagueHome` /
  `LeagueRankings`. This is why P0-7 is *targeted additions*, not 'instrument navigation
  from zero'.").
- **P0-8/9 §3.4 and Q5, and `scope-p0-8-9.md:50`, are wrong.** They repeat the audit's
  "zero client instrumentation on navigation" without re-verifying it.

**Resolution:** S-38 resolves to a **verification** task, not a build task. It is already
covered by P0-7's §9.3 end-to-end check — confirm `screen_viewed` rows land in
`user_events` with `platform = 'ios'` (not NULL) during the sim run, and confirm the
`dropped_unknown_type` health counter stays flat. **No code is written for S-38.**
Time-to-first-value and the LeaguePicker→Trades drop-off are therefore *already*
readable, and P0-9's A6 criterion is satisfiable today. This should be told to the
operator explicitly, because it removes the dependency that P0-9's test was said to hang
on.

### 10.2 `LeagueScreen.tsx` contention dissolved

P0-3 M3 claims it must edit `LeagueScreen.tsx:373` because that is a second
`buildInviteUrl` call site; P0-7 needs the same file for `league_view` + OPTIONAL-A.

Verified: `buildInviteUrl(leagueId, username)` is a module-level pure function
(`InviteLeaguematesBanner.tsx:27-31`) called from **handlers**, not render, at both sites
(`InviteLeaguematesBanner.tsx:40` inside `handleInvite`, `LeagueScreen.tsx:373` inside
`inviteLeaguemates`). It can therefore read the flag imperatively —
`useFeatureFlags.getState().flags['growth.invite_join_link']` — exactly the `getState()`
idiom `FreeAgentsScreen` already uses for callback-time reads.

**Resolution (mandated):** the flag read lives **inside** `buildInviteUrl`. Both call
sites stay byte-identical, P0-3 does not touch `LeagueScreen.tsx`, and P0-3's own risk
row ("two emitters drift") is closed by construction rather than by a comment.
`LeagueScreen.tsx` belongs solely to `W2-P07`.

### 10.3 `testid-lint.sh` does not read the `CLAUDE.md` registry

P0-1 change-list item 15 says the new `rank.unlocked-banner` id must be registered in
`mobile/src/components/CLAUDE.md` "so `mobile/scripts/testid-lint.sh` passes".

Verified: the script cross-checks **flow ids against `grep` over `mobile/src`**, and
falls back to `mobile/scripts/testid-lint-allow.txt` (globs, for template-literal ids
only). It never opens `CLAUDE.md`.

**Resolution:** registry updates are documentation and move to `W3-DOCS` (wave 3) without
blocking any wave-1/2 lint. This is what makes `mobile/src/components/CLAUDE.md` — a
file three plans wanted — a non-contended doc row rather than a build-time dependency.

### 10.4 The `D-011` / `G-013` collision — root `CLAUDE.md` is stale

Five plans (P0-1, P0-5, P0-6, P0-7, P0-8/9) each claim their DECISIONS entry is
**`D-011`**, and two claim their GOTCHAS entry is **`G-013`**. They copied the "next ID"
column from root `CLAUDE.md`.

Verified against the files: `living-memory/DECISIONS.md`'s last entry is **`D-024`**
(`:209`); `living-memory/GOTCHAS.md`'s highest id is **`G-026`** (`:200`). Only P0-2 read
the actual files (it correctly proposes `D-026` / `G-029`).

**Resolution:** the ids assigned in §7 (`D-026`…`D-032`, `G-029`…`G-031`) are
authoritative; `W3-DOCS` allocates them in that order. **Root `CLAUDE.md`'s "next ID"
columns are stale and should be corrected in the same docs commit** — otherwise the next
batch of parallel agents makes the identical mistake. (This is itself an instance of the
handoff's **A-33** class: a doc contradicting the artifact it describes.)

### 10.5 Other reconciliations

| Conflict | Plans | Resolution |
|---|---|---|
| Who owns the `celebration_fired` fix | P0-8/9 Q3 offers "rename in the client" *or* "P0-7 adds an alias" | S-41 settles it: **client renames, no alias.** Recorded here so P0-7 does not add one defensively. |
| `err.burst` deletion vs. P0-2's error state | P0-8/9 R2 asks P0-2 whether it wants a mascot line | **Delete.** §1.4 confirms P0-2's design offers strictly more (named error + working retry) and two error surfaces on one failure is worse than one. |
| P0-6's §9 "split the file: P0-6 owns 30-66 and 273-end, P0-7 owns 105-271" | P0-6 §9 | **Rejected as a *parallel* split.** S-23 makes it a *sequential* handoff: P0-6 lands the whole file in wave 1, P0-7 inserts in wave 2. A line-range split inside one wave is exactly the three-way merge P0-6 itself calls avoidable. |
| P0-7's `surface` declared **required** vs. commit-level greenness | P0-7 §2/§9.2 | Declared **optional in commit 8**, tightened to **required in commit 13** once all four mounts are plumbed. Preserves both the compile-time enforcement P0-7 wanted and the "every commit independently green" rule. |
| Sim-gate tier | P0-7 argues tier 2; P0-1 tier 2; P0-2/3/5/6/8 tier 1 | **One tier-1 run for the batch.** The batch contains navigation and screen changes, so the strictest class governs; P0-6 §7.5 already anticipates this. |
| P0-3 B4 edits `analytics_taxonomy.py` | P0-3 | Folded into **commit 1** (S-18/S-36). P0-3 must not open the file. |
| P0-5's new pytest cases "extend `test_account_first.py`" | P0-5 §7 | New file `backend/tests/test_account_only_harness.py`. `test_account_first.py` is P0-5's own stated **must-stay-green-untouched** contract; extending it would break that guarantee. |
| P0-3's `mobile/src/api/leagues.ts` | P0-3 M11 | The module is `mobile/src/api/league.ts` (singular). `fetchInviteMeta` goes there. |

### 10.6 Things in the plans I believe are wrong or unproven, after spot-check

1. **P0-8/9's `screen_viewed` claim is false** — §10.1. This is the most consequential
   error in the set, because an adjudication was issued on it.
2. **P0-1's `testid-lint.sh` claim is false** — §10.3. Harmless, but it would have
   created a false wave-1 dependency on a docs file.
3. **Five plans' `D-011` / `G-013` ids are wrong** — §10.4. Root `CLAUDE.md` is the
   source of the error and should be fixed.
4. **P0-6's line-range parallel split (§9) does not survive S-23** — §10.5.
5. **P0-2's "the toast z-order is a misdiagnosis" is correct and the audit is wrong.**
   Verified: `Toast.tsx` sets `zIndex: 50` (correct — the toast *should* be on top);
   the defect is `top: space.xxl` (32) colliding with the mode bar's y-range (16…52).
   The handoff's "fix the z-order" must be read as "fix the overlap"; an actual z-order
   change would hide the message, which is worse.
6. **P0-2's defect (i) is real and strictly worse than the audit's finding** — ladder row
   4 excludes `job?.status === 'error'`, but Path C sets `job` to `null`, so the
   exclusion misses and a first-run user whose polling dies sees `SkeletonTradeCard`
   forever. Confirmed by reading `:1295-1307` and `:4819-4823`. It is fixed for free by
   the row-4 guard and belongs in GOTCHAS (`G-029`).
7. **P0-6's `/api/sleeper/propose` finding is real and wider than P0-6** — MFL and
   Fleaflicker league ids are numeric, so `league_id.isdigit()` does not exclude them
   even though `is_linked_platform_league` is imported in the same file and used at five
   other sites. S-26 correctly defers the guard, but it is a *server-side* hole that
   survives this build and must be on `NEXT.md`, not just in a plan.
8. **P0-3's `invite_shared` finding is real** — the only invite event in the product has
   been dropped on the floor since it shipped, which means the "the loop converts zero"
   claim has never been measurable. Registering it (commit 1) is the first time this
   funnel becomes readable at all.
9. **Unproven and worth the operator's attention:** P0-6's `formatTradeForClipboard`
   output has never been pasted anywhere. The only end-to-end proof the clipboard write
   lands is the single manual paste in §7.3 of that plan. Keep it in the ledger verbatim.
10. **P0-7's `experiment_exposed` (F1) has no specified emission site** in the plan — it
    says what the event is for and why it matters, but not where it fires. §9 LLD-6
    supplies the design; without it F1 would have been "registered but never emitted",
    which is the exact defect F1 exists to fix.
