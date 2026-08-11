# Build handoff prompt

> Copy everything between the rules into a fresh session. Self-contained — assumes no prior context.
> Reflects the operator triage pass of 2026-08-09: 7 findings kept for build, 25 deferred, 1 withdrawn.

---

You are picking up remediation work from an independent UX/product audit of the FTF iOS app. The audit is complete; the operator has triaged it. Your job is to build the seven findings selected for fixing.

## Read first, in this order

1. `docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` — findings with evidence, failure mechanisms, and falsification handles.
2. `docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md` — the proposed fix for each, typed Bug / Polish / Idea.
3. Root `CLAUDE.md` — project conventions. Load-bearing here, not boilerplate.

## Audit the right tree

The audit ran against **`origin/main @ 72a0770`**. Do not assume the current checkout matches: at audit time the working branch was 155 commits behind and missing six shipped screens entirely. Per `CLAUDE.md`, **branch from a freshly fetched `origin/main`**, never from whatever is checked out.

Re-verify each finding against current `origin/main` before fixing it. The audit is four commits old at best and this repo has concurrent sessions writing to it.

## Scope — seven findings, all P0

### P0-1 · Default path never completes its own progression *(Bug, effort S)*
A user who finishes the entire 32-step Quick Set walk still registers `unlocked: false`, so **the push-permission prompt never fires for them**.

`ranking_method` is written from only two call sites — `RankHomeScreen.tsx:64` and `SettingsScreen.tsx:231` — neither on the default path. `get_ranking_method` returns `None` when unset (`database.py:3362-3370`); `NULL` falls to the trio branch requiring 40 interactions (`server.py:6172-6174`); tier saves never touch `_interactions`.

**Fix:** write the method at the point of *use*. In each save handler, if the user has no stored `ranking_method`, set it from the action: `/api/tiers/save` → `quickset`/`tiers` per the `via` tag, `/api/rank3` → `trio`, `/api/rankings/reorder` → `manual`, `/api/anchor/save` → `anchor`. Then backfill: existing users with saved tiers but a null method get `quickset`.

**Operator note:** *"Per position progression and trade unlock should both be covered."*
The per-position ring is already correct — `LeagueScreen.tsx:328-334` reads `tiersSaved` directly and never consults `ranking_method`. Only the global unlock is broken. That combination is the sharp edge: a Quick Set user sees **4/4 positions ranked** and is *still* locked.

**Acceptance:** a fresh account that only ever uses Quick Set reaches 4/4 on the ring and `unlocked:true` **together**, and the push primer fires.

---

### P0-2 · A failed trade search looks identical to never having searched *(Bug, effort S)*

**Verified against real captures — the finding holds, but it splits into two failure modes and the original fix spec covered only one.**

| Failure | What the user gets today |
|---|---|
| `POST /api/trades/generate` fails outright | A transient toast — *"Unexpected server error."* — from `generateMutation.onError`. Page beneath unchanged. |
| Job starts, then errors during polling (`status:'error'`, `job.error` populated) | **Nothing at all.** No toast, no state. |

`job.error` is read nowhere in `TradesScreen.tsx` (confirmed by grep). Comparing `screens/mobile/trades/error.png` against `empty.png`: below the toast they are **pixel-identical** — same "FULLY GUIDED" headline, same Find a Trade button, same "HIT 'FIND A TRADE' TO START" card. No retry, no persistent trace.

**Fix, three parts:**
1. Branch the deck empty-state ladder on `job?.status === 'error'` *before* the never-searched case (~`TradesScreen.tsx:4910`); render the backend message with a working Retry.
2. Leave a persistent trace on the POST-failure path too — a toast alone disappears.
3. The toast currently overlays the mode-bar segmented control, truncating "Guided" to "G" and "Free agents" to "…ts". Fix the z-order/offset while you're there.

**There is already a good pattern in this app — copy it rather than inventing one.** The Rank tab's error states (`tiers/error.png`, `manual-ranks/error.png`, `anchors/error.png`) each show explicit error copy with a distinct Retry affordance, clearly different from any valid empty state. Mirror that treatment.

**Acceptance:** a forced generation failure — on both paths — produces a distinct, named, persistent state with a working retry. A user cannot confuse "it broke" with "I haven't searched yet."

---

### P0-3 · The invite loop is broken at both ends *(Bug + additive half, effort S–M)*
`buildInviteUrl` (`InviteLeaguematesBanner.tsx:27-31`) emits `/?league=<id>&ref=<user>`. The app reads `?ref=` but **never reads `?league=`**, and because the URL has no path, `deepLinks.ts:301-302` short-circuits it: *"Bare open / referral-only URL (no path) — nothing to route, no toast."*

**Fix, two halves:**
- **Bug:** emit a real path — `/app/league/join/<leagueId>?ref=<user>` — add the matching `V2_SCREENS` entry, parse the league id, pin it as active once auth completes.
- **Additive:** when a referral is present, name the inviter and league on sign-in.

Universal links are correctly configured (`app.json:52` entitlement, AASA at `server.py:8075-8108`), so the hard part is already done and currently unused.

**Open question the audit could not close:** whether `web/` parses `?league=` and completes the journey server-side. Check before designing, since it changes the shape of the fix.

**Acceptance:** a tapped invite on a device with the app installed lands the recipient in the inviting league, with the inviter named.

---

### P0-5 · Apple account-only branch strands users *(Bug, effort S)*
A new Apple identity with no bound Sleeper account gets `account_only`, a `no_league` sentinel, and routes **straight to the tabs** — skipping league selection. Every league surface is empty; the only way out is Settings.

**Fix:** route account-only sessions to `LeaguePicker` in `onAccountSignedIn` (`RootNav.tsx:398`), and give the picker a companion state leading with platform options rather than an empty list.

**Operator note:** *"we need a post apple sign in platform selector… should we update the landing page with a way for users to select ESPN or MFL (or maybe that is impossible without an account first?)"*

Answered by the audit: **a post-Apple selector needs no backend work.** `_mint_account_only_session` issues a real session token, and both `/api/espn/link` (`server.py:18493`) and `/api/mfl/link` (`:20119`) require a *session*, not a Sleeper identity. **Landing-page selection before any account is not possible as built** — both routes `_require_session()` and 401, because linking binds the league to `session.user_id`. Put the choice immediately after Apple sign-in.

**Acceptance:** a brand-new Apple sign-in reaches a platform/league choice without visiting Settings.

---

### P0-6 · Matched ESPN users have no action, and aren't told why *(Bug, effort S)*
`SendInSleeperButton.tsx:59-66` excludes `platform==='espn'` by rendering `null` — no message. A matched ESPN user's only remaining action is Dismiss.

Confirmed during the operator pass: **ESPN leagues do produce matches.** `check_for_match` fires on any like carrying a `target_user_id` outside the demo league (`server.py:10011`), with no ESPN exclusion. This finding is firmer than originally graded.

**Fix:** replace the silent `null` with an explanatory state and a real fallback — "Sending is Sleeper-only for now — copy this trade to propose it in ESPN" plus a copy-to-clipboard action. `FreeAgentsScreen` already does this pattern for its dimmed Add button; mirror it.

Also decide the dead path: `setMatchDisposition` (accept/decline) is wired server-side and never called from the app. Surface it or delete it — do not leave it.

**Acceptance:** a matched ESPN user has a stated reason and at least one useful action.

---

### P0-8 · The guided tour announces completion before teaching anything *(Bug, effort S)*
A user's first like fires the celebration beat `s6.1` (`TradesScreen.tsx:3129`); in the **same chain tick** the sign-off `s8.1` fires (`:2456-2459`) and calls `completeTour()` (`useGuide.ts:137-141`). The user is told guidance is over having received none. Nine of fifteen scripted steps are structurally unreachable because every `onboarding.*` sub-flag is false while the master flag is true.

**Fix:** gate `s8.1` on having actually delivered a tour — a minimum count of seen steps, or specifically requiring the swipe-coaching beat. Also: `err.burst` has zero call sites anywhere; delete it or wire it.

**Do not** flip the onboarding sub-flags as part of this. That is P0-9 and it is the operator's call.

**Acceptance:** a user who sees only the first-like celebration is never told the tour is complete.

---

### P0-9 · A new user's first act is a 32-tap chore *(Idea, A/B candidate, effort M)*
**Operator note: *"I need to test this experience."* Do not implement this yet.**

**Materially updated after the visual pass — read this before doing anything.**

The screen library contains 16 `onboarding/` captures taken under `flags: "onboarding-v2"`, while every other screen was captured under `flags: "release"`. Those onboarding captures show a **complete, well-crafted, thirteen-beat guided tour that does not ship**: username coaching, swipe coaching, an explicit *"see that label? CONSENSUS VALUES. These prices are the market's, not yours. We'll fix that shortly"*, a contextual **"Fix WR →"** CTA, and then *"WR is done — QB is your next-highest leverage."*

It shows a trade **before** any ranking work, and it ranks by leverage rather than alphabetically. **That is precisely the fix this finding asks for, already designed and built.** The work is not "design a better first session" — it is "decide whether to turn on the one that exists."

What the release-flag captures independently confirmed about the current default:
- `quick-set/step-populated--seeded.png` has **no payoff copy at all**. The only line is a mechanics hint ("Each card shows the tier the player is in now"). Trios, by contrast, states its payoff prominently. So the default landing gives no reason to do the work — worse than the audit originally graded.
- **In fairness to the operator's skepticism:** cards arrive pre-seeded with suggested tiers, and the button reads "Continue — no QBs this high," so a user who accepts the defaults can clear a tier in one tap. The 32-tap floor is structural, but whether it *feels* like a grind is not knowable from stills. That is exactly the thing worth testing.

**Your job is still to help the operator test it, not to ship it.** Ask what they need. Do not flip flags unilaterally. If they want a cheap intermediate step, adding payoff copy to Quick Set is a small, low-risk change that does not require deciding the ordering question.

**Dependency worth surfacing:** the operator deferred P0-7 (analytics blindness), but there is currently **zero client instrumentation on navigation, both League screens, and Send-in-Sleeper**. Testing the first-session experience meaningfully needs some of that. Raise this before they invest in a test that cannot be read.

## Before you write code — two decisions that are the operator's

1. **Feature gates.** `CLAUDE.md` §Conventions mandates a scope block, Maestro delta, doc updates, and a pre-ship sim run for anything touching user-visible behaviour. The operator may declare **express** to skip them. **Agents never self-select express.** No declaration → full gates.

2. **The bright line.** `CLAUDE.md` states that a change touching schema, API contracts, feature-flag surfaces, or analytics events is *not* a quick fix. **P0-3 adds a deep-link route** (route surface) and **P0-9 flips feature flags**. If the operator declares express on either, say so explicitly and get a confirming yes before proceeding.

## Traps that will cost you time

- **Analytics taxonomy is default-deny.** If any of this work adds a client `track()` call, register the event name server-side *first* or it is silently dropped. There is prior art of exactly this failure in this repo.
- **Do not trust comments over code.** The audit lost a finding to a stale comment: `config/features.json` says the mock draft "stays OFF and refuses" while `mock_draft_service.py:294` says `CPU_MODEL_VALIDATED = True`. Read the constant that decides behaviour. If you find more contradictions, that is finding **A-33** and it wants fixing.
- **`TradesScreen.tsx` is ~6,158 lines.** Grep to navigate; do not read it linearly.
- **The working tree mutates under you.** Concurrent sessions write to this repo. Re-diff before acting on any file list.

## Definition of done

- Each finding's acceptance criterion demonstrably met.
- Tests green: `python3 -m pytest backend/tests/ -q` and `cd mobile && npx tsc --noEmit`.
- Maestro tier per the change class (`docs/runbook.md` § Pre-ship simulator gate) unless express was declared, logged in `TEST_LEDGER.md`.
- Docs updated per `docs/CLAUDE.md` triggers — P0-3 touches routes, so `api-reference.md` is in scope.
- Living-memory write-back per `CLAUDE.md` §Session memory: `CHANGELOG.md` entry, `HANDOFF.md` if stopping mid-flight, `NEXT.md` item 0 updated as blockers close.

## Out of scope

The other 25 findings were deferred by the operator and are in `04-priority-backlog.md`. Do not build them. If you spot something while working, note it — don't scope-creep into it.

---
