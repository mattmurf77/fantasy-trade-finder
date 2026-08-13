# P1-5 — Invite is buried, duplicated, and unmeasured

> Build plan for audit finding **P1-5 / A-14** (`docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` §P1 row 5; `06-resolutions.md` row A-14).
> Branch `p1-remediation-2026-08-11`, worktree `ftf-p1-remediation` @ `ab9368f` (== `origin/main`).
> **Plan only — no code written.** Every citation below was re-read in this worktree on 2026-08-11.
> **Full feature gates apply** — this change touches **analytics events**, which `CLAUDE.md` §Conventions names as a bright line. Not a quick fix; not agent-selectable for express.
> Scope block: [`scope-p1-5.md`](scope-p1-5.md).
> **Sequencing dependency: P0-3 (`p0-remediation-2026-08-10`) merges to `main` before this build starts.** See [P0-3 dependencies](#p0-3-dependencies-hard).

## Table of contents

- [Verified current state](#verified-current-state)
- [Design](#design)
- [P0-3 dependencies (hard)](#p0-3-dependencies-hard)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact table](#docs-impact-table)
- [Test plan](#test-plan)
- [Risks and cross-item collisions](#risks-and-cross-item-collisions)
- [Operator checkpoints](#operator-checkpoints)

---

## Verified current state

### The claim the task asked me to falsify — **it holds, and it is stronger than the audit says**

A-14 asserts the social-proof number ships today via `load_league_member_unlock_states`, "per-member join status is already returned; NO new endpoint needed." Verified, three separate ways:

| Fact | Evidence |
|---|---|
| `load_league_member_unlock_states(league_id, exclude_user_id)` returns **`"joined": bool` per member** — literally `joined = True` iff a `users` row exists for that `sleeper_user_id` | `backend/database.py:5656-5746`; the `joined` assignment at `:5713`, docstring contract at `:5665` |
| Its dedicated route `GET /api/league/member-unlock-states` is **flag-gated** on `league.unlock_badges_per_member` and returns `{"members": [], "flag_off": true}` when off | `backend/server.py:13463-13507`, gate at `:13497` |
| **The ungated path exists**: `GET /api/league/members` calls the *same loader* via the same 60 s cache and projects `joined` — explicitly documented as *not* flag-gated because "join status is base info, always shown" | `backend/server.py:13511-13581`, docstring `:13519-13521`, projection `:13566-13574`, cache `_league_members_cached` at `:5776-5786` |
| The mobile client **already calls it on League Home**, unconditionally, with a 60 s `staleTime` | `mobile/src/screens/LeagueScreen.tsx:198-204` (`membersQuery`), typed `LeagueMember.joined` at `mobile/src/api/league.ts:207-213` |

**Stronger than the audit knew — the aggregate is already on a payload the screen already has.** `get_league_summary` returns `leaguemates_total` and `leaguemates_joined` (`backend/database.py:5642-5643`, zero-branch at `:5606-5608`), served unflagged by `GET /api/league/summary` (`backend/server.py:13363-13389`), and **`LeagueScreen.tsx:310-311` already destructures both into `totalMates` / `joinedMates`**. They are already rendered in the hero "joined" chip (`:450-464`) and the members-overlay subtitle (`:816-820`).

> **Consequence for the build: the social-proof string needs no new endpoint, no new query, and not even a new field read.** It is `totalMates - joinedMates` of `totalMates`, from data in scope at `LeagueScreen.tsx:311`. On `MatchesScreen` the same rollup is already fetched (`leagueSummaryQuery`, consumed at `:385-397`) — only `leaguemates_total`/`_joined` need adding to the `emptyModule` memo, which is a two-line change, not a request.

### The affordance, as it actually stands

| Fact | Evidence |
|---|---|
| League tab root is **`LeagueRankings`** (the power-rankings chart), not League Home | `mobile/src/navigation/TabNav.tsx:449-452` |
| League Home (`LeagueHome`) is a **pushed sub-route** reached by a row tap from the rankings screen | `TabNav.tsx:455-461`; the only in-app entry is `LeagueSummaryScreen.tsx:808` (`navigate('LeagueHome')`), plus one from `RankScreen.tsx:388` |
| On League Home the invite affordance is an **inline underlined text link inside a sentence**, appended to the unlock line of `LeagueProgressModule` | `mobile/src/components/LeagueProgressModule.tsx:124-137` (`inviteLink`, copy `"Invite them"`), spliced into the sentence at `:155`; second variant `"Invite leaguemates"` at `:200-212` for the matches-already-unlocked case |
| That link is **not a 44 pt target** — the component's own comment concedes it: *"Nested-Text link ⇒ no 44pt target; documented deviation"* | `LeagueProgressModule.tsx:263-272` |
| The module — and therefore the only invite affordance — renders **only while an unlock is outstanding** (`moduleVisible`), and disappears entirely once ring 4/4 + matches exist + contrarian unlocked | `LeagueScreen.tsx:351-359`, mounted at `:693-703` with `onInvite={inviteLeaguemates}` at `:700` |
| Tap count to invite, confirmed: `tab.league` → row tap to League Home → scroll → tap the text link → OS sheet. **Three taps deep**, exactly as the audit says. | chain above |
| The **Matches empty state has no invite affordance at all** — it mounts the `compact` variant, and `compact` never renders the invite (`!compact && onInvite`) and is passed no `onInvite` | `MatchesScreen.tsx:552-561`; guard at `LeagueProgressModule.tsx:125` |
| Matches empty state today: `matches.empty-text` title, body copy, **primary** `matches.go-to-trades` "Find a trade", compact module, ghost "Refresh", optional help link | `MatchesScreen.tsx:520-585` |
| `LeagueScreen.inviteLeaguemates` **fires no analytics of any kind** — it is a bare `Share.share` | `LeagueScreen.tsx:371-382` |
| `LeagueScreen.tsx` has **zero `track()` calls**, full-file grep | `grep -n "track(" mobile/src/screens/LeagueScreen.tsx` → no matches |
| The third emitter — the Trades cold-start banner — is the only one that tracks, and only when `growth.share_landing` is on | `mobile/src/components/InviteLeaguematesBanner.tsx:38, 46-48`; mounted at `TradesScreen.tsx:3543` |
| **`invite_shared` is NOT in `ALLOWED_CLIENT_EVENTS`** — the only invite event in the product has been counted-and-dropped behind a 200 since it shipped | `backend/analytics_taxonomy.py:38-99` (full block read; no `invite*` name present). Confirmed by `grep -n "invite" backend/analytics_taxonomy.py backend/analytics_queries.py` → **no matches in either file** |
| The members overlay lists every leaguemate with a `Joined` / `Not joined` chip and has **no invite button** — the one screen that already names the people who haven't joined | `LeagueScreen.tsx:791-848`, chips at `:837-842` |

### Analytics substrate (re-verified, not inherited from P0-7)

| Fact | Evidence |
|---|---|
| Default-deny: an `event_type` absent from `ALLOWED_CLIENT_EVENTS` is `dropped_unknown_type`, counted as accepted-and-dropped, **200 returned** | `backend/analytics_ingest.py` ingest guard; mechanism documented in `plan-p0-7.md` §1.2 and re-checked against `analytics_taxonomy.py:38-99` |
| Unknown **props are stripped**, event still lands — a silent partial loss, which is why extending an existing event's prop row matters as much as registering the name | same |
| An allowlisted event with no `CLIENT_EVENT_PROPS` row raises at **import** — loud, not silent | `analytics_taxonomy.py` import-time asserts |
| `INTENT_EVENTS = (SERVER_FIRED ∪ ALLOWED_CLIENT) - NON_INTENT_EVENTS` — a **deny-list**, so every new name enters DAU/WAU/retention by default | `backend/analytics_queries.py:64`; `NON_INTENT_EVENTS` at `:60-63` |
| **No reserved invite name exists in code.** `WAT_LIVE`/`WAT_DARK` (`:51-54`), `FUNNEL_STAGES` (`:66-80`) and `FEATURE_VERTICALS` (`:83-95`) contain nothing invite/growth-shaped | read in full |
| **But the tracking plan reserves a *different* name in prose:** tracking plan v2 §S3 specs `invite_sent` (`channel`) — while the code fires `invite_shared`. A naming fork, unresolved. | `docs/business/analytics/2026-07-17-tracking-plan-v2.md:78` |
| `platform` as an event prop means **LEAGUE** platform (`league_selected` precedent, `analytics_taxonomy.py:185`); device platform is a server-derived **column** on `user_events` | `analytics_taxonomy.py:185`; mechanism per `plan-p0-7.md` §1.1 |
| `growth.share_landing = true`, `growth.referral = false`, `growth.group_unlock = false` | `config/features.json:92-93, 125`; `backend/feature_flags.py:230-231, 272` |

### Test-harness reality

| Fact | Evidence |
|---|---|
| Fixture `standard` seeds `total_rosters: 12` with **2 listed (joined) members** plus the app user; the remaining 9 seats are filled with `joined=False` generated members | `backend/tests/fixtures/profiles/standard.json`; seeding loop `backend/tests/fixtures/seed_ui_test_db.py:563-593`, `_add_user(..., joined=False)` at `:592` |
| ⇒ `leaguemates_total = 11`, `leaguemates_joined = 2`, **not-joined = 9** — a real, deterministic, assertable string in the harness |  derived from the above |
| ESPN fixture members are synthetic `espn:` ids **deliberately not registered as users** | `seed_ui_test_db.py:568-573, 585-589`; `profiles/espn.json` |
| ⇒ on `espn`, `leaguemates_joined = 0` — so `joinedZero` folds the hero chip (`LeagueScreen.tsx:450`) and the invite ask would read "9 of your 9…" for a league whose invite link cannot resolve. See [risk R4](#risks-and-cross-item-collisions) |  |
| Maestro law 17: deep links are dead; launch-arg entry only. Law 23: a green run is not a good capture | `mobile/.maestro/README.md:140-146, 173-175` |
| Existing assertions that cross these surfaces: `flows/smoke/09-league.yaml:34` (`league.hero`), `flows/smoke/08-matches.yaml:38` (`matches.empty-text`) | grep of `mobile/.maestro/` |
| **No existing flow asserts any invite affordance.** `grep -rn "invite" mobile/.maestro/` → zero hits. Nothing asserts the bug being fixed; nothing needs un-asserting | verified |
| Capture library variants that will change visually: `league`, `league@espn`, `league@near-unlock`, `league@quickset-done`, `league@single-format`, `league@two-leagues`, `matches`, `matches@fresh`, `matches@near-unlock`, `matches@two-leagues`, `matches@espn` | `ls mobile/.maestro/capture/` |

### Drift from audit

| Audit citation | Current truth |
|---|---|
| "Invite is a text link inside a module, three taps deep" | **Accurate.** `LeagueProgressModule.tsx:124-137` + `:155`; entry chain `TabNav.tsx:449-461` → `LeagueSummaryScreen.tsx:808`. |
| "on an unmeasured page" | **Accurate and understated.** Zero `track()` in `LeagueScreen.tsx`, *and* `LeagueScreen.inviteLeaguemates` (`:371-382`) fires nothing even though the Trades-banner twin does. |
| "Use `load_league_member_unlock_states`, which already returns per-member join status … ships today with no new endpoint" | **True, but routed through a flag** (`league.unlock_badges_per_member`, `server.py:13497`). The correct, unflagged source is `GET /api/league/members` (`server.py:13511`, same loader) — and better still, the **aggregate is already on `/api/league/summary` and already in scope on both screens** (`LeagueScreen.tsx:310-311`; `MatchesScreen.tsx:385-397`). Building this against the flagged route would have made a default-ON feature depend on a flag for no reason. |
| "Matches empty state" needs the invite promoted | **Accurate — there is no invite there at all today**, not a demoted one. `compact` structurally cannot render it (`LeagueProgressModule.tsx:125`). |
| P0-3's citation `deepLinks.ts:301-302` | Already corrected by P0-3 to `:352-354`. Not touched by P1-5. |
| P0-3's citation `InviteLeaguematesBanner.tsx:27-31` (`buildInviteUrl`) | **Unchanged and accurate** in this worktree. P1-5 depends on P0-3's rewrite of exactly these lines. |
| Audit §Growth for League Home: *"P1 · Use the member list you already have"* graded **M** effort | With the aggregate already in scope, the data half is **S**. The M is the UI + analytics + capture refresh. |

### Comments that lie (the A-33 class — checked, per the method)

1. `InviteLeaguematesBanner.tsx:34-37` — *"the invite URL already IS the landing page … no URL change needed; the flag adds the share→open funnel event only."* **False on both halves as of today:** P0-3 proved mobile never read `?league=`, and the "funnel event" it claims to add has been dropped by the allowlist since it shipped. P0-3 M1 rewrites this comment; P1-5 must not reintroduce it.
2. `LeagueProgressModule.tsx:122-123` — *"saves the button row's ~36pt everywhere the full variant mounts."* True as written, but it records a **space** trade-off with no record that the thing traded away was the product's most important growth action. Worth a line in the replacement comment so the next reader sees why the button came back.
3. `LeagueScreen.tsx:369-370` — *"the OS share sheet with the same referral URL the InviteLeaguematesBanner builds (`?league=&ref=`)"*. Becomes wrong the moment P0-3's `growth.invite_join_link` flips. Both call sites must read the format from `buildInviteUrl`, never restate it.

---

## Design

Three principles, in the order they resolve conflicts:

1. **One invite affordance per screen, promoted — not a second one added.** Two invite CTAs on League Home would be worse than one buried link. The inline link is *suppressed* when the promoted card renders.
2. **One formatter, one share helper.** The codebase's own convention (`pickAssignmentSubline` — *"the ONE formatter behind both the League tab's sub-line and the screen's progress line so they cannot disagree"*, `mobile/src/api/CLAUDE.md`; `matchesUnlockRemaining` in `utils/leagueUnlocks.ts`). Four surfaces sharing one string and one share path cannot drift.
3. **Never fabricate a count.** The screen already folds sections only on *confirmed* data (`LeagueScreen.tsx:336-349`). The social-proof line renders only when the summary has actually arrived; otherwise the card renders its CTA with no number, never a `—` or a guess.

### S1 — League Home: a promoted invite card

New component `mobile/src/components/InviteLeaguematesCard.tsx`, mounted on `LeagueScreen` **directly below the hero and above the day-one action row** (`LeagueScreen.tsx:474`, between `:473` and `:478`). Chalkline `Card`, no new tokens:

```
┌───────────────────────────────────────────────┐
│ ▍Grow your league                             │   ← TickLabel-style label
│ 9 of your 11 leaguemates haven't joined yet.  │   ← social proof (heading weight)
│ Matches need two boards. Every leaguemate     │   ← body-sm rationale
│ who joins makes your trades better.           │
│ ┌───────────────────────────────────────────┐ │
│ │          Invite leaguemates               │ │   ← Button variant="primary"
│ └───────────────────────────────────────────┘ │
└───────────────────────────────────────────────┘
```

**Persistence.** Unlike the progress module it is **not** gated on `moduleVisible`. A league that has unlocked matches still has un-joined members, and that is the audit's whole point ("promote it, and use the member data you already have"). It is gated only on the ask being real.

**Render ladder — every branch stated:**

| Condition | Behaviour |
|---|---|
| `summaryQuery` has no data yet | Card does not render. No skeleton, no `—`. (Consistent with `summaryPending` discipline at `:297`.) |
| `totalMates === 0` (solo / unknown league) | Card does not render. Mirrors `LeagueProgressModule`'s `totalTeams <= 1` bail (`:113`). |
| `notJoined === 0` (everyone is here) | Card does not render — **OC-8** offers the affirmation alternative. |
| League platform ≠ `sleeper` | Card does not render; the legacy inline link stays. **OC-4** — the invite link cannot resolve for a non-Sleeper league id (see R4). |
| otherwise | Card renders with the social-proof line. |

**Suppressing the duplicate.** When the card renders, `LeagueScreen` passes `onInvite={undefined}` to `LeagueProgressModule` (`:700`). The component already treats a missing `onInvite` as "render no link" at `:125` and `:200` — **no change to `LeagueProgressModule.tsx` at all**, which keeps the #243-approved mock intact for every state where the card is absent (ESPN, solo, everyone-joined). This is the single cheapest way to honour principle 1. **OC-5**.

### S2 — Matches empty state: an invite action with its reason

`MatchesScreen.tsx:520-561`, mutual-empty branch. Insert **below** the existing `matches.go-to-trades` button and **above** the compact module:

```
        Find a trade            ← existing primary, unchanged
   9 of your 11 leaguemates
   haven't joined yet.         ← same formatter, body-sm
     Invite leaguemates        ← Button variant="secondary"
```

Same render ladder as S1, plus the screen's existing league-scoping guard: the block renders only when `emptyModule` is non-null — i.e. `filterLeagueId` is `'all'` or the active league, and both league reads have confirmed (`MatchesScreen.tsx:387-397`). A per-league social-proof number must never render under another league's filter chip.

**Why secondary, not primary.** The audit asks for primary on both screens. On League Home nothing competes — the card owns its own primary. On Matches, `matches.go-to-trades` is already primary, and two adjacent solid-ice buttons violate the Chalkline hierarchy and, worse, split the one action that converts *today* (find a trade) against one that pays off in days. Recommendation is the pair primary/secondary; **OC-2** offers the literal reading and the swap.

### S3 — Members overlay (OPTIONAL-M)

A `secondary` compact "Invite leaguemates" button in the overlay head (`LeagueScreen.tsx:803-815`), beside the close control. This is the surface that already renders `Not joined` per named person (`:837-842`) — the natural home for the audit's follow-on *"named-leaguemate invite"* (`02-tier-a-briefs.md:552`). Costs ~8 lines and one `testID`. **OC-7** — drop it cleanly by deleting one block and one `surface` enum value.

### The shared string

New export in the existing `mobile/src/utils/leagueUnlocks.ts` (already the home of `matchesUnlockRemaining`, already imported by `LeagueProgressModule.tsx:7`):

```ts
export function inviteSocialProof(totalMates: number, joinedMates: number): string | null
```

Returns `null` for every case where the ask isn't real (`totalMates <= 0`, `notJoined <= 0`, non-finite input) — so "should the card render" and "what does it say" are one decision, in one place, testable without a screen. Copy variants (grammar is not optional here):

| n = notJoined | total | String |
|---|---|---|
| ≥ 2 | ≥ 2 | `{n} of your {total} leaguemates haven't joined yet` |
| 1 | ≥ 2 | `1 of your {total} leaguemates hasn't joined yet` |
| 1 | 1 | `Your leaguemate hasn't joined yet` |
| 0 | any | `null` |

Framing is **OC-1** (this table is the "self-interested / factual" option).

### The shared share path

New `mobile/src/utils/inviteShare.ts` — one async helper owning URL construction, the share sheet, and both events:

```ts
shareInvite({ leagueId, leagueName, username, surface, notJoined, totalMates, platform }): Promise<void>
```

- Builds the URL by calling **`buildInviteUrl` imported from `../components/InviteLeaguematesBanner`** — P0-3 owns that function and its flag read; P1-5 never re-implements or copies it. (Import direction util→component is unusual but preserves P0-3's file ownership and produces a zero-line conflict there.)
- Fires `invite_cta_tapped` **before** `Share.share` (so an abandoned sheet is still counted), then `invite_shared` only when `res.action !== Share.dismissedAction` — preserving today's semantics at `InviteLeaguematesBanner.tsx:46`.
- Swallows the throw, exactly as all three existing call sites do.

All four call sites collapse to one line. This directly retires the drift risk P0-3's own risk table names (*"Two emitters drift — `LeagueScreen.tsx:373` and the banner"*), and does it for four emitters instead of two.

### Measurement design

Three events. The point of the finding is that promotion is unmeasurable today, so an impression denominator is not optional — a tap count with no exposure count cannot tell "the button works" from "more people saw it."

| Event | Class | Props | Fires when |
|---|---|---|---|
| `invite_cta_shown` | impression → **NON_INTENT** | `surface`, `not_joined` int\|null, `total_mates` int\|null, `platform` (**league** platform) | Once per mount per surface, `firedRef`-guarded, when the summary settles and the CTA is actually rendered |
| `invite_cta_tapped` | intent | same 4 | First statement of `shareInvite`, before the OS sheet |
| `invite_shared` | intent | same 4 + existing `league_id` | Sheet resolved non-dismissed — **existing behaviour, existing name, currently dropped on the floor** |

`surface` ∈ `league_home | matches_empty | trades_banner | members_overlay` — a closed 4-value enum covering every emitter including the two that exist today, so the promoted CTAs are comparable against the buried one.

**`not_joined` / `total_mates` are nullable**, and null is honest: `trades_banner` has `total` but not join counts (`InviteLeaguematesBanner` Props, `:20-25`), and a card can be tapped from a stale summary. Never substitute 0.

`platform` is the **league** platform (`sleeper|espn|mfl|fleaflicker|unknown`), matching the `league_selected` precedent at `analytics_taxonomy.py:185`. It is **not** the device platform — that is a server-derived column on `user_events` (the NULL-`platform` incident). This is written into the registry comment, not just here.

**Ordering is the whole finding.** The taxonomy commit lands and deploys **before** any client `track()` ships. Failure mode is a 200 with no row and no error signal.

**No new feature flag.** Justified: no route, no schema, no contract change; the bright line crossed is *analytics events*, and the remedy for that bright line is registration + ordering, not a flag. Rollback is a revert of a UI-only diff with no data migration. The A/B the resolutions doc wants (generic vs named, altruistic vs self-interested) is deferred — it needs `experiment_exposed`, which is in `FUNNEL_CRITICAL` and the mobile SDK mirror but **not** in `ALLOWED_CLIENT_EVENTS` (P0-7 §6-F1). Reading an A/B on assignment rather than exposure is arm-correlated-diluted. **OC-10.**

---

## P0-3 dependencies (hard)

P0-3 merges to `main` first. This plan is written against post-P0-3 `main`.

| # | Dependency | Consequence if ignored |
|---|---|---|
| **D1** | Both new CTAs emit through **P0-3's** `buildInviteUrl` (`InviteLeaguematesBanner.tsx:27-31`, rewritten by P0-3 M1 to resolve `/app/league/join/<id>?ref=` vs the legacy `/?league=&ref=` from `growth.invite_join_link`). | Promoting a CTA that emits today's format would *scale the broken link*. The single worst outcome available in this item. |
| **D2** | P1-5's `shareInvite` helper is layered **on top of** P0-3's M1/M2/M3, not merged with them. P0-3 keeps ownership of `buildInviteUrl` and the flag read; P1-5 replaces only the *bodies* of `handleInvite` (`InviteLeaguematesBanner.tsx:39-52`) and `inviteLeaguemates` (`LeagueScreen.tsx:371-382`). | Two agents rewriting the same 25 lines. Sequencing removes the conflict entirely. |
| **D3** | **`backend/analytics_taxonomy.py` is claimed by P0-3 (B4) and P0-7.** P0-3 B4 already registers `invite_shared` + `invite_link_opened` + `invite_league_pinned` + `invite_pin_failed`. **P1-5 must NOT re-add `invite_shared`** — it must *extend that event's `CLIENT_EVENT_PROPS` row* with `surface`, `not_joined`, `total_mates`, `platform`, and add the two new names. | Duplicate name = harmless; **missing prop row extension = the four new props are silently stripped and every row lands propless.** This is the subtle failure this item must not repeat. |
| **D4** | P0-3 records that cross-platform invites are unsolved: an ESPN/MFL league id is not in a Sleeper league list, so the invitee gets the not-member notice, and web's auto-select (`web/js/app.js:589-601`) does a `findIndex` over Sleeper leagues that cannot hit. | Promoting invite on ESPN League Home amplifies a known dead end. Hence the platform gate in S1 (**OC-4**). |
| **D5** | If `growth.invite_join_link` is still OFF at P1-5 ship (P0-3's own recommendation is to graduate it only after AASA CDN propagation), the promoted CTAs emit the **legacy** format — which P0-3 M5 has by then made readable on mobile and which web already handled. | None — this is safe, and it is why P1-5 does not need to wait on the flag. State it explicitly so nobody blocks. |

**Do not start the P1-5 build until `git log origin/main` contains P0-3's merge.** Re-run `grep -n "buildInviteUrl" -A 8 mobile/src/components/InviteLeaguematesBanner.tsx` and confirm the flag-resolved format before writing a line.

---

## Exact change list

Ordered. **Steps 1–4 are a standalone commit that ships and deploys before any client wiring** — that ordering is load-bearing and non-negotiable.

### Phase A — analytics registration (own commit, merges and deploys first)

| # | File | Change |
|---|---|---|
| A1 | `backend/analytics_taxonomy.py` `ALLOWED_CLIENT_EVENTS` (`:38-99`) | Add `"invite_cta_shown"`, `"invite_cta_tapped"`. **`invite_shared` should already be present from P0-3 B4 — verify, and add it only if P0-3 did not.** Commented block naming this plan + the addendum. |
| A2 | `backend/analytics_taxonomy.py` `CLIENT_EVENT_PROPS` (`:165-255`) | New rows for the two new names; **extend the existing `invite_shared` row** (P0-3 B4's) to `frozenset({"league_id","surface","not_joined","total_mates","platform"})`. Comment states `platform` = **league** platform, not device. |
| A3 | `backend/analytics_queries.py` `NON_INTENT_EVENTS` (`:60-63`) | Add `"invite_cta_shown"` — **required, not optional.** `INTENT` is a deny-list (`:64`); an impression event left in INTENT step-changes DAU/WAU on ship day and breaks every retention/churn series at that seam. `invite_cta_tapped` and `invite_shared` stay INTENT (real growth intent). |
| A4 | `docs/business/analytics/2026-08-11-p1-5-addendum.md` (**new**) | Tracking-plan addendum — the precondition `analytics_taxonomy.py:9-10` demands. Shape follows `2026-08-06-draft-room-w1-addendum.md`. Must record: (a) `invite_shared` was firing into a default-deny wall since it shipped, so there is **no invite baseline**; (b) the `invite_shared` vs tracking-plan-§S3 `invite_sent` fork and its resolution (**OC-3**); (c) league-`platform` vs device-`platform`; (d) the DAU/WAU seam date; (e) the four-value `surface` enum. |
| A5 | `backend/tests/test_events_api.py` | New `test_p1_5_invite_events_accepted`: POST one envelope per invite event with the **full** prop set; assert `accepted == N`, `dropped == 0`, exact `set(by_type)`, and that `props.surface == "league_home"` and `props.not_joined == 9` **survive** (the prop-stripping regression guard — this is the assertion that would have caught D3). Negative mirror: a misspelled `invite_cta_shwon` is counted-and-dropped. |
| A6 | `backend/tests/test_analytics_p0.py` | Extend `test_live_taxonomy_is_disjoint`'s membership assertion with the three invite names. |

> **Gate between phases:** Phase A is merged to `main` and Render has deployed it before Phase B's first `track()` call is written. Verify with `GET /api/analytics/health` and a hand-rolled `POST /api/events` carrying `invite_cta_shown` — `dropped == 0` or Phase B does not start.

### Phase B — mobile

| # | File | Change |
|---|---|---|
| B1 | `mobile/src/utils/leagueUnlocks.ts` | Add `inviteSocialProof(totalMates, joinedMates): string \| null` per the copy table. Pure, no imports, no side effects. |
| B2 | `mobile/src/utils/inviteShare.ts` (**new**) | `shareInvite({leagueId, leagueName, username, surface, notJoined, totalMates, platform})`. Imports `buildInviteUrl` from `../components/InviteLeaguematesBanner` (**P0-3's version — D1**). Fires `invite_cta_tapped` → `Share.share` → `invite_shared` on non-dismissed. Swallows throws. |
| B3 | `mobile/src/components/InviteLeaguematesCard.tsx` (**new**) | The S1 card. Props `{ leagueId, leagueName, username, totalMates, joinedMates, platform, surface }`. Returns `null` per the S1 ladder. `testID`s: `league.invite-card`, `league.invite-social-proof`, `league.invite-cta`. Chalkline `Card` + `Button variant="primary"` + `TickLabel`; **no new tokens, no gradients, no emoji** (ADR-004/005). |
| B4 | `mobile/src/screens/LeagueScreen.tsx` — insert between `:473` and `:478` | Mount `InviteLeaguematesCard` with `totalMates`/`joinedMates` (already in scope, `:310-311`) and the league platform. |
| B5 | `mobile/src/screens/LeagueScreen.tsx:700` | Pass `onInvite={inviteCardVisible ? undefined : inviteLeaguemates}` to `LeagueProgressModule` — the S1 duplicate suppression. **No change to `LeagueProgressModule.tsx`.** |
| B6 | `mobile/src/screens/LeagueScreen.tsx:371-382` | Rewrite `inviteLeaguemates` body to delegate to `shareInvite({..., surface: 'league_home'})`. Fix the now-wrong URL-format comment at `:369-370`. |
| B7 | `mobile/src/screens/LeagueScreen.tsx` | `invite_cta_shown` mount effect, `firedRef`-guarded, fires only when the card actually rendered and the summary settled. **Coordinate with P0-7 — same file, see C1.** |
| B8 | `mobile/src/screens/LeagueScreen.tsx:803-815` *(OPTIONAL-M)* | Overlay-head `secondary compact` invite button → `shareInvite({surface:'members_overlay'})`. `testID="league.members-invite"`. |
| B9 | `mobile/src/screens/MatchesScreen.tsx:387-397` | Add `totalMates: matchesSummary.leaguemates_total ?? null` and `joinedMates: matchesSummary.leaguemates_joined ?? null` to the `emptyModule` memo. Two lines; the payload is already fetched. |
| B10 | `mobile/src/screens/MatchesScreen.tsx:548-552` | Insert the social-proof line + `Button variant="secondary"` "Invite leaguemates" between `matches.go-to-trades` and the compact module. Same render ladder + the existing active-league guard. `testID`s: `matches.invite-social-proof`, `matches.invite-cta`. |
| B11 | `mobile/src/screens/MatchesScreen.tsx` | `invite_cta_shown` mount effect for `surface:'matches_empty'`, `firedRef`-guarded on the empty branch actually rendering. |
| B12 | `mobile/src/components/InviteLeaguematesBanner.tsx:39-52` | `handleInvite` delegates to `shareInvite({surface:'trades_banner', notJoined:null, totalMates:null, ...})`. **Drop the `growth.share_landing` gate on the event** (measurement must not be flag-gated; the flag key itself is untouched) — **OC-9**. Rewrite the lying comment at `:34-37`. |

### Phase C — docs

| # | File | Change |
|---|---|---|
| C1 | `docs/cross-client-invariants.md` §"Client analytics event contract" (`:268-271`) | Add the three invite names + addendum link; state explicitly that web (`web/js/events.js`) and the extension fire **none** of them, so the omission reads as deliberate. |
| C2 | `docs/design/components.md` | Record `InviteLeaguematesCard` alongside the other named League Home modules. |
| C3 | `living-memory/DECISIONS.md` (next id per file) | Two non-obvious choices: (1) the promoted card **suppresses** the inline link rather than coexisting with it; (2) one `shareInvite` helper owns all four emitters and both events, layered on P0-3's `buildInviteUrl` rather than merged into it. |
| C4 | `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | On ship, per `CLAUDE.md` §Session memory. TEST_LEDGER carries the tier-1 sim run **and** the row-landed verification. |

---

## Surface changes

| Surface | Verdict |
|---|---|
| **API routes** | **None.** No route added, renamed, removed, or contract-changed. Every number comes from `GET /api/league/summary`, already called by both screens. `POST /api/events` accepts the new names purely by registry membership; its shape is untouched. |
| **Schema / migrations** | **None.** `user_events` already stores every one of these. No new table, column, or index. |
| **Feature flags** | **None added.** One *read* is removed: `growth.share_landing` no longer gates the `invite_shared` `track()` call (B12, **OC-9**). The flag key, its default (`true`), and every other read stay exactly as they are. No `FLAG_KEYS` edit, no `config/features.json` edit, no `release.json` edit. |
| **Env vars / `model_config`** | **None.** |
| **Deep links / universal links / AASA** | **None.** P0-3 owns all of it; P1-5 consumes `buildInviteUrl` and adds no new destination. |
| **Analytics events** | **YES — enumerated below.** This is the bright line this item crosses. |
| **UI** | **YES** — new card on `LeagueHome`, new action block on the Matches mutual-empty state, optional overlay button; one existing inline link conditionally suppressed. |

### Analytics events — complete enumeration

**New client-fired (2)** — `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`:

1. `invite_cta_shown` — props `{surface, not_joined, total_mates, platform}` — **also added to `NON_INTENT_EVENTS`**
2. `invite_cta_tapped` — props `{surface, not_joined, total_mates, platform}` — INTENT

**Existing client-fired, prop row extended (1):**

3. `invite_shared` — registered by **P0-3 B4**; P1-5 extends its prop row to `{league_id, surface, not_joined, total_mates, platform}` — INTENT

**Server-fired:** none. **Removed/renamed:** none.

**`surface` enum (closed, 4 values):** `league_home` · `matches_empty` · `trades_banner` · `members_overlay`. If OPTIONAL-M (B8) is dropped, drop `members_overlay` with it.

**`platform` = LEAGUE platform** (`sleeper|espn|mfl|fleaflicker|unknown`). Not device platform. Written into the registry comment.

---

## Maestro delta

**Not waived.** This is a user-visible mobile change on two screens; `CLAUDE.md` requires a flow.

**Prior check, per the method:** `grep -rn "invite" mobile/.maestro/` returns **zero hits**. No existing flow asserts any invite affordance, so none is asserting the bug being fixed and none needs correcting. Two flows cross the touched screens and must stay green **unmodified** — `flows/smoke/09-league.yaml:34` (waits on `league.hero`, which stays above the new card) and `flows/smoke/08-matches.yaml:38` (waits on `matches.empty-text`, which stays above the new block). Asserted by running them, not assumed.

**New flow — `mobile/.maestro/flows/growth/invite-promotion.yaml`** (`# flags: release`), four blocks:

1. **League Home, promoted card + real number.** Profile `standard` (11 leaguemates, 2 joined). Sign-in preamble (law 10: assert the typed username first), `tab.league`, settle on the rankings root, tap the League home row, `assertVisible id: league.invite-card`, `assertVisible id: league.invite-social-proof` **with `text: ".*9 of your 11.*"`** — the deterministic proof that the count is real and not fabricated — then `assertVisible id: league.invite-cta`.
2. **Duplicate suppression.** In the same state, `assertNotVisible id: league.progress-invite` — the inline link is gone precisely because the card is present. This is the assertion that keeps principle 1 from silently regressing.
3. **Matches empty state.** Same profile, `tab.matches`, mutual segment, `assertVisible id: matches.empty-text`, then `matches.invite-social-proof` and `matches.invite-cta`. Confirms the block sits below the existing primary and above the compact module.
4. **ESPN gate.** Profile `espn`. League Home: `assertNotVisible id: league.invite-card` **and** `assertVisible id: league.progress-invite` — the promoted card is withheld and the legacy affordance is intact. (Reach Matches/League through the league picker, not a direct entry — `profiles/espn.json` documents that the ESPN league cache must be warmed or the wrong state is captured.)

**Deliberately not automated:** the OS share sheet itself. Tapping `league.invite-cta` opens system UI whose dismissal is the same hazard class as law 17's SpringBoard confirm and law 20's native-overlay poisoning. Flows assert **up to and including the CTA**; the sheet → `invite_shared` leg is verified by the end-to-end row check (Test 8) and manual sim QA. Recorded as a deliberate coverage boundary, not an omission.

**`testID`s added** (all static string literals; `mobile/scripts/testid-lint.sh` clean, no `testid-lint-allow.txt` entry needed):
`league.invite-card` · `league.invite-social-proof` · `league.invite-cta` · `matches.invite-social-proof` · `matches.invite-cta` · `league.members-invite` *(OPTIONAL-M only)*.
**None renamed or removed** — `league.progress-invite` (`LeagueProgressModule.tsx:126, 202`) survives untouched and is now *asserted absent* in one state, which is a new use of an existing id, not a change to it.

**Capture delta (law 23 applies — eyeball every shot):** `league`, `league@espn`, `league@near-unlock`, `league@quickset-done`, `league@single-format`, `league@two-leagues`, `matches`, `matches@fresh`, `matches@near-unlock`, `matches@two-leagues`, `matches@espn`. Run `mobile/scripts/screen-capture.sh --screen league --screen matches` (never with `--prune` plus a profile filter — law 21).

**Sim-gate tier: 1** (`docs/runbook.md:96` — "Mobile screen / navigation / state change"): full 11-flow smoke + `flows/growth/invite-promotion.yaml` + the capture refresh above. Log in `TEST_LEDGER.md`; write `qa/sim-runs/last-sim-run.json`.

---

## Docs impact table

Row per `docs/CLAUDE.md` trigger, answered or explicitly n/a.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| **`docs/business/analytics/2026-08-11-p1-5-addendum.md`** | **NEW (mandatory)** | The precondition `analytics_taxonomy.py:9-10` demands before any new client event. Parent: tracking plan v2 §S3. Records the no-baseline fact, the `invite_shared`/`invite_sent` fork, the league-vs-device `platform` distinction, the DAU/WAU seam date, and the `surface` enum. **A4.** |
| `docs/cross-client-invariants.md` | **Updated** | §"Client analytics event contract" (`:268-271`) already states names are shared verbatim by every client SDK and the backend allowlist and that "changing either side alone breaks ingestion silently." Add the three invite names + addendum link + the explicit note that web and extension fire none of them. **C1.** |
| `docs/data-dictionary.md` | **n/a** | No table or column added or changed in `backend/database.py`. All three events are client-fired and are documented via the taxonomy + addendum — the same treatment `guide_*` and `draft_room_*` received. Nothing new is *stored*. |
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. `/api/league/summary` and `/api/league/members` are consumed exactly as documented. `POST /api/events` accepts new names by registry membership alone. |
| `docs/config-reference.md` | **n/a** | No flag, env var, or `model_config` key added or changed. B12 removes one *read* of `growth.share_landing`; the key, default, and every other read are untouched, so the reference stays correct. **Re-check at build if OC-9 is declined and the gate is kept.** |
| `docs/architecture.md` | **n/a** | No backend module wiring or data-flow change. Every call rides existing paths (`track` → queue → `POST /api/events`). |
| `living-memory/HLD.md` | **n/a** | No architectural shift — no new module, client, or major flow. |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shift. "Register the name, then wire the client" is an existing convention this plan obeys rather than establishes. |
| `docs/glossary.md` | **n/a** | No new domain term. "Invite", "leaguemate", "joined" are all in use; `surface` is an event prop, not a domain concept. |
| `docs/design/design-system.md` | **n/a** | No new token, color, radius, or type step. The card composes existing `Card` / `Button` / `TickLabel` primitives. |
| `docs/design/components.md` | **Updated** | New named League Home module `InviteLeaguematesCard` + the Matches-empty invite block, alongside the existing League Home entries. **C2.** |
| `docs/runbook.md` | **n/a** | No new operational lever or failure mode. (If the end-to-end check in Test 8 surprises, that becomes a `GOTCHAS.md` entry, not a runbook one.) |
| `docs/adr/` | **n/a** | No architectural choice at ADR altitude. |
| `living-memory/DECISIONS.md` | **Updated** | Two entries: suppression-over-coexistence; one `shareInvite` helper layered on P0-3's `buildInviteUrl`. **C3.** |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **On ship** | Per `CLAUDE.md` §Session memory. TEST_LEDGER carries the tier-1 run + the row-landed verification. **C4.** |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if Test 8 surprises. G-017 (paired analytics gates fail silently) already covers the known trap. |
| `docs/templates/feature-scope.md` | **Copied, not edited** | → [`scope-p1-5.md`](scope-p1-5.md), every section filled. |

---

## Test plan

**Backend (pytest)**

1. `test_p1_5_invite_events_accepted` — one envelope per invite event with the full prop set. Assert `accepted == N`, **`dropped == 0`**, exact `set(by_type)`, and — the load-bearing assertion — that `props.surface`, `props.not_joined`, `props.total_mates`, `props.platform` **survive on `invite_shared`**. That last clause is the D3 regression guard: a name can be registered while its props are silently stripped.
2. Negative mirror: `invite_cta_shwon` (misspelt) is counted-and-dropped, proving the default-deny guard is still armed.
3. Prop-stripping pin: post `invite_cta_shown` with a bogus `device_platform` prop; assert the event lands and the prop is gone — pins the decision that no event carries a device-platform prop.
4. `test_live_taxonomy_is_disjoint` membership extended with the three names. (The two import-time asserts are self-enforcing: get either wrong and the suite fails to import.)
5. `invite_cta_shown ∈ NON_INTENT_EVENTS` and `invite_cta_tapped ∉ NON_INTENT_EVENTS` — asserted directly, because the deny-list default makes this the easiest thing in the file to get silently wrong.
6. Pure-function tests for `inviteSocialProof` are **mobile-side and there is no jest in `mobile/`** — so the four copy branches are covered by the Maestro `text:` assertion (block 1) plus manual QA of the singular cases. Recorded as a real coverage limit, not hidden.

**Mobile**

7. `cd mobile && npx tsc --noEmit` clean.
8. **End-to-end row check (G-017's rule: verify a row at the destination, not a 200 at the source).** Sim against a dev backend, both `analytics.client_events` and `analytics.ingest` on: open League Home, open Matches empty, tap both CTAs and complete one real share; wait ≥10 s (`FLUSH_INTERVAL_MS`) or background to force a flush; then
   `SELECT event_type, props, platform FROM user_events WHERE event_type LIKE 'invite%';`
   Assert (a) all three names present, (b) `props.surface` distinguishes `league_home` from `matches_empty`, (c) `props.not_joined = 9` on the `standard` fixture, (d) **`platform` column is `'ios'`, not NULL** (direct regression check for the NULL-platform incident), (e) `GET /api/analytics/health` shows `dropped_unknown_type` / `dropped_unknown_prop` **flat** across the session.
9. Maestro `flows/growth/invite-promotion.yaml` blocks 1–4.
10. Full smoke suite (11 flows), unmodified — `smoke/09-league` and `smoke/08-matches` are the regression proof for the two touched screens.
11. Capture refresh for the 11 variants listed in the Maestro delta; eyeball each (law 23).

**Manual / simulator**

12. Everyone-joined league → card absent, no gap, no orphaned label; the progress module's inline link **returns** (proving B5's conditional both ways).
13. Solo / `total_teams = 1` league → card absent.
14. Summary in flight → card absent; card appears when data lands, with no layout jump above the fold.
15. Matches screen with a **non-active** league filter chip selected → social-proof block absent (per-league counts must never render under another league's filter).
16. ESPN league → card absent, inline link present (**OC-4**); confirm via the league picker, not a direct entry.
17. Tap → share sheet → **dismiss** → assert `invite_cta_tapped` landed and `invite_shared` did **not**. Then tap → share → complete → both landed. This is the funnel step the whole measurement design rests on.
18. With `growth.invite_join_link` OFF **and** ON, confirm the shared URL matches P0-3's expected format in each case (**D1/D5**).

**Ship gate:** tier 1 — full smoke + the new flow + the capture refresh; `TEST_LEDGER.md` entry; `qa/sim-runs/last-sim-run.json` written.

---

## Risks and cross-item collisions

### File collisions — for the orchestrator

| File | P1-5 needs | Also claimed by | Resolution |
|---|---|---|---|
| **`backend/analytics_taxonomy.py`** | 2 new names, 2 new prop rows, **1 extended prop row (`invite_shared`)** | **P0-3 B4** (registers `invite_shared` + 3 join events) · **P0-7 §3.1** (8 client names, 1 server name) | **Serialize: P0-3 → P0-7 → P1-5.** P1-5 lands last and *extends* rather than adds `invite_shared`. Mechanical but unforgiving — a missing extension strips four props silently. Test 1 is the guard. |
| **`backend/analytics_queries.py`** | `NON_INTENT_EVENTS` += `invite_cta_shown` | **P0-7 §3.2** (NON_INTENT, WAT_LIVE/DARK, dark caveat) | Adjacent lines in the same frozenset. Trivial rebase; whoever lands last re-reads. |
| **`mobile/src/screens/LeagueScreen.tsx`** | card mount (`:474`), `onInvite` suppression (`:700`), `inviteLeaguemates` rewrite (`:371-382`), `invite_cta_shown` effect, optional overlay button (`:803`) | **P0-7 step 8** (`league_view` mount effect + OPTIONAL-A `league_home_action_tapped` on ~11 handlers) · **P0-1** *reads* `:328-334` but fixes backend-only | **Real overlap.** Both add mount effects to the same screen. Give the file to **one owner for the wave**, or land P0-7 first and insert P1-5's effect beside `league_view`. **Semantic rule: if P0-7's OPTIONAL-A ships, its `action` enum must NOT gain an `invite` value** — `invite_cta_tapped` is the invite's event and carries the social-proof props; two events for one tap double-counts the single most important growth action in the product. |
| **`mobile/src/components/InviteLeaguematesBanner.tsx`** | `handleInvite` body → `shareInvite`; drop the flag gate on the event; rewrite the lying comment | **P0-3 M1/M2** (rewrites `buildInviteUrl` + the same comment block) | **P0-3 first, always.** P1-5 then replaces only `:39-52`. `buildInviteUrl` is never touched by P1-5. |
| `mobile/src/screens/MatchesScreen.tsx` | `emptyModule` memo + the empty-state block | **P0-6** touches `SendInSleeperButton.tsx`, not this screen; no P0 claims `MatchesScreen` | Clean. Verify at build. |
| `mobile/src/utils/leagueUnlocks.ts`, `mobile/src/utils/inviteShare.ts`, `mobile/src/components/InviteLeaguematesCard.tsx` | edited / new | none | Clean. |
| `mobile/src/components/LeagueProgressModule.tsx` | **not edited** | — | Deliberate. Suppression is a prop value, not a component change — the #243-approved mock stays intact for every state the card doesn't cover. |

### Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Client wired before the taxonomy deploys** → all three events counted-and-dropped, 200 throughout, a dashboard that looks plausible with zero rows. This repo has already done exactly this to `invite_shared`. | **High** | Phase A is a separate commit that merges and deploys first, with an explicit gate check between phases. Tests 1–2 automate it; Test 8(e) is the manual confirmation. |
| **R2** | **`invite_shared`'s prop row not extended** (D3) → the name works, the four new props vanish, and `surface` — the entire comparison this item exists to enable — is permanently absent with no error. | **High** | A2 is explicit; Test 1 asserts prop survival, not just acceptance. Called out again in the collision table. |
| **R3** | **DAU/WAU step-change** if `invite_cta_shown` lands as INTENT — an impression event fired on every League Home and Matches-empty mount would inflate DAU toward app-open count and break every retention/churn series at the seam, silently and permanently. | **High** | A3 is mandatory, not optional. Test 5 asserts it directly. Seam date in the addendum (A4). |
| **R4** | **ESPN/MFL invites are a dead end** (D4): the id can't be found in a Sleeper league list, and web's auto-select `findIndex` (`web/js/app.js:589-601`) cannot hit. Promoting the CTA there scales a broken journey and burns the one social ask a user gets. | **Medium-high** | S1's platform gate (**OC-4**); Maestro block 4 asserts the card is withheld on `espn` and the legacy link survives. If OC-4 is declined, this becomes an accepted, recorded exposure — not an oversight. |
| **R5** | **No baseline.** `invite_shared` has never landed a row, so there is nothing to measure "promotion worked" against. Any post-ship read is absolute, not a lift. | Medium | Stated plainly in the addendum (A4a). Do not let a dashboard imply a before/after that does not exist. The A/B (OC-10) is the honest way to get a comparison, and it is gated on `experiment_exposed`. |
| **R6** | **Duplicate CTA regression.** A later change re-enables the inline link while the card is up, and League Home has two invites again — the exact anti-pattern this item fixes. | Medium | Maestro block 2 asserts `league.progress-invite` **absent** in the card state. It is the only assertion protecting principle 1. |
| **R7** | **`invite_cta_shown` double-fires** on a screen with `placeholderData: (prev) => prev` and multiple parallel queries — `LeagueScreen` re-renders often. | Medium | `firedRef` guard + fire only once the summary has settled *and* the card actually rendered. Verified by counting rows for one visit in Test 8. |
| **R8** | **Stale count on a cached summary** (60 s `staleTime`) — the card can claim 9 haven't joined moments after the 9th joins. | Low | Cosmetic and self-correcting within 60 s; pull-to-refresh (`refetchAll`, `:267-276`) fixes it immediately. The backend cache is invalidated on membership writes (`_invalidate_league_members_cache`, `server.py:5789-5798`). |
| **R9** | **Dropping the `growth.share_landing` gate** (B12) changes behaviour under a flag-off config — an event that used to be suppressed now fires. | Low | The flag is `true` in `config/features.json:125` and in the release fixture, so prod behaviour is unchanged. **OC-9** is the operator's call; declining it costs only that the release fixture keeps gating one event. |
| **R10** | **Layout regression above the fold.** A new card between hero and action row pushes the day-one actions down on small devices, on the screen the audit already calls section-heavy. | Low-medium | Capture refresh across all 6 league variants is mandatory and eyeballed (law 23). If the fold suffers, S1's placement moves below the action row — a one-line move, decided from the screenshots, recorded in the scope block. |
| **R11** | **A-34 (FAB clipping)** is an open P1: the feedback FAB overlays bottom content on data-dense screens and has already truncated a button label. A new bottom-adjacent button on the Matches empty state is a candidate victim. | Low-medium | The Matches invite button sits mid-column, above the compact module and Refresh, not pinned to the bottom. Confirm in the `matches@fresh` capture. Flag to whoever owns A-34 so the two are checked together. |

---

## Operator checkpoints

Each has options and a recommendation. None is agent-decidable.

**OC-1 — Social-proof copy and framing.** The resolutions doc names this an A/B candidate: generic vs named, altruistic vs self-interested.
- (a) *Factual/self-interested* — "9 of your 11 leaguemates haven't joined yet. / Matches need two boards. Every leaguemate who joins makes your trades better."
- (b) *Altruistic* — "Bring your league. / 9 of your 11 leaguemates are missing out."
- (c) *Named* — "Dave, Priya and 7 others haven't joined yet." (Requires the members list — already fetched at `LeagueScreen.tsx:198-204` — and only works on League Home, not on Matches.)
→ **Recommend (a).** It is the only framing that stays literally true if the reward or the mechanic changes, it matches the codebase's established honesty discipline (`(you)` labels, confirmed-zero folds), and it is the one variant that renders identically on both screens from the aggregate alone. (c) is the strongest candidate for the deferred A/B, once exposure is measurable.

**OC-2 — Matches empty-state button hierarchy.**
- (a) Invite **primary**, "Find a trade" demoted to secondary (the audit's literal ask).
- (b) "Find a trade" stays primary, Invite **secondary** below it.
- (c) Both primary.
→ **Recommend (b).** "Find a trade" is the action that converts today with zero dependencies; invite pays off in days and depends on someone else acting. (c) violates the Chalkline hierarchy. The audit's intent — that invite be a *button, present, and prominent*, not an absent text link — is fully met by (b).

**OC-3 — Event name: `invite_shared` or `invite_sent`?** The client fires `invite_shared` (`InviteLeaguematesBanner.tsx:47`) and P0-3 B4 registers that name. Tracking plan v2 §S3 (`:78`) specs `invite_sent` (`channel`). **Nothing in code reserves `invite_sent`** — unlike `sleeper_send_*`, which `analytics_queries.py` genuinely wires into WAT/funnel/verticals, this is a prose-only reservation.
→ **Recommend `invite_shared`**, and amend tracking plan v2 §S3 to match runtime. It is what the client already emits, what P0-3 registers, and renaming would mean a client change on top of a registration change for zero analytical gain. Adopting `invite_sent` instead is defensible but must then be done in *both* P0-3 and P1-5, consistently, in the same wave.

**OC-4 — ESPN / non-Sleeper gate.** The promoted card is withheld on non-Sleeper leagues because the invite link cannot resolve for those ids (R4, D4).
- (a) Gate to Sleeper; legacy inline link stays for everyone else.
- (b) Show everywhere and accept the dead end until cross-platform invites are solved.
- (c) Show everywhere with different copy ("Invite them to Dynasty Trade Finder" — no league landing promised).
→ **Recommend (a).** It is the only option that doesn't scale a known-broken journey, and it is one condition in the render ladder. (c) is a reasonable follow-on once someone owns cross-platform invites; it is not this item.

**OC-5 — Suppress the inline link when the card renders?**
- (a) Suppress (pass `onInvite={undefined}`) — one affordance, promoted.
- (b) Keep both — more surface area.
→ **Recommend (a).** Two invites on one screen is the same disease as the current one, wearing a better coat. Costs one conditional and zero changes to `LeagueProgressModule.tsx`. Maestro block 2 protects it.

**OC-6 — Ship `invite_cta_tapped`, or only shown + shared?** The tapped→shared gap is the OS-share-sheet abandon rate, and today the whole leg is invisible.
→ **Recommend in.** One registry row, one prop row, one call inside `shareInvite`. Without it, a drop between impression and share is unattributable to either the copy or the sheet. Drop it by deleting one name, one prop row, and one line in `inviteShare.ts`.

**OC-7 — OPTIONAL-M: invite button in the members overlay (B8).** The overlay already names every un-joined person.
→ **Recommend in.** ~8 lines, one `testID`, one `surface` enum value; it is the natural home for the audit's follow-on named-leaguemate invite. Drop by deleting the block and the `members_overlay` enum value together.

**OC-8 — Zero-not-joined state.**
- (a) Card absent (recommended).
- (b) Affirmation — "Your whole league is here."
→ **Recommend (a).** (b) is a permanent card with no action on the app's most section-heavy screen. If the operator wants the affirmation it belongs in the hero chip, which already renders `{joined}/{total} joined`.

**OC-9 — Drop the `growth.share_landing` gate on `invite_shared` (B12).**
- (a) Drop it — measurement is not a feature.
- (b) Keep it, and extend it to the two new events for consistency.
→ **Recommend (a).** The flag is `true` in prod, so this is a no-op there; what it buys is that a flag-off configuration can no longer silently blind the invite funnel. The flag key and all other reads are untouched either way. This is a flag-*surface* touch and is therefore surfaced rather than assumed.

**OC-10 — Defer the copy A/B.** The resolutions doc marks A-14 an A/B candidate. The experiment cannot be read honestly today: `experiment_exposed` is in `FUNNEL_CRITICAL` and the mobile SDK mirror but **not** in `ALLOWED_CLIENT_EVENTS`, so exposure is unmeasurable and any read is arm-correlated-diluted (P0-7 §6-F1).
→ **Recommend: ship one variant now, register the three events, and queue the A/B behind P0-7 F1.** Shipping a promoted invite that is measurable beats shipping an experiment that isn't. If the operator wants the A/B in this wave, F1 becomes a hard prerequisite and P1-5's effort moves from M to L.

**OC-11 — Wave sequencing.** `backend/analytics_taxonomy.py` is claimed by P0-3, P0-7 and P1-5; `mobile/src/screens/LeagueScreen.tsx` by P0-7 and P1-5.
→ **Recommend: P0-3 → P0-7 → P1-5**, with a single owner for `LeagueScreen.tsx` across the P0-7/P1-5 boundary, and a re-verification of `buildInviteUrl` and the `invite_shared` prop row at the top of the P1-5 build.
