# 19. Extension: Sleeper trade-screen overlay

> Tier 1 · #19 · ENH · Effort M · Sources: FTF (existing MV3 extension — unique asset, underused)

## Summary

FTF ships a Chrome/Edge MV3 extension no competitor matches; today it does one thing — injects the user's personal tier + position-rank badge next to player names on sleeper.com. This item points that beachhead at the highest-value moment on the platform: as the user (or a league-mate's offer) assembles a trade in **Sleeper's web trade screen**, the extension reads the two asset lists from the DOM, sends them to FTF's rescore endpoint, and renders the verdict banner (#6), gap, and both-team impact (#5) inline — live, updating as assets are added and removed, with "ask for more" candidates (#4) when the deal clears with headroom. Read-DOM + display only: the overlay never clicks, fills, or submits anything in Sleeper's UI, and never touches Sleeper's network APIs. Zero write, zero ToS exposure — it's a smarter pair of glasses, not a hand on the controls.

Grounding in the actual extension (read this session): `manifest.json` v0.1.0 already holds host permissions for `https://sleeper.com/*`, `https://sleeper.app/*`, the Render API host, and localhost, with `storage`/`alarms`/`tabs` permissions and a single content script (`content.js` + `content.css`) matched to all Sleeper pages. So — unusually — **no new permissions and no new host entries are required**; the deltas are a second content-script file pair, a popup toggle, and one new background message type. `content.js` also already solves the hard parts: SPA URL watching (pushState hooks + polling backstop), a MutationObserver scan loop, and three player-identification strategies (href `/players/nfl/<id>` anchors, aria-label parsing, short-name+position fallback) that the trade-screen reader will reuse. The genuinely new work is a DOM-mapping spike on Sleeper's trade builder and a debounced rescore loop against `POST /api/trades/rescore` (built by #3 — referenced here, not redesigned), plus an auth-path detail: that endpoint is session-cookie auth, while the extension speaks bearer-token to `/api/extension/*`.

## PRD

### Problem & user story

> As a user building (or reviewing) a trade on sleeper.com, I want FTF's verdict — who's favored, by how much, what it does to both rosters, and what I could ask for on top — right there on the trade screen, without alt-tabbing to FTF and rebuilding the trade by hand.

This meets users at the exact decision moment, on the platform where the trade happens. It's also the distribution wedge: the overlay verdict shows up in every screenshot a user drops into league chat.

### Goals / Non-goals

**Goals**
- Detect the Sleeper web trade screen and extract both sides' assets (players; picks if identifiable) as the user edits.
- Live-rescore via FTF (debounced) and render a compact overlay panel: verdict banner (#6 copy matrix), gap value, mini both-team impact (#5), ask-for-more chips (#4) when applicable.
- Degrade gracefully: unrecognized assets ⇒ explicit "couldn't read N assets — verdict partial" state, never a silently wrong verdict.
- One-click off: popup toggle + collapse control on the panel itself.

**Non-goals**
- No DOM writes beyond FTF's own injected panel/badges — no clicking Sleeper buttons, no form filling, no submitting, no interception of Sleeper's own network calls. (Read-only policy, same line as #79/#80.)
- No Firefox/Safari port in this pass; no Sleeper *mobile-web* layouts (desktop web first).
- No standalone value display for signed-out users — overlay requires the existing extension sign-in.

### Functional requirements

- **FR1 (spike, ships first):** map Sleeper's web trade-builder: URL pattern(s), DOM structure of each side's asset list, how players/picks are represented (href? aria-label? class names?), and how offer-review screens differ from offer-compose. Output: selector spec checked into this thread folder + fixture HTML snapshots for tests. *All current claims about that screen are unverified; nothing below assumes a specific structure.*
- **FR2** Trade-screen detection runs inside the existing content-script lifecycle (URL watcher + MutationObserver); on match, mount the overlay panel; on navigation away, unmount.
- **FR3** Asset extraction reuses `content.js`'s identification strategies in priority order (player-id href → aria-label name → short-name+position), mapped against the rankings payload already cached per league. Each extracted side is a list of player ids + an `unrecognized_count`.
- **FR4** Rescore loop: on extraction change, debounce (~500ms) → background script POSTs the two sides + league_id to the rescore endpoint → overlay renders the returned verdict/impact. In-flight de-duping; stale responses discarded by sequence number.
- **FR5** Overlay panel renders: verdict line (#6 matrix, them/you resolved via which roster is the user's — from league rosters FTF already syncs), gap value, two-row impact summary, ask-for-more chips (display-only labels; clicking copies the player name — it does NOT modify Sleeper's UI), and an FTF link to open the full card in the web app.
- **FR6** States: signed-out (one-line "Sign in to FTF" pointing at the popup), partial-read (FR3's unrecognized count), API error (retry affordance), flag-off (render nothing).
- **FR7** Popup gains an "Overlay on Sleeper trade screen" toggle persisted in `chrome.storage.local`; server-side kill switch via feature flag (FR-flag below) checked on rankings fetch.
- **FR8** Telemetry: overlay mount + rescore count batched to the backend (extension-auth'd endpoint), feeding engine-metrics (#84).

### UX notes (per client)

- **Extension only.** Panel is a fixed-position card (bottom-right of the trade area; spike confirms safe anchoring), styled in `overlay.css` consistent with the badge aesthetic; collapsible to a pill showing just the verdict color + gap.
- Copy comes from the shared #6 matrix verbatim — the overlay is the third renderer of that object, and consistency across app/extension is a cross-client invariant.
- Dual-lens footnote matters *more* here than in-app: the user may be reviewing an offer the engine never suggested, so "by your rankings you gain ~X / by consensus this favors them by ~Y" is the headline value of the overlay.

### Success metrics

- Overlay sessions per weekly-active extension user; rescores per session (proxy for live use while composing).
- Click-through from overlay → FTF web app.
- Extension installs trend after launch (distribution-wedge hypothesis), via the existing auth counts.

### Acceptance criteria

- [ ] Spike selector spec + fixture snapshots committed; extraction unit-tested against fixtures.
- [ ] Building a trade on sleeper.com shows a verdict within ~1s of each edit; removing all assets clears the panel.
- [ ] The extension performs zero DOM mutations outside its own panel/badges and zero requests to Sleeper endpoints (code-review checklist + network audit).
- [ ] Partial-read state appears when an asset can't be identified; verdict labelled partial.
- [ ] Popup toggle and server flag both kill the overlay without breaking badges.
- [ ] Works on `sleeper.com` and `sleeper.app` hosts; manifest version bumped; no new permission prompts on update (deltas are within existing grants).
- [ ] docs updated: api-reference.md (rescore auth note / new extension route), architecture.md (extension section), cross-client-invariants.md (verdict rendering parity).

## HLD

### Components touched

- `extension/manifest.json` — add `overlay.js` + `overlay.css` to the existing `content_scripts` entry (same matches); bump version. **No permission/host changes** (sleeper.com, sleeper.app, Render host, localhost already granted).
- `extension/overlay.js` (new) — detection, extraction, debounce, panel render. Shares helpers with `content.js` (factor `normalizeName`/strategy code into a shared module or duplicate minimally — MV3 content scripts can list multiple files, so a `common.js` first in the array is the clean path).
- `extension/background.js` — new message type `ftf:rescore` performing the authenticated POST (content scripts shouldn't hold the token; today the token lives in `chrome.storage.local` and background does all API calls — keep that pattern).
- `extension/popup.html/js/css` — overlay toggle.
- `backend/server.py` — make rescore reachable with extension auth (see LLD).

### Data flow

User edits trade on Sleeper → MutationObserver → `overlay.js` re-extracts sides → debounce → `chrome.runtime.sendMessage({type:'ftf:rescore', league_id, give, receive})` → background POSTs with `X-Session-Token` → server scores via the #3 rescore path (user's shrunk Elo + consensus, same valuation as the deck) → response `{verdict, impact, ask_for_more}` → overlay renders. League id comes from the existing URL parser (`detectLeagueIdFromUrl`); user's roster identity from the rankings/league payload (extend `/api/extension/rankings` to include the user's roster player-ids if not already derivable).

### Flags & config interplay

- Server flag `ext.trade_overlay` (default false), delivered to the extension piggybacked on the `/api/extension/rankings` response (add a `flags` key) so no new fetch is needed; client toggle ANDs with it.
- Consumes #6 thresholds/copy and #4's ask-for-more candidates through the rescore response — the extension holds no threshold logic.
- `model_config`: `ext_rescore_debounce_ms` served in the same payload if we want server-tunable pacing (nice-to-have).

## LLD

### API changes (routes + example payloads)

`POST /api/trades/rescore` exists per 03-swap-player-counter.md (web session auth). Extension access options, pick one in implementation review:

1. **Preferred:** accept `X-Session-Token` (extension bearer) on `/api/trades/rescore` alongside cookie auth — the token already resolves to a user-scoped session with per-format RankingServices (`_extension_build_session`).
2. Thin wrapper `POST /api/extension/rescore` that validates the token and delegates to the same internal function (matches the existing `/api/extension/*` convention and keeps CORS/token handling in one route family).

Request/response (either route):

```json
POST { "league_id": "112233", "give": ["8136"], "receive": ["4046","pick:2027:2"], "perspective": "self" }
→ 200 { "verdict": {"band":"slight","favored":"them","gap_value":480,...},
        "impact": {"you":{...},"them":{...}},
        "ask_for_more": [{"player_id":"7564","name":"...","value":310}],
        "unpriced": [] }
```

New (small): `POST /api/extension/telemetry` `{counts:{overlay_mounts:n, rescores:m}}`, token-auth, batched.

### Schema changes

None. (Telemetry lands in `user_events` via `record_event`.)

### Client changes (extension manifest deltas)

`manifest.json` delta — the only structural change:

```diff
   "content_scripts": [
     {
       "matches": ["https://sleeper.com/*", "https://sleeper.app/*"],
-      "js":  ["content.js"],
-      "css": ["content.css"],
+      "js":  ["common.js", "content.js", "overlay.js"],
+      "css": ["content.css", "overlay.css"],
       "run_at": "document_idle",
       "all_frames": false
     }
   ],
-  "version": "0.1.0",
+  "version": "0.2.0",
```

Plus: new `extension/common.js` (shared name-normalization + strategy helpers extracted from `content.js`), `extension/overlay.js`, `extension/overlay.css`; `background.js` `ftf:rescore` + telemetry handlers; popup toggle. Permissions (`storage`, `alarms`, `tabs`) and `host_permissions` unchanged — store review friction stays minimal and existing users get no re-consent prompt.

### Sleeper integration notes (read-only boundary)

- Interaction with Sleeper is **DOM reading on a page the user already has open**, plus FTF's own injected elements. No Sleeper API calls, no auth tokens, no synthetic events into Sleeper's UI (the ask-for-more chip copies to clipboard precisely to avoid "helpfully" mutating their builder). This is the same posture as the shipped badge feature, extended to one more screen.
- **Unknowns:** trade-builder URL pattern and DOM shape (FR1 spike — fragile-by-nature; the selector spec + fixtures and the partial-read state are the mitigations); whether picks are identifiable in that DOM (if not, v1 prices players only and lists picks as unpriced — shown, not guessed). Pending-offer *API* readability is irrelevant here (that's #11/#83) — the overlay reads offers only when the user opens them on screen, which no auth question touches.
- Breakage protocol: when Sleeper ships a redesign, extraction fails closed (panel shows "can't read this screen — open in FTF"), never a wrong verdict. Add a runbook entry.

### Rollout

Server flag `ext.trade_overlay` default **false**; ship extension v0.2.0 with the client toggle defaulting **on** but inert until the server flag flips. Order: spike → fixtures + extraction tests → operator dogfood against a real league → flip flag → store update notes. Web-store review lag (days) is the schedule driver — submit early; the server flag decouples release from activation.

### Open questions

1. Spike outputs: URL pattern(s) for compose vs. review screens; DOM identification quality (href ids available, or names only?); pick representation.
2. Rescore auth: option 1 (token on `/api/trades/rescore`) vs option 2 (`/api/extension/rescore` wrapper)? Leaning 2 for convention; decide with #3's implementer.
3. Does `/api/extension/rankings` already carry enough to know *which roster is the user's*? If not, extend that payload (cheap) rather than adding a fetch.
4. Rate limiting: a user dragging assets quickly could fire many rescores — is 500ms debounce + server-side per-token throttle enough on the Render dyno?
5. Should the overlay render on league-mates' *proposed* offers screen too (it should — same reader), and does that screen differ enough to be a phase 2?

## Dependencies & sequencing

- **Hard:** #3's rescore endpoint (`POST /api/trades/rescore` — reuse, don't redesign) and #6's verdict object/copy matrix. **Soft:** #5 (impact rows; panel ships verdict-only without it), #4 (ask-for-more chips).
- Wave 4 placement: after #12/#18; the spike (FR1) can run any time and de-risks early.
- Feeds #84 (telemetry) and the acquisition narrative in #90 (overlay screenshots as marketing). Independent of #11/#83 — no API-side offer reading here.
