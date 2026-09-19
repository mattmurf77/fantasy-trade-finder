# Auth + Multi-Platform Plan (2026-06-11, rev. 2026-06-23)

*Strategic + technical plan for two investments the operator has prioritized: (A) third-party identity/authentication and (B) multi-platform league support (ESPN, then MFL). Grounded in branch `trade-engine-v2` as of 2026-06-13. This is a planning doc — no code changes. Companion reading: [competitor-feature-backlog-2026-06-11.md](competitor-feature-backlog-2026-06-11.md), [competitor-teardown-web-tools.md](../competitor-teardown-web-tools.md), [../architecture.md](../architecture.md), [../data-dictionary.md](../data-dictionary.md).*

> **Rev. 2026-06-23 (operator direction change).** Two scope changes from review: (1) providers are now **Apple, Google, Discord, and X (Twitter)** — not Apple+Google only; (2) the onboarding model is **inverted from auth-first to Sleeper-first**: users still start the experience with Sleeper exactly as today, and are *prompted to save their account* via a provider at three moments — after Sleeper login, after finishing the minimum tier ranks for any position, and upon opening the Trade feature. Auth never blocks the core loop. See "Sleeper-first progressive auth (the three prompts)" and the revised Phase 1. Line-number citations are from the 2026-06-13 grounding and have drifted slightly; anchors re-verified 2026-06-23 where noted.
>
> **Rev. 2026-07-02 (new: in-app Sleeper trade creation — see [Part C](#part-c--in-app-sleeper-trade-creation-the-sign-in-with-sleeper-provider)).** A competitor ships **in-app Sleeper trade creation** — sending a proposed trade straight into the user's Sleeper league — which this plan previously treated as impossible. It *is* possible, via Sleeper's **undocumented authenticated GraphQL API** (the same one Sleeper's own app uses), unlocked by a real **Sleeper login** (not just a username). That makes Sleeper a **5th auth provider — the strongest one**, because it's the only one that also carries a write capability (one-tap "send to Sleeper"). This is likely the single highest-value feature in the app. Researched 2026-07-02; the exact login-token flow and trade mutation are undocumented and must be captured live (Spikes C1/C2 below). **Honest correction:** the earlier "Sleeper has no write API" statement is true only of the *public* `api.sleeper.app/v1` REST API; the *private* GraphQL is a different surface.

---

## Executive summary

**What.** Three structural investments. (A) Add real identity via **Sign in with Apple, Google, Discord, and X (Twitter)** through Expo — so FTF never stores passwords and never owns the identity primitive. Identity is layered **progressively**: users still start with Sleeper as today, then get prompted to *save their account* with a provider at three defined moments (post-Sleeper-login, first rankings-established, first Trades open). (B) Add **multi-platform league ingestion** behind a single `PlatformAdapter` interface, with **ESPN first** (largest TAM, but unofficial cookie-based API) and **MFL second** (smaller, but an official documented API). Both fold into FTF's existing Sleeper-keyed internal model. **(C) [Rev 2026-07-02] In-app Sleeper trade creation** via Sleeper's undocumented authenticated GraphQL — a real "Sign in with Sleeper" login (the **5th, write-capable auth provider**) that lets users send proposed trades straight into their league. Likely the app's most valuable feature; sequence it as the flagship right after (A).

**Why now.** The entire current stack conflates *identity* with *Sleeper username*: `users_table`'s primary key is literally `sleeper_user_id` ([database.py:54](../../backend/database.py)), sessions are minted off a Sleeper username lookup ([server.py extension_auth](../../backend/server.py)), and there is no account that exists independently of a Sleeper handle. That assumption blocks both goals — you cannot link an ESPN or MFL league to "a user" because today a user *is* a Sleeper id. The operator's own backlog parks Yahoo (#68) and a multi-platform hub (#69) as "horizon" items precisely because "the entire current stack assumption is Sleeper-only." Auth is the unlock: once identity is decoupled, platforms become *linked data sources* hanging off one account.

**The big architectural shift.** Today: `Sleeper username → user_id → everything`. Target: `FTF account (opaque provider subject) → {linked Sleeper id, linked ESPN league creds, linked MFL franchise} → everything`. Identity becomes an Apple/Google subject id + optional email. Sleeper, ESPN, and MFL all become **linked sources** under that account, each contributing leagues/rosters that normalize into FTF's existing internal model. Sleeper player_ids remain FTF's canonical key space; ESPN/MFL ids get cross-walked onto them via the name-normalization layer the engine already runs for DynastyProcess values. This is the one-way door — everything in Parts A and B depends on getting the account/identity split right, so it ships first.

---

## Part A — Identity & Authentication

### Current state (grounded)

Identity today *is* a Sleeper user id. The chain:

- **Login.** The web/mobile/extension clients resolve a Sleeper *username* to a Sleeper *user_id* via `GET /api/sleeper/user/<username>` ([server.py:4866](../../backend/server.py)) or `POST /api/extension/auth` ([server.py:7030](../../backend/server.py)). There is no password, no provider, no verification of *who the human is* — anyone who types a valid Sleeper username gets a session as that user. (Test bypasses, state as of 2026-06-23: `test_user_fp_*` skips Sleeper on the **committed** branches with no prod gate, and hardcoded `User1`..`User5` seeded test-league logins are **live in prod** — PRs #89/#90. The `_IS_PROD_ENV` gate that disables `test_user_fp_*` in prod exists only in uncommitted WIP. Reconcile all test bypasses when real auth lands — they become the "impersonation surface" this plan closes.)
- **Sessions.** Purely in-memory: `_sessions: dict[str, dict]` keyed by an opaque `secrets.token_urlsafe(32)` token ([server.py:863](../../backend/server.py), minted in `session_init` at [server.py:5505](../../backend/server.py)). `_require_session()` ([server.py:928](../../backend/server.py)) reads the `X-Session-Token` header and looks the dict up. **Sessions are not persisted** — a server restart logs everyone out, and there is no refresh/expiry beyond the informational `expires_at = last_active + 4h` returned by the extension route. The mobile app stores the token in expo-secure-store and re-inits on launch.
- **Identity record.** `users_table` PK = `sleeper_user_id` ([database.py:53](../../backend/database.py)). Every downstream table (`leagues`, `league_members`, `member_rankings`, `trade_matches`, `swipe_decisions`, `draft_picks.owner_user_id`) foreign-keys to that Sleeper id by convention (no DB-level FKs; enforced in code). `invited_by` even stores a *Sleeper username*.

So "account recovery," "multiple devices," "same human, two Sleeper accounts," and "a human with no Sleeper account at all" are all currently unrepresentable.

### Target model

- **The FTF account is the identity.** A new `accounts` row, PK = opaque internal `account_id` (uuid). The human authenticates with **Apple, Google, Discord, or X (Twitter)**; FTF stores only the **provider subject id** (`sub` / provider user id) + **email** (optional — may be a private Apple relay address; X does not return email at standard API access; Discord email may be unverified). No passwords, ever. This is exactly the operator's stated intent: "Auth should ideally rely on existing auth patterns (Apple, Google, etc.) so that I don't have to handle authentication/identity myself."
- **Providers, plural, per account.** One account can link any subset of the four providers. Identity lookup is `(provider, subject) → account_id`.
- **Sleeper-first, auth-second (operator decision, 2026-06-23).** Sleeper stays the front door — the sign-in screen keeps the Sleeper-username entry exactly as today, and the session keeps working with **no account at all**. The account is created lazily, the first time the user accepts a **"save your account"** prompt (three defined triggers, below). Auth is an upsell that protects their data (rankings, tiers, matches survive device loss; multi-device sync; recovery), never a wall in front of the product. A secondary "Already saved your account? Sign in" path on the sign-in screen serves returning users on a fresh device.
- **Sleeper becomes a linked source, not the identity.** On an account, "I am Sleeper user `mattmurf77`" becomes a row in a `linked_sources` table, not the primary key. The same table later holds ESPN and MFL links (Part B).
- **Apple-required-on-iOS rule (hard constraint).** App Store **Guideline 4.8** requires that any app offering a third-party/social login (Google, Discord, and X all count) for account setup **must also offer an equivalent privacy-preserving login service** that (1) limits data to name + email, (2) lets the user keep email private, (3) doesn't collect in-app activity for ads without consent. **Sign in with Apple satisfies all three** and is the de-facto safe choice. The 2024 revision softened "must offer Sign in with Apple specifically" to "must offer *an* equivalent privacy option," but SiwA remains the only turnkey one. **Decision: Apple ships in the same release as any other provider — never ship Google/Discord/X without it.** (The progressive-prompt model doesn't exempt us: the prompts ARE account setup.) ([Apple 4.8](https://developer.apple.com/app-store/review/guidelines/), [9to5Mac 2024](https://9to5mac.com/2024/01/27/sign-in-with-apple-rules-app-store/))
- **Email is optional and never the key.** Apple users can hide their email (relay address) or withhold it after first authorization (Apple only returns name/email on the *first* authorization). The account key is always `(provider, sub)`, never email.

### Data model changes

New tables (additive; existing tables keep working through a compatibility shim during migration):

```
accounts
  account_id        TEXT PK         -- internal uuid
  primary_email     TEXT NULL       -- may be an Apple relay address; nullable
  display_name      TEXT NULL
  created_at        TEXT
  last_login_at     TEXT

auth_identities                      -- one row per linked provider
  id                INTEGER PK
  account_id        TEXT  -> accounts.account_id
  provider          TEXT            -- 'apple' | 'google' | 'discord' | 'twitter'
  subject           TEXT            -- provider 'sub' claim / user id (opaque, stable)
  email             TEXT NULL       -- email as seen from this provider
  created_at        TEXT
  UNIQUE(provider, subject)

linked_sources                       -- replaces "Sleeper id == identity"
  id                INTEGER PK
  account_id        TEXT  -> accounts.account_id
  platform          TEXT            -- 'sleeper' | 'espn' | 'mfl'
  source_user_id    TEXT            -- Sleeper user_id / ESPN SWID / MFL franchise owner id
  source_username   TEXT NULL
  credentials_ref   TEXT NULL       -- pointer to encrypted creds (see Cross-cutting), NOT plaintext
  linked_at         TEXT
  UNIQUE(account_id, platform, source_user_id)
```

**How `users_table` relates.** Two viable paths; **recommend Path 1** for surgical migration:

- **Path 1 (keep `sleeper_user_id` as the working key, add account on top).** `users_table` stays keyed by `sleeper_user_id`. Add a nullable `account_id` column linking each Sleeper-keyed user to its owning account. All the engine/match/ranking tables keep using `sleeper_user_id` unchanged — **zero churn to the trade engine, matches, swipes, draft picks.** The `accounts`/`auth_identities` layer sits *above* the existing model and resolves `account_id → sleeper_user_id` at session creation. For ESPN/MFL-only users (no Sleeper id), mint a **synthetic source key** in the existing namespace (e.g. `ftf:<account_id>`) so downstream tables still have a non-null string user id to hang rows off — the `isdigit()` heuristic already used to distinguish local vs Sleeper leagues ([server.py:4968](../../backend/server.py)) generalizes to "non-numeric == non-Sleeper."
- **Path 2 (re-key everything to `account_id`).** Cleaner long-term, but touches every table and every `_require_session()` consumer (60+ call sites). Reject for now — violates "surgical changes"; revisit only if multi-source-per-account data fusion demands it.

**Migration path for existing Sleeper-keyed users (rev. 2026-06-23 — inverted to Sleeper-first).** The **common path** now runs the other direction: the user already has an active Sleeper session when the account is created. Flow on prompt-acceptance:
1. User is signed in via Sleeper (today's flow, unchanged) and taps a "save your account" prompt → completes Apple/Google/Discord/X auth.
2. Backend verifies the provider token (below), creates `accounts` + `auth_identities` rows.
3. **The Sleeper link is automatic** — the session already knows `sleeper_user_id`, so write the `linked_sources` row and set `users_table.account_id` in the same transaction. No separate "connect Sleeper" step for this path. All historical rankings/matches/swipes for that `sleeper_user_id` are now owned by the account — **no data migration of the heavy tables required.**
4. The session dict gains `account_id`; the token the client holds keeps working (no re-login).

**Fresh-device / returning-user path** (the reason to save at all): "Already saved your account? Sign in" → provider auth → `(provider, sub) → account_id` → load `linked_sources` → auto-restore the Sleeper identity and initialize the session with no username typing. If an authed account has **no** linked source (edge: they saved before ever linking, or unlinked), fall into the source-less `session_init` seed (see "Sleeper-less user journey") instead of erroring.

**Existing token-only sessions** keep working until expiry; nothing forces re-login at rollout.

### Backend changes

- **Token verification, server-side — never trust the client.** Two verification shapes across the four providers:
  - **OIDC providers (Apple, Google, Discord): verify the ID token against provider JWKS.** The app sends the provider's **ID token** (signed JWT) to `POST /api/auth/<provider>`. Backend: (1) fetch the provider JWKS (`https://appleid.apple.com/auth/keys`, `https://www.googleapis.com/oauth2/v3/certs`, `https://discord.com/api/oauth2/keys` — Discord supports OIDC via the `openid` scope), cached with TTL; (2) select by JWT header `kid`, verify the **signature**, validate `iss`, `aud` (FTF's client/bundle id), `exp`, and the `nonce` where the flow supplies one; (3) extract `sub` (+ `email` if present). Only then create/resolve the account. ([Apple JWKS verification](https://medium.com/@meszmate/apple-sign-in-with-expo-golang-complete-2025-guide-to-server-side-oauth-jwt-validation-and-01677dc27e08), [Discord OAuth2](https://discord.com/developers/docs/topics/oauth2))
  - **X (Twitter): no OIDC — server-side code exchange + user fetch.** X is OAuth 2.0 + PKCE only (no id_token). The app sends the **authorization code + code_verifier**; the **backend** performs the token exchange (client secret never on device) and then calls `GET /2/users/me` with the resulting access token — the user id in that response is the verified subject. Never accept a client-supplied X user id or a bare client-held access token as identity. ([X OAuth 2.0 PKCE](https://docs.x.com/resources/fundamentals/authentication/oauth-2-0/authorization-code))
  - This is the load-bearing security property either way: an unverified client-supplied `sub` would let anyone impersonate any account. **Verify cryptographically (JWKS) or transactionally (server-side exchange); never parse-and-trust.**
- **New routes** (`/api/auth/*`):
  - `POST /api/auth/apple` — body `{ identity_token, nonce?, full_name? }` → verifies, upserts account, mints/updates session.
  - `POST /api/auth/google` — body `{ id_token }` → same.
  - `POST /api/auth/discord` — body `{ id_token }` (OIDC `openid identify email` scopes) → same. Fallback if OIDC friction: `{ code, code_verifier, redirect_uri }` server-side exchange + `GET /users/@me`.
  - `POST /api/auth/twitter` — body `{ code, code_verifier, redirect_uri }` → server-side exchange + `GET /2/users/me` → same.
  - **All four routes are dual-mode:** with no session → sign-in (returning user); with a valid `X-Session-Token` for a Sleeper-keyed session → **save/attach** (create account, auto-link the session's `sleeper_user_id`, keep the same session token). This is what the three prompts call.
  - `POST /api/auth/link/sleeper` — authenticated; body `{ username }` → resolves via existing Sleeper lookup, writes `linked_sources` + back-fills `users_table.account_id`. (Used by the fresh-device path when an account has no Sleeper link yet; redundant on the prompt path, where linking is automatic.)
  - `GET /api/auth/me` — returns account + linked identities + linked sources for the session.
  - `POST /api/auth/logout` — drops the session.
- **Session issuance.** Reuse the existing `secrets.token_urlsafe(32)` + `_sessions` mechanism so `_require_session()` and its 60+ consumers don't change — but the session dict now carries `account_id` alongside the resolved `user_id` (the active source key). **Strongly recommend persisting sessions** (a `sessions` table or signed stateless JWT) so a Render restart no longer logs everyone out; today's in-memory store is a latent reliability gap that auth makes more visible (users will expect "stay signed in").
- **Keep the `CRON_SECRET` pattern untouched.** `_require_cron_auth()` ([server.py:6207](../../backend/server.py)) and all `/api/cron/*` + `/api/feedback/admin` + `/api/admin/*` operator routes are orthogonal to user auth and **must not change**. User auth (`X-Session-Token` → account) and operator auth (`X-Cron-Secret`) stay separate axes.

### Mobile changes

- **Expo modules.** Add `expo-apple-authentication` (native SiwA button + token), `expo-auth-session` for **Google, Discord, and X** (all three are standard `expo-auth-session` providers/endpoints; Google can alternatively use `@react-native-google-signin/google-signin` for the native sheet). All managed-workflow compatible; EAS build already in use (ascAppId 6771488431). ([Expo auth docs](https://docs.expo.dev/develop/authentication/), [AppleAuthentication SDK](https://docs.expo.dev/versions/latest/sdk/apple-authentication/))
- **SignInScreen (rev. 2026-06-23 — Sleeper stays primary).** Today [`SignInScreen.tsx`](../../mobile/src/screens/SignInScreen.tsx) is a Sleeper-username text field calling `POST /api/extension/auth`. **That stays the primary path, unchanged.** Add one secondary affordance below it: **"Already saved your account? Sign in"** → opens a provider sheet (Apple button per HIG, Google, Discord, X) for returning users on a fresh device; resolves the account, auto-restores the linked Sleeper identity, lands in the same session flow. New users never see a provider wall.
- **`SaveAccountSheet` (new, the workhorse).** One reusable bottom sheet: value-prop copy ("Don't lose your rankings — save your account"), the four provider buttons, "Not now". On success it calls the dual-mode `/api/auth/<provider>` with the current session token (attach mode), then updates `useSession` with the returned `account`. `useSession` ([useSession.ts](../../mobile/src/state/useSession.ts)) gains an `account` slice above the current Sleeper `user`/`leagues` state; the secure-store token still drives `_require_session`.
- **Web + extension.** Web app gets the same four provider web flows (Apple JS, Google Identity Services, Discord/X OAuth redirects) behind the same "save your account" prompts. The extension's one-shot username auth stays a *Sleeper-link* convenience, re-pointed at an account once one exists.

### Sleeper-first progressive auth (the three prompts)

The account-save prompt fires at exactly **three trigger moments** (operator-specified). All three render the same `SaveAccountSheet`; only the copy varies. Code anchors verified 2026-06-23:

| # | Trigger | Anchor | Copy angle |
|---|---|---|---|
| 1 | **After Sleeper login** — first successful `session_init` for a device with no account | Post-init navigation in the sign-in flow (mobile: where SignInScreen hands off to Main) | "Save your account so your rankings and leagues are safe if you switch phones." |
| 2 | **After finishing minimum tier ranks for any position** — the moment a position first flips to "rankings established" | Client: the `['progress', …]` query transition (per-position established flags from `GET /api/rankings/progress`, [server.py:2265](../../backend/server.py)). Server truth: the `ranking_complete_first_time` event ([server.py:2374](../../backend/server.py)) | "You just built QB rankings — save your account so they're backed up." |
| 3 | **Upon opening the Trade feature** — first mount of TradesScreen | TradesScreen mount effect. **Composition rule:** if the FB4-59 `FormatGate` (single-format error card, shipped PR #88) is showing, defer the prompt until the gate clears — never stack two interrupts. | "Trades found here sync to your account — save it to keep your match history." |

**Prompt discipline (pin these rules; prompt fatigue is the failure mode):**
- Each trigger fires **at most once, ever, per user** — tracked per-trigger. Store client-side (AsyncStorage) *and* server-side (a `user_events` row per prompt shown/dismissed/accepted, so the cap survives reinstalls and syncs across devices).
- "Not now" on any prompt suppresses **that trigger permanently**; remaining triggers still get their one shot. Three lifetime prompts max, then the only path is pull, not push.
- A standing, non-modal entry point lives in **Settings → "Save your account"** (and a subtle badge on the Settings tab while unsaved), so a user who dismissed all three can still convert any time.
- Once an account exists, all three triggers are permanently inert; the Settings row flips to account status (provider badges, "link another provider").
- Never block: every prompt is dismissible, and every feature behind it works identically without an account. The prompts sell durability (backup/recovery/multi-device), not access.
- Instrument the funnel: `auth_prompt_shown` / `auth_prompt_dismissed` / `auth_prompt_accepted` events with `{trigger, provider}` props through the existing `record_event` pipeline — the three-trigger design is a hypothesis; measure which trigger converts.

### Risks / decisions

- **Account recovery.** With no password, recovery = "sign in with the same provider." If a user loses access to their provider account, they lose the FTF account. Acceptable for v1 (industry-standard for social-only auth), but **document it** and consider letting users link a *second* provider as a self-recovery hedge (the `auth_identities` model already supports it).
- **X (Twitter) is the fragile provider — flag it.** X login requires an X developer app; API access tiers/pricing have changed repeatedly and login availability is subject to policy churn; standard access returns **no email**. Ship X **behind a feature flag**, sequence it last, and treat it as droppable without redesign (it's one more row in `auth_identities`, nothing keys on it). Discord is stabler but its email can be unverified — never key on email (already the rule).
- **Prompt-order edge:** a user can hit trigger 2 or 3 in the same session as trigger 1 (rank fast, open Trades early). The per-trigger once-ever cap plus "never stack two interrupts" (also see the FormatGate composition rule) means at most one sheet per screen transition; if two triggers fire simultaneously, the earlier-numbered one consumes the moment and the other stays armed.
- **Multiple providers, same email.** Apple relay emails make email-based account merging unreliable. **Decision: do NOT auto-merge on email.** Treat `(provider, sub)` as the only key; offer an explicit in-app "link another provider" action instead of silent merge. (Silent email-merge is a known account-takeover vector.)
- **Sleeper-username uniqueness no longer guaranteed.** Today the system implicitly assumes one Sleeper id == one human. Post-decoupling, two FTF accounts *could* link the same Sleeper id (e.g. a shared family Sleeper account). `linked_sources` UNIQUE is on `(account_id, platform, source_user_id)`, **not** globally on `source_user_id` — so the same Sleeper id under two accounts is allowed but should be flagged. Decide whether league-mate features (matches, member rankings) key off `account_id` or `sleeper_user_id`; **recommend they stay keyed on the source id** (`sleeper_user_id`) so existing league-mate matching is unaffected, with the account as a presentation-layer overlay.
- **`invited_by` stores a Sleeper username.** Referral attribution ([database.py:64](../../backend/database.py)) is Sleeper-handle-based. Leave as-is for now (referrals predate accounts); revisit if referral lands an ESPN/MFL-only user with no Sleeper handle.

---

## Part B — Multi-Platform League Support

### The core abstraction: `PlatformAdapter`

Every platform feeds the same internal model the trade engine already consumes. Grounded in what `session_init` builds today ([server.py:5189](../../backend/server.py)): a user roster as a **list of player ids**, opponent `LeagueMember`s (`user_id`, `username`, `roster` as player-id list, `elo_ratings`), and league scoring/format metadata (`superflex`/`tep`/teams/scoring → resolved to FTF's `1qb_ppr` | `sf_tep`). The engine does **not** care where rosters came from — only that they're Sleeper-player-id lists in a known scoring format. That's the seam.

```python
class PlatformAdapter(Protocol):
    platform: str                                   # 'sleeper' | 'espn' | 'mfl'

    def list_leagues(self, creds) -> list[LeagueRef]:
        """User's leagues for the season. LeagueRef = {league_id, name, season, total_teams}."""

    def get_league_settings(self, creds, league_id) -> LeagueSettings:
        """Normalized: {superflex: bool, tep: bool, ppr: float, teams: int,
                        roster_positions: [...]} → maps to FTF scoring_format."""

    def get_rosters(self, creds, league_id) -> list[RosterRef]:
        """Per team: {source_user_id, username, player_ids_native: [...]}.
        player_ids_native are PLATFORM ids, not yet Sleeper ids."""

    def get_members(self, creds, league_id) -> list[MemberRef]:
        """{source_user_id, username, display_name} per team."""

    def get_draft_picks(self, creds, league_id) -> list[PickRef] | None:
        """Tradeable future picks if the platform exposes them; None if unsupported."""

    def crosswalk_players(self, player_ids_native) -> dict[str, str | None]:
        """Map native player ids → Sleeper player_ids (FTF canonical). See below."""
```

The existing Sleeper code paths become the **reference `SleeperAdapter`** (a refactor, not a rewrite — `_sleeper_get` + the `/api/sleeper/*` proxy routes already implement every method). `session_init` then consumes `RosterRef`/`MemberRef` regardless of source. **Recommend extracting `SleeperAdapter` first as a no-behavior-change refactor**, so ESPN/MFL slot into a proven interface.

### Player ID cross-walk strategy

**Sleeper player_ids are FTF's canonical key.** The universal pool, all rankings, all `member_rankings`, and the DynastyProcess value join all live in Sleeper-id space. ESPN and MFL emit *their own* player ids, so every non-Sleeper adapter must cross-walk native → Sleeper.

**Current state (grounded — there is NO cross-platform mapping today).** What exists is narrow and single-purpose:
- [`normalise_name()`](../../backend/data_loader.py) (lowercase, strip punctuation/accents, collapse whitespace) — the only normalization primitive.
- [`DP_TO_SLEEPER_NAME`](../../backend/data_loader.py) — a **50-entry, hand-curated, one-direction** table (DynastyProcess name → Sleeper name), built solely for suffix mismatches (DP keeps "Jr./Sr./II/III", Sleeper strips them). Generated once 2026-04-12, manually validated.
- Matching is **"exact normalised name only — no fuzzy fallback"** (the code comment says so).
- `players_table` is **Sleeper-`player_id`-only — zero cross-platform id columns** (`espn_id`/`mfl_id`/`yahoo_id`/`gsis_id` do not exist).

This is fine for joining *one curated CSV by name*; it is **not** a foundation for ESPN/MFL. Name-matching is one-source, one-direction, exact-match, and breaks on exactly the ambiguous cases that matter (the two Josh Allens, Mike Williams ×2, suffix-variant rookies). **The cross-walk must be id-first, with a persisted table.**

- **Primary mechanism: a persisted player-id crosswalk, seeded from the ffverse id map.** ESPN and MFL emit stable numeric player ids, so map by id, not name. Build a `player_id_xwalk` table (Sleeper-id canonical, one row per player with the native ids):
  ```
  player_id_xwalk
    sleeper_id   TEXT PK   -> players_table.player_id (canonical)
    mfl_id       TEXT NULL
    espn_id      TEXT NULL
    yahoo_id     TEXT NULL
    gsis_id      TEXT NULL   -- nflverse anchor; useful for future sources
    fantrax_id   TEXT NULL
    updated_at   TEXT
    INDEX(mfl_id), INDEX(espn_id)
  ```
  **Seed source — the ecosystem FTF already draws from publishes exactly this.** The **nflverse / ffverse `ff_playerids` map** (the same DynastyProcess/`ffscrapr` world the *values* come from) maps `mfl_id ↔ sleeper_id ↔ espn_id ↔ gsis_id ↔ pfr_id ↔ yahoo_id` in a single canonical file — more authoritative and complete than scraping a competitor. Secondary corroboration: **FantasyCalc's and Dynasty Daddy's APIs carry the same id set per player** (verified this session — FantasyCalc returns `sleeperId/mflId/espnId/fleaflickerId/ffpcId`, Dynasty Daddy returns `sleeper_id/mfl_id/espn_id/yahoo_id/ffpc_id/fantrax_id`), usable to fill gaps or validate. A daily/weekly cron refreshes the table (same cadence as values). **Note the gap that forces a new source:** the DynastyProcess values CSV FTF ingests today has only `fp_id` (FantasyPros), **not** MFL/ESPN ids (verified header: `player,pos,team,age,draft_year,ecr_*,value_*,scrape_date,fp_id`) — so the id map is a *new* ingest, not a column already present.
- **Fallback: name-normalization + a real fuzzy layer (new) + a generalized override table.** When a native id misses the crosswalk (brand-new rookie, obscure id), fall back to `normalise_name` against `players_table.full_name`. But note exact-match-after-normalize is **not** fuzzy — ambiguity needs a genuine fuzzy step that does not exist yet (token-sort ratio / bounded edit distance, position+team as tie-breakers, refuse-on-ambiguous). Generalize `DP_TO_SLEEPER_NAME` from a DP-only suffix table into a multi-platform `name_overrides` map (per-source normalized-name → sleeper_id) for the irreducible hand-fixes every platform has.
- **Spike #1 measures coverage against this design.** Run real ESPN + MFL leagues through the id crosswalk and report the *id-match rate* (not name-match) — that number gates viability. Below threshold → multi-platform isn't shippable without heavy per-roster curation.
- **Unmatched handling.** A player that resolves to nothing (rookie not yet in any source, defense/IDP in an unsupported league) is **dropped with a logged warning**, exactly as `session_init` already drops opponent ids not in `players_dict` ([server.py](../../backend/server.py) `if str(x) in players_dict`). For ESPN/MFL, additionally surface a **"N players couldn't be matched"** notice (the partial-coverage UX state from "Sleeper-less user journey"). Picks and IDP are out of scope for v1 cross-walk.

### ESPN adapter — priority 1

**Honest caveat up front: ESPN has no official/public fantasy API.** Access is via undocumented endpoints that the community has reverse-engineered. This is the highest-value (largest user base) and highest-fragility platform. Plan accordingly.

- **Endpoints.** `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/<season>/segments/0/leagues/<league_id>` with `?view=mRoster&view=mTeam&view=mSettings` (and `mMatchup` etc.). Older host `fantasy.espn.com/apis/v3/...` still seen. ([stmorse v3 writeup](https://stmorse.github.io/journal/espn-fantasy-v3.html), [espn-api lib](https://github.com/cwendt94/espn-api))
- **Auth: `espn_s2` + `SWID` cookies for private leagues.** Public leagues are readable with no auth. Private leagues (the common case) require two cookie values the user copies from their logged-in ESPN session. **The user cannot obtain these programmatically** — they open browser DevTools → Application/Storage → Cookies for `fantasy.espn.com`, copy `espn_s2` and `SWID`. ([ffscrapr ESPN auth](https://ffscrapr.ffverse.com/articles/espn_authentication.html), [cwendt94 discussion #150](https://github.com/cwendt94/espn-api/discussions/150)) This is a clunky UX and a support-load risk; design a guided copy-paste flow (screenshots per browser) or a browser-extension capture path (the FTF extension already runs in-browser and could read the user's own cookies with permission).
- **League id + season required.** Unlike Sleeper (username → leagues), ESPN gives no clean "list my leagues" without the cookies, and even then league discovery is awkward. **Plan for user-supplied league id + season** as the primary path; auto-discovery is a stretch.
- **ToS / fragility.** Community consensus: using *your own* cookies for *your own* league is not against ESPN ToS, but the **endpoints are undocumented and can change without notice** — ESPN has broken these clients repeatedly across seasons. Treat the ESPN adapter as **best-effort with graceful degradation**, version-pin the `view` params, monitor for shape changes, and never let an ESPN outage take down Sleeper users. Store cookies encrypted (see Cross-cutting); **never log `espn_s2`/`SWID`.**
- **Player ids.** ESPN player ids ≠ Sleeper ids → cross-walk required (FantasyCalc id-map primary, name-normalization fallback).

### MFL adapter — priority 2

**Official, documented API** — the opposite fragility profile to ESPN, which is why it's the safer (if smaller-TAM) second platform.

- **Endpoints.** `https://api.myfantasyleague.com/<year>/export?TYPE=<type>&L=<league_id>&JSON=1`. Relevant types: `TYPE=rosters` (all franchise rosters), `TYPE=league` (settings, franchise list), `TYPE=players` (player db incl. MFL ids), `TYPE=futureDraftPicks`. ([MFL API info](https://api.myfantasyleague.com/2024/api_info))
- **Auth.** League *read* data is **largely public** (`TYPE=rosters`/`league` work with just `L=`). Some endpoints and private-league data require a **login cookie** obtained from `TYPE=login` (returns an `MFL_USER_ID` cookie passed as `&APIKEY=` or cookie on subsequent calls). For v1, **start with public read** (rosters + league settings); add login only if private-league users need it.
- **Franchise model.** MFL leagues are made of **franchises** (`fid`), each with an owner. Map `franchise → MemberRef` (`source_user_id = fid` or franchise owner id, `username = franchise name`). MFL exposes `TYPE=futureDraftPicks` → maps cleanly to FTF's `draft_picks` model.
- **Player ids.** MFL player ids ≠ Sleeper ids → cross-walk. Bonus: `TYPE=players` returns MFL's own player db, and the FantasyCalc id-map explicitly includes MFL ids, so the MFL cross-walk should be the **most reliable** of the three non-canonical mappings.

### Data model changes

- **`leagues_table` gains a platform discriminator + native ids.** Today PK = `sleeper_league_id` ([database.py:91](../../backend/database.py)). Add `platform TEXT` ('sleeper'|'espn'|'mfl', default 'sleeper' for back-compat) and keep the id column as a generic source-native league id. The `isdigit()` convention already in `/api/sleeper/rosters` ([server.py:4968](../../backend/server.py)) is an existing precedent for "this id isn't a Sleeper id" — generalize it rather than special-casing per route.
- **`league_members_table`** ([database.py:130](../../backend/database.py)) gains `platform` + keeps `user_id` as the source-native member id. UNIQUE stays `(league_id, user_id)`.
- **Per-source credentials: encrypted, never plaintext.** ESPN cookies (`espn_s2`/`SWID`) and any MFL login cookie are **secrets**. Store them encrypted at rest (envelope encryption with a key from `secrets.local.env` locally / Render env in prod, per the [secrets convention](../../CLAUDE.md)), referenced by `linked_sources.credentials_ref` — **not** as plaintext columns. They are per-account, so they live with the account/`linked_sources`, not the league. **Never log them; redact in any debug buffer** (the `/api/debug/log` ring-buffer already carries sensitive data and is CRON-gated — same discipline applies).

### Effort + sequencing

| Step | Scope | Risk |
|---|---|---|
| B0 — Extract `SleeperAdapter` | Refactor existing Sleeper paths behind the interface; **no behavior change** | Low — pure refactor, covered by existing tests |
| B1 — Cross-walk service | FantasyCalc/Dynasty Daddy id-map ingest + `normalise_name` fallback; `crosswalk_players` | Med — new external data dependency; needs a coverage spike |
| B2 — MFL adapter (public read) | Official API; rosters + league + futureDraftPicks; franchise mapping | Low-Med — documented API |
| B3 — ESPN adapter (cookie auth) | Cookie capture UX + undocumented endpoints + degradation | **High** — unofficial API, UX friction, ongoing maintenance |
| B4 — Platform discriminator migration | `leagues`/`league_members` columns + encrypted creds store | Med — additive migration |

**Note the inversion vs. operator priority:** ESPN is priority *1 by value* but should *ship after* MFL *by build order* — MFL's documented API de-risks the whole `PlatformAdapter` + cross-walk machinery against a stable target before betting the harder build on ESPN's fragile one. Call this out to the operator as a deliberate sequencing recommendation, not a deprioritization of ESPN.

---

### The Sleeper-less user journey

The plan decouples identity from Sleeper (Part A) — but it deliberately keeps **two different "Sleeper" things**, and only one of them is optional. Make the distinction explicit so nobody later reads "Sleeper-keyed" as "Sleeper-required":

| "Sleeper" thing | Required for a user? | Why |
|---|---|---|
| Sleeper **account** (the user's username/`user_id`) | **No** | Identity is the Apple/Google subject; Sleeper is one optional `linked_source`. ESPN/MFL-only users get a synthetic `ftf:<account_id>` source key. |
| Sleeper **player-id namespace** (the canonical id space all values/engine math key on) | **Yes — but internal** | DynastyProcess values, the universal ranking pool, and divergence math all key on Sleeper player_ids. ESPN/MFL rosters are cross-walked *onto* them. The user never sees this; their players just need to *resolve* to a Sleeper player_id to be valued. |

**Fetching Sleeper *information* needs no user Sleeper account — confirmed in code, and it's the foundation that makes a Sleeper-less user viable:**

- **Sleeper's read API is keyless/public.** All calls are `https://api.sleeper.app/v1/...` with no API key, token, or headers ([server.py:444](../../backend/server.py), [profile_session_init.py:39](../../backend/profile_session_init.py)). FTF (or anyone) can fetch the player universe, a public league, or any username's data with no credentials.
- **The global player reference data is already account-independent.** `_load_sleeper_cache` / `_maybe_sync_players` populate the ~5MB player payload at **server startup**, no user context ([server.py:349,574](../../backend/server.py)). `GET /api/sleeper/players` and `GET /api/players` serve it with **no `_require_session()`** — they're open endpoints. The universal ranking pool (`g_universal_players`, built from `sleeper_cache` × DynastyProcess values in `build_universal_pool`) is likewise global. So a user who has never linked a Sleeper account can still fetch every player, every consensus value, and every player profile (#17).
- **Therefore the only thing a Sleeper *account* unlocks is the user's own leagues/rosters** — the `username → user_id → leagues/rosters` chain. ESPN and MFL provide the exact same thing through their adapters. Sleeper is interchangeable here, not foundational.

**The one real gap to close so a source-less / Sleeper-less user reaches the core loop.** The ranking loop is FTF's primary engagement (rank the global player universe via 3-player matchups — you rank *all* players, not just your roster). But `POST /api/rank3` and the league routes use `_require_initialized_session()`, which requires `sess["league"]` + `sess["players"]` ([server.py](../../backend/server.py)) — and today those are populated **only** by a Sleeper league import in `session_init`. So a freshly-authed user with no linked source currently has a bare session and can't rank. **Required change (small, additive):** give `session_init` a "no source yet" path that seeds `sess["players"]` from the **global universal pool** and `sess["league"]` as a synthetic solo/global league, so ranking works immediately after Apple/Google sign-in, before any platform is linked. This also improves the *Sleeper* onboarding funnel (rank first, link later) and is the natural home for the #8 outlook-seed once a source exists. Treat it as a prerequisite of Part A, not Part B.

**Three decisions this surfaces (pin them now):**
1. **`users_table.sleeper_user_id` PK now holds non-Sleeper values** (`ftf:<account_id>`). Mechanically fine via the "non-numeric == non-Sleeper" heuristic, but the column name lies. Decision: rename to a neutral `source_user_id` in a follow-up migration, OR add a load-bearing comment + a `is_synthetic` helper. Don't leave it implicit.
2. **Partial cross-walk coverage is a UX state, not an error.** An ESPN/MFL roster that's 85% mappable to Sleeper player_ids must degrade gracefully — surface "N players couldn't be matched to our value database" rather than silently dropping them from suggestions. Spike #1 measures the *rate*; this pins the *handling*.
3. **The divergence engine's cold-start is platform-independent.** FTF's differentiator needs ≥2 league-mates ranked. For a Sleeper-less league, those league-mates are ESPN/MFL users who must also adopt FTF — same cold-start as today (the existing watch item), now spanning platforms. League-mate features stay keyed on the source id (`sleeper_user_id`/synthetic), with the account as a presentation overlay, so this doesn't regress existing Sleeper leagues.

---

## Part C — In-app Sleeper trade creation (the "Sign in with Sleeper" provider)

*Added 2026-07-02. Grounded in web research (below) + the code state that FTF today only **reads** Sleeper (`api.sleeper.app/v1/`, keyless) and, to "send" a trade, generates a `sleeper.com/leagues/<id>/…` deep link the user must recreate by hand ([server.py:7345 share_trade_page](../../backend/server.py)). There is **no** write path in the codebase today (grep-confirmed: zero `graphql` / propose-trade / transaction-create references).*

### The finding

- **Sleeper's *public* API is read-only and keyless** — `api.sleeper.app/v1/*`, no token, cannot mutate. This is the API FTF uses and the reason "Sleeper trade creation isn't possible" got written into the earlier plan. It's correct *about that API*.
- **Sleeper's *own apps* write through an undocumented, authenticated API** — a GraphQL endpoint at `https://sleeper.com/graphql` (plus undocumented REST on `https://api.sleeper.com`), all carrying a **bearer/session token obtained by logging in**. Research **confirms** this surface handles add-player and chat (and stats reads) via GraphQL; **trade creation and waivers are not yet independently confirmed to be on it** — they ride the same authenticated surface (GraphQL and/or the private REST), but *which endpoint and what shape the trade-create call takes is exactly what Spike C2 must capture.* The community reverse-engineers these from DevTools/proxy traffic; the maintainer consensus is they "aren't meant to be used by consumers… should be considered unstable, could be blocked/deprecated at any point." ([undocumented-endpoints discussion](https://github.com/joeyagreco/sleeper/discussions/11), [Zuplo guide](https://zuplo.com/learning-center/sleeper-api))
- **So the competitor's flow is:** make the user **log into Sleeper** (real credentials, not a username) → capture the auth token → call the private GraphQL trade mutation on the user's behalf. That's the whole trick, and it's replicable.

### Why this is the strongest auth option (operator's insight, confirmed)

The other four providers (Apple/Google/Discord/X) prove *identity*. **Sleeper login proves identity *and* grants a capability none of the others can: writing to the user's league.** "Connect Sleeper to send trades straight to your league" is a concrete, feature-shaped value prop — far more compelling than "save your account." It becomes a **5th `auth_identities` provider** (`provider='sleeper'`, `subject=sleeper_user_id`) that simultaneously creates a **write-capable `linked_sources` row** carrying the encrypted token. One action, three payoffs: identity, backup, and the flagship feature.

**Two Sleeper paths now coexist — keep both:**
| Path | What it is | Unlocks |
|---|---|---|
| **Sleeper *username*** (today) | keyless read lookup, zero friction | find trades, rank, everything read-only — the frictionless start stays |
| **Sleeper *login*** (new) | real auth → captured token | everything above **+ send trades directly into the league** |

The username path remains the front door; the login is the **upgrade prompt at the Trade feature** — which is exactly trigger #3 in "the three prompts," now reframed from generic "save your account" to **"Connect Sleeper to send this trade."** Stronger prompt, feature-driven.

### How to do it right (mechanism + the security-critical choices)

1. **Token capture — the make-or-break unknown, because Sleeper is NOT an OAuth provider.** There's no redirect-with-`code` handoff to lean on. Two candidate mechanisms, and C1 must determine which is actually viable:
   - **Preferred: webview to Sleeper's *real* login page**, then read the resulting **token** out of the webview session (cookie / localStorage / an authenticated request the SPA fires). FTF never sees the password. **But this may not cleanly work** — the token could live in in-memory JS state a webview can't easily read, or be an httpOnly cookie, so treat "the webview yields a usable token" as a hypothesis, not a given.
   - **Fallback the competitor may actually be using: capture credentials in-app and POST them to Sleeper's login endpoint.** This *does* handle the password and carries a real App-Store-review risk (phishing pattern) — but if it's the only mechanism that works, that tradeoff has to be faced head-on (server-side exchange so the password never persists, clear disclosure, etc.).
   **So the "never touch the password" recommendation is the goal, not a guarantee** — C1 decides whether it's achievable. **Do not build against a guessed flow.**
2. **The token lives server-side, encrypted; the client never keeps it.** Send the captured token to the backend once, store it **encrypted at rest** in `linked_sources.credentials_ref` (the exact envelope-encryption mechanism Part B already specifies for ESPN cookies), and do **all writes from the backend**. The Sleeper token is a **full-account credential** — it can post, chat, and move rosters, not just trade — so it's the highest-value secret in the system. Encrypt it, **never log it** (add it to the `/api/debug/log` redaction set), scope its use to trade proposal, and make "Disconnect Sleeper" revoke it.
3. **New backend route `POST /api/trade/propose`.** Authenticated FTF session → resolve the user's encrypted Sleeper token → call the private GraphQL create-trade mutation (league id, the user's `roster_id`, `adds`/`drops` as Sleeper player_ids, draft picks, the counterparty's consent target) → return the created transaction id/status. A `SleeperWriteAdapter` keeps write concerns separate from the keyless read `SleeperAdapter` (Part B).
4. **It creates a *proposal*, not a forced trade.** A Sleeper trade goes to the other manager to accept/reject — same two-sided model as FTF's own matches. The UX must say "proposal sent," not "trade done." Note: reading the proposal's *pending* status back likely needs the **authenticated** API too — the public `transactions` endpoint tends to surface completed transactions, not open offers (confirm in C2), so don't assume the keyless read path can track proposal state.
5. **Token lifetime/refresh + graceful degradation.** Tokens expire; Spike C3 defines the refresh/re-login path. If the token is dead or the mutation shape has drifted, **fall back to today's deep-link** ("Open in Sleeper") rather than erroring — never let a Sleeper-write outage break trade discovery.

### Data model fit

No new tables — it reuses Part A/B:
- `auth_identities` row: `provider='sleeper'`, `subject=<sleeper_user_id>`.
- `linked_sources` row: `platform='sleeper'`, `source_user_id=<sleeper_user_id>`, `credentials_ref=<encrypted token>`. (Today's username-only users have a `linked_sources` row with a **null** `credentials_ref`; logging in *upgrades* the same row with the encrypted token — read-only → write-capable in place.)

### Risks / decisions (this is high-value **and** high-fragility — same profile as the ESPN adapter)

- **ToS / gray area.** Automating writes on a user's **own** account with the user's **own** token is the benign case, but the endpoint is undocumented and explicitly "not meant for consumers" — Sleeper can change the schema or block it without notice, and could object. Treat as **best-effort with graceful degradation** (deep-link fallback), monitor for shape drift, and never let it take down the read path. Decision to make with eyes open: the competitor doing it de-risks the ToS-tolerance question somewhat, but it's still Sleeper's call.
- **Security blast radius.** A leaked Sleeper token = takeover of the user's Sleeper account (not just FTF). This raises the bar on the encrypted-creds store from "nice to have" (ESPN) to **mandatory and audited**. Envelope encryption, key in env, redaction everywhere, revocation on disconnect, and consider short-TTL storage (re-prompt login rather than holding a long-lived token).
- **App Store review (+ the 4.8 question that gates sequencing).** Two parts. (a) **Capture pattern:** webview-to-real-Sleeper, not a fake native form (phishing-pattern rejection risk). (b) **Does Guideline 4.8 apply to "Sign in with Sleeper"?** *Ambiguous* — 4.8's named examples (Facebook/Google/Twitter/LinkedIn/Amazon/WeChat) are general-purpose identity providers; Sleeper is a niche fantasy app, so a reviewer may not treat it as a "social login service" at all. **Two framings, and the choice drives sequencing:**
  - *If Sleeper-login can create the **primary** FTF account* → 4.8 likely applies → **Sign in with Apple must ship in the same iOS release.**
  - *If Sleeper-connect is framed as a **capability grant on an already-established account*** (the user already has a session/account; connecting Sleeper only adds write) → 4.8 likely does **not** apply, and Part C can ship without any OIDC provider.
  **Decision to confirm at App Store review / with counsel; do not assume.** The Sleeper-first model already establishes a session before the Trades prompt, so the capability-grant framing is natural and is the recommended way to keep Part C decoupled. Be explicit in the connect flow that FTF will send trades on the user's behalf, and make it revocable.
- **Consent + clarity.** Users must understand "Connect Sleeper" grants send-trade power. One-line disclosure + a visible "Disconnect" in Settings.

### Spikes (ranked — do before committing to build)

- **C1 — Login → token capture (gates everything).** On a throwaway Sleeper account in a test league, capture the real login flow (mitmproxy on the mobile app / DevTools on web): the login endpoint(s), token format, where it rides (header/cookie/localStorage), lifetime, and — the decisive question — **whether a webview can extract a usable token without FTF handling the password, or whether direct credential capture is the only viable path.** That answer determines both the App Store risk and the whole UX. Output: the exact, current auth handshake **and** a go/no-go on the no-password capture.
- **C2 — Trade-create mutation.** Capture a real trade proposal end-to-end: the GraphQL operation name, full variable shape (league id, `roster_id` resolution, `adds`/`drops` player_id encoding, draft-pick encoding, consenter/target), and the success/error responses. Output: a validated request FTF can reproduce. **Do not ship against a guessed schema.**
- **C3 — Token lifetime + failure modes.** Expiry/refresh behavior; errors for invalid roster, locked league, non-consenting counterparty, rate limits. Defines the degradation + re-login UX.
- **C4 — Legal/ToS gut-check.** A quick read of Sleeper's ToS re: automated access on a user's own account, and how exposed the competitor is, before betting the flagship feature on it.

### Sequencing

Depends only on the **account/`linked_sources` data model + the encrypted-creds store** — the token needs an account and an encrypted home. It does **not** depend on the four social OIDC providers (a Sleeper session already exists to hang the login on), so it can be decoupled from and even run ahead of them, not gated behind all of Part A — **the sole exception is Apple/4.8** (see "App Store review" above): full "ahead of everything" decoupling holds only under the capability-grant framing; if Sleeper-login creates the primary account, Sign in with Apple must accompany it on iOS. Given the operator ranks this the **most critical feature in the app**, sequence it as the **flagship right after the identity data model lands**, *ahead of ESPN/MFL*: it's higher-value than a second read-only platform and reuses the exact same encrypted-creds machinery, so building it first also proves that machinery against the highest-stakes secret. Concretely: **identity data model + encrypted creds → Phase 1.5 (this: Sleeper-login provider + `POST /api/trade/propose` + webview capture) → then** the social providers and the Part B adapters, in whatever order value dictates. Gate on Spike C4 (ToS) before C1/C2 capture; ship behind a flag to a beta cohort given the fragility/ToS profile.

---

## Cross-cutting

### Security

- **Verify provider tokens server-side against JWKS** (Part A) — the single most important property. Never trust a client-supplied `sub`.
- **Encrypt all per-source credentials at rest** (ESPN cookies, MFL login cookie, **and the Sleeper write token — Part C**). Envelope-encrypt with a key from env; store ciphertext + key ref in `linked_sources.credentials_ref`. The Sleeper token is the **highest blast-radius secret** (full Sleeper account control) — treat its handling as mandatory-and-audited, do writes server-side only, and revoke on disconnect.
- **Never log secrets.** `espn_s2`, `SWID`, MFL cookies, and provider ID tokens must be redacted everywhere — especially the `/api/debug/log` ring-buffer ([server.py:52](../../backend/server.py)), which already aggregates usernames/tracebacks and is CRON-gated.
- **Token storage on device:** keep using expo-secure-store for the FTF session token; never persist provider ID tokens on device beyond the exchange.
- **Persist sessions** (Part A) to remove the in-memory single-point-of-logout, and add real expiry/refresh now that real accounts exist.

### Backlog re-ranking impact

This plan **elevates** two parked items and **reframes** the top-20:

- **#68 (Yahoo league support)** and **#69 (Multi-platform host hub: ESPN/MFL/Fantrax)** — currently parked as Tier 3/4 "horizon" items explicitly because "the entire current stack assumption is Sleeper-only" ([backlog #68/#69](competitor-feature-backlog-2026-06-11.md)). This plan **is** the prerequisite work for both; once `PlatformAdapter` + accounts land, #69 becomes "add the next adapter" and #68 (Yahoo, which has an *official* API) becomes a near-trivial third adapter. **Promote both to "now / next" once Part A ships.**
- **Engine items #1–#20 are platform-agnostic and unaffected.** The outlook classifier (#1), package adjustment (#10), verdict banner (#6), confidence ranges (#16), per-league outlook (#8), draft-pick valuation (#13) all operate on the *normalized internal model* (rosters as player-id lists + scoring format). Because every adapter feeds that same model, these features work identically across Sleeper/ESPN/MFL with **no per-platform engine changes** — a strong reason to land the abstraction cleanly. **Reframe #1–#20 in the backlog as platform-agnostic engine work.**
- **Items that assume Sleeper and need rework:** the **trade deep-link + share (#12)** generates `sleeper.com/leagues/<id>/...` style links and the **extension overlay (#19)** is literally a `sleeper.com` content script ([server.py extension routes](../../backend/server.py)). These are **Sleeper-specific by construction** — ESPN/MFL would need their own deep-link targets and the overlay simply won't apply off-Sleeper. Flag #12/#19 as "Sleeper-only until per-platform link/overlay variants are scoped." (#86 trade-card image generator is platform-agnostic and unaffected.)

### Open questions / spikes needed (ranked)

1. **Cross-walk coverage spike.** Build the `player_id_xwalk` table from the **nflverse/ffverse `ff_playerids` map** (primary) and FantasyCalc/Dynasty Daddy id sets (corroboration); measure the **id-match rate** (ESPN-id / MFL-id → Sleeper-id) on a real ESPN and a real MFL league. Quantify the residual that falls through to name-matching + fuzzy, and the truly-unmatched rate. **This gates whether multi-platform is even viable** — if 15% of a roster can't be cross-walked, the trade math is garbage. Highest-priority spike. (See "Player ID cross-walk strategy" for the table design.)
2. **ESPN cookie-capture UX spike.** Validate the DevTools copy-paste flow end-to-end against a private league, and prototype the extension-capture alternative (read the user's own `fantasy.espn.com` cookies with permission). Determines whether ESPN is shippable to non-technical users at all.
3. **Provider-token verification spike — all four providers.** Stand up Apple + Google + Discord JWKS verification against real Expo-issued ID tokens (Apple's `aud`/nonce handling and the first-authorization-only name/email quirk are the usual footguns; confirm Discord's `openid`-scope id_token in `expo-auth-session` — if clunky, fall back to code-exchange + `/users/@me`), and the X PKCE code exchange server-side (register the X developer app early — approval latency and access-tier cost are the real risk, not the code). De-risks all of Part A.
4. Session persistence: stateful `sessions` table vs. stateless signed JWT (affects Render-restart behavior and the 60+ `_require_session` consumers).
5. Account-merge policy when the same human signs in with Apple on one device and Google on another (the "link a second provider" UX).
6. MFL private-league login: how many target users have private MFL leagues that need the `TYPE=login` cookie path vs. public read.

---

## Recommended phasing

Auth is sequenced **first** because multi-platform linked sources have nothing to attach to without an account — this is a true dependency, not just a priority call.

**Phase 1 — Identity foundation (Part A, rev. 2026-06-23).** `accounts` + `auth_identities` + `linked_sources` tables; `users_table.account_id` column; dual-mode `/api/auth/apple|google|discord|twitter` (JWKS verification for the OIDC three; server-side PKCE exchange for X); persist sessions; **SignInScreen unchanged as the Sleeper front door** + the "Already saved? Sign in" returning path; the `SaveAccountSheet` + the **three prompt triggers** (post-login, rankings-established, Trades-open) with the once-ever caps and funnel events. Provider sequencing inside the phase: **Apple + Google first** (one JWKS code path, and Apple is the 4.8 gate for everything else), **Discord second** (OIDC, same path), **X last, feature-flagged** (different flow, fragile platform). Account creation is **lazy** — on prompt acceptance, auto-linking the session's Sleeper id. **Include the source-less `session_init` seed** (see "Sleeper-less user journey") — in this model its Phase-1 role is the returning-authed-user-with-no-linked-source edge, and it becomes the Sleeper-less onboarding enabler in Part B. Ship behind a flag; existing token sessions keep working through the transition.

**Phase 1.5 — In-app Sleeper trade creation (Part C, the flagship).** Comes before the read-only adapters — the dependency is **narrower than all of Part A**: it needs only the `accounts` / `auth_identities` / `linked_sources` tables + the **encrypted-creds store**, *not* the four social OIDC providers. Since users already hold a working Sleeper session, "Sign in with Sleeper" can be built as soon as that scaffolding lands — **in parallel with, or ahead of, Google/Discord/X.** **The one caveat is Apple/4.8** (see the Part C "App Store review" note): shipping ahead of *all* providers is only clean if Sleeper-connect is framed as a **capability grant on an already-established account** (4.8 likely N/A); if instead it can create the primary account, **Sign in with Apple must ship in the same iOS release.** Confirm that framing before assuming full decoupling. Given the operator ranks it #1, decouple from the *social-provider* work either way rather than gating it behind all of them.

Build order within the phase:
1. **Gate on Spike C4 (ToS / legal gut-check) first** — cheapest, and it can kill the feature before any capture effort.
2. **Spikes C1 (login→token capture) + C2 (trade mutation)** — **do not build against a guessed schema**; if either can't be captured cleanly, keep today's deep-link and stop.
3. **Encrypted-creds store** — the store *only*, not B4's `platform` discriminator (that's ESPN/MFL's).
4. **"Sign in with Sleeper" via a webview to Sleeper's *real* login** (not a native credential form) → capture token → server-side.
5. **`SleeperWriteAdapter` + `POST /api/trade/propose`** — token stays server-side, encrypted; client never holds it.
6. **Lifecycle:** token refresh / re-login on expiry, and a **"Disconnect Sleeper"** control that revokes the stored token.
7. **Client UX:** "proposal sent — pending on Sleeper" (it's a proposal, not a forced trade) + deep-link fallback on any write failure.

Reframes trigger #3's prompt to "Connect Sleeper to send this trade." **Ship flag-gated to a beta cohort**, with an explicit **App-Store-review checkpoint**: the webview capture pattern, plus the 4.8 question — whether Sleeper-connect is a *capability grant on an existing account* (4.8 likely N/A, ships alone) or a *primary-account login* (4.8 applies → Apple ships alongside). See the Part C "App Store review" note; confirm before submission. Highest value in the plan; reuses the encrypted-creds machinery against the highest-stakes secret, proving it early.

**Phase 2 — Adapter abstraction + cross-walk (Part B foundation).** Extract `SleeperAdapter` (read) as a no-behavior-change refactor (B0). Build the cross-walk service (B1) and **run Spike #1 first** — if coverage is unacceptable, stop and reassess before building adapters. The `platform` discriminator + encrypted-creds store (B4) already landed in Phase 1.5.

**Phase 3 — MFL adapter (B2).** Documented API; public-read leagues first. Proves the whole pipeline (account → linked source → adapter → cross-walk → normalized model → engine) against a *stable* platform. Lower TAM but lower risk — the de-risking run before ESPN.

**Phase 4 — ESPN adapter (B3).** The high-value, high-fragility build. Cookie-capture UX (Spike #2), undocumented endpoints with graceful degradation, encrypted cookie storage, monitoring for endpoint drift. Ship to a beta cohort first given the maintenance/ToS profile.

**Then:** promote backlog #68 (Yahoo, official API — easy third adapter) and #69 (host hub) into the active roadmap; scope per-platform variants of #12/#19 if off-Sleeper deep-linking/overlay demand materializes.

---

*Sources: [Apple App Store Guidelines 4.8](https://developer.apple.com/app-store/review/guidelines/) · [9to5Mac on 4.8 revision](https://9to5mac.com/2024/01/27/sign-in-with-apple-rules-app-store/) · [Expo AppleAuthentication](https://docs.expo.dev/versions/latest/sdk/apple-authentication/) · [Expo authentication guide](https://docs.expo.dev/develop/authentication/) · [Apple JWKS server-side verification](https://medium.com/@meszmate/apple-sign-in-with-expo-golang-complete-2025-guide-to-server-side-oauth-jwt-validation-and-01677dc27e08) · [Discord OAuth2/OIDC](https://discord.com/developers/docs/topics/oauth2) · [X OAuth 2.0 PKCE](https://docs.x.com/resources/fundamentals/authentication/oauth-2-0/authorization-code) · [ESPN v3 API writeup](https://stmorse.github.io/journal/espn-fantasy-v3.html) · [ffscrapr ESPN auth (espn_s2/SWID)](https://ffscrapr.ffverse.com/articles/espn_authentication.html) · [cwendt94/espn-api](https://github.com/cwendt94/espn-api) · [MFL API info](https://api.myfantasyleague.com/2024/api_info) · [MFL get-endpoint (ffscrapr)](https://packages.oit.ncsu.edu/cran/web/packages/ffscrapr/vignettes/mfl_getendpoint.html) · **Part C (Sleeper write, researched 2026-07-02):** [Sleeper undocumented-endpoints discussion (joeyagreco/sleeper #11)](https://github.com/joeyagreco/sleeper/discussions/11) · [Zuplo Sleeper API guide (public API is read-only; GraphQL is undocumented/internal)](https://zuplo.com/learning-center/sleeper-api) · [Sleeper API docs (read-only, keyless)](https://docs.sleeper.com/). Code grounding: backend/server.py, backend/database.py, backend/data_loader.py, mobile/src/screens/SignInScreen.tsx, mobile/src/state/useSession.ts on branch trade-engine-v2 @ 2026-06-13; trigger anchors (progress :2265, ranking_complete_first_time :2374, FB4-59 FormatGate) re-verified 2026-06-23.*
