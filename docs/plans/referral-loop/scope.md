# Feature Scope — Referral loop v1 (credited, measured league invites)

<!--
Copied from docs/templates/feature-scope.md. Every section answered or explicitly waived.
Full gates: this change writes a table and adds columns, adds two routes, changes three API
contracts, adds flags and analytics events. No express lane was declared, and agents never
self-select it. Requirements: prd.md. Evidence: loop-audit.md.
-->

**Date:** 2026-10-15
**Entry point:** direct ask: operator 2026-10-15 via `head-product` ("Growth loops. Need to be built and need to work. Referral growth loop is the primary one, …"); growth backlog GB-01
**Builder:** TBD — `head-eng` allocates (likely `engagement-eng` backend + invite routes, `onboarding-eng` for web/LeagueJoin/SignIn)
**Operator sign-off on waivers:** pending (one waiver: §3 has no automated runtime proof of the universal-link tap or the TestFlight install; the operator checklist is the only runtime evidence, per D-056)

---

## 1. Analytics scope

- [x] **(a) New events specced.** Names and classes are proposals; `analytics-lead` owns the
  final taxonomy and registers + classifies each in the same commit as (or before) its
  emitter (D-040). No prop key may contain `token`: ingest drops it silently
  (`backend/analytics_ingest.py:160, :195`), so the id travels as `invite_id`.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `invite_landing_opened` (new, NON_INTENT) | `invite_id`?, `league_id`, `token_status`, `device_class` | Human GET of `/app/league/join/<id>` with the ledger flag on (PRD FR-8) | server; owner = referrer, else `system:invite`; non-touching write |
  | `invite_landing_cta` (new, NON_INTENT) | `invite_id`?, `league_id`, `cta`, `device_class` | Landing click-through `/app/league/join/<id>/go/<cta>` | server; same owner rule |
  | `referral_attributed` (new, NON_INTENT) | `invite_id`, `referral_id`, `league_id`, `attribution_method`, `referred_user_id`, `league_platform`, `notified` | Ledger credit at a new user's first session (PRD §7.4/§7.5) | server; owner = referrer; non-touching write |
  | `referral_activated` (new, NON_INTENT) | `invite_id`, `referral_id`, `league_id`, `days_to_activate`, `notified` | Invitee's first `trades_generated` with `count ≥ 1` within 14 days (PRD FR-17) | server; owner = referrer; non-touching write |
  | `signup` (changed props) | + `attribution` (`token\|league_match\|legacy_ref\|none`), `attribution_miss` (`unknown\|expired\|not_member\|null`) | First session | server; owner = new user |
  | `invite_shared` (changed props, new web emitter) | + `invite_id`?, `mint_outcome` | Share sheet not dismissed | mobile, web |
  | `invite_cta_tapped` (new web emitter) | `surface` gains `web_invite` | Invite tap | mobile, web |
  | `invite_cta_shown` (new emitters) | unchanged | Mount of Trades banner, members overlay, web modal | mobile, web |
  | `invite_link_opened` (changed props, new web emitter) | + `invite_id`?; `format` gains `web` | Invite URL parsed | mobile, web |
  | `invite_league_pinned` (changed props, new web emitter) | + `invite_id`?; `source` gains `web_autoselect` | Invited league becomes active | mobile, web |
  | `invite_pin_failed` (changed props, new web emitter) | + `invite_id`? | Intent can't be honoured | mobile, web |

  Proposed, not committed: `channel` on `invite_shared` and first-touch props on `signup`
  (marketing-lead wave 2 §C, pending `analytics-lead`, P18).

  → follow-through: tracking-plan addendum under `docs/business/analytics/` (owner
  `analytics-lead`); `docs/cross-client-invariants.md` § Client analytics event contract (web
  now emits the invite names); `docs/data-dictionary.md` for the stored ledger columns (§2).
- [ ] (b) Existing events cover it — no: the server open, the attribution and the activation
  have no event today (loop-audit H3a, H5, H6).
- [ ] (c) Waived — no.

## 2. Schema & flag scope

- **New/changed tables or columns:** `referrals` gains `share_token` (indexed), `surface`,
  `opened_at`, `last_opened_at`, `open_count` (`server_default 0`), `unfurled_at`,
  `attribution_method`; new index `ix_referrals_league_status (league_id, status)`
  (PRD §9). Migration through `_migrate_db` `migration_cols` (`backend/database.py:3345-3360`)
  plus explicit `CREATE INDEX IF NOT EXISTS`. Data rights: deletion and export cover the new
  columns; export omits `share_token` with `invite_token` (`backend/accounts.py:829-838,
  :1043-1044`). No change to `users`. → `docs/data-dictionary.md` § `referrals`.
- **New/changed feature flags:**
  - `growth.referral_ledger` — **new**, default **false**. Gates the mint route, clients'
    use of the id, open recording, attribution, activation, the new notification rules and
    impact v2. Graduation: Phase 0 done + 2 weeks with ≥95% of invite-following signups
    carrying a ledger row (PRD §2.1). Deploy-free rollback: flip off.
  - `growth.join_landing` — **new (proposed by this PRD; `growth-pm`/`head-product` to
    accept, PRD D-7)**, default **false**. Landing vs today's 302. Graduation: words approved,
    `design-lead` `/design-review` verdict (`design-review.md`), operator device pass.
    Rollback: flip off (T4–T7 contract).
  - `growth.invite_join_link` — existing, **flipped during Phase 1 rollout** after the #239
    device checklist passes; meaning unchanged.
  - `growth.referral` — existing, **untouched, reserved** for rewards (Phase 3).
  - `invite.k_factor_dashboard` — existing, key kept; payload changes when on (PRD §8.5).
  → `config/features.json` + `backend/feature_flags.py` `FLAG_KEYS` +
  `backend/tests/fixtures/flags/release.json` together; `docs/config-reference.md`.
- **New env vars / `model_config` keys:** `IOS_INSTALL_URL` (unset by default): the
  landing's iOS install target (public TestFlight link under option A; App Store URL after
  the listing). Unset ⇒ the honest note instead of a button. Deploy-free lever: unset it.
  → `docs/config-reference.md` § Environment variables.

## 3. Evidence scope

D-056: no Maestro, no simulator, no captures.

- [x] **Structural guard:** `mobile/tests/check-invite-links.js` (new; dependency-free; add
  `"test:invite-links": "node tests/check-invite-links.js"` to `mobile/package.json`; CI runs
  every `check-*.js`, `.github/workflows/ci.yml:47`). Pins:
  1. `buildInviteUrl`'s 2×2×2 matrix (ledger flag × join-link flag × id present/absent)
     against PRD §7.2, byte for byte; flag-off rows identical to today's.
  2. No flag-on URL contains `ref=`.
  3. `shareInvite` event order: `invite_cta_tapped` → mint call → `Share.share` →
     `invite_shared`, and `invite_shared` only on a non-dismissed result, carrying
     `invite_id` (when minted) and `mint_outcome`.
  4. No invite share text contains "Dynasty Trade Finder" or "Fantasy Trade Finder".
  5. Every session-init body builder (two Sleeper in `api/auth.ts`, ESPN in `api/espn.ts`,
     MFL/Fleaflicker in `api/platformLink.ts`) includes `invite_id`.
  6. No invite event prop key contains `token`.
  Also extend `mobile/tests/check-notif-glyphs.js` for `referral_activated` (glyph +
  `V2_LEAGUE_KINDS` membership). Web: extend `qa/web/check_web_structure.py` (CI) to assert
  the web invite builder never emits `ref=` with an id, and `captureReferralFromUrl` stores
  `t`.
- [x] **Unit tests (backend pytest):**
  - `backend/tests/test_referral_mint.py` (new): flag off → 404; 201 shape; `invalid_surface`;
    demo/unverified → 403; non-member → 403; 11th mint per league per UTC day → 429, next day
    resets; row written as specced.
  - `backend/tests/test_join_landing.py` (new): flag off → T4–T7 behaviour unchanged, plus `t`
    forwarded only with the ledger flag on; flag on → 200, `noindex`, absolute `og:image`,
    league name, inviter display name from a valid id, no query-string username echoed;
    page links `/css/tokens.css` and none of the `_share_html` chrome (PRD AC-7e);
    iPhone/Android/desktop CTA variants with `IOS_INSTALL_URL` set and unset, one primary
    action each, no button on Android or on iPhone with it unset (PRD AC-7c); human UA
    increments `open_count` + fires `invite_landing_opened`; preview UA sets only
    `unfurled_at`; HEAD records nothing; unknown/expired ids; click-through closed set and
    targets (no user-supplied redirect).
  - `backend/tests/test_referral_attribution.py` (new): token credit for Sleeper, ESPN and MFL
    invitees; first session in a different league with verified membership; `unknown`,
    `expired`, `not_member` misses; group-chat second and third joiners → sibling rows;
    league-match picks most recent open, legacy-ref tie-break, >14-day open ignored; existing
    user → no credit; legacy `invited_by` alone → no row, no bell row; `users.invited_by`
    written from the ledger; `signup` props per case; repeat session init idempotent; inviter
    `users.last_active_at` unchanged by inviter-owned events; FR-20 dedupe.
  - `backend/tests/test_referral_activation.py` (new): `count ≥ 1` within 14 days → activated
    once + `referral_activated` + inbox row; outside 14 days, `count = 0`, second
    `trades_generated` → no-op; both emitters covered.
  - `backend/tests/test_invite_impact.py` (new): v2 payload from the ledger; flag off →
    today's zeroed payload.
  - Updated: `test_invite_links.py` (T4–T7 under `growth.join_landing` off, unmodified
    assertions; T12-style registration for the new flags), `test_notif_inbox_growth.py`
    (`referral_activated` type; title ≠ body), `test_account_deletion_coverage.py` and
    `test_account_data_rights.py` (new columns), the taxonomy registration tests (new names
    registered, NON_INTENT, namespaces disjoint).
- [x] **Code-walk proof** (written by the builder into `docs/plans/referral-loop/code-walk.md`,
  file:line-cited at the build sha), covering what tests can't reach:
  1. Inviter: each of the six surfaces → `shareInvite` / `shareVia` → mint → link → sheet.
  2. Installed invitee: universal link → `handleDeepLink` / `LeagueJoinScreen` → intent with
     `inviteId` → SignIn banner via `invite-meta?t=` → auto-pin → session-init body carries
     `invite_id` → daemon attribution.
  3. Account-only invitee: companion state keeps `inviteId` across a platform link.
  4. Web: landing → click-through → `captureReferralFromUrl` → extension sign-in → auto-select
     → session init with `invite_id`.
  5. The intent's `inviteId` survives `consumeInvitedLeague` (pin) until a body consumes it.
- [x] **Manual TestFlight checklist** (operator; the only runtime evidence mobile gets).
  Preconditions: backend deployed with `growth.referral_ledger` on; a TestFlight build with
  the client change; a second test device or account that is a member of the test league;
  `IOS_INSTALL_URL` set if option A. Record each step's outcome in `TEST_LEDGER.md`.
  1. **Inviter mint.** On device A (signed in, Sleeper league L), tap Invite on League Home.
     Expected: the sheet opens within ~2 s; the message says "Fleeced" and the link has
     `t=` and **no `ref=`**.
  2. **Preview does not count as an open.** Send the link to yourself in Messages; wait for
     the preview to render; don't tap. Expected: the admin/readout shows `unfurled_at` set
     and `open_count` = 0 for that id.
  3. **Not installed (iPhone).** On device B with the app deleted, tap the link from Messages.
     Expected: Safari shows the join landing with L's name, the inviter's display name, "Get
     the iOS beta" (A) or the honest note (unset), and the re-tap line; `open_count` = 1.
  4. **Install + re-tap.** Install via TestFlight, return to Messages, tap the link again.
     Expected: the app opens on LeagueJoin → SignIn naming the inviter; after sign-in, L is
     pinned; device A's bell gets **one** "joined via your invite" row (title and body
     different) and no second row for the same join.
  5. **Install, no re-tap (league match).** Repeat 3 with a fresh account on device B; after
     installing, open the app from the home screen (not the link), sign in, pick L.
     Expected: the readout shows the join with `attribution_method = league_match`.
  6. **Installed + signed out.** With the app installed and signed out, tap a fresh link.
     Expected: the app opens (not Safari) on SignIn with the inviter named.
  7. **Installed + signed in, member of L (existing user).** Tap a fresh link. Expected: L
     becomes active; **no** bell row for device A; no ledger credit.
  8. **Non-Sleeper invitee.** Mint from an ESPN (or MFL) league; on device B, tap, install,
     link the same ESPN league in the app. Expected: credited by token; device A gets the row.
  9. **Expired id.** Use an id older than 30 days (backdated in a staging DB, or a test
     fixture id supplied by the builder). Expected: the landing renders without the inviter
     name, with a neutral headline (not error red); signing up gives no credit;
     `signup.attribution_miss = expired`.
  10. **Flag off.** Flip `growth.referral_ledger` off and reload flags; tap Invite on device A.
      Expected: the link is today's `/?league=…&ref=…` form (or path form if
      `growth.invite_join_link` is on), byte-identical to before the build. Flip
      `growth.join_landing` off and open a path-form link in Safari. Expected: today's 302 to
      `/?league=…`.
  11. **Desktop.** Open a fresh link on a desktop browser with the extension installed.
      Expected: landing shows "Open the web app" and the extension line; sign in; L is
      auto-selected; credited by token.
  12. **Android.** Open a fresh link on an Android phone. Expected: the honest note, **no**
      web button; `open_count` increments.
  13. **Activation.** On device B (credited in step 4), generate trade suggestions in L.
      Expected: device A gets one activation row that routes to League.
  14. **Group chat.** Post one link into a chat with two test invitees; both join. Expected:
      two ledger rows sharing the same `share_token`; device A gets one row per joiner.
  15. **Landing primary action per device** (PRD FR-7 design rules). Open a fresh link on each
      device and check there is exactly one ice primary action. iPhone with `IOS_INSTALL_URL`
      set: "Get the iOS beta" is the ice button; "Open in the app" is outlined, not filled.
      iPhone with it unset, and Android: no button; the note is readable (not the faintest
      grey). Desktop: "Open the web app" is the ice button, the extension line is dimmer, the
      iOS link is plain text. On every device the page is dark, says "Fleeced", and buttons
      are comfortably tappable; on desktop, Tab shows the ice focus ring. There is no
      "already joined" landing state (no auth, and one link can credit several joiners); an
      existing user is step 7, in the app.
- [x] **Design review** (`design-lead`): a `/design-review` verdict at
  `docs/plans/referral-loop/design-review.md` before ship, covering the join landing (per-device
  states, PRD FR-7), the OG card, and the invite card/banner diff (copy and events only, no
  visual change). Every string stays with `marketing-lead`; the mockup lab
  (`mockup/referral-loop`) tags each PROPOSED COPY. The landing's before-pane is today's 302 to
  `/` (the web landing), a labelled reconstruction until `head-product` rules on web
  before-panes (W2).
- [ ] **WAIVED because:** — (no waiver of the rows above; the waiver noted in the header is
  only that the universal-link tap and TestFlight install have no automated proof).
- `testID`s added/renamed: none planned; any added by the builder must pass
  `mobile/scripts/testid-lint.sh`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **yes** | New `POST /api/invite/token`; `GET /app/league/join/<league_id>` (landing vs 302, `t` forwarding, open recording) and the new `/go/<cta>` click-through; `GET /api/league/invite-meta` (`t`, `inviter_display_name`, `token_status`); `POST /api/session/init` (`invite_id`); `GET /api/invite/impact` (v2 payload, `k_factor` removed) |
| `docs/data-dictionary.md` | **yes** | § `referrals`: new columns, index, status values in use, `league_id` any platform, writer named |
| `docs/config-reference.md` | **yes** | `growth.referral_ledger`, `growth.join_landing` (new); `growth.invite_join_link` flip note; `growth.referral` reserved; `invite.k_factor_dashboard` meaning; `IOS_INSTALL_URL` env var |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **yes** | Inviter-owned server events use a non-touching write (no `last_active_at` bump); no analytics prop key contains `token`; per-share ids in links, never usernames |
| `docs/architecture.md` (module wiring / data flow changed) | **yes** | The referral ledger data flow: mint → link → landing open → session-init attribution → activation → notifications |
| `living-memory/HLD.md` (architecture genuinely shifted) | **yes** | A new server-rendered pre-auth surface (the join landing) and the first writer of `referrals` |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **yes** | Invite URL format: the `t` param and the flag matrix; legacy still parsed forever; `InviteSurface` gains `web_invite`; notification type `referral_activated` (glyph, route); web emits the invite events |
| `docs/glossary.md` (new domain term) | **yes** | invite id; referral ledger; attribution method (token / league match); referral activated; loop coefficient `K_30` (distinct from the Elo K-factor, `docs/glossary.md:29`) |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **yes** | New D-entry superseding D-028 part 2 (a join page replaces the 302 into `/`); per-share ids replace usernames in links; league-match fallback instead of an attribution SDK |
| `docs/runbook.md` | **yes** | Rollout sequence (PRD §12) next to § Universal Links AASA; how to set/unset `IOS_INSTALL_URL` |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (which also runs the `check-*.js`
  suites, including the new `check-invite-links.js`) + `web-structure` +
  `maestro-testid-lint` (the testID lint job) — all passing on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the pytest files, the
  structural guard, the code-walk, and the `FTF_SKIP_SIM_GATE=1` posture (D-056).
- **Design review:** `design-lead`'s `/design-review` verdict recorded at
  `docs/plans/referral-loop/design-review.md` before ship (§3).
- **TestFlight verification:** the §3 checklist run by the operator before rollout steps 4–6
  (PRD §12); outcome logged in `TEST_LEDGER.md`.
- Express lane declared by the operator? **no** — full gates.
