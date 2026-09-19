# #225 — Notifications de-chalk (emoji out, Chalkline rows in)

**Status:** built · ships live (no flag) · isolated worktree branch `teardown-remediation`
**Spec:** approved mock `mockups/polish-lab-2026-08/notifications-dechalk.html` (PROPOSED side) — operator verdict: "I prefer the SVG glyph."

## What shipped

1. **Backend template de-emoji** (`backend/server.py`, copy only — every event/notification TYPE, trigger, dedup key, and metadata payload unchanged): all `create_notification` / `_send_typed_push` titles and bodies rewritten fact-first with zero emoji. Bodies carry only NEW information (players · league / next step) — never repeat the title.
2. **Mobile bell-sheet rows** (`mobile/src/components/TopBar.tsx`): specced `NotificationRow` (components.md) — 20px Chalkline stroke glyph in status color, title 14 semi / body 13 dim / Plex Mono time, unread = flare 6px square + one-surface-step row fill. Old client-side body-only emoji strip replaced by a defensive title+body strip covering the full legacy emoji set (old DB rows are NOT migrated; they render clean).
3. **Web bell panel** (`web/js/app.js` + `web/css/styles.css`): the panel previously rendered `body || title` only — with the fact-first split that would have dropped the actor. Now renders title (semi) + body (dim), collapses legacy title-restated-in-body rows to one line, and extends the strip regex to the full legacy set. Icon + flare-square unread construction already existed on web.
4. **QA seed** (`qa/seed_test_dispositions.py`) updated to seed the new templates.

## Template before → after

| Surface / kind | Before (title — body) | After (title — body) |
|---|---|---|
| inbox `trade_match` | 🤝 New trade match with {p} in {lg}! — New trade match with {p} in {lg}! {give} for {recv} | Trade match with @{p} — {give} for {recv} · {lg} *(no names: "Tap to review the matched trade.")* |
| inbox `trade_accepted` | ✅ {p} accepted your trade in {lg} — ✅ {p} accepted your trade in {lg}: {trade} | @{p} accepted your trade — {trade} · Tap to ratify on Sleeper |
| inbox `trade_declined` | ❌ {p} declined your trade in {lg} — ❌ {p} declined your trade in {lg}: {trade} | @{p} declined your trade — {trade} · {lg} |
| inbox `referral_joined` | 🤝 @{u} joined Fantasy Trade Finder via your invite. | @{u} joined Fantasy Trade Finder via your invite. |
| push `new_match` | 🎯 Match with @{p} — {give} for {recv} | Match with @{p} — {give} for {recv}. Both boards say yes. |
| push `first_match` | 🎉 You got your first trade match! — @{p} matched a trade with you. Tap to review. | Your first trade match — *(body unchanged)* |
| push `match_accepted` | ✅ @{u} accepted your trade — Tap to ratify on Sleeper. | @{u} accepted your trade — *(body unchanged)* |
| push `league_member_unlocked_trades` | 🔓 New trade options in your league — @{u} just unlocked Trade Finder. … | New trade options in your league — *(body unchanged)* |
| push `league_member_joined` | 🤝 New leaguemate on Fantasy Trade Finder — @{u} joined {lg}. More trades may unlock. | @{u} joined {lg} — A new leaguemate can mean new trade matches. |
| push `match_expiring` | ⏳ A trade match is expiring soon — Tap to review before it disappears. | A trade match is expiring soon — *(body unchanged)* |
| push bundled morning summary | 🌅 Good morning — You have {n} new trade matches waiting. / {n} new matches and {m} updates while you slept. / {n} updates while you slept. | {n} new trade match(es) — They arrived overnight. Tap to review. / {n} new match(es) and {m} update(s) — From overnight. Tap to review. / {n} update(s) overnight — Tap to review. |
| push `weekly_digest` | 📰 Your weekly trade roundup — Tap to see what's new in your leagues. | Your weekly trade roundup — *(body unchanged)* |
| push `pending_review` | 👀 You have unreviewed matches — You have {n} match(es) waiting. | {n} unreviewed match(es) — Waiting for your call. Tap to review. |
| push `season_start` | 🏈 Football is back — Re-rank your players… | Football is back — *(body unchanged)* |
| push `finish_ranking` | 🎯 You're 5 minutes away from your first trade — Finish ranking… | You're 5 minutes from your first trade — *(body unchanged)* |
| push `winback_dormant` (both variants) | 👋 Your league misses you — *(bodies unchanged)* | Your league misses you — *(bodies unchanged)* |
| push `winback_matches` | 🔥 Trade matches are waiting — You have {n} unreviewed match(es). | {n} match(es) waiting — Your leaguemates have been busy. Tap to review. |

## Glyph set (mobile bell sheet, `data.type` → Chalkline `Icon`)

| Types | Glyph | Color |
|---|---|---|
| `trade_match`, `new_match`, `first_match` | `match` (link) | ice |
| `trade_accepted`, `match_accepted` | `check` | semantic.pos |
| `trade_declined` | `x` | semantic.neg |
| everything else (referral, digest, winback, …) | `bell` | chalk.dim |

The glyphs reuse the shared `chalkline/Icon.tsx` set (match/check/x/bell already exist there and are the same 20×20 / 1.75-stroke / square-cap construction as the mock's paths) rather than duplicating local Svg — PlayerContextMenu's `LockGlyph` is local only because `lock` isn't in Icon.tsx yet.

## Documented deviations

- **Unread row fill:** components.md says "--ink-2 row fill", written against the web panel (ink-1 ground). The mobile sheet itself sits on ink-2, so the mobile unread fill uses ink-3 — same one-surface-step intent. Web already used ink-3.
- **Old DB rows:** not migrated (per PRD). Both clients strip leading legacy emoji from titles AND bodies on render; web additionally collapses legacy title-repeated-in-body rows to one line.

## Out of scope (flagged for follow-up)

- League activity feed messages (`backend/database.py` `load_league_activity`) still embed ✅ ✖️ 🤝 📋 🎯 🔄 in `message`/`summary` strings. Mobile `ActivityFeed` ignores the `emoji` field but renders `summary` verbatim — leading emoji likely visible there and on web. Separate surface, separate item.
- Invite milestone badge names (`_INVITE_MILESTONES` in `backend/server.py`: 🌱 🤝 🔥 👑) — flag-gated invite dashboard payload, not a notification surface.
- Startup/log emoji (log.info/print) intentionally untouched.

## Verification

- Backend: `python3 -m pytest backend/tests -q` — baseline 1380 passed / 1 skipped; post-change identical (no tests asserted template strings; only `qa/seed_test_dispositions.py` referenced them and was updated).
- Mobile: `npx tsc --noEmit` clean.
- Web JS: `node --check web/js/app.js` clean.
- testIDs: unchanged (`topbar.notif-row.<id>` kept; registry untouched).
