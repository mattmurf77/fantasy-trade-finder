# #243 scroll audit — League tab, Matches, sign-in/onboarding, Settings

Read-only audit. No code changed. Method mirrors the #218 hub density pass
(`docs/feedback/items/218-hub-fit-to-screen/status.md`): usable viewport
budget for a Main-tab screen (iPhone 15/16-class, 393×852) —

```
852 − 59 (top safe inset) − 52 (TopBar) − 49 (tab bar) − 34 (bottom inset) = 658pt
```

For root-stack pushes without a tab bar (SignIn, LeaguePicker) the budget is
`852 − 59 − 34 = 759pt` (no TopBar/tab bar on those routes). Settings is a
root-stack push with a native-stack header (not rendered in the JSX — RootNav
supplies it), so its usable body is close to the tab-screen number, ~700–715pt;
exact header height wasn't decompiled from this file, so Settings numbers
below are directional, not load-bearing.

All state assumptions use **default flags** confirmed in `config/features.json`:
`league.rookie_board_entry: true` (adds a 3rd Explore row), `account.settings_v2: true`,
`outlook.odds: false` (odds section never renders), `landing.try_before_sync: false`
/ `onboarding.landing: false` (SignIn nominal = legacy layout, Apple primary),
`league.activity_feed: false` (no Recent Activity section). 12-team league
assumed throughout per the brief.

---

## 1. LeagueSummaryScreen — League tab root (`LeagueRankings`)

File: `mobile/src/screens/LeagueSummaryScreen.tsx`

### 1a. Nominal state (no team focused, starters_available, basis=consensus, no filter)

Budget arithmetic (screen `styles.scroll`: `padding: space.lg(16)`, `paddingBottom: space.xxl(32)`):

| Block | Height |
|---|---|
| Screen top padding | 16 |
| "League home" row (`homeRow`, tab-root only) | 79 |
| Basis chip row | 44 |
| Chart card (head 42 + updated-at 22 + subset control 48 + pos-filter pills 40 + hint 38 + 160pt chart + rank pills 21 + legend 30, padding 32 + border 2, marginBottom 12) | 447 |
| **Running total** | **586** |
| vs 658pt viewport | **72pt spare** — the entire analyzer chart (filters, bars, legend) fits above the fold; the caller's own team row (~45pt) peeks in, next row partially cut |

**Verdict: fits.** The chart — the screen's actual value — is fully visible on load. No action needed for this state.

### 1b. Drill-in state (team focused) — the #237 concern

Tapping a bar or list row focuses a team: the chart card **stays mounted with its own subset + position-filter controls** (now filtering a grayscale chart), and the drill-in panel below renders **its own full copy of the same two controls** (`league-summary.roster-subset.*` / `league-summary.roster-posfilter.*`) bound to the same shared state (#237, 2026-08-02).

| Block | Height | Running |
|---|---|---|
| Screen padding + home row + basis row | 139 | 139 |
| Chart card (focused variant — same 447, caption swaps but height is unchanged) | 447 | 586 |
| Drill panel sub-line (`#N of M · value`) | 18 | 604 |
| Drill panel's own **SubsetControl** (mirror #1) | 48 | 652 |
| Drill panel's own **PosFilterPills** (mirror #2) | 36 | 688 |
| Drill list top margin | 4 | 692 |

**At 692pt — before a single roster row renders — the viewport (658pt) is already exhausted.** Every drilled-in team focus requires a scroll before the user sees any player. The two mirrored control rows (subset + position pills, once in the still-visible chart card and once in the drill panel) account for 84pt of pure duplication: the same two controls, doing the same thing, both on screen at once, while the actual payload (the roster) is entirely below the fold.

**Reductions (ranked):**
1. **Structural — collapse the chart card's own filter row while focused.** The drill panel already exposes the identical subset + position controls right below the (now grayscale) chart; keep the chart's `SubsetControl`/`PosFilterPills` mounted but hidden (or replace with a one-line "Filtered by: All" caption) whenever `selected` is set. **Saves ~84pt**, single largest fix on this screen — brings the first roster group header into view without scrolling.
2. **Free space — dividers/margins already tight here (no `space.md` double-count bug found on this screen)**; skip.
3. **Density — hint line (`styles.hint`, `marginTop: sm, marginBottom: md` = 20pt of vertical padding around one sentence) could drop to `marginTop: xs, marginBottom: sm`** (mirrors the #218 hub's literal-value treatment) — **saves ~8pt**.
4. **Structural — the "League home" row (79pt) is irrelevant once a team is focused** (it's a nav-away affordance, not part of the roster-review task); hiding it while `selected` is set is a defensible collapse — **saves 79pt** and is free real-estate every time a user drills in from the tab root.

Combined (#1 + #3 + #4): **171pt recovered**, which drops the pre-roster total from 692pt to 521pt — comfortably under the 658pt budget with 137pt to spare for the first roster group.

### 1c. Nominal-state density pass (optional, mirrors #218)

Even in 1a's already-fitting state, the same literal-value density pass the hub got (`space.md`→smaller literals on subset row / pos-filter margins / legend margin) would reclaim roughly **24–32pt**, pushing the spare room from 72pt to ~100pt+ — enough to fully reveal the caller's own team row instead of a partial peek. Lower priority than the drill-in fix since the nominal state already fits.

---

## 2. LeagueScreen — classic League home (`LeagueHome`, reached from the tab root's "League home" row)

File: `mobile/src/screens/LeagueScreen.tsx`

This is a legitimately long page (hero, matches tiles, explore, activity, contrarian, coverage, leaderboards) — per the brief, the question is whether the above-the-fold slice is a complete, useful unit. The #229/#230/#234 low-activity treatment is the interesting state: a brand-new/quiet league (matches=0, joined=0, coverage=0, contrarian `insufficient_data`) renders an action row + the single `LeagueProgressModule` + a "Works right now" example card in place of the folded sections.

### Budget — low-activity state, default flags (`league.rookie_board_entry: true` adds a 3rd Explore row; `league.activity_feed: false` folds Recent Activity)

| Block | Height | Running |
|---|---|---|
| Screen top padding | 16 | 16 |
| Hero card (label + name + chips) | 118 | 134 |
| Action row (Rank players / Find a trade) | 44 | 178+gap12=190 |
| "Explore" TickLabel | 14 | 204+gap12=216 |
| Explore rows ×3 (rankings, free agents, **rookie board** — on by default) | 201 | 417+gap12=429 |
| Divider before progress module (`marginTop: md` **on top of** the ScrollView's own `gap: md` between siblings) | 13 | 442+gap12=454 |
| "League progress" TickLabel | 14 | 468+gap12=480 |
| **`LeagueProgressModule` (full variant)** | 300 | **780** |

**vs 658pt viewport: the module — the page's single most important explainer for a new user — starts at 480pt and needs to end at 780pt. Only 178pt of its 300pt is visible; the bottom ~122pt (the "Invite leaguemates" ghost button and the fold line explaining when Leaderboards/Contrarian return) is below the fold.** This directly fails the brief's example test ("action row + progress module fully visible") — the action row is visible, the module is not.

**Reductions (ranked):**
1. **Free space — the divider/gap double-count bug.** `styles.divider` carries `marginTop: space.md` (12), and the ScrollView's `contentContainerStyle` already carries `gap: space.md` (12) between every direct child. Every divider in this screen (there are up to 4 in the fully-collapsed state: before progress, before works-now, plus contrarian/coverage/leaderboards when they return) pays 24pt of vertical space for what should be a single 12pt gap. **Removing `marginTop` from `styles.divider` saves 12pt per divider** — 12pt land above the progress-module cutoff in this exact state (one divider precedes it), pulling the module up to start at 468 instead of 480.
2. **Structural — reflow the 3 Explore rows into 2 side-by-side tiles + 1 stacked row** (or a 2-up grid, matching the existing `StatCard` tile pattern already used for the Matches tiles above). Three list rows at 67pt each (201pt total) → two tiles at ~70pt + one row (or a 2×2 grid with the 4th slot free for the next Explore addition) ≈ 137pt. **Saves ~64pt.**
3. **Density — hero card padding 16→12** (mirrors the #218 hub's DNA-panel treatment, `space.lg`→`space.md`-adjacent literal): **saves ~8pt.**
4. **Density — Explore row `paddingVertical: space.md(12)` → `space.sm(8)`** per row (still clears the 44pt minHeight touch floor since each row's content — title 22 + sub 18 — already sums to 40pt without padding): **saves 8pt/row × 3 rows = 24pt.**
5. **Structural — `LeagueProgressModule`'s "Invite leaguemates" `Button` (compact, but still a full 36pt-tall row with its own `marginTop`) could be an inline text link appended to the unlock sentence** ("2 more ranked leaguemates unlocks mutual matches — Invite them") rather than a separate button row. **Saves ~30–36pt** and applies everywhere the module mounts (League home full variant + this same win doesn't apply to the `compact` variant on Matches, which never renders the invite button).

Combined (#1+#2+#3+#4): **12 + 64 + 8 + 24 = 108pt**, dropping the module's start from 480 to ~372 and (with #5 also trimming the module itself by ~30pt) its end from 780 to ~642 — **inside the 658pt budget**, making the module fully visible on load as the brief's example asks for. Even without #2 (the more invasive reflow), #1+#3+#4+#5 alone (74pt) get the module's end to ~706pt — still short, so the Explore-row reflow (#2) is the one non-optional item to actually close the gap.

### Populated-state note

Once a league is fully unlocked (ring 4/4, matches exist, contrarian live), the page renders the classic full layout — Matches tiles, Explore, Activity (if flagged), Contrarian, Coverage, Leaderboards. That state is unambiguously "legitimately long" (6+ sections of real content) and out of scope for fit-to-screen; the divider double-margin bug (item 1 above) still applies there and is worth fixing project-wide (every divider in this screen, ~5 instances in the fully populated state, so up to **60pt** of pure dead space stacked from that one bug alone).

---

## 3. MatchesScreen — mutual matches tab

File: `mobile/src/screens/MatchesScreen.tsx`

### Empty state (mutual, active league, `emptyModule` populated)

This state is a plain centered `View` (`flex:1, justifyContent:'center'`), not a ScrollView — content is vertically centered rather than pinned to the top.

Header (title+subtitle, ~80pt) + segment toggle (44+8, ~52pt) + league filter chip row (~48pt) leaves roughly **478pt** available for the centered block. Centered content (title 26 + body ~54 + Find-a-trade button 44 + compact `LeagueProgressModule` ~108 + Refresh ghost 36, with `gap: space.md` between each ≈ 5×12=60) totals **~316pt** — well inside the 478pt available. **Verdict: fits, no overflow.**

**One defensive note (not a current bug):** because this is a fixed `View` rather than a `ScrollView`, it has no fallback if the stack grows — e.g. `ux.help_surface` on (adds a "How matching works" link, +36pt) combined with Dynamic Type at a high scale on the body copy could in principle push past 478pt with nowhere to go (RN doesn't auto-scroll a non-scrollable flex container; content would just clip against the tab bar). The #218 hub precedent kept its `ScrollView` mounted specifically as "a Dynamic-Type / small-device safety net" even once the nominal layout stopped needing it. **Recommendation: wrap `styles.centered` in a `ScrollView` with `contentContainerStyle: { flexGrow: 1, justifyContent: 'center' }`** so it still centers in the nominal case but degrades to scrollable rather than clipped in the edge case. Low priority — no known failure today, cheap insurance.

### Awaiting-them empty state

Simpler (title + body + Refresh, `emptyCtasOn` flag currently gates the extra CTA and is presumably off by default given the pattern elsewhere) — comfortably fits with large margin. No action.

### Populated states (FlatList of TradeCards)

Naturally scrollable list content, out of scope for fit-to-screen by the brief's own rule.

---

## 4. Sign-in / onboarding

### SignInScreen

File: `mobile/src/screens/SignInScreen.tsx`

No `ScrollView` at all — `KeyboardAvoidingView` wraps a `body` with `flex:1, justifyContent:'center'`, i.e. this screen is **already built fit-to-screen by construction** (the exact end-state the rest of this audit is chasing). Budget: 759pt available (no TopBar/tab bar on this route).

Nominal state (default flags: `onboarding.landing:false`, `landing.try_before_sync:false`, `auth.accounts:true` → Apple button shown as primary, Sleeper demoted to secondary "Continue with Sleeper →"):

hero (~180pt) + form (Apple button 56 + or-divider 30 + [hint row 56, returning users only] + input 52 + button 52 + legal line 52 ≈ 242–298pt) = **~422–478pt total, vs 759pt available — 281–337pt spare.** Fits with large headroom in every realistic flag combination checked (including the rare simultaneous reauth-notice + demo-link + apple-link combination under `onboarding.landing`, which was also modeled and still fits under ~600pt).

**Verdict: no action needed.** Flagged as a positive reference pattern for the rest of the audit — no ScrollView, no scroll, comfortable margin. One defensive parity note: since it has zero scroll fallback, an extreme Dynamic-Type + longest-copy + all-flags-on combination is theoretically capable of clipping (not modeled precisely here); if that ever becomes a real complaint, the fix is the same ScrollView-safety-net pattern noted for Matches above.

### LeaguePickerScreen

File: `mobile/src/screens/LeaguePickerScreen.tsx`

Header (~74pt) + a native `FlatList` of the user's own leagues (typically 1–10 rows, 57pt each) + an optional link-platform footer (~90pt when ESPN/MFL/Fleaflicker linking flags are on). This is a natural list, not a fixed dashboard — FlatList already scrolls appropriately and the brief's "legitimately scrollable" carve-out applies directly. With 759pt available and header+footer costing ≤164pt, ~10 rows are visible before any scroll is needed for a typical account. **Verdict: fits; no fit-to-screen violation.** No further onboarding/guided-layer screens were found in `mobile/src/screens/` (guided tour is an overlay component, `AnalystGuide.tsx`, not a separate screen).

---

## 5. SettingsScreen (+ notifications)

File: `mobile/src/screens/SettingsScreen.tsx`. No separate `NotificationsScreen` exists — notification prefs are a section within Settings (`notifToggleRows`/`quietHoursRows`), folded together in Settings IA v2 (`account.settings_v2: true` by default).

This is an intentionally long preferences list (Leagues → Ranking → [Guided tour] → Notifications → Account → About → [Testing, dev/tester-gated] → Sign out) — the brief's "legitimately scrollable" case applies to the page as a whole; a native-stack header (not in this file — supplied by RootNav) means exact top-of-viewport math couldn't be decompiled precisely from source alone, so the numbers below are directional.

**Above-the-fold check (Leagues section, single-league user, no platform-link flags):** section TickLabel (~46pt incl. its `marginTop: space.xl` header spacing) + the "Connect another league" `Card` (help text + input + button, padding 32+border 2, ≈182pt total) ≈ **228pt** — a small fraction of the ~700pt+ available. The first section renders as a complete, immediately-useful unit with no waste; not a violation.

**Where density work would actually help:** getting from the top of the list down to high-value, low-frequency actions near the bottom (Verify account, Delete account, Sign out) requires scrolling through every section regardless of how tight any one section is — this is expected behavior for a long settings list (comparable to iOS Settings itself) and isn't a fit-to-screen defect. Two low-cost, low-risk trims that shorten that overall scroll distance without touching any row's touch target:

1. **`styles.section`'s `marginTop: space.xl (24)`** fires before every one of the ~6–7 section headers in the v2 IA (Leagues, Ranking, [Guided tour], Notifications, Account, About, [Testing]). Dropping to `space.lg (16)` **saves 8pt × ~6 visible sections ≈ 48pt** across the full page — shortens the trip to Account/About/Sign-out by roughly one row's worth of scrolling, at zero risk (it's whitespace between headers, not content).
2. Row constructions (`row`/`kvRow`/`linkRow`) are already at the 44pt touch floor via `minHeight:44` — these are correctly dense already and shouldn't be tightened further (further compression would violate the a11y hit-target floor).

**Verdict: not a fit-to-screen violation; one small, safe density trim available (#1) for the sake of scroll distance to the page's most important/destructive actions.** No structural (collapse/merge/reflow) changes are warranted — collapsing sections by default would hide settings users are specifically here to find.

---

## Top 10 ranked (impact × ease), across all surfaces in scope

| # | Finding | Surface | Impact | Ease | Est. savings |
|---|---|---|---|---|---|
| 1 | Progress module not fully visible on the low-activity League home (only 178/300pt shown) — needs the combined fix below | LeagueScreen | **High** — this is the primary first-run education surface | Medium | up to 108pt via items 2–4 |
| 2 | Divider `marginTop` double-counts the ScrollView's own `gap` (dead 12pt per divider, up to 4–5 dividers/screen) | LeagueScreen (+ same pattern likely worth checking elsewhere) | High (compounds across every divider) | **Easy** — delete one style line | 12–60pt depending on state |
| 3 | Drill-in roster panel: chart card's subset+filter controls duplicate the #237 mirrored controls below, consuming the whole viewport before any roster row shows | LeagueSummaryScreen | **High** — blocks the primary post-tap payload | Medium | 84pt |
| 4 | "League home" row stays mounted (and above the fold) even while a team is drilled in, where it's irrelevant to the task | LeagueSummaryScreen | Medium | Easy — conditional render on `selected` | 79pt |
| 5 | 3 Explore rows (List construction) could reflow to 2-up tiles, matching the existing StatCard pattern already on the same page | LeagueScreen | Medium | Medium (layout change, existing pattern to copy) | 64pt |
| 6 | `LeagueProgressModule`'s "Invite leaguemates" full-width Button row could be an inline text link on the unlock sentence | LeagueScreen (full variant) | Medium | Easy | 30–36pt |
| 7 | Explore row `paddingVertical` denser (12→8), still clears 44pt floor | LeagueScreen | Low-Medium | Easy | 24pt |
| 8 | Hero card padding 16→12 (mirrors #218's DNA-panel treatment) | LeagueScreen | Low | Easy | 8pt |
| 9 | Chart-card hint line margins trimmed (mirrors #218 literal-value pattern) | LeagueSummaryScreen | Low | Easy | 8pt |
| 10 | Settings `section` marginTop 24→16 across ~6 headers — shortens scroll distance to Account/Sign-out | SettingsScreen | Low (not a violation, just friction) | Easy | ~48pt total |

**Not actionable / no findings:** SignInScreen (already fit-to-screen by construction, large margin), LeaguePickerScreen (natural FlatList, fits), MatchesScreen empty states (fit, only a defensive ScrollView-safety-net suggestion), SettingsScreen's first section (fits cleanly).
