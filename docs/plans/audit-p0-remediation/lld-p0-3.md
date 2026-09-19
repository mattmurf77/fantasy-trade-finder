# LLD — P0-3 · The invite loop, both ends

> Code-level design for audit finding **P0-3**. Binding parents, in order:
> [`hld.md`](hld.md) (authority — §1.2 Spine A, §1.3 flow diagram, §2 S-13…S-18,
> §3 commits 3 and 12, §4 W1-BE + W2-P03, §5 harness, §6 row 7, §7, §8 R2, §9 LLD-3,
> §10.2), then [`plan-p0-3.md`](plan-p0-3.md) and [`scope-p0-3.md`](scope-p0-3.md).
> Where this document and the plan disagree, the HLD decided it; every such case is
> listed in [§6 Deviations](#6-deviations-from-the-plan).
>
> **Two executors, two commits, two waves.**
> §1 Server is built by **W1-BE** as **commit 3**. §2 Client is built by **W2-P03** as
> **commit 12**, *after* P0-5's commits 6 and 7 have landed. Neither half may be built by
> the other agent, and neither may touch a file outside its §4-assigned list.
>
> **Line numbers in this document are anchors of convenience, taken at
> `origin/main @ ab9368f` in worktree `ftf-p0-remediation`.** Per HLD §8 R1 every
> executor **re-greps the quoted text immediately before editing** and never navigates by
> line number. Every insertion point below is therefore given as a *quoted string* first
> and a line number second.
>
> `mobile/node_modules` is a symlink. **Never run `npm install`.**

## Contents

- [1. Server half — W1-BE, commit 3](#1-server-half--w1-be-commit-3)
- [2. Client half — W2-P03, commit 12](#2-client-half--w2-p03-commit-12)
- [3. Events](#3-events)
- [4. Maestro](#4-maestro)
- [5. Verification checklist per commit](#5-verification-checklist-per-commit)
- [6. Deviations from the plan](#6-deviations-from-the-plan)
- [7. Explicitly out of scope](#7-explicitly-out-of-scope)

---

## 1. Server half — W1-BE, commit 3

**Commit message:**
`P0-3(server): AASA /app/league/join claim, 302 fallback, invite-meta, growth.invite_join_link (OFF)`

**Files (exclusive within this commit's scope):** `backend/server.py` (three regions),
`backend/feature_flags.py`, `config/features.json`,
`backend/tests/fixtures/flags/release.json`, `backend/tests/test_invite_links.py` (new),
**and two existing test files that this change breaks** — see [§1.6](#16-two-existing-tests-break-and-must-be-updated-in-this-commit).

Everything here is additive and read-only. No schema change, no migration, no write path,
no new env var.

### 1.1 S1 — AASA claims `/app/league/join/*`

**Current code, quoted verbatim** (`backend/server.py`, route
`@app.route("/.well-known/apple-app-site-association")`, `:8076-8109`; grep anchor
`"components": [`):

```python
    team_id = os.environ.get("APPLE_TEAM_ID") or _APPLE_TEAM_ID_DEFAULT
    app_id = f"{team_id}.{_accounts.APPLE_AUDIENCE}"
    return jsonify({
        "applinks": {
            "apps": [],
            "details": [{
                "appID":  app_id,
                "appIDs": [app_id],
                "components": [
                    {"/": "/u/*"},
                    {"/": "/s/*"},
                    {"/": "/", "?": {"ref": "?*"}},
                    {"/": "/", "?": {"league": "?*"}},
                ],
                "paths": ["/u/*", "/s/*"],
            }],
        },
    })
```

**Change — exactly two list entries, nothing else:**

- `components` gains `{"/": "/app/league/join/*"}`, appended **after** `{"/": "/s/*"}` and
  **before** the two query matchers (keeps path matchers grouped; iOS evaluates
  `components` in order and a path matcher never shadows a query matcher on `/`).
- `paths` becomes `["/u/*", "/s/*", "/app/league/join/*"]`.

**Do not** broaden to `/app/*`. The mobile route table (`deepLinks.ts` `V2_SCREENS`)
already owns `app/league/summary`, `app/league/free-agents`, `app/league/draft-room`,
`app/league/pick-assignments`, `app/league/record-picks`, `app/rank/*`, `app/trades/*`,
`app/matches/*`, `app/league/*` — claiming `/app/*` in AASA would make iOS intercept every
one of those URLs even though the server serves none of them, converting today's honest
Safari 404 into an app-open with no destination.

**Also update the route's docstring**, which enumerates what it declares. The current
sentence `Declares the shared-surface paths: public profiles (/u/*), share links (/s/*),
referral links (/?ref=*), and league invite links (/?league=*; FB #239 …)` gains league
**join** links and a one-line statement of the ordering hazard:

> `/app/league/join/*` (P0-3) — the invite JOIN path. Claimed here **unflagged and ahead
> of the client emitter** (`growth.invite_join_link`, default OFF): Apple's CDN caches this
> file for up to ~24h, so a build that emitted the new URL before this claim propagated
> would send every invite to Safari — strictly worse than the legacy URL. Flag graduation
> requires an external AASA validator plus a device check. See `docs/runbook.md` § AASA.

### 1.2 S2 — `GET /app/league/join/<league_id>` → 302

**Placement:** immediately after `terms_page()` and **before** the
`_APPLE_TEAM_ID_DEFAULT` constant (grep anchor: `def terms_page():`, `:8064-8067`). That
puts it with the other clean-URL page routes and inside the same static-page region the
plan named.

Flask is configured `static_folder=<repo>/web, static_url_path=""` (`server.py:2003`), so
`/app/league/join/<id>` is a **404 today**; this route is purely additive and can shadow
nothing.

```python
@app.route("/app/league/join/<league_id>")
def league_join_redirect(league_id):
    """Web fallback for the mobile invite deep link (P0-3).

    iOS resolves Universal Links against AASA BEFORE any HTTP request, so on a
    device with the app installed this route is never reached. It exists for
    the recipient in Safari (no app, or a desktop browser): 302 straight into
    the web landing that already completes the journey —
    web/js/app.js captureReferralFromUrl() stores ftf_invited_by /
    ftf_invited_league, renders "Invited by @<ref>", and auto-selects the
    league once the Sleeper list loads (app.js:589-601).

    Deliberately NOT a new web page: the existing funnel converts and this
    hands off to it unchanged. Unflagged — the parsers must be live before any
    new-format link exists in the wild.
    """
    params = {"league": str(league_id)}
    ref = (request.args.get("ref") or "").strip()
    if ref:
        params["ref"] = ref
    return redirect("/?" + urlencode(params), code=302)
```

**Contract, pinned by tests:**

| Input | `Location` |
|---|---|
| `/app/league/join/123?ref=matt` | `/?league=123&ref=matt` |
| `/app/league/join/123` | `/?league=123` |
| `/app/league/join/..%2F..%2Fetc%2Fpasswd?ref=a b` | `/?league=..%2F..%2Fetc%2Fpasswd&ref=a+b` |
| `/app/league/join/123?ref=matt&utm=x` | `/?league=123&ref=matt` (unknown params dropped) |

**Invariants:**

1. **Relative Location only.** The target is built from a hard-coded `"/?"` plus
   `urlencode()` of a dict we constructed. No user-supplied string ever reaches the scheme
   or host position, so there is no open-redirect surface. Never build this with an
   f-string.
2. **`urlencode` is the encoder**, not manual concatenation — it is what makes the
   traversal row above encode rather than reflect.
3. **`ref` passes through by value only.** It is not looked up, not trusted, not logged as
   a user identifier. The web side already treats it as a display string.
4. **Only `league` and `ref` survive.** Dropping unknown query params keeps the redirect a
   closed contract; nothing downstream reads anything else.
5. **302, not 301.** A permanent redirect would be cached by browsers and CDNs and would
   outlive any future change to the landing.
6. `redirect` and `urlencode` must be present in `server.py`'s imports — **verify at edit
   time** (`grep -n "^from urllib.parse import\|^from flask import" backend/server.py`) and
   add only what is missing.

### 1.3 S3 — `GET /api/league/invite-meta`

**Placement:** immediately after `parse_league_url()` (grep anchor
`@app.route("/api/league/parse-url", methods=["POST"])`, `:17353`), reusing that route's
own helper.

**Request:** `GET /api/league/invite-meta?league_id=<id>`. No session, no headers, no body.

**Response — always 200 except for a missing param:**

```json
{ "league_id": "990000000000000001", "league_name": "QA Standard League", "platform": "sleeper" }
```

| Condition | Response |
|---|---|
| `league_id` missing/blank | `400 {"error": "missing_league_id"}` |
| Sleeper id, meta resolves | `200 {league_id, league_name: "<name>", platform: "sleeper"}` |
| Sleeper id, Sleeper unreachable / 404 / fixture miss | `200 {league_id, league_name: null, platform: null}` |
| Non-numeric id | `200 {league_id, league_name: null, platform: null}` |
| Numeric id of a **linked ESPN/MFL/Fleaflicker** league | `200 {league_id, league_name: null, platform: null}` |

```python
@app.route("/api/league/invite-meta")
def league_invite_meta():
    """Public, read-only league name for an invite banner (P0-3).

    PRIVACY CONSTRAINT — the name is resolved from Sleeper's PUBLIC API only,
    never from our `leagues` table. That is why ESPN/MFL/Fleaflicker leagues
    return null: their names live only in our DB, and this endpoint is
    unauthenticated, so serving them would make every imported league name
    enumerable by id. Sleeper league names are already public at
    https://api.sleeper.app/v1/league/<id>, so this endpoint discloses nothing
    that the id alone did not already disclose.

    Degrades, never fails: any resolution problem is a 200 with
    league_name: null, and the client's banner falls back to "their league".
    The P0-3 acceptance criterion (inviter named) is met WITHOUT this route.
    """
    league_id = (request.args.get("league_id") or "").strip()
    if not league_id:
        return jsonify({"error": "missing_league_id"}), 400
    name = None
    try:
        meta = _fetch_sleeper_league_meta(league_id)
        if meta:
            name = meta.get("name") or None
    except Exception as e:                       # pragma: no cover - defensive
        log.info("invite-meta: lookup failed (non-fatal) league_id=%s: %s", league_id, e)
    return jsonify({
        "league_id":   league_id,
        "league_name": name,
        "platform":    "sleeper" if name else None,
    })
```

**Why `_fetch_sleeper_league_meta` and not a bespoke fetch** (`server.py:673`, grep anchor
`def _fetch_sleeper_league_meta`): it already enforces all three guards this endpoint
needs, in the right order —

```python
    if not league_id or not str(league_id).isdigit() \
            or is_linked_platform_league(league_id):
        return None
```

`isdigit()` rejects junk; `is_linked_platform_league()` (`backend/database.py:6035`) rejects
platform-imported leagues; and the fetch itself goes to Sleeper's public endpoint through
`_sleeper_get`, which is the fixture seam under the test harness. `parse_league_url` — an
**unauthenticated** route — already calls it exactly this way (`:17388`), so this is a
reuse, not a new external surface.

**Read the privacy constraint precisely.** `is_linked_platform_league` performs one
`SELECT platform FROM leagues WHERE sleeper_league_id = ?`. That is a DB read, and it is
*how the constraint is enforced* — but no value from our `leagues` table is ever placed in
the response. The invariant to test is **"the response name never originates from our
DB"**, not "no query runs". See [§6 D-3](#6-deviations-from-the-plan).

**No rate limit, deliberately.** The route is a thin cache-friendly proxy of data Sleeper
already serves publicly and unauthenticated; it stores nothing, mutates nothing, and
returns one short string. Adding the `count_recent_shared_packages`-style hourly limiter
(`server.py:16856`) would require a user id this route deliberately does not have. Recorded
here so the omission reads as a decision. If abuse ever appears, the lever is
`_fetch_sleeper_league_meta`'s upstream, not this route.

### 1.4 S4 — the flag `growth.invite_join_link`

Three files, one key, default **OFF** (HLD S-13/S-14).

**`backend/feature_flags.py`** — `FLAG_KEYS`, in the teardown-remediation growth block
(grep anchor `"growth.share_landing",` at `:272`), inserted directly beneath it:

```python
    "growth.share_landing",
    "growth.rating_prompt",
    # P0-3 (2026-08-09 mobile UX audit) — EMITTER ONLY. On: buildInviteUrl
    # emits /app/league/join/<id>?ref=<u>. Off (default): today's
    # /?league=<id>&ref=<u>, byte-identical. Never gates the ?league= reader,
    # the LeagueJoin route, the AASA claim or the 302 — those are additive and
    # must be live BEFORE any new-format link exists. Graduation: AASA
    # validated live + ≥24h CDN propagation + a post-deploy install proves a
    # tapped link opens the app (docs/runbook.md § AASA).
    "growth.invite_join_link",
```

**`config/features.json`** — after `"growth.rating_prompt": true,` (`:126`):

```json
  "_comment_growth_invite_join_link": "P0-3 invite deep link. EMITTER ONLY, default OFF. Graduate to true only after: (1) the AASA file at /.well-known/apple-app-site-association validates live and lists /app/league/join/*, (2) >=24h of Apple CDN propagation has elapsed since that deploy, (3) a TestFlight build installed AFTER that deploy demonstrably opens the app on a tapped /app/league/join/... link. Flipping early sends every invite to Safari. Rollback = flip back to false; the legacy /?league= URL is parsed forever by both clients.",
  "growth.invite_join_link": false,
```

**`backend/tests/fixtures/flags/release.json`** — the same key, `false`, in the same
position (this file mirrors `config/features.json`; the `_comment_` is not required here,
and adding it keeps the mirror honest — either choice is acceptable, but the **key must be
present**, because a Maestro flow declaring `# flags: release` resolves against this file
and an absent key would fall back to a default the flow did not declare).

### 1.5 S5 — `backend/tests/test_invite_links.py` (new)

Module docstring names the finding, the branch, and the ordering hazard. Cases:

| # | Test | Asserts |
|---|---|---|
| T-1 | `test_aasa_claims_league_join_path` | `{"/": "/app/league/join/*"} in components`; `"/app/league/join/*" in paths` |
| T-2 | `test_aasa_still_claims_the_four_existing_patterns` | `/u/*`, `/s/*`, `?ref`, `?league` all still in `components`; `/u/*`, `/s/*` still in `paths` |
| T-3 | `test_aasa_never_claims_bare_root` | `{"/": "/"} not in components`; `{"/": "/*"} not in components`; `"/" not in paths`; `"/*" not in paths`; **and** `"/app/*" not in paths` and `{"/": "/app/*"} not in components` (the over-broad claim this design refuses) |
| T-4 | `test_join_redirect_with_ref` | 302; `Location == "/?league=123&ref=matt"` |
| T-5 | `test_join_redirect_without_ref` | 302; `Location == "/?league=123"` |
| T-6 | `test_join_redirect_encodes_hostile_ids` | traversal id + a `ref` containing a space and `&` are **percent-encoded** in `Location`; `Location` starts with `"/?"`; `"://" not in Location` (no open redirect) |
| T-7 | `test_join_redirect_drops_unknown_params` | `?ref=matt&utm_source=x` → `Location` contains no `utm_source` |
| T-8 | `test_invite_meta_resolves_sleeper_name` | with `_fetch_sleeper_league_meta` patched to `{"name": "Lakeview Dynasty"}` → `{league_name: "Lakeview Dynasty", platform: "sleeper"}`, **no session header sent**, 200 |
| T-9 | `test_invite_meta_degrades_on_failure` | patched to raise → 200 with `league_name is None`, `platform is None` |
| T-10 | `test_invite_meta_null_for_non_sleeper_ids` | non-numeric id and a `leagues` row with `platform='espn'` both → `league_name is None`. **This is the privacy test:** seed that row with a distinctive name and assert the name never appears in the response body |
| T-11 | `test_invite_meta_requires_league_id` | no param → 400 `missing_league_id` |
| T-12 | `test_invite_join_flag_registered_and_off` | `"growth.invite_join_link" in feature_flags.FLAG_KEYS`; `is_enabled("growth.invite_join_link") is False` under the default config; present and `false` in `backend/tests/fixtures/flags/release.json` |
| T-13 | `test_invite_event_names_are_registered` | `POST /api/events` accepts `invite_shared`, `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed` with `dropped == 0`. **Regression guard for the silent-drop class.** Depends on commit 1; if commit 1 has not landed, this test fails loudly, which is the intent |

Use the lightweight client construction from `backend/tests/test_universal_links.py:21-25`
(`server.app.test_client()`) for T-1…T-7 and T-11…T-12; T-8…T-10 and T-13 need the
in-memory-SQLite fixture pattern of `test_account_first.py`.

### 1.6 Two existing tests break and must be updated in this commit

Found by reading, not by running — **W1-BE must fix both or commit 3 is red**:

1. **`backend/tests/test_account_data_rights.py:258`**
   ```python
   assert detail["paths"] == ["/u/*", "/s/*"]
   ```
   An **exact list equality**. Adding `/app/league/join/*` to `paths` breaks it. Change to
   the three-element list in the same order the route emits, or relax to membership +
   `"/" not in paths`. Prefer the explicit list — it is a contract assertion and should
   stay one.
2. **`backend/tests/test_universal_links.py:40-55`** uses membership assertions and passes
   unchanged, **but** its module docstring says the components claim "ONLY the shared
   surfaces (profiles, share landings, invite/referral roots)". Extend that sentence to
   include the join path. A docstring that contradicts the assertions below it is the
   A-33 failure class this batch exists to stop repeating.

`test_universal_links.py` is otherwise **not** rewritten: T-1…T-3 in the new file are the
P0-3-specific additions and the old file stays the FB #239 contract.

---

## 2. Client half — W2-P03, commit 12

**Commit message:**
`P0-3(client): legacy ?league= reader, LeagueJoin route + screen, persisted invite intent, invited sign-in banner`

**Preconditions (HLD §3 hard ordering):** commit 3 (server routes + flag) **and** commit 6
(harness `IS_TEST_BUILD` export + `SIGNED_OUT_ENTRY_ROUTES`) **and** commit 7 (P0-5's
routing fix + companion state with its optional `invitedBy` / `invitedLeagueName` props)
have all landed. W2-P03 **rebases onto P0-5's landed state and re-greps every anchor** —
`RootNav.tsx`, `LeaguePickerScreen.tsx` and `SignInScreen.tsx` were all edited in wave 1.

**Files:** `mobile/src/utils/deepLinks.ts`, `mobile/src/state/useSession.ts`,
`mobile/src/screens/LeagueJoinScreen.tsx` (new), `mobile/src/navigation/RootNav.tsx`,
`mobile/src/screens/LeaguePickerScreen.tsx`, `mobile/src/screens/SignInScreen.tsx`,
`mobile/src/components/InviteLeaguematesBanner.tsx`, `mobile/src/api/league.ts`,
`mobile/.maestro/flows/league/invite-join.yaml` (new).

**`mobile/src/screens/LeagueScreen.tsx` is NOT in that list** and must not be opened —
HLD §10.2 dissolved the contention by moving the flag read inside `buildInviteUrl`. It
belongs to W2-P07.

### 2.0 The one network-call rule (rails-audit safety)

`fetchInviteMeta()` has **exactly one call site: `SignInScreen`.** No other screen may call
it. This is not style — it is a hermetic-harness constraint discovered by reading
`mobile/scripts/sim-run.sh:178`:

```
bad={k:v for k,v in c.items() if k in ('vcr_misses','sleeper_live_egress_attempts','completed_proposes') and v>0}
```

A sim run **fails** if `vcr_misses > 0`. `GET /api/league/invite-meta` →
`_fetch_sleeper_league_meta` → `_sleeper_get` → under `FTF_SLEEPER_FIXTURES_DIR` a cassette
miss raises 599 **and increments `vcr_misses`** (`server.py:529-536`). The seeder writes a
`league/<lid>.json` cassette for every seeded league and
`_verify_no_cassette_gap` refuses cassettes for any other league id
(`backend/tests/fixtures/seed_ui_test_db.py:1422, 1487, 1504-1522`). Therefore:

- Any Maestro leg that reaches a `fetchInviteMeta` call site **must use a seeded league
  id.** The invite-join flow's signed-out block uses `990000000000000001` (profile
  `standard`) for exactly this reason.
- `LeagueJoinScreen` and `LeaguePickerScreen` **never** call it — their non-member and
  account-only legs run with ids that have no cassette, and one call there would turn a
  passing tier-1 run red for a reason nobody would look for.
- The league **name** still reaches those screens: `SignInScreen` caches the resolved name
  into the persisted invite intent (§2.2), so the account-only companion state gets the
  real name whenever the user passed through sign-in, and degrades honestly to "their
  league" when they did not.

Reviewer check for this commit: `grep -rn "fetchInviteMeta" mobile/src` returns exactly
two lines — the export in `api/league.ts` and the import+call in `SignInScreen.tsx`.

### 2.1 C1 — `deepLinks.ts`: the `?league=` reader and the route-table entry

#### C1a — the legacy reader (the unflagged half that fixes every link ever shared)

**Current code, quoted verbatim** (`mobile/src/utils/deepLinks.ts:340-354`; grep anchor
`// Referral: ?ref=<username>`):

```ts
  // Referral: ?ref=<username>. queryParams may be Record<string, string | string[]>
  // Captured in BOTH router modes.
  const ref = parsed.queryParams?.ref;
  const refStr = Array.isArray(ref) ? ref[0] : ref;
  if (typeof refStr === 'string' && refStr.trim()) {
    useSession.getState().setInvitedBy(refStr);
  }

  const path = (parsed.path || '').replace(/^\/+/, '');

  if (useFeatureFlags.getState().flags['ux.deeplink_router_v2']) {
    // Bare open / referral-only URL (no path) — nothing to route, no toast.
    if (!path) return;
```

**Insert immediately after the `?ref=` block and before `const path = …`** — i.e. above
the `if (!path) return;` short-circuit, and outside the `ux.deeplink_router_v2` branch so
it is captured in **both** router modes:

```ts
  // Invited league: ?league=<id> (P0-3). The invite URL mobile has emitted
  // since FB #239 is `<base>/?league=<id>&ref=<u>` — a bare-path URL, so the
  // v2 short-circuit below returns before anything reads it and the league
  // has been dropped on the floor on every invite ever sent. Read it HERE,
  // above that return, in both router modes: this one block repairs every
  // link already sitting in a Sleeper chat, and it ships UNFLAGGED (HLD
  // S-13). The path form /app/league/join/:leagueId does NOT go through
  // here — LeagueJoinScreen owns that form's intent (one owner per form).
  const lg = parsed.queryParams?.league;
  const lgStr = Array.isArray(lg) ? lg[0] : lg;
  if (typeof lgStr === 'string' && lgStr.trim()) {
    void useSession.getState().setInvitedLeague(lgStr.trim());
  }
```

Notes an executor must not get wrong:

- **`void`** because `setInvitedLeague` is async (it writes AsyncStorage). `handleDeepLink`
  is sync and must stay sync — `App.tsx:161-173` calls it from a `Linking` listener and
  from `getInitialURL().then(...)`.
- The block goes **before** `const path = …`, not merely before `if (!path) return;`, so a
  reader sees the two query captures adjacent.
- No `decodeURIComponent`: `Linking.parse` already decodes `queryParams`.
- Idempotent by construction — repeat calls with the same URL re-write the same blob.

#### C1b — `V2_SCREENS` gains one route

Grep anchor `const V2_SCREENS = {` (`:95`). Insert next to the other root-stack
`app/league/*` entries, above `LeagueSummary`:

```ts
  // P0-3 — invite JOIN interstitial. ROOT stack on purpose: the invitee is
  // usually SIGNED OUT, and a route resolving inside `Main` would drop a
  // session-less user into empty tabs (exactly the failure P0-5 fixes).
  // Emitted only while `growth.invite_join_link` is on; parsed always, and
  // the legacy `/?league=` form is parsed forever (HLD S-13).
  LeagueJoin: 'app/league/join/:leagueId',
```

This single table feeds both resolution paths — react-navigation's `linking` config via
`getLinkingV2()` (cold start) and `_routePathV2()` (warm URL events) — so no second
registration is needed. `rewriteUniversalPath` is **not** touched: the path has a real
screen, so it needs no alias.

### 2.2 C2 — `useSession.ts`: the persisted invite intent

**New storage key**, declared beside the existing ones (grep anchor
`const RM_KEY = 'ftf_rank_method_pref';`, `:28`):

```ts
// P0-3 — invite intent: the league + inviter captured from an invite link,
// awaiting a pin. Persisted (web's localStorage ftf_invited_by /
// ftf_invited_league are the parity precedent, web/js/app.js:5832-5833)
// because the invitee's real path is often tap → app opens → close → return
// later, and because an account-only invitee (P0-5) can be league-less for
// several launches before they link a platform.
const INVITE_KEY = 'ftf_invite_intent';
const INVITE_TTL_MS = 14 * 24 * 60 * 60 * 1000;   // 14 days (HLD S-15)
```

**Blob shape** (all fields optional except `ts`; unknown fields ignored on read):

```ts
interface InviteIntent {
  leagueId: string | null;
  invitedBy: string | null;
  /** Display name resolved once by SignInScreen's banner via
   *  GET /api/league/invite-meta. Cached here so the LeaguePicker companion
   *  state can name the league without a second call site (§2.0). Null when
   *  unresolved — every consumer degrades to "their league". */
  leagueName: string | null;
  /** Capture time, ms epoch. TTL is evaluated on READ, never by a timer. */
  ts: number;
}
```

**State additions** (mirroring `invitedBy`, `:110` / `:363-373`):

```ts
  /** League id captured from an invite link (`?league=` or the
   *  /app/league/join path). PERSISTED with a 14-day TTL — unlike
   *  `invitedBy`, which is in-memory. Consumed when the league is pinned. */
  invitedLeagueId: string | null;
  /** Resolved league name for the invite copy, or null. */
  invitedLeagueName: string | null;

  setInvitedLeague: (leagueId: string) => Promise<void>;
  setInvitedLeagueName: (name: string) => Promise<void>;
  consumeInvitedLeague: () => Promise<string | null>;
```

**Semantics — each one is load-bearing:**

| Action | Behaviour |
|---|---|
| `setInvitedLeague(id)` | trims; no-ops on empty. Sets `invitedLeagueId`, **stamps a fresh `ts`**, and clears `invitedLeagueName` **when the id changed** (a stale name on a new league is worse than no name). Writes the blob merged with the current `invitedBy`. Last-write-wins. |
| `setInvitedLeagueName(name)` | no-ops when `invitedLeagueId` is null or `name` is blank. Patches `leagueName` only; **does not** re-stamp `ts` (resolving a name is not a fresh invite). |
| `consumeInvitedLeague()` | returns the current `invitedLeagueId` (or null), then clears `invitedLeagueId` + `invitedLeagueName` in state **and removes the key from AsyncStorage**. Consume-on-**pin**, never on read: only the caller that has actually pinned the league calls it. |
| `setInvitedBy(u)` | **extended**: after `set({ invitedBy: u })` it also merges `invitedBy` into the persisted blob (fire-and-forget, `void`), so a `?ref=`-only capture survives a relaunch the same way the league does. Its existing in-memory semantics and `consumeInvitedBy()` are unchanged — `api/auth.ts` keeps consuming it exactly as today. |
| `bootstrap()` | reads `INVITE_KEY` alongside the existing five reads (extend the `Promise.all` at `:199-206`). Parse defensively in a `try {} catch {}` like its neighbours. **TTL sweep on read:** `Date.now() - ts > INVITE_TTL_MS` ⇒ treat as absent **and** `AsyncStorage.removeItem(INVITE_KEY)` (fire-and-forget) so an expired blob is not re-evaluated on every launch. Hydrates `invitedLeagueId`, `invitedLeagueName`, and — only when `invitedBy` is not already set in memory — `invitedBy`. |
| `signOut()` | adds `AsyncStorage.removeItem(INVITE_KEY)` to the existing `Promise.all` (`:469-474`) and `invitedLeagueId: null, invitedLeagueName: null` to the `set({...})` block (`:475-485`, which already nulls `invitedBy`). |

**Do not** touch `revalidateSession`, `connectLeague`, `switchLeague` or the `NO_LEAGUE_ID`
export. `NO_LEAGUE_ID` is read by P0-5's predicate; P0-3 reads it nowhere.

**The rule that keeps P0-5's relaunch guard from fighting this (HLD §1.2 Spine A item 1,
and P0-5 §8 OQ-2 item 2):** the invited league becomes active **only** by
`LeaguePickerScreen.pickLeague(lg, { auto: true })`, which calls `setLeague({league_id,
league_name})` and thereby **overwrites the `no_league` sentinel**. P0-3 introduces no
parallel "active invited league" field and never writes `league` directly. If it did, an
account-only invitee would be pinned in memory while the persisted league stayed the
sentinel, and P0-5's `hasRealLeague` predicate would bounce them back to the picker on
every cold start — forever.

### 2.3 C3 — `LeagueJoinScreen.tsx` (new)

Root-stack interstitial. Props come from the route: `{ leagueId: string; ref?: string }`.

**Mount effect, in this order, once (`useRef` guard — the screen must be idempotent under
a re-render or a repeat tap on the same link):**

1. `void setInvitedLeague(leagueId)` — this is the path form's intent owner (C1a
   deliberately skips the path form).
2. `if (route.params?.ref) setInvitedBy(route.params.ref)` — belt-and-braces; the existing
   `?ref=` capture in `handleDeepLink` normally has it already, and `setInvitedBy` is
   last-write-wins.
3. `track('invite_link_opened', {...})` — see [§3](#3-events).
4. Decide and `replace()`, per the table below.

**The four-way decision** (HLD §1.3, S-17). Read state via
`useSession.getState()` inside the effect — this is a decision, not a render:

| Case | Condition | Action |
|---|---|---|
| **A — signed out** | `!user` | `navigation.replace('SignIn')`. The intent is already persisted, so the banner renders and the post-auth journey picks it up. |
| **B — member** | `user && !user.account_only` and `leagues.some(l => l.league_id === leagueId)` | `await pick` is **not** done here. `navigation.replace('LeaguePicker', { autoPinLeagueId: leagueId })` — the picker's auto-pin effect (§2.5) owns every pin, so there is exactly one pin implementation. The picker paints for one frame at most before `pickLeague(auto)` navigates to `Main`. |
| **C — signed in, not a member** | `user && !user.account_only` and the id is absent from `leagues` | `navigation.replace('LeaguePicker', { inviteNotice: true })` → honest notice row (§2.5). Never a spinner that never ends. |
| **D — account-only** | `user?.account_only === true` | `navigation.replace('LeaguePicker', { invitedBy, invitedLeagueName })` → **P0-5's companion state, carrying inviter + league context.** Never attempt a pin: an `acct_` user has no Sleeper roster in that league and `buildSessionInitBody`'s Sleeper branch would produce an empty `user_player_ids` (P0-5 §8 OQ-2 item 3). |

**Cases B and C both route through the picker on purpose.** `leagues` may be a *stale
cache* (`useSession.leagues` is the persisted switcher list). Handing the decision to the
picker — which refreshes and whose auto-pin effect keys on `cached` — means a
membership that only *appears* absent resolves itself the moment the refresh lands,
with no second code path. `autoPinLeagueId` / `inviteNotice` are therefore **hints, not
commands**; the picker re-derives the truth.

**Demo sessions:** `useSession.getState().isDemo === true` ⇒ treat as case C and
additionally **do not** consume the intent. A demo user must not be pinned into a real
league; the intent survives for their real sign-in. (Manual test 15 in the plan.)

**Render** (it is on screen for one frame in the common case, several seconds on a cold
start behind `bootstrap()`):

- `testID="leaguejoin.root"` on the SafeAreaView.
- `testID="leaguejoin.title"` — `Joining {name}…` where `name` is
  `invitedLeagueName ?? leagues.find(...)?.name ?? 'your league'`. **No fetch** (§2.0).
- `<ActivityIndicator color={ice.base} />`.
- Honest failure state, reached only if the decision throws or `leagueId` is missing:
  `testID="leaguejoin.not-member"` copy + `testID="leaguejoin.cta"` button labelled
  **"Choose a league"** → `replace('LeaguePicker')`. Never a dead end, never a bare
  spinner.
- Chalkline tokens only (`ink`, `chalk`, `ice`, `space`, `radii`, `type` from
  `../theme/chalkline`). No emoji, no gradient, no radius > 8.

**Law 5 note for the flow author:** this screen renders an `ActivityIndicator`, so its
Maestro leg takes its screenshot immediately after the trigger and never after
`waitForAnimationToEnd`.

### 2.4 C4 — `RootNav.tsx`: registration and param plumbing

Three edits, all in wave 2, all on top of P0-5's landed changes.

1. **`AuthStack` param list** (grep anchor `type AuthStack = {`, `:50`):
   ```ts
   // P0-3 — invite join interstitial. ROOT stack: reachable while signed out.
   LeagueJoin: { leagueId: string; ref?: string };
   ```
   and **extend the existing `LeaguePicker` entry** (currently
   `LeaguePicker: { espnLink?: boolean } | undefined;`) to
   ```ts
   LeaguePicker: {
     espnLink?: boolean;
     /** P0-3 case B — hint that this league should auto-pin if present. */
     autoPinLeagueId?: string;
     /** P0-3 case C — render the "not in that league yet" notice row. */
     inviteNotice?: boolean;
     /** P0-3 case D — invite context for P0-5's companion state. */
     invitedBy?: string;
     invitedLeagueName?: string;
   } | undefined;
   ```

2. **Register the screen** in the `Stack.Navigator` (grep anchor
   `<Stack.Screen name="LeagueSummary"` or `<Stack.Screen name="Profile"`), as a plain
   `component={LeagueJoinScreen}` with `options={{ headerShown: false }}` — it is an
   interstitial, not a pushed detail screen, and it must not present a back edge to a
   spent link.

3. **Pass the picker's new params through to props** in the existing
   `<Stack.Screen name="LeaguePicker">` render callback (grep anchor
   `autoOpenEspnLink={route.params?.espnLink === true}`):
   ```ts
   autoOpenEspnLink={route.params?.espnLink === true}
   autoPinLeagueId={route.params?.autoPinLeagueId}
   inviteNotice={route.params?.inviteNotice === true}
   invitedBy={route.params?.invitedBy}
   invitedLeagueName={route.params?.invitedLeagueName}
   ```
   `invitedBy` / `invitedLeagueName` are the **optional props P0-5 already declared** in
   commit 7 (HLD §4 W1-P05, §9 LLD-4). W2-P03 supplies them; it does not redefine them. If
   they are absent from the landed `LeaguePickerScreen` props at rebase time, **stop and
   raise it** — do not invent a second companion-state surface.

**Do not touch** `RootNav.tsx:341` (`applyTestRouteEntry`) — commit 6 already changed it to
`applyTestRouteEntry(navigationRef, { authed: initialRoute === 'Main' })` and owns the
signed-out allowlist. P0-3's M12 is **delivered by P0-5's commit 6**, not by this one (HLD
§5.2, S-16/S-21).

**Do not touch** the `initialRoute` predicate — P0-5 owns it, and P0-3 needs no change
there: a signed-out invitee lands on `SignIn` by the existing rule, and the launch-arg
harness enters `LeagueJoin` through `SIGNED_OUT_ENTRY_ROUTES`.

### 2.5 C5 — `LeaguePickerScreen.tsx`: the auto-pin effect and the notice

**New optional props** (added to the existing `Props` interface next to
`autoOpenEspnLink`; P0-5's `invitedBy` / `invitedLeagueName` are already there):

```ts
  /** P0-3 — case-B hint from LeagueJoinScreen. The effect below re-derives
   *  membership from `cached`, so this is an optimization, not a command. */
  autoPinLeagueId?: string;
  /** P0-3 — case-C hint: render the invite notice row. */
  inviteNotice?: boolean;
```

**The auto-pin effect.** Placed immediately **after** the existing single-league auto-skip
effect (grep anchor `const autoSkipTried = useRef(false);`, `:120-129`) so the two
programmatic pins are adjacent and their precedence is visible.

```ts
  // P0-3 — pin the invited league as soon as it appears in the list.
  //
  // Mirrors web one-for-one (web/js/app.js:589-601: read
  // localStorage.ftf_invited_league, findIndex over the loaded leagues,
  // remove the key = consume, selectLeague). Keyed on `cached`, NOT on mount,
  // and that is the whole trick: an account-only invitee (P0-5) arrives with
  // zero leagues, links Sleeper/ESPN/MFL from the companion state, and the
  // list repopulates — this effect re-fires and pins, with neither fix
  // knowing about the other.
  //
  // pickLeague({auto:true}) is the ONLY pin path: it calls setLeague(), which
  // OVERWRITES the `no_league` sentinel, so P0-5's relaunch predicate sends
  // the user to Main on every subsequent cold start instead of bouncing them
  // back here forever.
  const invitePinTried = useRef(false);
  useEffect(() => {
    if (invitePinTried.current) return;
    if (loading || error || selectingId) return;
    const wanted = useSession.getState().invitedLeagueId ?? autoPinLeagueId ?? null;
    if (!wanted) return;
    const lg = cached.find((x) => x.league_id === wanted);
    if (!lg) return;                       // not (yet) a member — notice row below
    invitePinTried.current = true;
    void (async () => {
      await useSession.getState().consumeInvitedLeague();   // consume ON PIN
      await pickLeague(lg, { auto: true });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cached, loading, error, selectingId, autoPinLeagueId]);
```

Precedence and ordering, stated so it is not rediscovered on device:

- The **auto-skip** effect (`cached.length === 1`, flag `onboarding.league_autoskip`) fires
  first when the invited league is the user's only league. Both end in
  `pickLeague(cached[0], { auto: true })` — the same destination — and `pickLeague`'s own
  `if (!user || selectingId) return;` guard makes the second call a no-op. The only
  visible consequence is that the intent is consumed by whichever ran; the invite effect's
  `invitePinTried` guard plus the consume-before-pin ordering keeps the blob from being
  left behind. **Consume before pin, not after** — `pickLeague` navigates away, and code
  after a navigation is a coin flip.
- `advanceGuideIfActive('s1.1')` is skipped by `pickLeague` for `auto: true`, so the guided
  tour is unaffected. That is existing behaviour, relied on, not changed.
- The effect never runs while `selectingId` is set, so it cannot race a manual tap.

**The notice row.** Rendered when an intent exists, the list has loaded, and the wanted id
is **not** in `cached`:

```tsx
{showInviteNotice ? (
  <Text testID="leaguepicker.invite-notice" style={styles.inviteNotice}>
    You're not in that league yet — pick one below, or join the league on
    Sleeper and open the invite again.
  </Text>
) : null}
```

- `showInviteNotice = !!wantedId && !loading && !error && cached.length > 0 &&
  !cached.some(l => l.league_id === wantedId)` — plus `inviteNotice === true` as an
  additional trigger for case C when the store's intent has already been consumed.
- Placed **above the list**, inside the list branch. **Not** rendered in the
  `cached.length === 0` branch: that branch is either P0-5's companion state (which carries
  the invite copy itself, below) or the untouched
  `"No 2026 NFL leagues found for this account."` sentence that
  `capture/leagues@fresh.yaml` asserts literally. **That sentence must not move.**
- The intent is **not** consumed here. The user may join the league on Sleeper and come
  back within the TTL, and the effect will fire on the refreshed list.
- Emits `invite_pin_failed { reason: 'not_member' }` **once per mount** (a `useRef` guard),
  not once per render.

**Case D wiring.** P0-5's companion state already accepts `invitedBy` /
`invitedLeagueName` and forks its copy on them. W2-P03's only job is to supply them, and to
supply them from **two** sources with this precedence:

```ts
const inviteName = invitedLeagueName ?? useSession.getState().invitedLeagueName ?? null;
const inviteBy   = invitedBy ?? useSession.getState().invitedBy ?? null;
```

Route params win (a link tapped *this* launch), the persisted intent is the fallback (the
user signed in with Apple three launches ago and only now linked a platform). The copy fork
itself is P0-5's, verbatim from HLD §1.3:

> **@matt** invited you to **Lakeview Dynasty** — connect Sleeper, ESPN or MFL to join.

degrading to `…invited you to their league — connect Sleeper, ESPN or MFL to join.` when
`inviteName` is null, and to P0-5's own
`Connect Sleeper, ESPN or MFL to see your leagues.` when `inviteBy` is null too.

**Do not** change `refresh()`, the footer suppression, the header copy, or the
`account_only` Sleeper skip — all four are P0-5's, landed in commit 7.

### 2.6 C6 — `SignInScreen.tsx`: the invited banner

**Placement:** directly beside the existing `reauthNotice` block (grep anchor
`{reauthNotice ? (`, `:375-380`), **inside `styles.form`**, so it renders in **both**
`landingOn` variants. This matters: with `onboarding.landing` ON the Apple entry demotes to
a text link (`:519-540`) and the whole layout above changes — a banner attached to the
Apple block would vanish exactly for the users P0-9 is testing.

```tsx
{invitedBy || invitedLeagueId ? (
  <Text testID="signin.invited-banner" style={styles.invitedBanner}>
    {inviteHeadline}
  </Text>
) : null}
```

`inviteHeadline`:

| `invitedBy` | resolved name | Copy |
|---|---|---|
| `matt` | `Lakeview Dynasty` | `@matt invited you to Lakeview Dynasty — sign in and we'll take you straight there.` |
| `matt` | null | `@matt invited you to their league — sign in and we'll take you straight there.` |
| null | `Lakeview Dynasty` | `You were invited to Lakeview Dynasty — sign in and we'll take you straight there.` |
| null | null | banner not rendered |

**The acceptance criterion is met by row 2**, with no endpoint at all. Rows 1 and 3 are the
upgrade.

**The one fetch (§2.0):**

```ts
  // P0-3 — resolve the invited league's name once, for the banner. Cached
  // into the persisted invite intent so the LeaguePicker companion state
  // (P0-5) can name the league without a second call site — see the
  // vcr_misses rail in lld-p0-3 §2.0. Never throws, never blocks the form.
  useEffect(() => {
    const id = invitedLeagueId;
    if (!id || invitedLeagueName) return;
    let alive = true;
    void fetchInviteMeta(id).then((meta) => {
      if (!alive || !meta?.league_name) return;
      void useSession.getState().setInvitedLeagueName(meta.league_name);
    });
    return () => { alive = false; };
  }, [invitedLeagueId, invitedLeagueName]);
```

- Reads `invitedLeagueId` / `invitedLeagueName` as zustand selectors so the banner
  re-renders when the name lands.
- **No loading state, no error state, no retry.** A missing name is a copy fallback, not a
  failure the user should see.
- Style `invitedBanner` mirrors `reauthNotice` (same slot, same rhythm): `type.bodySm`,
  `chalk.dim`, ice tick or ice accent only. No new visual pattern.

**Do not touch** the Apple SDK-call substitution — that is P0-5's commit 6 and this file's
only other change in the batch.

### 2.7 C7 — `InviteLeaguematesBanner.tsx`: the flagged emitter and the stale comment

**Delete this comment** (`mobile/src/components/InviteLeaguematesBanner.tsx:34-37`),
quoted verbatim:

```ts
  // S7 PRD-01 (growth.share_landing): the invite URL already IS the landing
  // page with ?ref= attribution preserved (verified against
  // utils/deepLinks + web captureReferralFromUrl) — no URL change needed;
  // the flag adds the share→open funnel event only.
```

It is **half true and wholly load-bearing in the wrong direction**: "verified against
utils/deepLinks" is false — `utils/deepLinks.ts` had no `?league=` reader, which is the
entire bug. It is the same comment-over-code failure class as finding A-33. Replace it
with a statement of what `growth.share_landing` actually gates (the `invite_shared` call,
nothing else) and leave the URL-format explanation inside `buildInviteUrl`, where the
decision now lives.

Also amend the file-header comment (`:9-18`), whose parenthetical
`(`/?league=<id>&ref=<username>` — captured by captureReferralFromUrl and utils/deepLinks
on the receiving end)` asserts the same false thing, to name **both** accepted formats and
the rule that the legacy one is parsed forever.

**`buildInviteUrl` — the flag read moves inside the function** (HLD §10.2, mandated):

```ts
/** The invite URL. Two accepted formats, and BOTH are parsed forever:
 *
 *   flag OFF (default) — <base>/?league=<id>&ref=<u>      (every link ever shared)
 *   flag ON            — <base>/app/league/join/<id>?ref=<u>
 *
 * The flag is read IMPERATIVELY, inside this function, so both call sites
 * (this banner's handleInvite, and LeagueScreen's inviteLeaguemates) stay
 * byte-identical one-liners and cannot drift into emitting different formats.
 * This is a callback-time read, never a render-time one — the same
 * useFeatureFlags.getState() idiom as ratingPrompt.ts:45 and TabNav.tsx:583.
 * Do NOT convert it to a useFlag() hook: this is a module-level pure
 * function called from handlers, not a component.
 *
 * `ref` stays optional — an unknown username omits it, which is why AASA
 * must match `league` on its own (FB #239).
 */
export function buildInviteUrl(leagueId: string, username?: string | null): string {
  const base = getBaseUrl();
  const ref = username ? `?ref=${encodeURIComponent(username)}` : '';
  if (useFeatureFlags.getState().flags['growth.invite_join_link'] === true) {
    return `${base}/app/league/join/${encodeURIComponent(leagueId)}${ref}`;
  }
  const params = [`league=${encodeURIComponent(leagueId)}`];
  if (username) params.push(`ref=${encodeURIComponent(username)}`);
  return `${base}/?${params.join('&')}`;
}
```

- `=== true` explicitly: an unhydrated flag map must emit the **legacy** URL, never the new
  one. Fail-safe direction matters here — a wrong `false` costs nothing, a wrong `true`
  before AASA propagates sends invites to Safari.
- The import changes from `useFlag` to `useFlag, useFeatureFlags` — `useFlag` is still used
  for `growth.share_landing` at `:38`.
- **`LeagueScreen.tsx:373` is not edited.** It calls `buildInviteUrl(leagueId,
  user?.username)` and now gets the flagged format for free. That is the whole point of
  §10.2.

### 2.8 C8 — `mobile/src/api/league.ts`: `fetchInviteMeta`

Appended to the existing module (it is `league.ts`, singular — plan M11's `leagues.ts` does
not exist; HLD §10.5).

```ts
/** P0-3 — public league name for an invite banner. Unauthenticated,
 *  short-deadline, NEVER throws: a null return means "say 'their league'".
 *  ONE call site by design (SignInScreen) — see lld-p0-3 §2.0. */
export interface InviteMeta {
  league_id: string;
  league_name: string | null;
  platform: string | null;
}

export async function fetchInviteMeta(leagueId: string): Promise<InviteMeta | null> {
  if (!leagueId) return null;
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), 4000);
  try {
    return await api.get<InviteMeta>(
      `/api/league/invite-meta?league_id=${encodeURIComponent(leagueId)}`,
      { skipAuth: true, signal: ac.signal },
    );
  } catch {
    return null;                      // degrade: the banner names the inviter only
  } finally {
    clearTimeout(t);
  }
}
```

- `skipAuth: true` (`RequestOptions.skipAuth`, `client.ts:286`) — the caller is a
  **signed-out** screen; attaching a stale token would be meaningless and would let a
  401-expiry hook fire on a cosmetic request.
- 4s `AbortController` deadline, not the default: a sign-in screen must never wait on a
  cosmetic string. (`AbortSignal.timeout` is not relied on — RN's availability varies.)
- The `catch` swallows everything. `api_request_failed` still fires from the client wrapper
  (`client.ts` `_reportApiFailure`), so the failure remains observable without a UI state.

---

## 3. Events

**Registration is not P0-3's.** All four names land in **commit 1** (`W0-TAX`,
`backend/analytics_taxonomy.py` + `backend/analytics_queries.py`) per HLD S-18/S-36.
**W2-P03 must not open either registry file**, and must not ship a `track()` call before
commit 1 has landed — the ingest path is default-deny with a 200 response
(`backend/analytics_ingest.py:376`), so an early emission is counted-and-dropped in silence.

Rows W0-TAX registers on P0-3's behalf, restated here so the two documents can be diffed:

| Event | `CLIENT_EVENT_PROPS` | Emitted from | New? |
|---|---|---|---|
| `invite_shared` | `{league_id}` | `InviteLeaguematesBanner.handleInvite` — **already exists** at `:47`, gated on `growth.share_landing` | **No new emission.** Registration only. It has been firing into a default-deny wall since it shipped, which is why "the loop converts zero" has never been measurable. |
| `invite_link_opened` | `{league_id, has_ref, format, auth_state}` | `LeagueJoinScreen` mount effect (path form) **and** the C1a `?league=` capture (legacy form) | Yes |
| `invite_league_pinned` | `{league_id, source, ms_since_open}` | `LeaguePickerScreen` auto-pin effect, immediately before `pickLeague` | Yes |
| `invite_pin_failed` | `{league_id, reason}` | the notice-row branch (`not_member`), once per mount | Yes |

**Property discipline — no PII, and the reason:**

- `has_ref: boolean`, never the username. The inviter's handle rides on
  `/api/session/init.invited_by` as it does today (`mobile/src/api/auth.ts:389-392, 406`);
  it is an attribution field, not an analytics dimension.
- `format: 'legacy' | 'path'` — the one number that answers "did the new URL help?".
- `auth_state: 'signed_out' | 'authed_member' | 'authed_non_member' | 'account_only'` —
  four values, matching LeagueJoinScreen's four cases. (The scope block listed three; case D
  is the HLD's S-17 addition and needs its own value or the account-only funnel is
  invisible. Flagged to W0-TAX.)
- `source: 'picker_autopin'`. The scope block also allowed `'join_screen'`; §2.3 case B
  routes every pin through the picker, so **only `picker_autopin` is ever emitted**.
  `'join_screen'` stays registered as an allowed value — a registry that permits a value
  nobody sends is harmless; a value sent but unregistered is silently dropped.
- `reason: 'not_member' | 'expired'`. `'session_init_failed'` is registered but not emitted
  by this build — `pickLeague`'s failure path is P0-2/P0-5 territory and instrumenting it
  from here would double-count.
- `ms_since_open` — `Date.now()` minus the intent's `ts`. Bounded by the 14-day TTL.
- **Intent classification:** all four are ordinary INTENT events. None is a high-frequency
  impression, so none belongs in `NON_INTENT_EVENTS` (contrast `tab_selected` / `league_view`,
  HLD S-32). W0-TAX must not add them there.

**A measurement gap this build does not close, recorded rather than fixed:**
`invite_shared` fires from `InviteLeaguematesBanner` only. The second share site,
`LeagueScreen.tsx:369-381` (`inviteLeaguemates`), fires **nothing** — so League-tab invites
are invisible even after registration. `LeagueScreen.tsx` belongs to W2-P07 in wave 2 and
P0-3 may not touch it (HLD §10.2). → **`NEXT.md` row**, supplied by W2-P03's scope block to
W3-DOCS: *"`invite_shared` is not fired from the League tab's Invite module
(`LeagueScreen.tsx` `inviteLeaguemates`) — half the invite volume is unmeasured."*

---

## 4. Maestro

**One new file: `mobile/.maestro/flows/league/invite-join.yaml`.** Header
`# tc: TC-P03-01`, `# profile: standard`, `# flags: release`, `tags: [league]`.

Entry is **launch arguments only** — `openLink` raises an undismissable SpringBoard confirm
on iOS 18 (law 17, `mobile/.maestro/README.md:140-146`). Params are a **query string, never
JSON** (`testRouteEntry.ts:111-120`).

### Block 1 — authed member → pinned

1. Sign in as `qa_standard` using the retry-hardened preamble **verbatim** from
   `flows/league/03-no-picks-league.yaml:25-48` (law 10 — assert the typed username before
   submitting). Settle on `tab.trades`.
2. Relaunch:
   ```yaml
   - launchApp:
       clearState: false
       stopApp: true
       arguments:
         FTFTestRoute: LeagueJoin
         FTFTestRouteParams: "leagueId=990000000000000001&ref=qa_inviter"
   ```
   `clearState: false` is deliberate — the persisted session **and** the persisted invite
   intent are what the flow is about (law 6).
3. `extendedWaitUntil: visible: id: "leaguejoin.root"` (10 000 ms).
4. `extendedWaitUntil: visible: id: "tab.trades"` (30 000 ms) — landed in the tabs.
5. `- tapOn: {id: "tab.league"}` then assert the seeded league name is visible
   (`text: ".*QA Standard League.*"`, law 1 — full-match regex, wrapped in `.*`). Law 8:
   the tab tap comes only after step 4 settled on a surface-owned control.
6. `takeScreenshot: p0-3-invite-pinned`.

### Block 2 — authed non-member → honest notice

1. Relaunch with `FTFTestRouteParams: "leagueId=990000000000000099&ref=qa_inviter"` — an id
   **not** in the seeded list.
2. `assertVisible: id: "leaguepicker.invite-notice"`.
3. `assertVisible: id: "leagues.row.990000000000000001"` — the real list is still usable.
4. `assertNotVisible: id: "tab.trades"` — it did **not** silently pin anything.
5. `takeScreenshot: p0-3-invite-not-member`.

**No `fetchInviteMeta` call is reachable in this block** — that is what keeps
`vcr_misses` at 0 for an unseeded id (§2.0). A reviewer who later adds a meta fetch to
`LeagueJoinScreen` or `LeaguePickerScreen` breaks this block's rails audit, not its
assertions, which is the hard failure to anticipate.

### Block 3 — signed-out → inviter named (needs the §5 harness seam)

1. ```yaml
   - launchApp:
       clearState: true
       clearKeychain: true
       stopApp: true
       arguments:
         FTFTestRoute: LeagueJoin
         FTFTestRouteParams: "leagueId=990000000000000001&ref=qa_inviter"
   ```
2. `extendedWaitUntil: visible: id: "signin.invited-banner"` (15 000 ms).
3. `assertVisible: text: ".*qa_inviter invited you to.*"` (law 1).
4. `takeScreenshot: p0-3-invite-signed-out`.

This block depends on **commit 6** — `SIGNED_OUT_ENTRY_ROUTES = new Set(['LeagueJoin'])`
inside `testRouteEntry.ts`, and `applyTestRouteEntry(ref, { authed })` in `RootNav`
(HLD §5.2, S-16/S-21). W2-P03 **consumes** that seam; it does not build or modify it. If
commit 6 has not landed at rebase time, block 3 does not run and the coverage gap is
escalated to the operator — it is **not** silently dropped.

**The seeded league id `990000000000000001` in step 1 is load-bearing**, not incidental:
the signed-out banner is the one screen that calls `fetchInviteMeta`, the server resolves
it through `_fetch_sleeper_league_meta` → `_sleeper_get`, and the harness serves
`sleeper/standard/league/990000000000000001.json` — a cassette **hit**. Any other id is a
`vcr_misses` increment and a red sim run (§2.0).

### New `testID`s

`leaguejoin.root` · `leaguejoin.title` · `leaguejoin.not-member` · `leaguejoin.cta` ·
`signin.invited-banner` · `leaguepicker.invite-notice`

All plain string literals — `mobile/scripts/testid-lint.sh` finds them by source grep over
`mobile/src`, so **no `testid-lint-allow.txt` entry is needed** (law 4). Registry rows in
`mobile/src/components/CLAUDE.md` are documentation and belong to **W3-DOCS** — the lint
never opens that file (HLD §10.3), so they are not a wave-2 dependency.

### Manual-QA-only, and why each one cannot be automated

| Leg | Why the harness cannot cover it |
|---|---|
| **Real universal-link tap** (`https://…/app/league/join/<id>` from Messages or Safari) | `openLink` is dead in this harness (law 17). AASA resolution is an OS-level behaviour with no simulator seam at all. This is the acceptance criterion's literal wording, so it **must** be a manual TestFlight test, on a build installed **after** the AASA deploy. |
| **Legacy `/?league=&ref=` link, cold and warm** | Same reason — it is a link tap. This is the leg that proves every already-shared link is repaired, so it is the **most important manual test in P0-3** despite covering the least new code. |
| **Web fallback** (302 → banner → sign in → league auto-selected) | Runs in a browser, outside the mobile harness entirely. Verified by `curl -I` for the 302 plus one manual browser pass. |
| **Case D — account-only + invited** | Needs P0-5's `FTFTestAppleSub` seam **and** the `LeagueJoin` launch arg in one launch. Composable in principle; out of scope for this flow, which the HLD scopes to three blocks. Covered by manual test 16 in `plan-p0-3.md`. |
| **14-day TTL expiry** | A clock-dependent assertion. Covered by reading the code plus one manual `AsyncStorage` inspection; a fake-clock harness for this alone is out of proportion. |
| **Demo-session no-op** | No demo profile is wired into the invite path; one manual pass (plan test 15). |

### Existing flows that must pass **unmodified**

`capture/leagues@fresh.yaml` (asserts the literal `No 2026 NFL leagues found for this
account.` sentence — the notice row must not leak into that state) and the full 11-flow
smoke suite. Smoke creates no invite intent, so the banner and notice never render in it —
**asserted by running the suite, not assumed** (scope §3).

---

## 5. Verification checklist per commit

**Commit 3 (W1-BE), before handing off:**

- [ ] `python3 -m pytest backend/tests/ -q` green — **including** the two updated existing
      tests (§1.6).
- [ ] `python3 -m pytest backend/tests/test_invite_links.py -q` — 13 cases.
- [ ] `curl -s localhost:5000/.well-known/apple-app-site-association | python3 -m json.tool`
      — eyeball that `/app/*` is **not** claimed.
- [ ] `curl -sI "localhost:5000/app/league/join/123?ref=matt"` → `302`,
      `Location: /?league=123&ref=matt`.
- [ ] `grep -n "growth.invite_join_link" backend/feature_flags.py config/features.json backend/tests/fixtures/flags/release.json`
      → three hits, all `false` where a value is present.
- [ ] No client file touched in this commit.

**Commit 12 (W2-P03), before handing off:**

- [ ] `cd mobile && npx tsc --noEmit` clean.
- [ ] `bash mobile/scripts/testid-lint.sh` clean.
- [ ] `grep -rn "fetchInviteMeta" mobile/src` → exactly two hits (§2.0).
- [ ] `git diff --name-only` contains **no** `mobile/src/screens/LeagueScreen.tsx`, no
      `backend/analytics_taxonomy.py`, no `backend/analytics_queries.py`, no
      `mobile/src/utils/testRouteEntry.ts`.
- [ ] The `?league=` capture sits **above** `if (!path) return;` — verified by reading the
      final diff, not by trusting the patch.
- [ ] `capture/leagues@fresh.yaml`'s literal sentence is untouched in
      `LeaguePickerScreen.tsx`.
- [ ] The stale comment at `InviteLeaguematesBanner.tsx:34-37` is **gone**, not amended in
      place.

---

## 6. Deviations from the plan

Every deviation below is either mandated by the HLD or forced by code read in this
worktree. None reopens a settled decision.

| # | Plan said | This LLD does | Why |
|---|---|---|---|
| **D-1** | M3: edit `LeagueScreen.tsx:373` so both emitters agree | `LeagueScreen.tsx` is **not touched**; the flag read lives inside `buildInviteUrl` | **HLD §10.2, mandated.** `buildInviteUrl` is a module-level pure function called from handlers at both sites, so an imperative `getState()` read closes the drift risk by construction and hands the file to W2-P07 uncontended. |
| **D-2** | B4: P0-3 registers its four event names in `analytics_taxonomy.py` | Registration is **commit 1 (W0-TAX)**; P0-3 opens neither registry file | **HLD S-18/S-36.** Register-before-emit, one owner, separately revertible. |
| **D-3** | Test 5: invite-meta "never touches the `leagues` table" | The privacy invariant is restated as **"no value from our DB ever reaches the response"**, and T-10 tests exactly that | `_fetch_sleeper_league_meta` calls `is_linked_platform_league()`, which *does* `SELECT platform FROM leagues`. That read is **how the constraint is enforced** — it is what makes ESPN/MFL names unresolvable. A literal "no query" test would forbid the guard that provides the protection. |
| **D-4** | M12: P0-3 extends `testRouteEntry.ts` + `RootNav.tsx:341` for signed-out entry | P0-3 **consumes** the seam; it is built by **P0-5's commit 6** | **HLD §5, S-16/S-21** — one unified harness extension serving both findings, no second ad-hoc hack, no third production gate. |
| **D-5** | M11: `fetchInviteMeta` in `mobile/src/api/leagues.ts` | `mobile/src/api/league.ts` (singular) | **HLD §10.5.** The plural module does not exist. |
| **D-6** | §3 flow: case B pins from `LeagueJoinScreen`; case "already active" shows a toast | Every pin routes through `LeaguePickerScreen`'s auto-pin effect; the "already active" case is folded into case B (the effect finds it in `cached`, `pickLeague` runs, `setLeague` is idempotent) | One pin implementation instead of two. A second pin path in `LeagueJoinScreen` would duplicate `buildSessionInitBody` + `setLeague` + `onLeaguePicked` and would be the likeliest place to forget the sentinel overwrite that P0-5's predicate depends on. The dropped toast was additive polish, not part of the acceptance criterion. |
| **D-7** | §4: the sign-in banner "fetches `/api/league/invite-meta` once" (no statement about other screens) | `fetchInviteMeta` has **exactly one call site**, and the resolved name is cached into the persisted invite intent for downstream screens | Forced by `mobile/scripts/sim-run.sh:178`: a fixture miss increments `vcr_misses` and **fails the sim run**. A meta fetch from `LeagueJoinScreen` or the picker would run with unseeded ids in the non-member leg. §2.0 states the rule and the reviewer check. |
| **D-8** | Scope §1: `auth_state` ∈ {`signed_out`, `authed_member`, `authed_non_member`} | Adds **`account_only`** | HLD S-17 made the account-only intersection a first-class case; without a fourth value its funnel is invisible. Flagged to W0-TAX for commit 1. |
| **D-9** | Test plan is silent on existing AASA tests | §1.6 names **two existing tests** that this change breaks or contradicts, and requires both to be fixed in commit 3 | `test_account_data_rights.py:258` asserts `detail["paths"] == ["/u/*", "/s/*"]` — an exact list equality that adding a path breaks. Commit 3 would be red on arrival. |
| **D-10** | Blob is `{leagueId, invitedBy, ts}` | Adds `leagueName` | The single-fetch rule (D-7) needs somewhere to cache the resolved name so the account-only companion state can be specific. One nullable string, cleared whenever the league id changes. |

---

## 7. Explicitly out of scope

Named so nobody re-derives them mid-build:

- **Deferred deep linking for a recipient without the app.** A user who taps the link, has
  no app, installs from the App Store, and opens it **loses the invite entirely**. iOS
  provides no deferred deep linking without a third-party attribution SDK (Branch, AppsFlyer,
  Adjust). This is not an oversight and it is not fixable within this build's constraints —
  it is a stated limitation of the design. The 302 covers the case web already converts
  (tap in Safari, sign in on the web).
- **Cross-platform invites.** An ESPN/MFL/Fleaflicker league's invitee gets
  `league_name: null` and, if the id is absent from their Sleeper list, the not-member
  notice. Honest copy, no dead end, no pin. Solving it needs a platform-agnostic league
  identity that does not exist.
- **`growth.referral`** (the give-get referral program, OFF at
  `backend/feature_flags.py:230`). Nothing here reads it. If invites graduate into that
  program, the four event names above are the ones it should build on.
- **Any web change.** `web/js/app.js` is untouched: the 302 hands off to a funnel that
  already works (`:5835-5848` capture, `:589-601` auto-select). Recorded as a decision.
- **Flipping `growth.invite_join_link` ON.** Operator action, in a later session, after the
  AASA verification sequence in [`prd-p0-3.md`](prd-p0-3.md) §4. Not a build step (HLD S-44:
  no flag defaults change anywhere in this build).
- **`/api/sleeper/propose`'s `is_linked_platform_league` guard**, `find_trades_tapped`'s
  empty prop allowlist, and the `LeagueScreen` `invite_shared` gap — all `NEXT.md` rows,
  supplied to W3-DOCS.
