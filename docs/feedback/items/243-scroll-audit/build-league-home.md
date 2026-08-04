# #243 build — League home fold (V1) + Market pulse strip (movers V3)

Two approved designs shipped as one coherent League-home change (2026-08-03).
Sources: the #243 scroll audit ([league-misc-surfaces.md](league-misc-surfaces.md) §2),
approved mocks `mockups/polish-lab-2026-08/league-home-fold.html` (**V1 —
combined density fix**) and `mockups/polish-lab-2026-08/risers-fallers-cards.html`
(**frame D1 — market pulse strip**, with the operator's placement override:
mounted **below Explore**, not top-of-page).

---

## Part 1 — League home fold V1 (`LeagueScreen.tsx`, `LeagueProgressModule.tsx`)

Four fixes, exactly the audit's items 1/2/3/5 — nothing removed, nothing
reordered:

| # | Fix | Where | Saves |
|---|---|---|---|
| 1 | **Divider double-margin bug** — `styles.divider` carried `marginTop: space.md (12)` on top of the ScrollView's own `gap: space.md (12)`: 24pt per divider for what should be one 12pt gap. The `marginTop` is deleted; every divider on the screen (up to 4–5 in the populated state) is covered by the one style. | `LeagueScreen.tsx` `styles.divider` | 12pt/divider (up to ~60pt populated) |
| 2 | **Explore reflow** — the 3 stacked hairline rows (~201pt with `league.rookie_board_entry` on) became ONE 3-across `ExploreTile` card row (icon + short title + one-line sub, ~78pt). The rookie flag adds the 3rd tile. testIDs unchanged (`league.rankings-row` / `league.free-agents-row` / `league.rookie-board-row`); full names kept as accessibilityLabels. Sub floor raised to 11px vs the mock's 10.5 (design-system type floor). | `LeagueScreen.tsx` | ~123pt |
| 3 | **Hero padding 16→12** — via a new optional `padding` prop on the chalkline `Card` (additive; default stays `space.lg`). | `LeagueScreen.tsx` + `components/chalkline/Card.tsx` | ~8pt |
| 5 | **Inline invite link** — the module's ghost "Invite leaguemates" Button row became an inline ice text link on the unlock sentence ("…unlocks mutual matches. **Invite them**", testID `league.progress-invite`, same OS-share handler). Full variant's sentence drops the "— trades both sides already like" tail per the mock. When matches are already unlocked (no sentence) but the module is still visible, a standalone "Invite leaguemates" text link keeps the affordance. Compact (Matches) variant untouched. | `LeagueProgressModule.tsx` | ~36–44pt |

**Fold result (658pt budget, iPhone 15/16-class):** audit-method estimate for
the low-activity state — hero 110 + action row 44 + Explore label/tiles
14+78 + market strip 36 + divider 1 + progress label 14 + module ~256, with
16pt screen pad and 12pt gaps ⇒ the module ends **~653pt, above the fold**
(mock-measured V1 without the strip: ~603pt; the strip consumes ~48pt of that
headroom — see Part 2 note below). Populated/classic state: no regression —
same sections, same order; it only *gains* 12pt per divider from fix 1.

## Part 2 — Market pulse strip (movers V3 / frame D1)

### Backend

- **`GET /api/market/movers`** (`backend/server.py`, new route region after
  `/api/league/rank-chip`) — flag **`market.movers`** (404 off; added to
  `feature_flags.py`, `config/features.json` **true**, and the test-enforced
  mirror `backend/tests/fixtures/flags/release.json` **true**). Query
  `scoring_format` / `window_days` (default 30) / `top_n` (default + hard cap
  10 each). → `{risers: [{player_id, name, position, team, pct_30d,
  value_now}…], fallers: […], as_of, window_days, source:
  "ftf_community_value"}` — risers % desc, fallers most-negative first.
  Deliberately open read (universal consensus data only, no user/board/league
  content — same class as `/api/tier-config`).
- **Service read** `database.load_value_movers_window(fmt, days)` — lives
  beside the other `player_value_history` readers
  (`load_value_snapshot_baseline` etc.): latest snapshot date vs the OLDEST
  in-window date strictly before it (earliest-in-window semantics, mirrors
  the FB4-61 baseline). No schema change, no new writes.
- **Noise guards:** players absent from the universal pool, flat movers,
  single-day players, and junk baselines (`consensus_value` < 100) excluded.
- **Thin-history behavior (empty-safe):** no snapshots at all → 200
  `{risers: [], fallers: [], as_of: null}`; exactly one accrued day → 200
  with empty lists and `as_of` = that day (a same-day-only snapshot is never
  a baseline, so no fake 0% moves). The route never 500s on thin data; the
  flag-off state is the only 404.
- **Tests** `backend/tests/test_market_movers.py` (5): flag gating (404
  off / 200 on), shape + ordering + noise guards, top_n + hard cap 10, thin
  single-day history, no history. Written first and verified failing (4/5 —
  the flag-off 404 passes trivially) before the route existed. Full suite:
  **1414 passed, 1 skipped**; the `release.json` ↔ `features.json` mirror
  test stays green.

### Mobile

- **`mobile/src/components/MarketPulseStrip.tsx`** (new, self-contained) —
  one compact card line below Explore: top riser + top faller (last name +
  signed %, chevron-up/down glyphs, pos/neg colors) + ice "See all movers ›".
  Whole strip opens the movers bottom sheet (#242 pattern: `maxHeight: '85%'`,
  sizes to content, backdrop/onRequestClose dismiss) with full Risers/Fallers
  columns (position dot + name + `POS · TEAM` + signed %) under the flare
  **"FTF community value · 30-day change"** honesty label (per the mock:
  community-value framing, never "market"). Renders **null** without the flag
  or without data — loading, errors (incl. the flag-off 404), and
  thin-history empty payloads all render nothing, so the strip costs the
  layout 0pt whenever it has nothing to say.
- **Fold note:** strip is ~36pt visual (paddingVertical 9, no minHeight) with
  `hitSlop` restoring the 44pt effective touch target — a full 44pt row
  would have pushed the progress module ~3pt past the 658pt fold in the
  low-activity state.
- **`mobile/src/api/market.ts`** (new) — `getMarketMovers(format)` typed
  client.
- Mounted in `LeagueScreen.tsx` directly below the Explore tiles (operator
  placement override; D1 mocked it under the hero).

## Files touched

`backend/server.py` (route region) · `backend/database.py`
(`load_value_movers_window`) · `backend/feature_flags.py` (key) ·
`config/features.json` + `backend/tests/fixtures/flags/release.json`
(mirror, both `true`) · `backend/tests/test_market_movers.py` (new) ·
`mobile/src/screens/LeagueScreen.tsx` ·
`mobile/src/components/LeagueProgressModule.tsx` ·
`mobile/src/components/MarketPulseStrip.tsx` (new) ·
`mobile/src/components/chalkline/Card.tsx` (additive `padding` prop) ·
`mobile/src/api/market.ts` (new) · docs: `api-reference.md`,
`config-reference.md`, `glossary.md` ("Market movers"), CLAUDE.md registries
(components/screens/api + testID tranche).

## Verification

- `python3 -m pytest backend/tests -q` → 1414 passed, 1 skipped.
- `cd mobile && npx tsc --noEmit` → clean.
- New testIDs: `league.market-pulse` · `league.market-pulse.see-all` ·
  `market-movers.sheet` · `league.progress-invite` (registered in
  `mobile/src/components/CLAUDE.md`).

## Deviations / notes

- Explore tile sub-copy renders at 11px (mock: 10.5) — design-system type
  floor.
- The inline invite link is a nested `Text` (no 44pt target of its own) —
  matches the approved V1 mock and the #213 text-link precedent; documented
  tradeoff.
- `pct_30d` is named for the default window but reflects the requested
  `window_days` (echoed in the payload) — kept per the task's specified
  shape.
