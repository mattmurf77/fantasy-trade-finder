# PRD — P0-3 · The invite loop, both ends

> Requirements and acceptance for audit finding **P0-3**
> (`docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-3).
> Implementation detail: [`lld-p0-3.md`](lld-p0-3.md). Binding parent: [`hld.md`](hld.md).
> Branch `p0-remediation-2026-08-10`, worktree `ftf-p0-remediation`.
>
> **Full gates apply — no express was declared** (root `CLAUDE.md`; HLD S-46). This change
> adds a deep-link route, a server route, an API route, a feature flag and four analytics
> names: four separate bright-line surfaces. Scope block: [`scope-p0-3.md`](scope-p0-3.md).

## Contents

- [1. Problem](#1-problem)
- [2. Requirements](#2-requirements)
- [3. Acceptance criteria](#3-acceptance-criteria)
- [4. The AASA ordering constraint — operator sequence](#4-the-aasa-ordering-constraint--operator-sequence)
- [5. Non-goals](#5-non-goals)
- [6. Docs rows](#6-docs-rows)
- [7. Rollback, per half](#7-rollback-per-half)
- [8. Open items for the operator](#8-open-items-for-the-operator)

---

## 1. Problem

The app has exactly one growth loop — a leaguemate invites you to a league — and it
converts nobody on mobile.

**The sender's half.** `buildInviteUrl` has emitted
`https://fantasy-trade-finder.onrender.com/?league=<id>&ref=<username>` since FB #239
(`mobile/src/components/InviteLeaguematesBanner.tsx:27-31`).

**The receiver's half.** `mobile/src/utils/deepLinks.ts` reads `?ref=` and **has never read
`?league=`**. The URL has no path, so `handleDeepLink` hits its bare-path short-circuit
(`if (!path) return;`, `:352`) and the league id is discarded. Every invite ever sent to an
iOS user has dropped the one fact that made it an invite.

**The measurement half.** `invite_shared` — the only invite event in the product — is fired
at `InviteLeaguematesBanner.tsx:47` and is **not** in `ALLOWED_CLIENT_EVENTS`. Ingest is
default-deny with a 200 response, so it has been counted-and-dropped since it shipped. The
claim "the loop converts zero" has never been measurable, in either direction.

**What already works, and must not be disturbed.** The web client parses **both** params
(`web/js/app.js:5835-5848`), stores them in `localStorage`, renders an "Invited by @x"
banner, and **auto-selects the invited league** once the Sleeper list loads (`:589-601`).
The loop is broken on mobile only. That inverts the framing of the fix: the URL change is
the risky half; the valuable half is reading a param the app already receives.

---

## 2. Requirements

### FR — Functional

| # | Requirement | Half |
|---|---|---|
| **FR-1** | Mobile parses `?league=<id>` from any incoming URL, in **both** router modes, and stores it as an invite intent. **Ships unflagged.** | Client |
| **FR-2** | Mobile registers a deep-link route `app/league/join/:leagueId` on the **root** stack, reachable while signed out, resolving to a `LeagueJoin` interstitial. **Ships unflagged.** | Client |
| **FR-3** | The invite intent — `{leagueId, invitedBy, leagueName, ts}` — persists to AsyncStorage under `ftf_invite_intent` with a **14-day TTL**, is hydrated at bootstrap, is cleared on consume and on sign-out, and is swept on read once expired. | Client |
| **FR-4** | `LeagueJoin` resolves four ways by auth state: signed-out → `SignIn`; member → auto-pin → tabs; signed-in non-member → `LeaguePicker` + honest notice; **account-only → `LeaguePicker`'s companion state carrying inviter + league context**. Never a dead end, never an endless spinner. | Client |
| **FR-5** | The invited league is pinned **only** via `pickLeague(lg, {auto:true})` → `setLeague()`, which overwrites the `no_league` sentinel. No parallel "active invited league" field exists. | Client |
| **FR-6** | The pin fires from an effect keyed on the cached league list, so it re-fires when a platform link repopulates that list — the account-only path works with no coupling between P0-3 and P0-5. | Client |
| **FR-7** | `SignIn` renders an invited banner naming the inviter, in **both** `landingOn` variants. | Client |
| **FR-8** | The emitter gains the new URL format behind `growth.invite_join_link`, **default OFF**; OFF emits today's URL byte-identically. Both call sites read the flag through one function, so they cannot drift. | Client |
| **FR-9** | AASA claims `/app/league/join/*` — and nothing broader. **Unflagged.** | Server |
| **FR-10** | `GET /app/league/join/<id>[?ref=]` 302s to `/?league=<id>[&ref=]`, preserving `ref`, encoding hostile input, emitting a relative `Location` only. **Unflagged.** | Server |
| **FR-11** | `GET /api/league/invite-meta?league_id=` returns `{league_id, league_name, platform}` from Sleeper's **public** API only. Unauthenticated, read-only, degrades to `league_name: null` on any failure. | Server |
| **FR-12** | `growth.invite_join_link` is registered in `feature_flags.py`, `config/features.json` and the release flag fixture, default `false`, with its graduation criterion recorded in the config comment. | Server |
| **FR-13** | `invite_shared` (existing, currently dropped) plus `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed` are registered in the taxonomy **before** any client emits them. | Taxonomy (commit 1) |

### NFR — Non-functional and constraints

| # | Requirement |
|---|---|
| **NFR-1** | **Legacy links are parsed forever.** `/?league=&ref=` remains a supported input on both clients, permanently, with no sunset. It is already in people's Sleeper chats. |
| **NFR-2** | **Web behaviour is unchanged.** No file under `web/` is modified. The 302 hands off to the existing landing. |
| **NFR-3** | **Privacy:** the league name is resolved from Sleeper's public API only, never from our `leagues` table. Imported ESPN/MFL/Fleaflicker names are not enumerable by id. No username appears in any analytics property. |
| **NFR-4** | **No schema change, no migration, no write path.** The invite intent is client-side storage. |
| **NFR-5** | **Register before emit.** No `track()` call for a P0-3 name ships before the taxonomy commit has landed. |
| **NFR-6** | **Hermetic harness safety:** no code path added by this build may cause a Sleeper fixture miss during a sim run (`vcr_misses > 0` fails `mobile/scripts/sim-run.sh:178`). Enforced by the single-call-site rule in LLD §2.0. |
| **NFR-7** | **Ship ordering is a hard constraint, not a preference** — see §4. |
| **NFR-8** | Both halves are independently green: `python3 -m pytest backend/tests/ -q` and `cd mobile && npx tsc --noEmit` + `bash mobile/scripts/testid-lint.sh`. |

---

## 3. Acceptance criteria

### A-1 — The audit's criterion (primary)

> **A tapped invite link, with the app installed, lands the recipient in the inviting
> league, with the inviter named.**

Decomposed into independently verifiable facts:

| # | Fact | Verified by |
|---|---|---|
| A-1a | A signed-out recipient sees the inviter's handle before signing in | Maestro `invite-join.yaml` block 3 (`signin.invited-banner`, `.*qa_inviter invited you to.*`) + manual TestFlight |
| A-1b | A signed-in recipient who is a member of the league lands in the tabs **with that league active** | Maestro block 1 (`tab.trades` reached, League tab shows `QA Standard League`) |
| A-1c | A signed-in recipient who is **not** a member gets an honest, actionable state — not a spinner, not a silent no-op | Maestro block 2 (`leaguepicker.invite-notice` + a usable list) |
| A-1d | An account-only (Apple, no Sleeper) recipient sees the invite as the strongest copy on the screen and a way to act on it | Manual TestFlight (LLD §4 — needs two harness seams in one launch; out of the automated flow's scope) |
| A-1e | The **real** tap — an actual universal link from Messages/Safari, on a build installed after the AASA deploy — opens the app rather than Safari | Manual TestFlight only. `openLink` is dead in this harness (law 17) and AASA resolution has no simulator seam |

### A-2 — Legacy links shared **before** this build route correctly

> **A `/?league=<id>&ref=<u>` link sent weeks ago, tapped today on a build carrying this
> change, pins the league and names the inviter — with no change to the link.**

This is the criterion that matters most and touches the least new code: it is the one
insertion in `deepLinks.ts` above the bare-path short-circuit, it ships **unflagged**, and
it repairs every invite already in circulation. It is verified **cold and warm** by manual
test, and it is a **release blocker** — a build that ships the new path but not the legacy
reader would fix future invites while leaving the existing ones broken, which is the worse
half of the trade.

### A-3 — Web behaviour is unchanged

> **No file under `web/` is modified, and the web invite journey (banner → sign in →
> league auto-selected) behaves exactly as it does on `origin/main`.**

Verified by `git diff --name-only origin/main -- web/` returning empty, plus one manual
browser pass of the 302 → landing → sign-in → auto-select sequence.

### A-4 — The emitter is inert until the operator says otherwise

> **With `growth.invite_join_link` OFF (its default, and its state at merge), every invite
> URL this build emits is byte-identical to `origin/main`'s.**

Verified by reading `buildInviteUrl`'s OFF branch against the current implementation, and
by the flag-default test (`test_invite_links.py` T-12).

### A-5 — The invite loop becomes measurable at all

> **`invite_shared` stops being dropped**, and `POST /api/events` accepts all four invite
> names with `dropped == 0`.

Verified by `test_invite_links.py` T-13 and by the sim-run check that
`GET /api/analytics/health`'s `dropped_unknown_type` counter stays flat.

### A-6 — Nothing else moved

- The full 11-flow smoke suite passes.
- `capture/leagues@fresh.yaml` passes **unmodified** (its literal
  `No 2026 NFL leagues found for this account.` sentence must not move).
- `python3 -m pytest backend/tests/ -q` is green, including the two existing AASA tests
  updated by commit 3 (LLD §1.6).

**Ship gate:** tier 1 for the batch (navigation + screen changes), one run covering all
seven findings, evidence in `living-memory/TEST_LEDGER.md` and
`qa/sim-runs/last-sim-run.json`.

---

## 4. The AASA ordering constraint — operator sequence

**This is the highest-severity risk in P0-3 (HLD §8 R2), and it is an ordering risk, not a
code risk.** Apple's CDN caches `/.well-known/apple-app-site-association` for up to ~24h
(`docs/runbook.md:410-412`). A build that emits `/app/league/join/...` before that claim has
propagated sends **every** invite to Safari — a strictly worse loop than the one being
fixed, because today's URL at least lands on a working web page while the new one would
land on a redirect to that same page having lost the app-open.

The flag exists **for this ordering and nothing else**. It is not an experiment, not a
gradual rollout, and it gates only the emitter.

### The sequence — each step is a gate on the next

| Step | Action | Gate before proceeding |
|---|---|---|
| **1** | Merge the batch to `main`. Render auto-deploys. AASA now claims `/app/league/join/*`; the 302 and `invite-meta` are live; `growth.invite_join_link` is **false**. | `curl -s https://fantasy-trade-finder.onrender.com/.well-known/apple-app-site-association` returns 200, `application/json`, **no redirect**, and lists `/app/league/join/*` in both `components` and `paths`. |
| **2** | Validate the live file with an **external** AASA validator (Apple's own tooling or `branch.io/resources/aasa-validator`). | The validator reports the file valid **and** resolves the app id `N5Y4N2Q49A.com.fantasytradefinder.app`. A locally-correct file that Apple's CDN has not accepted is not a pass. |
| **3** | **Wait ≥24h.** Do not compress this step. | 24h elapsed since the step-1 deploy. Record the timestamp. |
| **4** | Ship a TestFlight build **produced after** step 1 (the entitlement is already in `mobile/app.json:21`; what matters is that the device installs while the claim is live — iOS fetches AASA at install time). | Build installed on a real device from TestFlight. |
| **5** | **On device, with the app installed:** paste `https://fantasy-trade-finder.onrender.com/app/league/join/<a real league id>?ref=<a real username>` into Messages, send it to yourself, and tap it. | **The app opens** on `LeagueJoin` and lands per FR-4. If Safari opens instead, AASA has not propagated to that device — return to step 3, do not proceed. |
| **6** | Only now: flip `growth.invite_join_link` to `true` in `config/features.json`, deploy, and confirm via `GET /api/feature-flags`. | Flag reads `true` live. |
| **7** | Verify the emitted URL changed: share an invite from the app and inspect the message text. | It reads `/app/league/join/<id>?ref=<u>`. |

**Steps 6-7 happen in a separate session, after on-device verification — never inside this
build** (HLD S-14, S-44: no flag defaults change anywhere in this batch).

**If anything in steps 2-5 fails**, the correct action is to leave the flag OFF
indefinitely. The loop is still repaired: FR-1's legacy reader ships unflagged and fixes
every link the app emits in the OFF state. **The flag never being flipped costs the
product nothing that P0-3 promised.** That asymmetry is the reason the emitter is flagged
and the parsers are not.

---

## 5. Non-goals

Each of these was considered and deliberately excluded. They are recorded so nobody
re-opens them mid-build or reads their absence as an oversight.

1. **Deferred deep linking for a recipient who does not have the app.**
   The full unhappy path is: tap link → no app → App Store → install → open → **the invite
   is gone**. iOS provides **no** mechanism to carry a pre-install link into a post-install
   launch. Solving it requires a third-party attribution SDK (Branch, AppsFlyer, Adjust),
   which means a new native dependency, a new privacy-manifest entry, an SDK that
   fingerprints devices to do its job, and a native rebuild — in a *Bug, effort S* item on
   a P0 remediation branch. **This is known-unsolvable within the constraints and is stated
   as a limitation, not deferred as a task.** What the 302 does cover is the case web
   already converts: tap in Safari, sign in on the web, land in the league.
2. **A new web landing page for the join path.** The 302 into `/?league=&ref=` reuses a
   funnel that demonstrably works. A new page would be new JS on the highest-stakes
   pre-auth surface, for no gain.
3. **Cross-platform invites.** An ESPN/MFL/Fleaflicker league's invitee gets no resolvable
   name and, if the id is not in their Sleeper list, the not-member notice. Honest, no dead
   end, no pin. A platform-agnostic league identity does not exist and is not being built
   here.
4. **Any change to `web/`.** NFR-2.
5. **Retiring the legacy URL format.** NFR-1 — parsed forever, no sunset, no deprecation
   warning.
6. **Graduating into `growth.referral`** (the give-get program, OFF). Out of scope; the
   four event names are chosen so it could build on them later.
7. **Flipping any flag default in this build.** HLD S-44.
8. **A rate limit on `invite-meta`.** It proxies data Sleeper already serves publicly and
   unauthenticated, stores nothing, and has no user id to limit against. Recorded as a
   decision (LLD §1.3), not an omission.
9. **`invite_shared` from the League tab.** `LeagueScreen.tsx` belongs to W2-P07 in this
   batch (HLD §10.2), so half the invite volume stays unmeasured after this build. →
   `NEXT.md`.
10. **Match accept/decline, `/api/sleeper/propose`'s `is_linked_platform_league` guard, and
    `find_trades_tapped`'s prop allowlist.** Other findings' `NEXT.md` rows; listed here
    only because they surfaced during P0-3's reads.

---

## 6. Docs rows

**Owner: `W3-DOCS` (commit 14) for every row.** No build agent edits a `docs/` or
`living-memory/` file (HLD §4 Wave 3). W2-P03 and W1-BE supply the content below through
their scope blocks.

| Doc | Row | Source |
|---|---|---|
| `docs/api-reference.md` | **New row** — `GET /api/league/invite-meta?league_id=<id>` in the League section: public, unauthenticated, read-only; `{league_id, league_name, platform}`; **Sleeper public API only, never the `leagues` table** (imported-league names are not enumerable by id); degrades to `league_name: null` on any failure; `400 missing_league_id` is the only non-200. | W1-BE |
| `docs/api-reference.md` | **New row** — `GET /app/league/join/<league_id>` in the share/static section beside `/s/trade/<match_id>` (`:545`): 302 → `/?league=<id>[&ref=]`, unflagged, relative `Location`, unknown params dropped, hostile ids URL-encoded. Note that iOS resolves AASA **before** any HTTP request, so an installed device never reaches it. | W1-BE |
| `docs/api-reference.md` | **Amend the AASA row at `:587`** — it enumerates the claimed paths (`/u/*`, `/s/*`, `/?ref=*`, `/?league=*`) and becomes wrong the moment the claim lands. Add `/app/league/join/*`, and state that `/app/*` is deliberately **not** claimed even though the mobile route table owns several `app/...` paths. | W1-BE |
| `docs/config-reference.md` | **New flag row** — `growth.invite_join_link` | false | "P0-3 invite deep link, **emitter only**: on, `buildInviteUrl` emits `/app/league/join/<id>?ref=<u>`; off (default), today's `/?league=<id>&ref=<u>`. Never gates the `?league=` reader, the `LeagueJoin` route, the AASA claim or the 302. **Graduation:** live AASA validated externally + ≥24h CDN propagation + a post-deploy install proves a tapped link opens the app (`docs/runbook.md` § AASA)." | W1-BE |
| `docs/cross-client-invariants.md` | The invite URL is a **two-client contract**: mobile emits, web + mobile parse. Record **both** accepted forms and the rule that `/?league=&ref=` is parsed **forever**. Add the four invite event names to the client-analytics-contract section (`:268`) with the note that web and the extension fire none of them. | W2-P03 |
| `docs/runbook.md` | Extend the AASA section (`:410-412`) with §4's seven-step sequence, verbatim, including the "if steps 2-5 fail, leave the flag OFF indefinitely" instruction and the reason it costs nothing. | W1-BE |
| `docs/glossary.md` | **invite intent** — the persisted `{leagueId, invitedBy, leagueName, ts}` blob (`ftf_invite_intent`, 14-day TTL) captured from an invite link and awaiting a pin; consumed on pin, cleared on sign-out. | W2-P03 |
| `living-memory/LLD.md` | Convention: **deep-link destinations reachable while signed out belong on the root stack, never inside `Main`** — a link resolving into `Main` drops a session-less user into empty tabs. Second: `buildInviteUrl`-style shared emitters read flags **imperatively** (`useFeatureFlags.getState()`) so multiple call sites cannot drift. | W2-P03 |
| `living-memory/DECISIONS.md` | **D-027** (id per HLD §7) — legacy `/?league=` parsed forever; a 302 into the existing web landing rather than a new page; a 14-day persisted invite intent instead of `invitedBy`'s in-memory-only lifetime. | W2-P03 |
| `living-memory/NEXT.md` | `invite_shared` is not fired from the League tab's Invite module (`LeagueScreen.tsx` `inviteLeaguemates`) — half the invite volume is unmeasured. | W2-P03 |
| `living-memory/CHANGELOG.md` | At ship: the invite loop is repaired on mobile for **every link already shared**; the new path format stays dark behind `growth.invite_join_link` pending AASA verification. | W3-DOCS |
| `docs/architecture.md` · `living-memory/HLD.md` | **n/a** — no module wiring or data-flow change: one screen, one parser branch, two read-only routes. | — |
| `docs/data-dictionary.md` | **n/a** — no schema change. `ftf_invite_intent` is client-side AsyncStorage. | — |
| `living-memory/DEPENDENCIES.md` | **n/a** — nothing added, bumped or removed. | — |
| `docs/business/analytics/2026-08-11-p0-7-addendum.md` | The four invite names + the note that `invite_shared` had been firing into a default-deny wall since it shipped. **Owned by W0-TAX**, not W3-DOCS — it is the registry's stated precondition. | W0-TAX |

---

## 7. Rollback, per half

The two halves fail independently and roll back independently. That separation is the
design's main safety property.

### Server half (commit 3)

| Surface | Rollback | Cost |
|---|---|---|
| `growth.invite_join_link` | **Flip to `false` in `config/features.json`** and reload. No deploy of code, no app release. | **Zero.** Invites revert to the legacy URL, which both clients still parse. This is the primary lever and the reason the flag exists. |
| `GET /app/league/join/<id>` (302) | Revert the route. | Near-zero: with the flag OFF nothing emits that URL, so nothing links to it. If the flag was ON, revert the flag **first** — otherwise emitted links 404 in Safari for non-app users. |
| `GET /api/league/invite-meta` | Revert the route. | Zero UX: the client's `fetchInviteMeta` swallows every failure and the banner degrades to "their league". The acceptance criterion still holds. |
| AASA claim | Revert the two list entries. | **Slow, and asymmetric — this is the one to think about before flipping the flag.** Removing the claim is subject to the same ~24h CDN lag as adding it, so devices keep opening the app on `/app/league/join/...` for up to a day after the revert. Since the app parses that path regardless, the behaviour during that window is *correct*, just no longer intended. **Sequence: flag OFF first, then AASA, never the reverse.** |
| Flag registration | Revert `feature_flags.py` + both JSON files together. | Zero. Never revert the JSON without `FLAG_KEYS` — the features-json-keys-known guard fails on an unknown key. |
| The whole commit | `git revert` commit 3. | Clean: it is additive routes plus one default-OFF flag. The two AASA test updates (LLD §1.6) revert with it. |

### Client half (commit 12)

| Surface | Rollback | Cost |
|---|---|---|
| The emitter's new format | **Flag OFF** — same lever as above, no client release. | Zero. |
| `?league=` reader (FR-1) | **Requires an app release to remove.** It is unflagged by decision (HLD S-13). | Its OFF state *is* the bug. It ships unflagged precisely so it cannot be turned off by accident. |
| `LeagueJoin` route + screen | Requires an app release. | With the flag OFF, the route is only reachable by a hand-typed URL or the test harness. Effectively dormant until the flag flips. |
| Persisted invite intent | Requires an app release. Stale blobs self-clear via the 14-day TTL sweep at bootstrap and on sign-out. | Bounded by construction. |
| `SignIn` banner | Requires an app release. | Renders only when an invite intent exists, which no smoke path creates. |
| The whole commit | `git revert` commit 12. | Clean **if** commit 13 (P0-7's `surface`-required flip) has not landed on top — it has no interaction with these files, so no conflict is expected. Reverting commit 12 alone leaves commit 3's server routes live and harmless. |

**The failure mode with no rollback**, stated plainly: shipping a build that emits the new
URL while AASA has not propagated. That is exactly what §4's sequence and the default-OFF
flag exist to prevent, and it is why the flag is flipped in a **separate session, after
on-device verification** rather than in this build.

---

## 8. Open items for the operator

1. **Flag graduation is yours, and it is a separate session.** §4 steps 6-7. Nothing in
   this build flips it.
2. **The manual legs cannot be automated** and the acceptance criterion is not fully met
   without them: the real universal-link tap (A-1e), the legacy-link tap cold and warm
   (A-2), the web 302 pass (A-3), and the account-only intersection (A-1d). LLD §4 lists
   each with the reason. They belong in `TEST_LEDGER.md` verbatim.
3. **A recipient without the app still loses the invite on install.** Non-goal 1. If that
   population turns out to matter, the decision to make is "adopt an attribution SDK",
   which is a dependency and privacy decision, not an engineering one.
4. **`invite_shared` was silently dropped since it shipped.** Any historical claim about
   invite conversion — including the audit's "the loop converts zero" — rests on no data.
   Registration (commit 1) is the first time this funnel becomes readable at all, so
   **treat post-ship numbers as a new baseline, not a comparison.**
