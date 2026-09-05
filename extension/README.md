# Fantasy Trade Finder — Browser Extension

Injects your **personal** tier + position-rank next to every player name on
sleeper.com. Pulls rankings from your Fantasy Trade Finder account.

---

## What it does

Wherever Sleeper shows a player name — player popups, trade tabs, team
rosters, draft boards — you'll see a small pill like `1st · QB4`
reflecting **your** ranking in the league you selected, not community
consensus.

Tier bands mirror the main app's 8-tier pick-value ladder
(docs/cross-client-invariants.md):

| Tier    | Color   |
|---------|---------|
| 4+ 1sts | red     |
| 3 1sts  | fuchsia |
| 2 1sts  | gold    |
| 1st     | teal    |
| 2nd     | sky     |
| 3rd     | pink    |
| 4th     | lime    |
| FA      | gray    |

Hover the pill for format + league context.

---

## Installing (developer / unpacked)

**Chrome or Edge:**

1. Open `chrome://extensions` (or `edge://extensions`).
2. Toggle **Developer mode** (top right).
3. Extract the release zip, then click **Load unpacked** and pick its `extension/` directory. For a source checkout, pick this directory directly.
4. Open `https://sleeper.com/login` in the same browser and sign in to the Sleeper account you want to use. Refresh any Sleeper tab opened before extension installation.
5. Click the FTF toolbar icon, enter that account's Sleeper username, and verify. A different open Sleeper account is rejected.
6. Choose a league, then open a Sleeper player to see the badge. On the Fleeced web page, enter the same username and choose Verify to use the extension's proof flow.

To update an existing unpacked install, replace its files with the new package, press **Reload** on its extension card and refresh the Sleeper/Fleeced tabs. This is an unpacked Chrome/Edge release, not a Chrome Web Store listing. Do not paste your Sleeper password or session token into Fleeced.

---

## Configuration

The extension points at the production API by default:

```
https://fantasy-trade-finder.onrender.com
```

Verification fixes its API destination in `verify.mjs`; the web bridge accepts only the production first-party origin. Localhost is deliberately excluded. Use the synthetic auth harnesses in `qa/web/` for local validation instead of forwarding real credentials to a development page.

---

## How it works

- **popup.js** runs username → ownership verification → league selection and stores
  the verified Fleeced session token + cached rankings in `chrome.storage.local`.
- **verify.mjs / sleeper-proof.js** obtain the known Sleeper token only on an explicit request from a trusted extension caller, send it to the fixed verification endpoint, and discard it. Raw Sleeper proof is not stored by the extension or returned to the Fleeced web page.
- **web-auth.js** bridges a single trusted click/Enter request from the production Fleeced page. Origin, top-frame sender, focus, timeout and request correlation are checked.
- **background.js** is a MV3 service worker. Every 15 minutes it refetches
  rankings from `/api/extension/rankings` so the cache stays fresh. It also
  acts as the message hub between popup and content scripts.
- **content.js** runs on every `sleeper.com` page. It:
  1. Revalidates the verified session before displaying cached rankings.
  2. Attaches a `MutationObserver` to `<body>` so SPA navigations re-trigger
     scans without a full reload.
  3. Scans for anchors whose href contains `/players/nfl/<id>` — that's the
     stable primary strategy.
  4. Falls back to text-node name matching for surfaces without anchors
     (draft boards mostly).
  5. Inserts `<span class="ftf-badge ftf-tier-<tier>">` right after each
     matched player-name element, de-duplicating via a `data-ftf-scanned`
     attribute.
- **content.css** styles the badge — everything scoped under `.ftf-badge`
  so it can't conflict with Sleeper's own CSS.

---

## Backend contract

The verification and private-data flow uses these FTF endpoints:

### `POST /api/extension/auth`
- Body `{username}` discovers the account and returns an initially unverified session. Discovery alone does not grant private access.

### `POST /api/sleeper/link`
- Header `X-Session-Token`, body `{token}` supplies the transient Sleeper proof.
- The extension adopts the Fleeced session only when `verified === true` and the returned Sleeper ID matches the requested account.
- The backend retains the connection credential encrypted; the extension does not persist the raw proof.

### `GET /api/me/streak`
- The web client uses this private read to revalidate a restored session before displaying account data.

### `GET /api/extension/rankings`
- Header: `X-Session-Token: <token>`
- Requires a verified current session; rejection clears the matching cached session and prompts recovery.
- Returns:
  ```json
  {
    "format": "1qb_ppr",
    "league_id": "...",
    "username": "...",
    "updated_at": 1713500000,
    "players": {
      "<sleeper_pid>": {
        "name": "Josh Allen",
        "pos":  "QB",
        "pos_rank": 1,
        "tier": "first_1"
      }
    }
  }
  ```

Only players the user has actually ranked (non-default ELO) are included —
unranked players don't get a badge.

---

## Known limitations (v1)

- **Draft boards**: name-text fallback works but is sensitive to DOM
  variation. If some cells aren't getting badges, note the page and we'll
  tighten the selector.
- **Session TTL**: 4 hours. When it expires, the popup reverts to sign-in.
  Background alarm clears stale tokens automatically.
- **One league at a time**: v1 shows rankings for the league you chose in
  the popup. Multi-league support will come in v1.1 alongside the Portfolio
  integration.
- **No settings UI** beyond auth. Format toggle, pill size/compact mode,
  per-tier hide filters are v1.1 follow-ups.

---

## Post-v1 roadmap

- Community-values overlay (toggle between "Your rankings" / "Market")
- Trade-fairness verdict inline on Sleeper's Trade tab
- "Easy buy / easy sell" chip powered by `/api/trends/consensus-gap`
- Deep-link from badge hover to the `/og/tiers/<pos>/<username>` share card
- Firefox port (Manifest V3 support)

---

## File layout

```
extension/
├── manifest.json       MV3 config
├── popup.html          Popup shell
├── popup.js            Sign-in flow + session storage
├── popup.css           Popup styling
├── background.js       Service worker (alarm + message hub)
├── verify.mjs          Trusted ownership-proof orchestration
├── sleeper-proof.js    Explicit token capture on Sleeper only
├── web-auth.js         First-party verification bridge
├── content.js          Sleeper DOM scanner + badge injector
├── content.css         Badge styles (8 tier variants)
├── icons/
│   ├── 16.png
│   ├── 48.png
│   └── 128.png
└── README.md           (this file)
```
