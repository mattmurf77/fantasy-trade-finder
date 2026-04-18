# Fantasy Trade Finder — Browser Extension

Injects your **personal** tier + position-rank next to every player name on
sleeper.com. Pulls rankings from your Fantasy Trade Finder account.

---

## What it does

Wherever Sleeper shows a player name — player popups, trade tabs, team
rosters, draft boards — you'll see a small pill like `Elite · QB4`
reflecting **your** ranking in the league you selected, not community
consensus.

Tier bands mirror the main app:

| Tier    | Color  |
|---------|--------|
| Elite   | gold   |
| Starter | green  |
| Solid   | blue   |
| Depth   | purple |
| Bench   | gray   |

Hover the pill for format + league context.

---

## Installing (developer / unpacked)

**Chrome or Edge:**

1. Open `chrome://extensions` (or `edge://extensions`).
2. Toggle **Developer mode** (top right).
3. Click **Load unpacked** and pick this `extension/` directory.
4. Click the FTF icon in your browser toolbar.
5. Enter your Sleeper username → pick a league → done.
6. Open `sleeper.com`, click any player, and watch for the badge.

---

## Configuration

The extension points at the production API by default:

```
https://fantasy-trade-finder.onrender.com
```

To develop against a local backend, edit both `popup.js` and
`background.js` and swap the `API_BASE` constant at the top:

```js
// const API_BASE = 'https://fantasy-trade-finder.onrender.com';
const API_BASE = 'http://127.0.0.1:5000';
```

Then reload the extension on `chrome://extensions` (click the refresh icon
on its card).

---

## How it works

- **popup.js** runs the username → league-picker → connect flow and stores
  the session token + cached rankings map in `chrome.storage.local`.
- **background.js** is a MV3 service worker. Every 15 minutes it refetches
  rankings from `/api/extension/rankings` so the cache stays fresh. It also
  acts as the message hub between popup and content scripts.
- **content.js** runs on every `sleeper.com` page. It:
  1. Reads the cached rankings from `chrome.storage.local`.
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

Two endpoints on the FTF server:

### `POST /api/extension/auth`
- Body `{username}` → returns `{stage: "pick_league", leagues: [...]}`
- Body `{username, league_id}` → returns `{session_token, expires_at,
  scoring_format, username, league_id, ...}`

### `GET /api/extension/rankings`
- Header: `X-Session-Token: <token>`
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
        "tier": "elite"
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
├── content.js          Sleeper DOM scanner + badge injector
├── content.css         Badge styles (5 tier variants)
├── icons/
│   ├── 16.png
│   ├── 48.png
│   └── 128.png
└── README.md           (this file)
```
