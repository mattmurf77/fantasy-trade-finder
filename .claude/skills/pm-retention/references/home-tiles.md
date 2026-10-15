# Home hub and hub-screen tiles — pm-retention

> Rules for speccing the Home hub, or any hub screen whose job is to bring a returning user
> back into the product. The tile and its entry point are Engagement's. The screen a tile
> lands on belongs to that screen's owning area.

## Contents

- [1. Where Home stands](#1-where-home-stands)
- [2. Operator preference: tiles that preview live content](#2-operator-preference-tiles-that-preview-live-content)
- [3. Visual rules (Chalkline)](#3-visual-rules-chalkline)
- [4. FeedbackFAB (#188)](#4-feedbackfab-188)
- [5. Analytics: `home_tile_tapped`](#5-analytics-home_tile_tapped)
- [6. Flag posture](#6-flag-posture)
- [7. Destinations belong to other areas](#7-destinations-belong-to-other-areas)
- [8. Evidence for a tile change](#8-evidence-for-a-tile-change)
- [9. Tile spec block](#9-tile-spec-block)

---

## 1. Where Home stands

- **D-198 / #309 (2026-10-08):** the first Home tab. It was four plain text rows that
  repeated the tab bar (`living-memory/DECISIONS.md` D-202 context).
- **D-202 / #319 (2026-10-10):** Home became a tile hub behind `nav.home_hub` (on). It
  has three status rows (team outlook, current standings, overall rank), QB/RB/WR/TE
  position tiles with in-tile **Buy** | **Sell**, and five task tiles (Find a trade, Rank
  players, View matches, Check trends, Search free agents). The components are in
  `mobile/src/components/home/` (`HomeHub`, `StatusRow`, `PositionTile`, `TaskTile`).
- **Exemplar spec:** `docs/plans/home-engagement/scope.md`. It holds the operator rulings
  (§0), the build contract with per-agent file ownership (§6), and the 15-step operator
  TestFlight checklist (§3). Copy its shape.

## 2. Operator preference: tiles that preview live content

The operator wants **generous, tappable tiles that preview live content**, not tight lists
of text links. They found the four-row Home bland, and that was the reason for the
redesign (`living-memory/CHANGELOG.md` 2026-10-10 entry; preference restated by the
operator on 2026-10-09). The visual reference is the operator's FumbleAI home-hub mockup.
It lives outside this repo, so ask through `head-product` if you need it, and never cite a
path to it.

What that means in a spec:

- **Each tile shows a live value:** a rank, a count, a band, a date. "Find a trade" with
  a fresh-deck count beats "Find a trade" alone. If a tile can't show live data, ask
  whether it should be a tile at all.
- **The preview is the value refresh.** A tile whose number changed since the last visit
  is the in-app version of a good push, and it needs no permission.
- **Every tile states its loading, error and unavailable states.** The status-row
  construction already defines them (`docs/design/components.md:123`).
- **Hierarchy:** status first, then the user's own team, then tasks. Don't let Home become
  a second tab bar.

## 3. Visual rules (Chalkline)

Use the tokens in `docs/design/design-system.md` and the constructions in
`docs/design/components.md`. The live reference is `web/style-guide.html`. The Home
constructions already exist: status row, position tile and task tile
(`components.md:123-125`).

Hard rules from the design system's Prohibitions (`design-system.md:11-23`):

- Radius ≤ 8px (`--r-md`); pills only where a spec says pill.
- No gradients, glassmorphism or blur.
- No emoji icons; use the Chalkline icon set.
- No Inter, Roboto or system font stack.
- Ice on actions only, and flare on informational highlights only. The Home position
  tiles carry a documented operator exception to the ice ration (`components.md:124`).
  Don't extend it without a new ruling.
- Position and tier hexes are data encodings (`docs/cross-client-invariants.md`).

`design-lead` reviews every visual change and `ux-lead` reviews every flow change. Request
both through `head-product`.

## 4. FeedbackFAB (#188)

- **Home is a tab screen. It must NOT mount its own `FeedbackFAB`.** The single global
  mount in `mobile/src/navigation/RootNav.tsx:633` covers every tab. A second one is the
  #196/#197 double-FAB bug. `check-home-tab.js` (its check 4g) and `check-home-hub.js` (its
  check 9, `:312`) both assert there is no FAB in Home.
- **A root-stack push from a tile mounts its own FAB:**
  `<FeedbackFAB activeScreen="<Route>" aboveTabBar={false} />`. Standings does this
  (`mobile/src/screens/StandingsScreen.tsx:256`), and `check-home-destinations.js` pins
  it.
- **Exceptions:** modals, sheets and onboarding flows.

## 5. Analytics: `home_tile_tapped`

- **Every tap on a Home row, tile or button fires `home_tile_tapped`** before navigating
  (`docs/business/analytics/2026-10-10-home-hub-addendum.md`).
- **Its `tile` prop is a closed enum** (addendum line 19): `outlook`, `standings`,
  `overall_rank`, `buy`, `sell`, `position_ranking`, `find_trade`, `rank`, `matches`,
  `trends`, `usage_rates`, `free_agents`, `link_league`, `retry`. `position` and `band`
  ride only on `buy`, `sell` and `position_ranking`. Props are registered at
  `backend/analytics_taxonomy.py:1709`.
- **Both Home events are NON_INTENT** (`backend/analytics_queries.py:391-392`). Home is
  the launch tab, so counting a tap as intent would step-change DAU on ship day. The
  destination's own event carries the intent. This is pinned by
  `backend/tests/test_analytics_taxonomy_home_hub.py`.
- **A new tile extends the enum.** That needs `analytics-lead`'s grant, in the same commit
  as the emitter. Update the addendum, and the closed-vocabulary list in
  `mobile/tests/check-home-hub.js` §6 (`:238-259`), which asserts exactly one
  `track('home_tile_tapped'` call site per tile kind.
- **Never add league id, team, player or device platform as a prop** (addendum).

## 6. Flag posture

- **`nav.home_hub` is on** (`config/features.json:107`). It is client-only, read once per
  `HomeScreen` mount (`mobile/src/screens/HomeScreen.tsx:30`), and documented in
  `docs/config-reference.md:472`.
- **Flag-off must stay byte-identical** to the old four-row Home. `check-home-tab.js` is
  that net, and it must pass **unmodified** (scope §3).
- **A risky tile change ships behind its own flag** with a flag-off-identical guard.
  Rollback is the flag plus `POST /api/feature-flags/reload`, with no deploy.

## 7. Destinations belong to other areas

The tile, its live preview and its entry intent are Engagement's. The landing screen and
how it handles the arrival intent belong to the owning area, and need that lead in the PRD:

| Tile | Lands on | Owner of the landing |
|---|---|---|
| Standings, Overall rank, Buy / Sell | Standings page, League rankings split | League area's lead |
| Find a trade, Team outlook (Trade DNA) | Trades | `trades-pm` |
| Rank players | Rank | core-loop owners `trades-pm` / `onboarding-pm` (`/pm-pfo`) |
| View matches | Matches | `trades-pm` |
| Check trends, usage rates, free agents | Trends, Usage Trends | the owning area's lead (confirm via `head-product`) |
| Invite or referral tiles | Invite flow | `growth-pm` (mechanics); you own the placement |

Precedent: the Home build added no Trade DNA intent store. It reused the existing
`editDna` param that `TradesScreen` already consumed (scope §0, "One deviation"). Prefer the
destination's existing entry contract over a new one.

## 8. Evidence for a tile change

The D-056 evidence set:

- **Guard:** extend `check-home-hub.js` and `check-home-destinations.js`, or add a new
  `check-*.js`. CI runs every one of them (`.github/workflows/ci.yml:47`).
- **Code-walk:** trace `onPress` → `track('home_tile_tapped', …)` → the navigation call →
  the landing screen's intent handling, with file:line at each step (scope §3 shows the
  shape).
- **TestFlight checklist:** numbered operator steps. Cover a returning user, an empty
  state, an error state, a non-Sleeper league and the largest Dynamic Type (scope §3
  items 1–15).

## 9. Tile spec block

```markdown
### Tile: <name>  (`tile` enum value: `<new_value>`)
- **Live preview:** <what it shows, its source endpoint/query, staleTime>
- **Value refresh:** <what changes between visits that makes it worth a tap>
- **States:** loading · error (+ retry) · unavailable / empty (copy intent)
- **Placement:** <status row | position tile | task tile | new construction → design-lead>
- **Tap:** `track('home_tile_tapped', {tile: '<new_value>'}, 'Home')` → <navigate call> →
  <landing screen> (owner: <lead>)
- **Flags:** <nav.home_hub + its own flag?> · flag-off byte-identical: <how pinned>
- **Events:** enum extension granted by analytics-lead: <yes/pending> · addendum updated
- **FAB:** none on Home · landing is <tab screen | root-stack push with its own FAB>
- **Copy table:** for marketing-lead (title, detail line, empty-state line)
- **Evidence:** guard <file + what it pins> · code-walk · TestFlight steps
- **Reviews:** design-lead · ux-lead · analytics-lead · landing owner
```
