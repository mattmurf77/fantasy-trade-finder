# PRD — P1-5 · Promote and measure the league invite (audit A-14)

> **Product requirements.** What changes, on which surfaces, how each change is proven, what the
> operator must decide first, and how it comes back out.
>
> **Status:** requirements only. **No source file is changed by this document.**
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`, branch
> `p1-remediation-2026-08-11` @ `ab9368f`. **Author:** P1-5 LLD/PRD agent, 2026-08-11.
> **Pair:** [`LLD-p1-5.md`](LLD-p1-5.md) — diff sites, signatures, payloads, corrections.
> **Binding inputs:** [`DECISIONS-p1.md`](DECISIONS-p1.md) → [`HLD-p1.md`](HLD-p1.md) →
> [`plan-p1-5.md`](plan-p1-5.md) / [`scope-p1-5.md`](scope-p1-5.md).
>
> **Gate posture: FULL GATES.** This change registers analytics events — a bright line in root
> `CLAUDE.md` §Conventions. Express is not available and agents never self-select it.
> **Hard prerequisites:** P0-3 merged to `main`; commit **T1** merged **and deployed and probed**.

## Table of contents

- [0. Build addendum — 2026-08-11 (as built)](#0-build-addendum--2026-08-11-as-built)
- [1. Problem](#1-problem)
- [2. Goals and non-goals](#2-goals-and-non-goals)
- [3. Before / after — League Home](#3-before--after--league-home)
- [4. Before / after — Matches empty state](#4-before--after--matches-empty-state)
- [5. Before / after — measurement](#5-before--after--measurement)
- [6. Acceptance criteria](#6-acceptance-criteria)
- [7. Maestro flow specs](#7-maestro-flow-specs)
- [8. Non-Maestro verification](#8-non-maestro-verification)
- [9. Docs impact](#9-docs-impact)
- [10. Operator gates](#10-operator-gates)
- [11. Release risk — this item ships live on merge](#11-release-risk--this-item-ships-live-on-merge)
- [12. Rollback](#12-rollback)
- [13. Residual risks accepted](#13-residual-risks-accepted)

---

## 0. Build addendum — 2026-08-11 (as built)

> Added by the P1-5 build agent after implementation. Where this section
> contradicts anything below it, **this section describes what shipped.**

### 0.1 ⚠ The Matches-surface impression metric is UNRELIABLE — do not read it as an impression rate

**This is the record D-P1-04 requires.** `invite_cta_shown` with
`surface: 'matches_empty'` is a **mount counter, not an impression counter**, and
**any tap-through rate computed from it is invalid** until the Matches empty state gets
a scroll container.

**Mechanism.** The mutual-empty branch has no scrollable ancestor — it is a plain
`<View style={styles.centered}>` (`flex: 1` + `justifyContent: 'center'`), and the only
`ScrollView` on `MatchesScreen` is the horizontal filter-chip row. On smaller devices
that column is already taller than the viewport, so content below "Find a trade" is
clipped off-screen and unreachable to both a user and a camera. The event fires on
mount regardless.

**Scope of the damage, precisely.** The build places the *leading* action above the
clipping boundary (see §0.2), so the clipped element is whichever action does **not**
lead. The metric is therefore least trustworthy for the non-leading surface and its
tap-through will read artificially low.

**Accepted knowingly by the operator (D-P1-04), to be verified on TestFlight. Fixing
the scroll container is explicitly out of P1-5's scope** and belongs with the A-34
layout family. Maestro cannot detect the failure either — off-screen children remain in
the view hierarchy, so `assertVisible` passes whether or not anything is on screen.

**`invite_cta_shown` with `surface: 'league_home'` is unaffected and IS a real
impression** — that surface has a real `ScrollView`. Comparisons between the two
surfaces are not valid until the clipping is fixed.

The same warning is carried as a code comment at the emission site in
`mobile/src/screens/MatchesScreen.tsx`, so it cannot be lost by anyone reading only the
code.

### 0.2 PR-6 as built — conditional on league penetration

Reversed from this document's §4 and from gate OG-2. Which action leads on the Matches
empty state depends on `leaguemates_joined / leaguemates_total`:

| Penetration | Leads (primary, placed first) | Follows (secondary) |
|---|---|---|
| **< 50% joined** | Invite leaguemates | Find a trade |
| **≥ 50% joined** | Find a trade | Invite leaguemates |

Rationale: below half, an empty inbox is a *population* problem; at or above half the
boards mostly exist and it is a *discovery* problem. There is never more than one
primary on the surface.

### 0.3 PR-7 as built — **no platform gate**. The card ships on every platform

**§2's non-goal ("withhold the promoted CTA on ESPN/MFL leagues"), render-ladder branch
L2, AC-20…AC-22 and Maestro File B block 4 are all withdrawn.** D-P1-14 was right that
the premise was never verified; the invite path has now been traced end to end and the
finding is more specific than either position:

| Leg | Sleeper | ESPN / MFL / Fleaflicker |
|---|---|---|
| `buildInviteUrl` emission | works | **works — no platform branch exists** |
| `/app/league/join/<id>` → 302 (`backend/server.py`) | works | works — no lookup, no validation |
| Mobile deep-link capture (`utils/deepLinks.ts` `?league=` reader, `LeagueJoinScreen`) | works | works — no platform branch |
| Mobile auto-pin (`LeaguePickerScreen`) | works | **only if the invitee has independently linked that platform themselves** |
| Web auto-select (`web/js/app.js` `findIndex` over `/api/sleeper/leagues`) | works | **hard dead end** — `backend/database.py:6107` keeps only non-numeric league ids, and platform leagues are stored under their numeric platform-native id, so the id can never match. Web sign-in also demands a Sleeper username |
| Invite banner names the league (`/api/league/invite-meta`) | works | always "their league" — `backend/server.py:682-683` returns `None` for `is_linked_platform_league`, as its own docstring states |

**Why the card ships anyway.** The outcome the card asks for is still reachable on
mobile: an ESPN leaguemate who installs the app and links their own ESPN account lands
in the same league and increments `leaguemates_joined`. Gating the card would suppress a
*working* outcome while the legacy inline link — which emits the byte-identical URL —
stayed put, so the gate would not have prevented the degraded journey, only the promoted
one. Every invite event carries the league `platform` prop, which turns "do ESPN invites
convert?" into a measured question rather than an assumed one.

**Two real follow-ups this trace surfaced, neither in P1-5's scope:**

1. `mobile/src/screens/LeaguePickerScreen.tsx` — the terminal copy for a failed auto-pin
   says *"join the league on Sleeper and open the invite again"*, which is simply wrong
   for an ESPN/MFL invitee. Cheap copy fix, different file owner.
2. Web is a genuine dead end for non-Sleeper invitees (both the league-list filter and
   the Sleeper-only sign-in). Worth fixing or worth an explicit "open this in the app"
   interstitial.

### 0.4 Other deltas from this document

- **`inviteSocialProof` lives in `mobile/src/utils/inviteSocialProof.ts`**, not appended
  to `leagueUnlocks.ts` — a new file rather than an edit to a shared one. It keeps the
  same zero-runtime-imports discipline and has its own harness,
  `mobile/tests/check-invite-social-proof.js` (13 cases, wired as
  `npm run test:invite-social-proof`). **Waiver W3 is withdrawn**, as §8 requires.
- **`shareInvite` lives in `InviteLeaguematesBanner.tsx`**, beside `buildInviteUrl`, not
  in a new `utils/inviteShare.ts`. LLD §3's placement would have created a require cycle
  (`utils/inviteShare` → banner → `utils/inviteShare`) the moment the banner delegated
  to it. Same module ⇒ `buildInviteUrl` is called directly and still never copied.
- **OG-13 resolved as (a')**: the card's CTA is `variant="secondary"`. League Home's
  existing `league.action.find` keeps the only primary on the screen.
- **PR-9 shipped**: `league.members-invite`, secondary weight, in the members-overlay
  footer, gated on the same visibility predicate as the card.
- **The `platform` prop resolves absent ⇒ `'unknown'`**, matching P0-7's `league_view`
  call on the same screen, rather than LLD §5's `?? 'sleeper'`. With no platform gate the
  value is purely telemetry, and honest beats fail-open.

---

## 1. Problem

Audit finding **A-14 / P1-5**: *the invite is three taps deep, on an unmeasured page.* Every clause
was re-verified in this worktree at `ab9368f`. It holds, and it is worse than the audit stated.

| # | Verified fact | Evidence |
|---|---|---|
| P1 | The League tab **does not land on League Home.** Its root is the power-rankings screen; League Home is a pushed sub-route reached by a row tap | `mobile/src/navigation/TabNav.tsx:449-461`; the only in-app entries are `LeagueSummaryScreen.tsx:808` and `RankScreen.tsx:388` |
| P2 | On League Home the invite is **an underlined text link inside a sentence** — `Invite them` — spliced into the unlock line | `mobile/src/components/LeagueProgressModule.tsx:124-137`, spliced at `:155`; second variant `Invite leaguemates` at `:200-212` |
| P3 | That link **is not a 44 pt target, and the component says so**: *"Nested-Text link ⇒ no 44pt target; documented deviation"* | `LeagueProgressModule.tsx:263-272` |
| P4 | The link **disappears entirely** once the league's unlocks complete — `moduleVisible` gates the whole module, so a league that has unlocked matches has **no invite affordance at all** on League Home | `LeagueScreen.tsx:351-359`, mounted `:689-703` |
| P5 | **Tap count: three, confirmed.** `tab.league` → row tap → scroll → tap the text link → OS sheet | chain above |
| P6 | The **Matches empty state has no invite affordance at all.** It mounts the `compact` variant, which structurally cannot render one (`!compact && onInvite`) and is passed no `onInvite` | `MatchesScreen.tsx:552-561`; guard `LeagueProgressModule.tsx:125` |
| P7 | `LeagueScreen.inviteLeaguemates` **fires no analytics of any kind** — a bare `Share.share` | `LeagueScreen.tsx:371-382` |
| P8 | `LeagueScreen.tsx` contains **zero `track()` calls**, whole file | `grep -n "track(" mobile/src/screens/LeagueScreen.tsx` → no matches |
| P9 | **`invite_shared` is absent from `ALLOWED_CLIENT_EVENTS`.** Ingest is default-deny and returns **200** on a drop. The product's only invite event has been counted-and-discarded since it shipped | `grep -n "invite" backend/analytics_taxonomy.py backend/analytics_queries.py` → **zero matches in either file**. Firing site: `InviteLeaguematesBanner.tsx:47` |
| P10 | **The social-proof data is already on the screen.** `leaguemates_total` / `leaguemates_joined` are computed at `backend/database.py:5617, 5641-5642`, served unflagged by `GET /api/league/summary` (`server.py:13363-13389`), and **already destructured at `LeagueScreen.tsx:310-311`**; the same react-query key is already fetched on Matches (`MatchesScreen.tsx:142-148`, consumed `:385-397`) | — |

**The compound consequence.** The product's single most important growth action is (a) three taps
deep, (b) below the minimum touch target, (c) absent from the one screen where a user is *told* they
need more leaguemates, (d) absent entirely once a league unlocks, and (e) **invisible to analytics**,
so nobody can tell whether any of that matters. There is no baseline. Whatever ships here is the
first invite number the product has ever had.

**What the audit got wrong, and it matters.** A-14 says to build the social proof on
`load_league_member_unlock_states`. That loader is real (`backend/database.py:5656-5746`, `joined`
at `:5713`) but its dedicated route is **flag-gated** on `league.unlock_badges_per_member`
(`backend/server.py:13497`). Building a default-ON feature on a flagged route would have created a
hidden flag dependency. The aggregate on `/api/league/summary` needs **no new endpoint, no new
query, and not even a new field read**. This is settled (`scope-p1-5.md` §2 design note) and the
build must not drift back.

---

## 2. Goals and non-goals

**Goals**

1. One **promoted, 44 pt, primary** invite affordance on League Home, present regardless of unlock
   state, carrying a **true** social-proof number.
2. An invite action **with its reason** on the Matches mutual-empty state, where none exists today.
3. **One** invite affordance per screen — the promoted CTA *suppresses* the inline link rather than
   coexisting with it.
4. **One** share path and **one** formatter behind all four emitters, so four surfaces cannot drift.
5. Make the invite funnel **measurable end to end** — impression → tap → share — with an impression
   denominator, because a tap count with no exposure count cannot distinguish "the button works"
   from "more people saw it".

**Non-goals**

- **No new API route, no schema change, no migration, no new feature flag.**
- **No fix for cross-platform (ESPN/MFL) invites.** Unsolved upstream (P0-3 D4). P1-5's response is
  to *withhold* the promoted CTA on those leagues, not to scale a dead end.
- **No copy A/B.** `experiment_exposed` is in `FUNNEL_CRITICAL` and the mobile SDK mirror but **not**
  in `ALLOWED_CLIENT_EVENTS`, so exposure is unmeasurable and any read is arm-correlated-diluted
  (P0-7 §6-F1). Gate **OG-10**.
- **No change to `LeagueProgressModule.tsx`.** Suppression is a prop value at the call site.
- **No named-leaguemate invite** ("Dave, Priya and 7 others"). Follow-on, not this item.

---

## 3. Before / after — League Home

### Before

```
[hero: league name · badges · joined chip]
[action row: Rank players | Find a trade]            ← only when moduleVisible
…
[League progress module]                              ← only when moduleVisible
   Leaguemates ranked   2/12 (you)
   ▮▮▯▯▯▯▯▯▯▯▯▯
   1 more ranked leaguemate unlocks mutual matches. Invite them
                                                     ↑ 4th-tap text link,
                                                       no 44pt target,
                                                       gone once unlocked
```

### After

```
[hero: league name · badges · joined chip]

┌─────────────────────────────────────────────┐      ← league.invite-card  NEW
│ ▍Grow your league                           │
│ 9 of your 11 leaguemates haven't joined yet │      ← league.invite-social-proof
│ <rationale copy>                            │
│ ┌─────────────────────────────────────────┐ │
│ │        Invite leaguemates               │ │      ← league.invite-cta, Button
│ └─────────────────────────────────────────┘ │        variant="primary", 44pt
└─────────────────────────────────────────────┘

[action row: Rank players | Find a trade]
…
[League progress module]
   1 more ranked leaguemate unlocks mutual matches.   ← inline link SUPPRESSED
```

**Render ladder — the card renders only when the ask is real.** No skeleton, no `—`, no guess:

| Condition | Card | Inline link |
|---|---|---|
| Summary not yet arrived | absent | as today |
| League platform ≠ `sleeper` | absent | **present** (unchanged) |
| `leaguemates_total <= 0` (solo/unknown) | absent | as today |
| `notJoined === 0` (everyone joined) | absent | as today |
| otherwise | **present** | **suppressed** |

**Tap count after: one** — `tab.league` → row tap → the card is above the fold with the hero.
(The row tap and tab tap remain; what the finding attacks is the *third* tap and the scroll.)

---

## 4. Before / after — Matches empty state

### Before

```
No mutual matches yet
A match needs two boards — yours and a leaguemate's. …
[ Find a trade ]                       ← primary
[compact progress module]
[ Refresh ]  (ghost)
How matching works
```

**No invite anywhere.** Not demoted — absent.

### After

```
No mutual matches yet
A match needs two boards — yours and a leaguemate's. …
[ Find a trade ]                       ← primary, unchanged
9 of your 11 leaguemates haven't joined yet     ← matches.invite-social-proof  NEW
[ Invite leaguemates ]                 ← matches.invite-cta, secondary        NEW
[compact progress module]
[ Refresh ]  (ghost)
How matching works
```

**Scoped to the active league.** The block renders only when `emptyModule` is non-null — i.e. the
filter is `All` or the active league's own chip, **and** both league reads have confirmed
(`MatchesScreen.tsx:387-397`). A per-league count must never render under another league's chip.

> **⚠ Known layout defect on this surface — gate OG-12.** The empty branch has **no scroll
> container**: `styles.centered` is `flex: 1` + `justifyContent: 'center'`
> (`MatchesScreen.tsx:997-1003`) and the only `ScrollView` on the screen is the horizontal chip row
> (`:464`). On the canonical device the column already overflows: the progress module, Refresh and
> the help link are **clipped off-screen for users today**. Filed by the audit as *"a new finding,
> same class as A-34"* (`docs/business/product/2026-08-09-mobile-ux-audit/09-capture-requests-response.md:32-34`);
> photographed and diagnosed in `mobile/.maestro/capture/matches@near-unlock.yaml`. The new block
> lands at the boundary where clipping begins. **Maestro cannot detect this** (README law 2 —
> off-screen children stay in the hierarchy, so `assertVisible` passes). See [OG-12](#10-operator-gates)
> and [LLD §11 correction 1](LLD-p1-5.md#11-corrections-to-the-plan).

---

## 5. Before / after — measurement

| | Before | After |
|---|---|---|
| Impressions | none | `invite_cta_shown` — **NON_INTENT**, once per surface per league |
| Taps | none | `invite_cta_tapped` — INTENT, fired *before* the OS sheet so abandons still count |
| Shares | `invite_shared` fired from **one** of three emitters, gated on `growth.share_landing`, and **dropped by the allowlist** since it shipped | `invite_shared` from **all four** emitters, ungated, **landing rows** |
| Comparability | — | `surface` ∈ `league_home \| matches_empty \| trades_banner \| members_overlay` — the promoted CTAs are directly comparable against the buried one |
| Baseline | **none, and there never was one** | still none. Post-ship reads are **absolute, never a lift** — recorded in the addendum so no dashboard implies a before/after that does not exist |

**Ordering is the whole thing.** Commit **T1** (`HLD-p1.md` §A.2) registers the names, extends
`invite_shared`'s prop row, and adds `invite_cta_shown` to `NON_INTENT_EVENTS` — then merges,
deploys, and is **probed live** before a single client `track()` ships. `analytics_ingest.py:379-383`
returns 200 on an unknown type and `:384-389` strips unknown props. **There is no error signal on
either side.** This repo has already done exactly this to `invite_shared`.

---

## 6. Acceptance criteria

Numbered, individually testable. **Method** names the single check that proves it.
`AC-x [GATE: y]` means the criterion's *expected value* is set by an unresolved operator decision —
the criterion is still binding, its expected value is not yet fixed.

### Data and formatter

| # | Criterion | Method |
|---|---|---|
| **AC-1** | `inviteSocialProof(11, 2)` returns exactly `9 of your 11 leaguemates haven't joined yet` **[GATE: OG-1]** | `npm run test:league-unlocks` |
| **AC-2** | `inviteSocialProof(11, 10)` uses the **singular** verb (`1 of your 11 leaguemates hasn't joined yet`) | same |
| **AC-3** | `inviteSocialProof(1, 0)` returns the single-leaguemate string, not `1 of your 1 leaguemates…` | same |
| **AC-4** | `inviteSocialProof` returns `null` for: `notJoined === 0`; `totalMates <= 0`; any non-finite input; `joinedMates > totalMates` | same |
| **AC-5** | `mobile/src/utils/leagueUnlocks.ts` still has **zero runtime imports** after the change | `npm run test:league-unlocks` passes (its module shim throws on any `require`) |
| **AC-6** | No new network request is issued by either surface. `/api/league/member-unlock-states` is **not** called, and `league.unlock_badges_per_member` is **not** read, by any code added in this item | `grep` the diff for `getLeagueMemberUnlockStates` / `unlock_badges_per_member` → zero hits outside pre-existing lines |

### League Home

| # | Criterion | Method |
|---|---|---|
| **AC-7** | On a Sleeper league with ≥1 un-joined leaguemate and a settled summary, `league.invite-card` renders **below `league.hero` and above `league.action.rank`** | Maestro A block 1 + eyeballed capture |
| **AC-8** | `league.invite-cta` is a `Button` (`variant="primary"` **[GATE: OG-13]**) with `accessibilityRole="button"` and a ≥44 pt target — **the deviation at `LeagueProgressModule.tsx:263-272` is closed on this surface** | Maestro A block 1 + manual VoiceOver/inspector check |
| **AC-9** | `league.invite-social-proof` renders the **real** count for the fixture, not a placeholder — `9 of your 11` on `near-unlock` | Maestro A block 1, `text:` regex on the id |
| **AC-10** | While `league.invite-card` renders, `league.progress-invite` is **absent from the view hierarchy** (not merely off-screen) **[GATE: OG-5]** | Maestro A block 2 (`assertNotVisible`; on this non-virtualized screen it proves non-mount) |
| **AC-11** | When the card is **withheld** (any ladder branch), `league.progress-invite` **returns** — the suppression conditional works in both directions | Maestro B block 4 (ESPN) + manual test M-3 (everyone-joined) |
| **AC-12** | The card renders **regardless of `moduleVisible`** — a fully-unlocked league with un-joined members still shows it | Manual test M-5 |
| **AC-13** | The card is **absent** while the summary is in flight, and appears when data lands **with no layout jump above the fold** | Manual test M-6 + `league/first-paint-pending.png` |
| **AC-14** | `LeagueProgressModule.tsx` has **zero diff** | `git diff --stat` shows the file absent |

### Matches empty state

| # | Criterion | Method |
|---|---|---|
| **AC-15** | On the mutual-empty state for the active league, `matches.invite-social-proof` and `matches.invite-cta` render **between `matches.go-to-trades` and `matches.progress-module`** | Maestro A block 3 + eyeballed capture |
| **AC-16** | `matches.go-to-trades` remains **primary**; the invite CTA is **secondary** **[GATE: OG-6]** | Maestro A block 3 + eyeballed capture |
| **AC-17** | With a **non-active** league's filter chip selected, **neither** invite element renders | Manual test M-7 |
| **AC-18** | The count on Matches equals the count on League Home for the same league in the same session — one formatter, one cache key | Maestro A blocks 1 + 3 assert the same `text:` regex |
| **AC-19** | `matches.empty-text` and `matches.go-to-trades` keep their ids and positions; `smoke/08-matches.yaml` passes **unmodified** | full smoke suite |

### Platform gate

| # | Criterion | Method |
|---|---|---|
| **AC-20** | On a league whose cached `platform` is not `sleeper`, `league.invite-card` is **absent** and `league.progress-invite` is **present** **[GATE: OG-4]** | Maestro B block 4 |
| **AC-21** | The gate is `platform === 'sleeper'` with **absent ⇒ `'sleeper'`** (the `useSession.ts:436` idiom) — **not** `!isEspn`. An MFL or Fleaflicker league is withheld too | Code review of the predicate + `grep` showing `isEspn` is unchanged |
| **AC-22** | On a non-Sleeper league the legacy inline link still **fires `invite_cta_tapped` with `platform` = that platform** — the withheld surface is still measured | Manual test M-8 + row check |

### Share path

| # | Criterion | Method |
|---|---|---|
| **AC-23** | All four (or three, per OG-7) emitters call **one** `shareInvite`; `Share.share` appears **exactly once** in `mobile/src/` outside test code | `grep -rn "Share.share" mobile/src` → one hit, in `inviteShare.ts` |
| **AC-24** | `shareInvite` obtains the URL by **calling the imported `buildInviteUrl`**. `buildInviteUrl` is **not** re-implemented, copied, or edited by P1-5 | `git diff` shows `InviteLeaguematesBanner.tsx:27-31` untouched; `grep` shows one definition |
| **AC-25** | The shared URL matches P0-3's expected format with `growth.invite_join_link` **OFF** *and* **ON** | Manual test M-9 |
| **AC-26** | A dismissed share sheet fires `invite_cta_tapped` and **not** `invite_shared`; a completed share fires **both** | Manual test M-10 + row check |
| **AC-27** | `invite_shared` from the Trades banner **no longer depends on `growth.share_landing`** **[GATE: OG-9]**; the flag key, its `true` default (`config/features.json:125`), `backend/feature_flags.py:272` and the release fixture are **unchanged** | `git diff` on those four locations is empty |
| **AC-28** | A `Share.share` throw is swallowed — no error surfaces to the user on any of the four surfaces | Manual test M-10 |

### Analytics

| # | Criterion | Method |
|---|---|---|
| **AC-29** | All three names are accepted by `POST /api/events` with **`dropped == 0`** | `test_p1_5_invite_events_accepted` |
| **AC-30** | **All four new props survive on `invite_shared`** — `surface`, `not_joined`, `total_mates`, `platform` are echoed, not stripped. *(The single assertion that catches a bad three-way merge of the modified row.)* | same test, prop-level assertion |
| **AC-31** | A misspelled `invite_cta_shwon` is **counted-and-dropped** — default-deny is still armed | same test, negative mirror |
| **AC-32** | A `device_platform` prop on `invite_cta_shown` is **stripped** while the event lands — no invite event carries device platform | same test |
| **AC-33** | `invite_cta_shown ∈ NON_INTENT_EVENTS`; `invite_cta_tapped ∉`; `invite_shared ∉` | `test_analytics_p0.py` direct assertion |
| **AC-34** | One League Home visit produces **exactly one** `invite_cta_shown` row for that league, despite `placeholderData: (prev) => prev` on six queries | Row check E2E-1 |
| **AC-35** | The `platform` column on every landed `user_events` row is `'ios'`, **not NULL** | Row check E2E-1 |
| **AC-36** | `props.surface` distinguishes `league_home` from `matches_empty` from `trades_banner` in landed rows | Row check E2E-1 |
| **AC-37** | `GET /api/analytics/health` shows `dropped_unknown_type` and `dropped_unknown_prop` **flat** across the QA session | Row check E2E-1 |
| **AC-38** | If P0-7's OPTIONAL-A shipped, its `action` enum does **not** contain `invite` — one tap, one event | Re-verify row, before build |

### Hygiene

| # | Criterion | Method |
|---|---|---|
| **AC-39** | `cd mobile && npx tsc --noEmit` clean | typecheck |
| **AC-40** | `mobile/scripts/testid-lint.sh` exits 0 with **no** new `testid-lint-allow.txt` entry (all six ids are static literals) | lint |
| **AC-41** | `pytest backend/tests/` green | pytest |
| **AC-42** | Full smoke suite (11 flows) green **unmodified** — a diff to any smoke flow invalidates the claim that this change is additive | smoke run |
| **AC-43** | No new token, colour, radius or type step; no emoji, gradient or blur (ADR-004/005) | code review against `docs/design/design-system.md` |
| **AC-44** | `screens/manifest.json` `league.sources` includes `InviteLeaguematesCard.tsx` | `screen-freshness.sh` flags `league` after a card-only edit |
| **AC-45** | The three lying comments are gone and not reintroduced: `InviteLeaguematesBanner.tsx:34-37`, `LeagueScreen.tsx:369-370`; and the `LeagueProgressModule.tsx:122-123` space trade-off is recorded in the new comment | code review |

---

## 7. Maestro flow specs

**Prior state, verified:** `grep -rn "invite" mobile/.maestro/` → **zero hits.** No existing flow
asserts any invite affordance; none is asserting the bug being fixed; none needs un-asserting.

**Two files, not one.** The seeded backend takes **one** `--profile` per run
(`mobile/scripts/sim-run.sh:21, 31, 54`, handshake assert at `:114`), so a single YAML cannot span
`near-unlock` and `espn`. Naming mirrors the existing `capture/<screen>@<profile>.yaml` convention.
*(This corrects `plan-p1-5.md:316` — see [LLD §11 correction 3](LLD-p1-5.md#11-corrections-to-the-plan).)*

**Selector discipline.** Every element is selected **by `testID`**. The only `text:` usage is as an
*additional constraint on an id-selected element* (`assertVisible: id: … text: …`), which is what
proves the count is real rather than a placeholder. Text matchers are full-match regex (README law
1) — wrap in `.*` and re-derive from source bytes if copy changes.

---

### File A — `mobile/.maestro/flows/growth/invite-promotion.yaml`

```yaml
appId: com.fantasytradefinder.app
# tc: TC-GRO-INVITE-01
# profile: near-unlock
# flags: release
# source: mobile/src/components/InviteLeaguematesCard.tsx
#         mobile/src/screens/LeagueScreen.tsx
#         mobile/src/screens/MatchesScreen.tsx
#
# WHY near-unlock AND NOT standard: `standard` seeds matches_seed {mutual: 2},
# so the Matches empty branch never renders there (smoke/08-matches.yaml
# asserts matches.empty-text ABSENT on that profile, by design). near-unlock
# is 12 rosters / 2 listed members / matches_seed {mutual: 0, awaiting: 0}
# => leaguemates_total 11, leaguemates_joined 2, notJoined 9, and an empty
# mutual inbox — so ONE profile proves the card, the suppression and the
# Matches block, with the SAME "9 of your 11" string on both surfaces.
# That shared string is the point: one formatter, two screens.
#
# COUNT SOURCE: backend/tests/fixtures/seed_ui_test_db.py:563-593 fills the
# remaining seats with _add_user(..., joined=False). If a fixture's
# total_rosters or member list moves, the regex below must be re-derived.
tags: [growth, invite, near-unlock]
---
- launchApp:
    clearState: true
    clearKeychain: true
    stopApp: true
- extendedWaitUntil:
    visible:
      id: "signin.username-input"
    timeout: 15000

# Law 10 — prove the username landed BEFORE submitting; a raced inputText
# submits a partial name and books a real VCR miss.
- retry:
    maxRetries: 2
    commands:
      - tapOn:
          id: "signin.username-input"
      - eraseText
      - inputText: "qa_standard"
      - assertVisible:
          text: ".*qa_standard.*"
      - tapOn:
          id: "signin.continue-btn"
      - extendedWaitUntil:
          visible:
            id: "leagues.row.*"
          timeout: 30000
- tapOn:
    id: "leagues.row.*"
- extendedWaitUntil:
    visible:
      id: "tab.league"
    timeout: 30000

# ── BLOCK 1 — League Home: the promoted card carries a REAL number ───────
# Law 8: settle on the surface's own control before a tab tap; #244 launch
# routing can steal the first one.
- extendedWaitUntil:
    visible:
      id: "rank.more-ways"
    timeout: 60000
- waitForAnimationToEnd
- tapOn:
    id: "tab.league"
- extendedWaitUntil:
    visible:
      id: "league-summary.league-home"
    timeout: 30000
- tapOn:
    id: "league-summary.league-home"
- extendedWaitUntil:
    visible:
      id: "league.hero"
    timeout: 30000
- extendedWaitUntil:
    visible:
      id: "league.invite-card"
    timeout: 30000
# The load-bearing assertion of the whole item: the number is DERIVED, not
# fabricated. 11 leaguemates, 2 joined => 9 have not.
- assertVisible:
    id: "league.invite-social-proof"
    text: ".*9 of your 11 leaguemates.*"
- assertVisible:
    id: "league.invite-cta"
- takeScreenshot: invite__league-home-card

# ── BLOCK 2 — duplicate suppression ─────────────────────────────────────
# The ONLY assertion protecting "one invite affordance per screen". On
# near-unlock the inline link WOULD render (rankedMates = 1 => remaining = 0
# => LeagueProgressModule.tsx:200-212's standalone-link branch), so its
# absence is caused by the card, not by the module being unmounted.
# NOTE: LeagueScreen's body is a plain ScrollView, not virtualized, so
# off-screen children stay in the hierarchy (README law 2) — assertNotVisible
# here proves NON-MOUNT, which is exactly the claim. No scroll needed.
- assertVisible:
    id: "league.progress-module"
- assertNotVisible:
    id: "league.progress-invite"

# ── BLOCK 3 — Matches empty state ───────────────────────────────────────
- tapOn:
    id: "tab.matches"
- extendedWaitUntil:
    visible:
      id: "matches.segment.mutual"
    timeout: 30000
- extendedWaitUntil:
    visible:
      id: "matches.empty-text"
    timeout: 30000
- assertVisible:
    id: "matches.go-to-trades"
# Same string as block 1, from the same formatter and the same query key.
- assertVisible:
    id: "matches.invite-social-proof"
    text: ".*9 of your 11 leaguemates.*"
- assertVisible:
    id: "matches.invite-cta"
- assertVisible:
    id: "matches.progress-module"
# ⚠ READ THIS BEFORE TRUSTING THE THREE ASSERTIONS ABOVE.
# The empty branch has NO scroll container (styles.centered, flex:1 +
# justifyContent:'center', MatchesScreen.tsx:997-1003) and the column is
# taller than the viewport on the canonical device — the progress module,
# Refresh and the help link are already clipped for real users (audit
# 09-capture-requests-response.md:32-34; photographed in
# capture/matches@near-unlock.yaml). Off-screen children stay in the
# hierarchy, so these assertVisible calls pass whether or not anything is on
# screen. THE SCREENSHOT IS THE EVIDENCE, NOT THE ASSERTION (README law 23).
# Tracked as operator gate OG-12.
- takeScreenshot: invite__matches-empty-block
```

**Deliberately not automated: the OS share sheet.** Tapping `league.invite-cta` opens system UI
whose dismissal is the hazard class of README law 17 (undismissable SpringBoard confirm) and law 20
(native overlay poisoning). Flows assert **up to and including the CTA**; the sheet →
`invite_shared` leg is proven by row check E2E-1 and manual test M-10. **A declared coverage
boundary, not an omission** (scope W2).

---

### File B — `mobile/.maestro/flows/growth/invite-promotion@espn.yaml`

```yaml
appId: com.fantasytradefinder.app
# tc: TC-GRO-INVITE-02
# profile: espn
# flags: release
# source: mobile/src/components/InviteLeaguematesCard.tsx
#         mobile/src/screens/LeagueScreen.tsx
#
# THE PLATFORM GATE (OC-4 / PR-7). An ESPN league id is not in a Sleeper
# league list, so an invite link built for it cannot resolve (P0-3 D4) and
# web's auto-select findIndex (web/js/app.js:589-601) cannot hit. The
# promoted card is therefore WITHHELD and the legacy affordance survives.
#
# ENTRY PRECONDITION (profiles/espn.json): the ESPN league arrives via
# GET /api/espn/leagues and several components fail OPEN on a league id
# missing from useSession().leagues — so this flow MUST enter through the
# league picker. A direct/launch-arg entry leaves the cache empty and
# captures the WRONG state.
#
# WHY league.progress-invite IS EXPECTED HERE, AND WHY IT IS FRAGILE:
# espn.json has "members": [], so ranked_user_count = 1 < 3 =>
# /api/league/contrarian returns insufficient_data (server.py:13753-13763)
# => contrarianInsufficient => moduleVisible (LeagueScreen.tsx:358-359),
# even though qa_espn is fully ranked and the league has a seeded match.
# rankedMates = 0 => remaining = 1 => the inline link renders via the
# :124-137 sentence branch. If a future fixture gives this league three
# ranked members the module unmounts and this block fails for a reason
# unrelated to P1-5. Re-derive before "fixing".
tags: [growth, invite, espn]
---
- launchApp:
    clearState: true
    clearKeychain: true
    stopApp: true
- extendedWaitUntil:
    visible:
      id: "signin.username-input"
    timeout: 15000
- retry:
    maxRetries: 2
    commands:
      - tapOn:
          id: "signin.username-input"
      - eraseText
      - inputText: "qa_espn"
      - assertVisible:
          text: ".*qa_espn.*"
      - tapOn:
          id: "signin.continue-btn"
      - extendedWaitUntil:
          visible:
            id: "leagues.row.*"
          timeout: 30000
- tapOn:
    id: "leagues.row.*"
- extendedWaitUntil:
    visible:
      id: "tab.trades"
    timeout: 60000
- extendedWaitUntil:
    visible:
      id: "rank.more-ways"
    timeout: 60000
- waitForAnimationToEnd
- tapOn:
    id: "tab.league"
- extendedWaitUntil:
    visible:
      id: "league-summary.league-home"
    timeout: 30000
- tapOn:
    id: "league-summary.league-home"
- extendedWaitUntil:
    visible:
      id: "league.hero"
    timeout: 30000

# ── BLOCK 4 — ESPN gate: card withheld, legacy affordance intact ─────────
- assertVisible:
    id: "league.espn-badge"          # proves the ESPN branch is really live
- assertNotVisible:
    id: "league.invite-card"
- assertNotVisible:
    id: "league.invite-social-proof"
- scrollUntilVisible:
    element:
      id: "league.progress-module"
    direction: DOWN
    visibilityPercentage: 100
    timeout: 30000
- assertVisible:
    id: "league.progress-invite"
- takeScreenshot: invite__espn-gate

# ── BLOCK 5 — Matches on ESPN: no invite block either ────────────────────
# espn.json seeds 1 mutual match, so this is the POPULATED branch — the
# assertion is that the invite block is scoped to the empty state AND
# withheld on a non-Sleeper league. Two guarantees, one cheap block.
- tapOn:
    id: "tab.matches"
- extendedWaitUntil:
    visible:
      id: "matches.segment.mutual"
    timeout: 30000
- assertNotVisible:
    id: "matches.invite-cta"
- takeScreenshot: invite__espn-matches
```

> `league.espn-badge` is asserted from the existing capture state list
> (`screens/manifest.json` `league.states` includes `espn-badge`). **Re-verify the id exists at
> that name before writing the flow**; if it does not, anchor on `league.espn-resync`
> (`LeagueScreen.tsx:744`) instead. Do not invent an id.

---

### Flows that must stay green **unmodified**

| Flow | Why it is unaffected | Note |
|---|---|---|
| `flows/smoke/09-league.yaml` | Waits on `league.hero`; the card is inserted **below** it | **Plan's reason verified correct** |
| `flows/smoke/08-matches.yaml` | Runs on `standard` and **asserts `matches.empty-text` is NOT visible** (that profile seeds 2 mutual matches). P1-5 adds nothing to the populated branch | **The plan's stated reason — "waits on `matches.empty-text`" — is wrong.** [LLD §11 correction 2](LLD-p1-5.md#11-corrections-to-the-plan) |
| the other 9 smoke flows | No touched surface | tier-1 requires all 11 anyway |

**A diff to any smoke flow invalidates the additive claim** and must be escalated, not absorbed.

### Capture delta

**20 frames**, not 11 — `screens/manifest.json` tracks *states*, not profiles:

- `league` (11): `coverage--single-format`, `draft-picks-row`, `espn-auth-expired`, `espn-badge`,
  `espn-resyncing`, `first-paint-pending`, `hero--second-league`, `populated`, `progress-module`,
  `progress-ring--4-4-locked`, `works-now`
- `matches` (9): `empty--mutual`, `error`, `populated--all-filter`, `populated--awaiting`,
  `populated--espn-awaiting`, `populated--espn-mutual`, `populated--mutual`, `progress-module`,
  `skeleton`

Re-taken in the **single consolidated R1 pass** at the end of the round (`HLD-p1.md` §A.5 / §C step
5), **not** by P1-5's own commit. `mobile/scripts/screen-capture.sh --screen league --screen matches`;
**never `--prune` with a profile filter** (law 21); **eyeball every shot** (law 23) — OG-12 and OG-13
are decided from these frames, not from an assertion.

### Sim-gate tier

**Tier 1** (`docs/runbook.md` — "Mobile screen / navigation / state change"): full 11-flow smoke +
both new growth flows + the capture refresh. Log in `TEST_LEDGER.md`; write
`qa/sim-runs/last-sim-run.json`. Enforced by `githooks/pre-push`. **No deviation proposed**; a
tier-2 argument exists (League Home gains one mounted card) and is rejected because the Matches
change is a state-conditional layout change on a screen with a live clipping defect — the captures
*are* the evidence.

---

## 8. Non-Maestro verification

### Backend (pytest, inside commit T1)

`T1.4` / `T1.6` per [LLD §8](LLD-p1-5.md#8-event-payload-shapes-and-the-t1-registry-rows) — covering
AC-29 … AC-33.

### Gate between T1 and the client wave — **blocking, verified never assumed**

T1 merged → Render deployed → `GET /api/analytics/health` → hand-rolled `POST /api/events` per new
name with the **full** prop set → **`dropped == 0` and every prop echoed back**. Failure mode is a
200 with no row and no error signal. **No client `track()` is written before this passes.**

### E2E-1 — the row check (G-017's rule: verify a row at the destination, not a 200 at the source)

Simulator against a dev backend with `analytics.client_events` **and** `analytics.ingest` on:
open League Home, open Matches empty, tap both CTAs, complete one real share, dismiss another;
wait ≥10 s (`FLUSH_INTERVAL_MS`) or background to force a flush; then

```sql
SELECT event_type, props, platform FROM user_events WHERE event_type LIKE 'invite%';
```

Proves AC-34, AC-35, AC-36, AC-37 and the second half of AC-26.

### Manual / simulator

| # | Test | Proves |
|---|---|---|
| M-1 | Typecheck `npx tsc --noEmit` | AC-39 |
| M-2 | `testid-lint.sh` | AC-40 |
| M-3 | Everyone-joined league → card absent, **no gap, no orphaned label**, inline link **returns** | AC-11, AC-4 |
| M-4 | Solo league (`total_teams = 1`) → card absent | AC-4 |
| M-5 | Fully-unlocked league with un-joined members → **card present** even though the progress module is gone | AC-12 |
| M-6 | Summary in flight → card absent; appears on data land with no above-fold jump | AC-13 |
| M-7 | Matches with a **non-active** league chip selected → no invite block | AC-17 |
| M-8 | ESPN league → tap the inline link → `invite_cta_tapped` lands with `platform: 'espn'` | AC-22 |
| M-9 | `growth.invite_join_link` **OFF** and **ON** → shared URL matches P0-3's expected format in each case | AC-25 |
| M-10 | Tap → sheet → **dismiss** ⇒ `invite_cta_tapped` only. Tap → sheet → **complete** ⇒ both. No error surfaces either way | AC-26, AC-28 |
| M-11 | VoiceOver on `league.invite-cta`: announced as a button, ≥44 pt | AC-8 |

**Known coverage limits, declared:** the OS share sheet is not driven by Maestro (W2); the
`members_overlay` surface has no flow (PR-9-dependent, ~8 lines, covered by M-10 if it ships).
**Waiver W3 (no unit test for the formatter) is withdrawn** — see AC-1…AC-5 and
[LLD §11 correction 6](LLD-p1-5.md#11-corrections-to-the-plan).

---

## 9. Docs impact

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/business/analytics/2026-08-11-p1-5-addendum.md` | **NEW — mandatory**, in **T1** (T1.8) | The precondition `analytics_taxonomy.py:9-10` demands before any new client event. Records: no invite baseline; the `invite_shared` / `invite_sent` fork and D-P1-03's **assumed** resolution; league-vs-device `platform`; the **DAU/WAU seam date**; the closed `surface` enum; what is deliberately not instrumented |
| `docs/business/analytics/2026-07-17-tracking-plan-v2.md` | **Updated in T1** (T1.7) | One appended "Addendum 2026-08-11 — P1 round" section covering all nine round events; P1-5's detail lives in the standalone file above |
| `docs/cross-client-invariants.md` | **Updated in T1** (T1 owns `:268-271`) | §"Client analytics event contract" — add the three invite names + the addendum link, and state that web (`web/js/events.js`) and the extension fire **none** of them so the omission reads as deliberate. Folded into T1 because three P1 items target the same block (`HLD-p1.md` §A.5) |
| `docs/design/components.md` | **Updated** (P1-5) | `InviteLeaguematesCard` beside the other named League Home modules; the Matches-empty invite block |
| `living-memory/DECISIONS.md` | **Updated** (P1-5) | (1) the card **suppresses** the inline link rather than coexisting; (2) one `shareInvite` owns all four emitters and both events, **layered on** P0-3's `buildInviteUrl`. **ID allocated at write time by re-reading the file** — nine claimants on `D-011` |
| `screens/manifest.json` | **Updated** (P1-5) | `league.sources` += `mobile/src/components/InviteLeaguematesCard.tsx`, or freshness under-reports on the next card change |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **On ship** | TEST_LEDGER carries the tier-1 sim run **and** the row-landed verification |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if E2E-1 surprises. G-017 already covers the paired-analytics-gates trap |
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed. `/api/league/summary` is consumed exactly as documented; `POST /api/events` accepts new names by registry membership alone, with no envelope change |
| `docs/data-dictionary.md` | **n/a** (**W1**) | Nothing new is *stored*. All three events are client-fired into the existing `user_events` table and documented via the taxonomy + addendum — the treatment `guide_*` and `draft_room_*` received |
| `docs/config-reference.md` | **n/a** | No flag, env var or `model_config` key added or changed. One *read* of `growth.share_landing` is removed; the key, default and every other read are untouched. **Re-check only if OG-9 is declined** |
| `docs/architecture.md` · `living-memory/HLD.md` | **n/a** | No module, client or data-flow change; every call rides `track` → queue → `POST /api/events` |
| `living-memory/LLD.md` | **n/a** | "Register the name, then wire the client" is an existing convention this item obeys, not one it establishes |
| `docs/glossary.md` | **n/a** | No new domain term. `surface` is an event property, not a domain concept |
| `docs/design/design-system.md` | **n/a** | No new token, colour, radius or type step |
| `docs/runbook.md` · `docs/adr/` | **n/a** | No operational lever, no architecture-altitude choice |

---

## 10. Operator gates

**Eleven checkpoints are unresolved. None is agent-decidable. Each row states what it blocks and what
happens if it is not answered.** Recommendations shown are the plan's / HLD's, reproduced for the
operator's convenience — **this document does not adopt any of them.**

| Gate | Question | Plan's recommendation | Blocks | Consequence if unanswered |
|---|---|---|---|---|
| **OG-1** (OC-1 / PR-5) | Social-proof copy framing: (a) factual/self-interested, (b) altruistic, (c) named leaguemates | (a) | **BUILD** | `inviteSocialProof`'s four string literals cannot be written. AC-1…AC-3 have no expected value; **Maestro File A's `text:` regexes cannot be authored** |
| **OG-2** (OC-2 / PR-6) | Matches hierarchy: invite primary (the audit's literal ask), or "Find a trade" primary with invite secondary | (b) | **BUILD** | AC-16 has no expected value; the Matches capture cannot be signed off |
| **OG-3** (OC-3 / AN-3 / **D-P1-03**) | Event name `invite_shared` (runtime + P0-3 B4) vs `invite_sent` (tracking plan v2 §S3, **prose only**) | `invite_shared`, and amend the tracking plan | **BUILD — and before T1 freezes.** If the answer is `invite_sent`, **before P0-3 merges** | **This is the assumption in force.** After T1, reversal costs a T1 amendment commit with the full deploy-and-verify gate, and a desync between P0-3 and P1-5 drops the event silently behind a 200 |
| **OG-4** (OC-4 / PR-7) | ESPN / non-Sleeper: withhold the card, show everywhere, or show with different copy | (a) withhold | **BUILD** | The render ladder's L2 branch **and Maestro File B block 4**. Declining (a) means knowingly scaling a broken journey (P0-3 D4) |
| **OG-5** (OC-5 / PR-8) | Suppress the inline link when the card renders? | (a) suppress | **BUILD** | The `onInvite` conditional at `LeagueScreen.tsx:700`; **AC-10 and Maestro block 2 are void without it** |
| **OG-6** (OC-6 / AN-5) | Ship `invite_cta_tapped`, or only shown + shared? | in | **BUILD — before T1** | T1's name list. Without it, a drop between impression and share is unattributable to either the copy or the sheet |
| **OG-7** (OC-7 / PR-9) | OPTIONAL-M: invite button in the members overlay | in | **BUILD — before T1** | Whether `members_overlay` exists in the **closed `surface` enum**, which is documented in T1's prop-row comment. Answer before T1, not before B1 |
| **OG-8** (OC-8 / PR-10) | Zero-not-joined: card absent, or an affirmation | (a) absent | **BUILD** | `inviteSocialProof`'s C4 branch and the ladder's L3 |
| **OG-9** (OC-9) | Drop the `growth.share_landing` gate on `invite_shared`? | (a) drop | **BUILD** | AC-27. Declining keeps one flag-off configuration able to silently blind the invite funnel; the key and every other read are untouched either way |
| **OG-10** (OC-10 / AN-8) | Defer the copy A/B? | defer; queue behind P0-7 F1 | release | Nothing in the build. Answering "now" makes P0-7 F1 a **hard prerequisite** and moves P1-5 from **M to L** |
| **OG-11** (OC-11) | Wave sequencing / `LeagueScreen.tsx` ownership | **Adjudicated by `HLD-p1.md`** §A.2 / §B / §C — T1 → Wave A → Wave B (B1 = P1-5, sole owner of `LeagueScreen.tsx` and `MatchesScreen.tsx`) | — | **Removed from the operator's queue** by the HLD |

### Two gates this LLD/PRD round adds

| Gate | Question | Options | Blocks | Consequence if unanswered |
|---|---|---|---|---|
| **OG-12** — **NEW, BLOCKING** | The Matches empty branch **has no scroll container** and its column already overflows the viewport (`MatchesScreen.tsx:997-1003`; audit `09-capture-requests-response.md:32-34`; photographed in `capture/matches@near-unlock.yaml`). P1-5's block lands **inside the clipped region**. What ships? | **(a)** P1-5 adds a `ScrollView` / top-anchors the column while it owns the file in Wave B — closes the defect, but is a layout change **outside P1-5's scope block** and re-frames 3+ capture states. **(b)** Ship the block into the clipped region knowingly, and record that `invite_cta_shown{surface:matches_empty}` counts **mounts, not sightings**. **(c)** Drop the Matches surface from P1-5 and hand it to the A-34 owner; ship League Home alone | **BUILD** of the Matches half | Silence ships **(b) by default** — a CTA no user can see, a green Maestro run certifying it (law 2), and a poisoned denominator on the one metric this item exists to create. **No recommendation is made here** |
| **OG-13** — **NEW** | The card's `primary` CTA sits directly above `league.action.find`, also `primary` (`LeagueScreen.tsx:487-493`) — **two adjacent solid-ice buttons on League Home.** Neither the plan nor the audit examined this; the plan's R10 treats the insert purely as a fold risk | **(a)** keep both primary; **(b)** card primary, demote the action row's "Find a trade" to secondary; **(c)** move the card **below** the action row (a one-line move) | release *(decided from the R1 captures, per law 23)* | The `league/populated.png`, `league/progress-module.png` and `league/works-now.png` frames cannot be signed off. Absent a call, **(a)** ships |

---

## 11. Release risk — this item ships live on merge

**Stated as a release fact, not a footnote** (`HLD-p1.md` §F R-1):

- **P1-5 adds no feature flag.** Justification: the bright line crossed is *analytics events*, whose
  remedy is registration + ordering, not a flag. No route, no schema, no contract change.
- **Consequence:** the moment the P1 branch merges to `main`, a new card appears on League Home and a
  new action block on the Matches empty state for **every** user on the next build. There is no
  staged rollout and no kill switch. **Rollback is `git revert`.**
- **P1-5 is one of four items in this round that ship live on merge** — with P1-1/2, P1-7 and P1-11.
  **P1-9 is the only item in the round with a real kill switch.** The round's rollback story is
  `git revert` for four of seven items. `HLD-p1.md` recommends the operator answer **RL-1 for the
  whole round**, not just for P1-1/2.
- **Two things are live-on-merge for *analytics* rather than UI:** `invite_cta_shown` begins
  producing rows on ship day (a **DAU/WAU seam** if T1.3 is wrong), and `invite_shared` begins
  landing rows for the first time ever from all four surfaces. **Both seam dates go in the CHANGELOG
  and the addendum** so a later analyst sees a documented discontinuity rather than discovering one
  in a chart.
- **Adding a flag now would itself be a bright-line surface change** and is an operator decision to
  be made **before** build, not during (`HLD-p1.md` RL-1).

---

## 12. Rollback

| Layer | Lever | Cost | Notes |
|---|---|---|---|
| **UI (both surfaces)** | `git revert` of P1-5's Wave-B commit | Minutes | UI-only diff, **no data migration**. Reverts the card, the Matches block, the suppression, the four `shareInvite` call sites and the two new files. `LeagueProgressModule.tsx` was never touched, so the legacy inline link returns automatically at both of its guards (`:125`, `:200`) |
| **Just the Matches half** | Revert B9/B10/B11 only | Minutes | The two halves are independent; `MatchesScreen.tsx` is B1-exclusive in Wave B. This is the lever if **OG-12** goes wrong in the field |
| **Just the members overlay** | Delete the B8 block + the `members_overlay` enum value **together** | Minutes | Enum and code must move as one, or the prop is stripped silently |
| **Just `invite_cta_tapped`** | Delete one name, one prop row, one line in `inviteShare.ts` | Minutes | Requires a **T1 amendment commit** with the full deploy-and-verify gate — the taxonomy is frozen after T1 |
| **Analytics names** | **Not independently revertible.** Removing a name from `ALLOWED_CLIENT_EVENTS` while a shipped client still fires it re-creates the exact silent-drop condition this item fixes | — | **Revert the client, leave the registry.** An allowlisted name with no emitter is harmless; an emitter with no allowlist entry is the bug |
| **`growth.share_landing`** | Not a rollback lever for this item | — | The flag is `true` in prod; P1-5 removes one *read* of it. Flipping it off no longer suppresses `invite_shared` (that is the point of OG-9) |
| **Data already landed** | None. Rows are permanent | — | The seam dates in the CHANGELOG + addendum are the mitigation — a later analyst must be able to see the discontinuity |

**Revert safety check before merge:** confirm the P1-5 commit touches **no** file also touched by
T1, so a P1-5 revert cannot un-register an event name that another item's client still fires.

---

## 13. Residual risks accepted

| # | Risk | Severity | Disposition |
|---|---|---|---|
| **R-P1-5-a** | **No baseline.** `invite_shared` never landed a row, so "promotion worked" has nothing to compare against. Every post-ship read is **absolute, not a lift** | Medium | Stated plainly in the T1.8 addendum. **Do not let a dashboard imply a before/after that does not exist.** OG-10's A/B is the honest route to a comparison, and it is itself gated on P0-7 F1 |
| **R-P1-5-b** | **Fail-open platform gate.** A league missing from `useSession().leagues` resolves to `'sleeper'` and gets the card. Matches `SendInSleeperButton`'s existing behaviour deliberately | Low | Accepted for consistency; documented in `InviteLeaguematesCard`'s header comment |
| **R-P1-5-c** | **Stale count.** 60 s `staleTime` means the card can claim 9 un-joined moments after the 9th joins | Low | Cosmetic, self-correcting; pull-to-refresh fixes it immediately; the backend cache is invalidated on membership writes |
| **R-P1-5-d** | **Matches CTA clipped** — see **OG-12** | **Medium-high until OG-12 is answered** | **Not accepted by default.** An unanswered OG-12 ships option (b) by silence, which is the worst of the three |
| **R-P1-5-e** | **Double-count** if P0-7's OPTIONAL-A `action` enum gains `invite` | Medium | Hard re-verify row before B1 builds (AC-38). **Not agent-resolvable — escalate** |
| **R-P1-5-f** | **`invite_cta_shown` left INTENT** ⇒ DAU/WAU step-change on ship day, breaking every retention and churn series at the seam, silently and permanently | **High** | T1.3 is mandatory, not optional. AC-33 asserts it directly. Seam date in the addendum |
| **R-P1-5-g** | **`invite_shared`'s prop row not extended** ⇒ the name works, the four props vanish, `surface` is permanently absent with **no error** | **High** | AC-30 asserts **prop survival**, not merely acceptance. Re-verified live before B1 builds |
| **R-P1-5-h** | **Fixture drift.** The `9 of your 11` regex is derived from `near-unlock`'s roster; P0-1 and P1-7 both edit `seed_ui_test_db.py` | Medium | Re-derive the counts in the §10 re-verify pass; the flow carries the derivation in a comment |
| **R-P1-5-i** | **Above-the-fold regression** on small devices — the card pushes the day-one action row down on the screen the audit already calls section-heavy | Low-medium | Decided from the R1 captures, eyeballed (law 23). One-line move if the fold suffers. Interacts with **OG-13** |
