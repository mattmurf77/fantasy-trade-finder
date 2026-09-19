# FTF Mobile — Per-Feature Test Cases (2026-07-10)

Part of the mobile-testing suite: `plan.md`, `prd.md`, `hld.md`, `lld.md`, `app-inventory-2026-07-10.md`. Covers all 82 features from the app inventory §7 (column **Feat#**). **Layer 1 case IDs are referenced by Maestro flow headers (`# tc:` lines)** — renaming an ID here requires updating the matching flow header.

**Columns:** `ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected`

- **Pri:** P0 (launch-blocking gate) / P1 / P2.
- **Layer:** `1` = Maestro sim flow. Every Layer-1 case also runs at Layer 2 (release-gate rerun on the RC build) — Layer 2 is only listed where a case is layer-2-specific (static/build checks). `3` = real-device Claude pass. `M` = manual/operator. `NA` = deliberately not automated (reason in the row + NOT-AUTOMATE register).
- **Profile:** `standard | fresh | near-unlock | no-leagues | two-leagues | large-league | sparse-roster | empty-league | single-format | demo | n/a` (LLD §3.1). `fresh` = exactly 1 league, Trade Finder locked, **zero** rankings. `near-unlock` = threshold−1 rankings (one submit crosses the unlock threshold). `no-leagues` = a second fixture user inside the fresh profile with zero leagues. `demo` = runner alias → standard DB + `+landing.try_before_sync=on` pin; the demo session is server-generated, so backend profile content is irrelevant. Demo profile is used **only** for demo-mode cases, never as a fixture shortcut for non-demo cases.
- **Flags:** `release` = release flag set (`config/features.json`). Six gated surfaces ship **ENABLED** in release: `swipe.qc_compliments`, `swipe.gesture_audit`, `trade_math.human_explanations`, `trade.finder_targeting`, `trade.preference_lists`, `trade.send_in_sleeper`. The remaining inventory-gated flags are **false** in release: `landing.smart_start_cta`, `landing.try_before_sync`, `league.activity_feed`, `league.unlock_badges_per_member`, `profiles.public_pages`, `trades.new_partners_alerts`, `trades.queue_2k`. Pins name any non-default state: `+flag=on` for a release-false flag, `+flag=off` for a release-true flag. Each release-enabled flag has an explicit off-boundary case (TC-TRI-16, TC-TRI-10, TC-TRD-13, TC-TRD-34, TC-TRD-35, TC-TRD-36); `trades.queue_2k`'s off state IS plain release (TC-TRD-27).
- **Steps shorthand:** `(O)` = ranked-opponent fixture; `(W)` = Sleeper write token (Layer 3 only, never Layer 1); `(P)` = push permission; `(persist)` = relaunch **without** clearState/clearKeychain (all other flows start `clearState+clearKeychain`); `INJ` = `/__test__/fail_next|latency` injection — the extended interface (LLD §4.3c) accepts `fail_next {path, status, body}`; `seed:` = profile-schema seed field (`matches_seed`, `activity_seed`, `feedback_reply_seed` — notifications are exercised via simctl push-injection, not DB seeds).
- `★` in the ID column = member of the 10-case smoke set.

**Conventions (from HLD/LLD, binding):** gestures are NOT automated in Layer 1 — button equivalents (Check/X, chevrons, jump-to-rank) carry the semantics; real gestures are Layer 3 checklist items. Server-chosen content is asserted structurally, never by player name. Error states use injection, not live failures (except the two kill-Flask cases, which are explicit). The `fail_next {path, status, body}` interface (LLD §4.3c) makes server error-branch bodies (`sleeper_not_linked`, `sleeper_rejected`, `roster_not_found`, `league_not_found`) automatable in Layer 1. Send-in-Sleeper always stops at/before the confirmation sheet; propose fails closed. Push cases use simctl payload injection and prove rendering + tap-routing only.

**Counts:** 201 cases — 45 P0 · 106 P1 · 49 P2 · 1 unprioritized NA row (TC-SLC-01). Smoke set: 10. NOT-AUTOMATE register: 12 entries (incl. 1 unreachable-by-nav entry).

*ID mapping note: cases were renumbered from both drafts; the only verbatim carry-over is Draft B's state-pollution canaries XC-07..09, which keep their numbers as TC-XC-07..09.*

---

## 1. SignIn (SGN) — features 1–5

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| ★TC-SGN-01 | 1 | P0 | 1 | standard | release | Fresh install; type `qa_standard`; tap Continue (variant leg: submit via keyboard "go") | Busy spinner in button; lands LeaguePicker; token stored; no error |
| TC-SGN-02 | 1 | P0 | 1 | standard | release | Enter unknown username (fixture 404); Continue | Error text "not found"; stays on SignIn; input editable |
| TC-SGN-03 | 1 | P1 | 1 | standard | release | Kill Flask; attempt sign-in; restore; retry | Error copy rendered, no crash; retry succeeds after restore |
| TC-SGN-04 | 2 | P1 | 1 | standard | release | Sign in; relaunch (persist) | "Continue as @qa_standard" Keychain hint shown; tap → auth succeeds |
| TC-SGN-05 | 3 | P1 | 1 | standard | +landing.smart_start_cta=on | Paste fixture Sleeper league URL; Continue | Resolves roster owner; proceeds to session/LeaguePicker |
| TC-SGN-06 | 4 | P1 | 1 | standard | +landing.smart_start_cta=on | Paste ESPN/MFL URL | Soft "coming soon" error; no crash; input retained |
| TC-SGN-07 | 3 | P1 | 1 | standard | release | Inspect input (flag off) | Plain username placeholder; no URL hint |
| TC-SGN-08 | 5 | P1 | 1 | demo | +landing.try_before_sync=on | Tap "Try the app on a sample league →" | demoBusy spinner → Main (skips LeaguePicker); Rank tab active; `isDemo` surfaces |
| TC-SGN-09 | 5 | P1 | 1 | standard | release | Inspect SignIn (flag off) | Demo link not rendered |
| TC-SGN-10 | 1 | P2 | 1 | standard | release | Tap Continue with empty field | No request fired; button disabled or inline error |
| TC-SGN-11 | 1 | P2 | 1 | standard | release | INJ latency 5000ms on auth; tap Continue (tap again mid-flight) | Busy state; exactly one request (no double-submit) |

## 2. LeaguePicker (LPK) — features 6–9

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-LPK-01 | 6 | P1 | 1 | two-leagues | release | Sign in | Both fixture leagues listed with names/sizes |
| ★TC-LPK-02 | 7 | P0 | 1 | standard | release | Tap league row | Row spinner; optimistic nav → Main; phase-2 init detached; Rank tab shows RankHome |
| TC-LPK-03 | 6 | P2 | 1 | standard | release | Pull-to-refresh list | RefreshControl spins; list re-renders; no dupes |
| TC-LPK-04 | 7 | P0 | 1 | standard | release | INJ fail_next `session/init` 500; pick league | Error surfaced; retry works; no half-initialized Main |
| TC-LPK-05 | 8 | P1 | 1 | standard | release | INJ latency 5000ms on leagues fetch | "Waking up server… 30s" slowLoad copy appears after 4s, then list |
| TC-LPK-06 | 6 | P1 | 1 | no-leagues | release | Sign in as the no-leagues fixture user | "No 2026 NFL leagues found" empty state |
| TC-LPK-07 | 9 | P0 | 1 | standard | release | Tap Sign out | Back to SignIn; token cleared (relaunch lands on SignIn, not Main) |
| TC-LPK-08 | 7 | P2 | 1 | standard | release | INJ latency on init; tap row, then tap a 2nd row | Per-row spinner; all rows disabled during select |
| TC-LPK-09 | 7 | P1 | 1 | standard | release | INJ fail phase-2 `submitSessionInit` only | Still lands Main (detached failure non-fatal by design); no error modal |

## 3. RankHome (RKH) & Rank-tab menu (NAV) — features 10–11

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-RKH-01 | 10 | P0 | 1 | fresh | release | First entry to Rank tab (pref null) | Chooser: 4 method cards + HandsOnMeter + axis render |
| TC-RKH-02 | 10 | P1 | 1 | fresh | release | Choose Trios; relaunch (persist) | Navigates to Trios; after relaunch Rank stack opens directly at Trios (pref persisted) |
| TC-RKH-03 | 10 | P1 | 1 | fresh | release | Choose each other card — parameterized (Anchors/Tiers/Manual) | Each navigates to its screen |
| TC-NAV-01 | 11 | P0 | 1 | standard | release | Tap Rank tab while on another tab | Action sheet with 5 rows opens (tab intercepted; no route change) |
| TC-NAV-02 | 11 | P1 | 1 | standard | release | Tap each row (Trios/Anchors/Tiers/Overall/Trends) | Navigates to target screen; HeaderBack returns |
| TC-NAV-03 | 11 | P2 | 1 | standard | release | Open sheet → Cancel; open → tap backdrop | Sheet dismisses both ways; underlying screen unchanged |

## 4. Trios — RankScreen (TRI) — features 12–20

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| ★TC-TRI-01 | 12 | P0 | 1 | standard | release | Tap 3 cards in order; Confirm | Rank badges 1/2/3 on tap; submit succeeds; progress count +1; next trio loads (structural — server-chosen players never asserted by name) |
| TC-TRI-02 | 12 | P1 | 1 | standard | release | Rank 2 cards; tap 1st again | Undo: its selection + later ranks cleared; badges recompute |
| TC-TRI-03 | 13 | P1 | 1 | standard | release | Enable "I AM SPEED"; tap 2 cards; relaunch (persist) | 3rd auto-ranked + auto-submit; next trio; toggle persists (`ftf.trios.speedMode`) |
| TC-TRI-04 | 14 | P1 | 1 | standard | release | Tap Skip | New trio fetched; progress count unchanged |
| TC-TRI-05 | 15 | P0 | 1 | standard | release | Switch position QB→RB→WR→TE | Trio refetches per position; per-position `count/threshold` shown |
| TC-TRI-06 | 16 | P1 | 1 | standard | release | Toggle SF/1QB FormatToggle | Trio + progress refetch under new format; active format persists |
| TC-TRI-07 | 17 | P2 | 1 | standard | release | Tap streak chip | Navigates to League tab |
| TC-TRI-08 | 18 | P2 | NA | standard | release | — | **NOT AUTOMATED:** QC-trio occurrence is server-chosen/nondeterministic; toast timing flaky. Flag ships ON in release — L3 eyeball; off-boundary pinned by TC-TRI-16 |
| TC-TRI-09 | 19 | P1 | 1 | standard | release | Long-press a card (flag ships on in release) | Player info sheet opens; dismiss works |
| TC-TRI-10 | 19 | P2 | 1 | standard | +swipe.gesture_audit=off | Long-press a card | No sheet opens (off-boundary) |
| TC-TRI-11 | 20 | P0 | 1 | near-unlock | release | Submit 1 trio (profile sits at threshold−1) | Segmented progress fills; "Trade Finder unlocked" banner; Trades gate opens |
| TC-TRI-12 | 12 | P0 | 1 | standard | release | INJ fail_next `POST /api/rank3` 500; confirm a trio | Rollback: selection cleared, fail toast, trio refetched, count NOT incremented |
| TC-TRI-13 | 12 | P2 | 1 | standard | release | INJ latency 3000ms on trio load | 3 skeleton cards while loading |
| TC-TRI-14 | 12 | P1 | 1 | standard | release | INJ fail_next trio load 500 | Error + "Try again"; retry recovers |
| TC-TRI-15 | 12 | P1 | 3 | standard | release | Real device: rapid tap-tap-tap cadence | Haptics fire; no double-submit; feels responsive |
| TC-TRI-16 | 18 | P2 | 1 | standard | +swipe.qc_compliments=off | Submit 3 trios | No compliment toast ever renders (deterministic off-boundary for the release-enabled flag) |

## 5. Tiers — TiersScreen (TIR) — features 21–29 (+16)

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-TIR-01 | 21 | P1 | 1 | standard | release | Open Tiers | Board renders: tier bins + tiles + Unassigned |
| ★TC-TIR-02 | 22, 28 | P0 | 1 | standard | release | Tap chevron on a tiered tile; Save; reload screen | Tile moves one tier; dirty state (Save enabled); Save toast; edit persisted after reload |
| TC-TIR-03 | 28 | P1 | 1 | standard | release | Make edit; background app (triggers refetch); foreground | Dirty edits survive background refetch (dirty-guard) |
| TC-TIR-04 | 23 | P1 | 1 | standard | release | Select mode → tap 2 chips → bulk Tier up → Done; then multi-select → quick TierTargetChips (send to a named tier) | Both players move; quick-chip targets land correctly; selection clears |
| TC-TIR-05 | 24 | P1 | 1 | standard | release | "Copy tier list from {other format}" → confirm Alert; repeat → Cancel | Confirm: tiers replaced + toast. Cancel: untouched |
| TC-TIR-06 | 25 | P1 | 1 | standard | release | "Reset to suggested" → confirm Alert; repeat → Cancel | Confirm: cleared to suggested + toast. Cancel: untouched |
| TC-TIR-07 | 26 | P2 | 1 | standard | release | Expand full-screen board → collapse | Board toggles; controls reachable in both states |
| TC-TIR-08 | 27 | P2 | NA | standard | release | — | **NOT AUTOMATED:** sticky tier header is viewability-driven visual polish; assertion is pixel-guesswork. L3 eyeball (TC-TIR-15) |
| TC-TIR-09 | 21 | P1 | 1 | standard | release | Multi-select a tiered player → bulk move down past Bench toward Unassigned | Rejected with toast "Tiered players can't move to Unassigned" (button-equivalent of drag-reject) |
| TC-TIR-10 | 29 | P1 | 1 | standard | release | (O) Inspect a tile | TileStats "You 30d" + consensus render; TradeMeter bars present with fixture values |
| TC-TIR-11 | 28 | P0 | 1 | standard | release | INJ fail_next tiers save 500; Save | Error toast; dirty state preserved (edits not lost) |
| TC-TIR-12 | 16 | P1 | 1 | standard | release | FormatToggle on Tiers | Board reloads for other format; per-format tiers independent |
| TC-TIR-13 | 21 | P2 | 1 | large-league | release | Open Tiers in 32-team league; scroll to bottom | Renders without hang; headers stay correct |
| TC-TIR-14 | 30 | P1 | 1 | standard | release | Tap Anchors button | PickAnchor opens; HeaderBack returns to Tiers |
| TC-TIR-15 | 21, 27 | P1 | 3 | standard | release | Real device: long-press 220ms + drag tile across tier boundary; attempt drag to Unassigned; observe sticky header while scrolling | Drag activates; drop re-bins and list settles; drag-to-Unassigned shows reject toast; sticky header tracks current tier |

## 6. Anchors — PickAnchorScreen (ANC) — features 30–31

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-ANC-01 | 30 | P0 | 1 | standard | release | Open Anchors; tap "2 firsts" on current player | Saves; next player card; consequence line shows last placement |
| TC-ANC-02 | 31 | P1 | 1 | standard | release | Tap "Skip — not sure" | Advances without save |
| TC-ANC-03 | 31 | P1 | 1 | standard | release | Anchor 2 players; relaunch (persist); return | Resumes at player 3 (`ftf_anchor_done_v1_<fmt>` resume set, per format) |
| TC-ANC-04 | 31 | P1 | 1 | sparse-roster | release | Anchor through full (small) pool; then "Start over" | "All anchored" done card; start-over restarts queue |
| TC-ANC-05 | 30 | P1 | 1 | standard | release | Anchor one player; navigate to Tiers/Trios | Downstream caches invalidated (no stale spinner/error; rankings reflect anchor influence structurally) |
| TC-ANC-06 | 30 | P1 | 1 | empty-league | release | Open Anchors with empty pool | "No players to anchor" state; no crash |
| TC-ANC-07 | 30 | P1 | 1 | standard | release | INJ fail_next anchor save 500 | Error surfaced; player NOT marked done; retry works |
| TC-ANC-08 | 31 | P2 | 1 | standard | release | Background/foreground mid-run | Same player still presented (staleTime-Infinity queue stability) |

## 7. Overall Ranks — ManualRanksScreen (MRK) — features 32–35

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-MRK-01 | 32 | P1 | 1 | standard | release | Open Overall Ranks | Board renders with rank numbers |
| TC-MRK-02 | 33 | P0 | 1 | standard | release | Tap rank number; type target rank; submit | Player jumps to rank; list reorders; status pill pending→saving→saved |
| TC-MRK-03 | 35 | P0 | 1 | standard | release | Two quick jump-edits <600ms apart; reload | Single coalesced save (pill cycles once; flask log: exactly 1 reorder request); final order correct |
| TC-MRK-04 | 34 | P1 | 1 | standard | release | Filter ALL→QB→RB→WR→TE | Client-side filter; jump-to-rank still targets overall rank; ALL restores |
| TC-MRK-05 | 35 | P0 | 1 | standard | release | INJ fail_next reorder save 500 | Pill shows error state; edit retained locally; retry recovers |
| TC-MRK-06 | 32 | P2 | 1 | fresh | release | Open with no rankings | "No rankings yet" empty state |
| TC-MRK-07 | 32 | P2 | 1 | large-league | release | Jump a player to rank 1, then to last | Both extremes land correctly; no index drift |
| TC-MRK-08 | 32 | P1 | 3 | standard | release | Real device: long-press drag a row 5+ positions | Drag smooth (activationDistance 5 + 220ms); order persists after save |

## 8. Trends — TrendsScreen (TRN) — features 36–37 (+34)

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-TRN-01 | 36 | P1 | 1 | standard | release | Open Trends | Risers/fallers render with TrendBars (seeded 30d history; TrendBar count >0) |
| TC-TRN-02 | 37 | P1 | 1 | standard | release | (O) Scroll to easiest sells/buys | Consensus-gap section renders (leagueId-gated query) |
| TC-TRN-03 | 34 | P1 | 1 | standard | release | Position filter each of ALL/QB/RB/WR/TE | Both sections re-filter; explainer copy present (FB-94) |
| TC-TRN-04 | 36 | P2 | 1 | standard | release | Pull-to-refresh | Sections refetch (structural) |
| TC-TRN-05 | 36 | P1 | 1 | standard | release | INJ fail_next risers-fallers 500 | Per-section error + "Try again"; other section unaffected |
| TC-TRN-06 | 36, 37 | P2 | 1 | fresh | release | Open with no history / no baseline | Per-section empty states (no-history, no-baseline, no-gaps); screen intact |

## 9. Trades deck — TradesScreen (TRD) — features 38–53 (+8, 20)

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| ★TC-TRD-01 | 38 | P0 | 1 | standard | release | Tap "Find a Trade" | Progress strip + meter during job; cards append as they stream; peek of next card behind top; first card ≤60s (poll backoff budget) |
| TC-TRD-02 | 38 | P1 | 1 | sparse-roster | release | Find a Trade; disposition through all cards | Graceful sparse deck (fewer/no cards, no crash); "That's all for now" terminal state; "Find more trades" re-arms |
| ★TC-TRD-03 | 40 | P0 | 1 | standard | release | Tap Check on card 1; X on card 2 | Deck advances each tap (optimistic); peek card promotes to top |
| TC-TRD-04 | 38 | P1 | 1 | standard | release | Open Trades before any job | "Hit Find a Trade" empty state |
| TC-TRD-05 | 40 | P0 | 1 | standard | release | INJ fail_next `/api/trades/swipe` 500; tap Check | Optimistic advance ROLLS BACK (card rewinds to top); error toast |
| TC-TRD-06 | 39 | P1 | 3 | standard | release | Real device: physical swipe right / left with flick velocity | Swipe registers (>120px + velocity>200); rotation animates; same disposition as buttons |
| TC-TRD-07 | 41 | P1 | 1 | standard | release | Toggle fairness OFF; relaunch (persist) | Persisted (`ftf:trades:fairness_on`); deck re-sorted (mismatch mode) indicated |
| TC-TRD-08 | 42 | P1 | 1 | standard | release | Tap "Bad trade?" flag | `/api/trades/flag` POST fires; card handled per UX; no crash |
| TC-TRD-09 | 43 | P1 | 1 | standard | release | (O) Open swap affordance; pick replacement player | SwapPlayerSheet lists candidates; re-priced via evaluate Mode B; card verdict updates |
| TC-TRD-10 | 44 | P1 | 1 | standard | release | Long-press give-side player → mark untouchable; unmark (flag ships on in release) | Pref saved (asset-prefs POST); next generation excludes player (structural chip/state); unmark works |
| TC-TRD-11 | 45 | P1 | 1 | standard | release | Direction "Acquire" → picker (@owner badges) → pick leaguemate player → Find (flag ships on in release) | Chip pinned + removable; job request carries `pinned_receive` (flask log) |
| TC-TRD-12 | 45 | P1 | 1 | two-leagues | release | Pin a target; switch league | Chips cleared (session-local per league) |
| TC-TRD-13 | 46 | P1 | 1 | standard | release / +trade_math.human_explanations=off pair | Inspect card under both flag states | Reason lines present under release (flag on); absent under the off pin |
| TC-TRD-14 | 47 | P1 | 1 | standard | release | Open Outlook Edit sheet; change stance; save | Sheet opens/closes; selection persists; next generation reflects outlook (structural: job accepts param) |
| TC-TRD-15 | 48 | P1 | 1 | two-leagues | release | Tap LeaguePill → pick other league; rerun with INJ latency >4s on switch | Switching overlay; deck/league context swaps; latency leg shows slowSwitch copy |
| TC-TRD-16 | 8 | P1 | 1 | standard | release | INJ latency 5000ms on generate | 4s "waking up" slow copy appears (deterministic) |
| TC-TRD-17 | 49 | P2 | 1 | standard | +trades.new_partners_alerts=on | seed: `activity_seed` (new-partner event); open Trades | NewPartnersBanner renders; dismiss works |
| TC-TRD-18 | 50 | P2 | 1 | empty-league | release | Open Trades in cold-start league (low coverage) | InviteLeaguematesBanner renders |
| TC-TRD-19 | 51 | P0 | 1 | single-format | release | Open Trades | FormatGate copy + copy-tiers/manual paths offered; no deck; gate clears after copy |
| TC-TRD-20 | 52 | P1 | 1 | standard | +trades.queue_2k=on | Queue 2 trades; open queue sheet; dequeue 1 | Footer bar count=2; sheet lists both; dequeue works |
| TC-TRD-21 | 52 | P2 | 3 | standard | +trades.queue_2k=on | (W, QA account) Real device: "Send All" | Opens Sleeper URLs with 500ms stagger (external app hop; see NOT-AUTOMATE register — Layer 1 asserts only to button-enabled via TC-TRD-20) |
| TC-TRD-22 | 38 | P0 | 1 | standard | release | INJ fail_next `/api/trades/status` 500 ×5 | MAX_POLL_FAILURES hit → job-failed UI; polling stops (no infinite spinner, no runaway requests) |
| TC-TRD-23 | 38 | P0 | 1 | standard | release | INJ fail_next generate 500 | Clean error state; "Find a Trade" retryable |
| TC-TRD-24 | 38 | P2 | 1 | standard | release | Tap "Hide" during running job | Job dismissed; UI returns to idle; no zombie progress strip |
| TC-TRD-25 | 38 | P2 | 1 | standard | release | Kill app mid-job; relaunch | No stuck overlay; deck idle or resumes cleanly |
| TC-TRD-26 | 20 | P1 | 1 | fresh | release | Open Trades while Trade Finder locked | Gating state (not a broken deck); directs to ranking |
| TC-TRD-27 | 52 | P2 | 1 | standard | release | Inspect Trades footer/queue affordance (`trades.queue_2k` is false in release) | Queue button absent — queue_2k's off state IS plain release |
| TC-TRD-28 | 53 | P0 | 1 | standard | release | (no W — fixture has no write token by construction; flag ships on in release) Tap Send in Sleeper | checking → not-linked Alert offering Connect; **NO propose call fired** (propose also fails closed under FTF_TEST_MODE) |
| TC-TRD-29 | 53 | P0 | 1 | standard | release | (O) Step 1: INJ `fail_next {path: GET /api/sleeper/link, status: 200, body: {"connected": true}}` — precondition override past the client's link-status gate (LLD §4.3c licenses 2xx overrides; propose itself refuses 2xx overrides); step 2: INJ `fail_next {path: POST /api/trades/propose, status: 400, body: {"error":"sleeper_not_linked"}}`; attempt send | Propose is reached (`propose_route_hits` +1, non-gating; `completed_proposes` stays 0); reconnect-branch messaging rendered; **fails closed**; no retry storm |
| TC-TRD-30 | 53 | P0 | 3 | standard | release | (W, QA account) Real device: full flow up to confirmation sheet → **STOP**; cancel | Confirmation renders correct give/receive; tester cancels; **no send** (protocol rail) |
| TC-TRD-31 | 53 | P1 | 3 | standard | release | (W) Return from SleeperConnect to sending screen | Focus-return re-check Alerts result (`awaitingLinkRef`) |
| TC-TRD-32 | 53 | P2 | 1 | standard | release | Send button in calculator real-values mode (no league/opponent context); tap | Tap does not crash; **no propose attempt** (flask log). `Linking.openURL` leaves the app — deep-link landing not assertable in Maestro (see register) |
| TC-TRD-33 | 53 | P1 | 1 | standard | release | (O) Step 1: INJ `fail_next {path: GET /api/sleeper/link, status: 200, body: {"connected": true}}` (same gate override as TC-TRD-29); step 2: attempt send with NO propose injection (bare FTF_TEST_MODE fail-closed default: propose → 599) | App degrades sanely on the un-bodied 599: generic error surfaced, no crash, no send (`completed_proposes` stays 0), flow recoverable |
| TC-TRD-34 | 45 | P2 | 1 | standard | +trade.finder_targeting=off | Inspect Trades finder controls | Targeting toggle/picker absent (off-boundary) |
| TC-TRD-35 | 44 | P2 | 1 | standard | +trade.preference_lists=off | Long-press give-side player | No untouchable affordance (off-boundary) |
| TC-TRD-36 | 53 | P2 | 1 | standard | +trade.send_in_sleeper=off | Inspect a trade card | SendInSleeperButton not rendered (off-boundary) |

## 10. Trade Calculator (CLC) — features 55–59

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| ★TC-CLC-01 | 55 | P0 | 1 | standard | release | Real-values mode: add 2-for-1 via picker | Debounced (250ms) evaluate; ConsensusVerdictCard renders with values |
| TC-CLC-02 | 55 | P1 | 1 | standard | release | Rapid add/remove players <250ms apart | Single final evaluate; verdict matches final sides |
| TC-CLC-03 | 56 | P0 | 1 | standard | release | Demo-league mode: build trade; switch partner chips | Local math; dual-board VerdictPanel; rosters swap + verdict recomputes; **zero calc requests in flask log** |
| TC-CLC-04 | 57 | P0 | 1 | standard | release | (O) In-league mode: pick ranked opponent; build trade | Two-board LeagueVerdict mutual-gain verdict (Mode B) with both deltas |
| TC-CLC-05 | 57 | P1 | 1 | standard | release | (O) In-league: pick unranked opponent | Unranked dot on picker row; consensus-fallback verdict copy |
| TC-CLC-06 | 55 | P1 | 1 | standard | release | INJ fail_next `/api/trade/values` 500 | Error + retry + "switch to demo" escape hatch works |
| TC-CLC-07 | 55 | P1 | 1 | standard | release | Toggle 1QB↔SF chips (live mode) | Values re-fetched per format; verdict recomputes |
| TC-CLC-08 | 58 | P1 | 1 | standard | release | Picker add/remove players both sides; remove last player | Sides update; removing last player clears verdict |
| TC-CLC-09 | 58 | P1 | 1 | standard | release | Tap a suggestion/add-on card | Applied to sides; verdict re-evaluates |
| TC-CLC-10 | 59 | P1 | 1 | standard | release | Clear trade | Sides emptied; verdict cleared; draft cleared |
| TC-CLC-11 | 59 | P1 | 1 | standard | release | Build trade; relaunch (persist); open Calculator | Draft restored (`ftf:tradecalc:v1`) |
| TC-CLC-12 | 59 | P2 | M | standard | release | Share trade | **MANUAL:** OS share sheet is outside the app process; automation asserts tap-no-crash only; content checked by hand |
| TC-CLC-13 | 55, 58 | P2 | 1 | standard | release | One-sided trade (give side only) | One-sided value readout; no bogus verdict; no-suggestions text when none |

## 11. Matches — MatchesScreen (MAT) — features 60–63

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| ★TC-MAT-01 | 60 | P0 | 1 | standard | release | (O; seed: `matches_seed`) Open Matches | Skeleton tiles → seeded mutual matches render |
| TC-MAT-02 | 60 | P0 | 1 | standard | release | Dismiss a mutual match | Optimistic removal; stays gone after refetch |
| TC-MAT-03 | 60 | P0 | 1 | standard | release | INJ fail_next dismiss 500 | ROLLBACK: match card returns; error toast |
| TC-MAT-04 | 61 | P1 | 1 | standard | release | (O; seed: `matches_seed` awaiting entry) Switch to Awaiting segment | Lazy query fires; seeded awaiting trade renders |
| TC-MAT-05 | 62 | P1 | 1 | two-leagues | release | League filter chips: All → league 2 → All | Filtered list; per-filter empty state where none; All restores |
| TC-MAT-06 | 62 | P2 | 1 | standard | release | Pull-to-refresh | Refetch (structural); no dupes |
| TC-MAT-07 | 63 | P1 | 1 | standard | release | From League screen, tap a Matches tile | Lands on Matches with segment/filter from `route.params` |
| TC-MAT-08 | 44 | P2 | 1 | standard | release | Long-press player on a match card → untouchable (flag ships on in release) | Same asset-pref behavior as deck |
| TC-MAT-09 | 60, 61 | P2 | 1 | fresh | release | Open both segments with no matches | Per-segment empty states |
| TC-MAT-10 | 60 | P1 | 1 | standard | release | INJ fail_next matches/all 500 | Error state; recovery on retry |

## 12. League — LeagueScreen (LEA) — features 64–69 (+48, 73)

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| ★TC-LEA-01 | 64 | P0 | 1 | standard | release | Open League tab | Hero card, team/joined chips, sections render (skeletons then data) |
| TC-LEA-02 | 65 | P1 | 1 | standard | +league.unlock_badges_per_member=on | Tap joined chip | Members overlay; unlock/join chips per member |
| TC-LEA-03 | 65, 66 | P2 | 1 | standard | release | Inspect members overlay + scroll (flags off) | Flag-off sweep: no unlock badges; activity section absent |
| TC-LEA-04 | 66 | P1 | 1 | standard | +league.activity_feed=on | seed: `activity_seed`; scroll to feed | ActivityFeed rows render |
| TC-LEA-05 | 67 | P1 | 1 | standard | release | (O) Scroll to contrarian leaderboard | Renders with seeded rankings-divergence data |
| TC-LEA-06 | 68 | P1 | 1 | standard | release | Inspect coverage meter | Meter reflects seeded coverage fraction |
| TC-LEA-07 | 69 | P2 | 1 | standard | release | Scroll to leaderboards section | Renders; no crash on partial data |
| TC-LEA-08 | 48, 73 | P0 | 1 | two-leagues | release | Hero card → LeagueSwitcherSheet → switch | Context swaps; caches invalidated (rankings/matches/sections reflect league B) |
| TC-LEA-09 | 64 | P2 | 1 | standard | release | Pull-to-refresh | All sections refetch |
| TC-LEA-10 | 64 | P2 | 1 | standard | release | INJ latency 3000ms | Per-section skeletons |
| TC-LEA-11 | 64 | P1 | 1 | standard | release | INJ fail_next `/api/league/activity` 500 only | Rest of screen renders — one section's failure never blanks the dashboard |

## 13. Portfolio (POR) — feature 70

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-POR-01 | 70 | P1 | 1 | two-leagues | release | Open Trades subnav → Portfolio | Cross-league exposure rows; per-player tier-chip strips |
| TC-POR-02 | 70 | P1 | 1 | standard | release | Portfolio entry with 1 league | Gate: "Connect a second league"; subnav pill hidden (assert absence) |
| TC-POR-03 | 70 | P2 | 1 | two-leagues | release | Profile-schema roster config: the two leagues' rosters disjoint (no shared players); open Portfolio | "No exposure yet" empty state |
| TC-POR-04 | 70 | P1 | 1 | two-leagues | release | INJ fail_next `/api/portfolio` 500 | Error state + retry works |
| TC-POR-05 | 70 | P2 | 1 | two-leagues | release | Inspect chips | "Pool" label (backend emits no per-league tier — pins current contract) |

## 14. Public profile (PRO) — feature 71

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-PRO-01 | 71 | P1 | 1 | standard | +profiles.public_pages=on | `simctl openurl dtf://u/qa_opp_ranked` | Profile renders: hero, ranks-by-position, tiers snapshot, contrarian takes |
| TC-PRO-02 | 71 | P1 | 1 | standard | +profiles.public_pages=on | Deep link to unknown username; check flask log | "Profile not found" 404 state, no crash; exactly 1 request (retry skips 404 — pins client retry contract) |
| TC-PRO-03 | 71 | P1 | 1 | standard | release | Open a /u/ link (flag off) | "Coming soon" state |
| TC-PRO-04 | 71 | P2 | 1 | standard | +profiles.public_pages=on | Malformed /u/ (empty username) | Missing-username state |

## 15. Settings (SET) — features 72–75 (+9)

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-SET-01 | — | P2 | 1 | standard | release | Open Settings modal; close | Modal header renders; back dismisses cleanly |
| TC-SET-02 | 9 | P1 | 1 | standard | release | Sign out from Settings | Back to SignIn; SecureStore token cleared; relaunch stays signed out |
| TC-SET-03 | 73 | P1 | 1 | two-leagues | release | Switch league via Settings | Same contract as TC-LEA-08; Main reflects new league |
| TC-SET-04 | 72 | P1 | 1 | standard | release | Connect another Sleeper league | Routes to LeaguePicker flow; league count increments; Portfolio unlocks at 2 |
| TC-SET-05 | 74 | P1 | 1 | standard | release | Move ranking-method SteerSlider; reopen; relaunch (persist) | `/api/ranking-method` POST fires; persisted on reopen; Rank stack initial route changes next launch (relaunch must NOT clearState — clearState wipes `ftf_rank_method_pref`) |
| TC-SET-06 | 75 | P1 | 1 | standard | release | Toggle a notification pref + quiet hours | PUT prefs fires; toggles persist across relaunch |

## 16. SleeperConnect (SLC) — feature 54

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-SLC-01 | 54 | — | NA | n/a | — | — | **NOT AUTOMATED:** live sleeper.com login in a WebView — external site, real credentials, injected-JS token polling; unmockable and ToS-sensitive. Covered at L3 by TC-SLC-03 with QA account |
| TC-SLC-02 | 54 | P2 | M | standard | release | Open Connect with network to sleeper.com blocked (host-level block) | "Couldn't connect — try again" error overlay |
| TC-SLC-03 | 54 | P0 | 3 | standard | release | (W, QA account) Real device: full connect | Sleeper login page loads; token captured; "Connecting…" overlay → back; link status connected; then SendInSleeper reaches confirm sheet → **STOP** (no send) |

## 17. Feedback (FBK) — features 79–80

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-FBK-01 | 79 | P1 | 1 | standard | release | Tap FeedbackFAB on Trades | Sheet opens, screen field prefilled "Trades"; FAB persists across tabs |
| TC-FBK-02 | 79 | P1 | 1 | standard | release | Severity bug → note → submit; open inbox (Settings → Test feedback) | Saved locally + POST `/api/feedback`; inbox lists note with badge Synced |
| TC-FBK-03 | 80 | P1 | 1 | standard | release | INJ fail_next `/api/feedback`; submit; open inbox; Retry sync | Pending/Failed badge → Retry → Synced |
| TC-FBK-04 | 80 | P2 | M | standard | release | Share feedback markdown | **MANUAL:** OS share sheet (same reason as TC-CLC-12); tap-no-crash asserted, content by hand |
| TC-FBK-05 | 80 | P2 | 1 | standard | release | Long-press row → Delete → confirm; Clear all → confirm; repeat with Cancel | Row deleted; list cleared; Cancel leaves intact |
| TC-FBK-06 | 80 | P2 | 1 | standard | release | seed: `feedback_reply_seed`; open inbox | Operator status line + unread dot render (via `/api/feedback/mine`); `closed` notes hidden |

## 18. Push & notifications (PU) — features 76–78

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-PU-01 | 77 | P1 | 1 | near-unlock | release | Submit 1 trio to cross unlock threshold (priming gated on `progress.unlocked`); tap "Maybe later" | PushPrimingModal appears once; dismisses; not re-shown this session; no system dialog |
| TC-PU-02 | 77 | P1 | 3 | standard | release | (P, QA account) Real device: priming → "Enable notifications" | iOS permission dialog; accept → token registered (sim can't: `Device.isDevice` guard + no APNs) |
| TC-PU-03 | 78 | P1 | 1 | standard | release | `simctl push` payload `data.type=match` with app backgrounded; tap banner | App foregrounds on Matches tab. **Proves rendering + tap-routing ONLY — not permission, registration, or delivery** |
| TC-PU-04 | 78 | P2 | 1 | standard | release | `simctl push` league-kind and rank-kind payloads | Routes to League / Rank respectively |
| TC-PU-05 | 76 | P1 | 1 | standard | release | `simctl push` foreground payload (primary leg — the in-app feed is in-memory, not DB-seedable); open bell | TopBar bell badge increments; sheet lists item; read/read-all clears badge |
| TC-PU-06 | 78 | P2 | 3 | standard | release | (P) Real device: trigger real backend push, foreground + background | True APNs receipt on hardware — the only place this is real |

## 19. Deep links, session, cross-cutting & canaries (XC) — features 81–82 + suite rails

| ID | Feat# | Pri | Layer | Profile | Flags | Steps | Expected |
|---|---|---|---|---|---|---|---|
| TC-XC-01 | 82 | P1 | 1 | standard | release | Background app 60s+; foreground | Session revalidation fires (flask log); no sign-out flash; screens refetch; UI undisturbed |
| TC-XC-02 | 82 | P0 | 1 | standard | release | `POST /__test__/reset` (clears in-memory sessions — sessions are a dict, not a table); perform an action | FB-45 path: 401 → token cleared only if matching → re-mint/re-auth; NO infinite signout loop |
| TC-XC-03 | 71, 81 | P1 | 1 | standard | +profiles.public_pages=on | `simctl openurl` on TERMINATED app: `dtf://u/x?ref=qa_ref` | Cold-start `getInitialURL` path: boots, routes to Profile; `invited_by` forwarded on next session/init (flask log) |
| TC-XC-04 | 81 | P1 | 1 | standard | +profiles.public_pages=on | Same URL with app foregrounded (warm) | Manual handler routes to Profile; no duplicate nav |
| TC-XC-05 | 81 | P1 | 1 | standard | release | Sign in via `dtf://signin?ref=qa_opp_ranked`; pick league | `invited_by` present in `/api/session/init` body (flask log/DB row) |
| TC-XC-06 | — | P1 | 1 | standard | release | Run with a flag ON; relaunch (persist) against flag-OFF backend | Boot shows cached-flag surface, then degrades after revalidate — pins flag-cache staleness behavior |
| ★TC-XC-07 | — | P0 | 1 | n/a | release | **CANARY:** after any prior flow, launch with clearState+clearKeychain | SignIn shown; no session, no league, no cached deck — proves per-flow reset |
| TC-XC-08 | — | P0 | 1 | standard | release | **CANARY:** phase 1 — browse rankings to populate the persisted cache; phase 2 — mutate server state via UI (jump-to-rank reorder; no DB-mutation endpoint exists); phase 3 — relaunch (persist) <30min | Persister restores stale data, then refetch corrects (refetch-over-stale) — stale data must not stick |
| TC-XC-09 | — | P0 | 1 | standard | release | **CANARY:** fresh (cleared) launch after TC-SGN-04 ran previously | NO "Continue as" hint (keychain actually cleared) |
| TC-XC-10 | — | P0 | 1 | standard | release | Kill Flask mid-session; navigate all tabs; restore Flask | Error/empty states everywhere; zero crashes; recovery when backend returns |
| TC-XC-11 | — | P1 | 1 | standard | release | INJ latency 20000ms on a GET (15s client timeout) | "Server is waking up — please retry." copy path exercised |
| TC-XC-12 | — | P2 | 1 | standard | release | INJ fail_next a GET 503 ×1 | Silent auto-retry succeeds; exactly 2 requests in flask log (retry contract) |
| TC-XC-13 | — | P0 | 1 | standard | release | Tabs-render sweep: visit all 4 tabs + one Rank sub-screen + Calculator | Every screen renders; screenshot each; no redbox/blank |
| TC-XC-14 | 5, 56 | P0 | 1 | demo | +landing.try_before_sync=on | Demo smoke: demo start → trio submit → calculator demo verdict | Full no-auth path green (cheapest end-to-end canary; runs pre-flight before the signed-in chain) |
| TC-XC-15 | — | P0 | 2 | n/a | release | `sim-build.sh --env prod-check` | Shipping config resolves to onrender.com URL + real DSN (static check) |
| TC-XC-16 | — | P0 | 1 | n/a | release | Run-end rail audit (implicit in every run) | run-report rails: `sleeper_live_egress_attempts=0` (canonical name), `write_token_present=false`, `sentry_dsn_nulled=true`. The counter observes **backend** live-Sleeper attempts; app-side prod-contact proof is indirect — fixture-only usernames fail loudly at sign-in against any non-fixture backend |
| TC-XC-17 | — | P0 | 1 | n/a | release | `ui-test.sh` pointed at prod (onrender) URL — drill | Exit 3, nothing launched (rail drill) |
| TC-XC-18 | — | P1 | 1 | standard | release | HeaderBack on Anchors/Tiers/ManualRanks/Trends/Calculator | Always-on back returns (fallback route Trios/TradesHome — regression guard) |
| TC-XC-19 | — | P1 | 1 | standard | release | Render sweep on iPad Pro 11" and iPhone 16e | No clipped controls/unreachable buttons; screenshots filed (iPad report-only) |
| TC-XC-20 | — | P1 | 3 | standard | release | Real device: dark-mode OLED pass, safe-area/notch, touch-target comfort, scroll feel, haptics spot-check, cold-launch splash gate | Judgment findings in Layer-3 report; boot gate spinner → SignIn/Main with no flash-of-wrong-screen |
| TC-XC-21 | — | P2 | 1 | standard | release | Exercise prefetch paths (tab-tap prefetch, RankMenu prefetch) | No error toasts from prefetch; navigation instant after prefetch (soft assert) |
| TC-XC-22 | — | P1 | 2 | standard | release | Release-build cold start | No dev menu, no redbox; Sentry inert (bundle-dump assert); splash → SignIn |

---

## Smoke set (10, ★)

`TC-SGN-01, TC-LPK-02, TC-TRI-01, TC-TIR-02, TC-TRD-01, TC-TRD-03, TC-CLC-01, TC-MAT-01, TC-LEA-01, TC-XC-07`

**Ten independent flows — no chaining.** Each flow self-signs-in (~8–12 s against the seam), so any one can fail or be rerun in isolation; the set still fits the <15 min budget (PRD M1). Touches auth, session init, all four tabs, a persisted mutation (tiers save), the streaming job, an optimistic-disposition surface, the calculator, and the state-reset canary. TC-XC-14 (demo no-auth canary) runs as the pre-flight; TC-XC-16 (rail audit) is implicit in every run.

## P0 gate set (45)

Sign-in/session: TC-SGN-01, TC-SGN-02, TC-LPK-02, TC-LPK-04, TC-LPK-07, TC-XC-02
Ranking: TC-RKH-01, TC-NAV-01, TC-TRI-01, TC-TRI-05, TC-TRI-11, TC-TRI-12, TC-TIR-02, TC-TIR-11, TC-ANC-01, TC-MRK-02, TC-MRK-03, TC-MRK-05
Trades: TC-TRD-01, TC-TRD-03, TC-TRD-05, TC-TRD-19, TC-TRD-22, TC-TRD-23, TC-TRD-28, TC-TRD-29, TC-TRD-30 (L3)
Calculator/Matches/League: TC-CLC-01, TC-CLC-03, TC-CLC-04, TC-MAT-01, TC-MAT-02, TC-MAT-03, TC-LEA-01, TC-LEA-08
Sleeper link: TC-SLC-03 (L3)
Rails & canaries: TC-XC-07, TC-XC-08, TC-XC-09, TC-XC-10, TC-XC-13, TC-XC-14, TC-XC-15 (L2), TC-XC-16, TC-XC-17

## NOT-AUTOMATE register (honest coverage)

| Item | Case(s) | Reason | Compensating coverage |
|---|---|---|---|
| QC-compliment toast | TC-TRI-08 | QC-trio occurrence is server-chosen/nondeterministic; toast timing flaky (flag ships on in release) | L3 eyeball; TC-TRI-16 pins the deterministic off-boundary |
| Sticky tier header | TC-TIR-08 | Viewability-driven visual polish; assertion would be pixel-guesswork | TC-TIR-15 (L3) + TC-XC-20 |
| Tier drag-to-bin + drag-reject toast | (no Layer-1 case) | Patched DraggableFlatList 220ms long-press drag = documented top flake source (inventory §6) | TC-TIR-02/04/09 cover movement semantics via buttons; TC-TIR-15 (L3) covers drag feel + reject toast |
| Overall-ranks drag reorder | (no Layer-1 case) | Same flake class (activationDistance 5 + 220ms) | TC-MRK-02/03 cover reorder semantics via jump-to-rank; TC-MRK-08 (L3) |
| Trade-card pan swipe | (no Layer-1 case) | 120px + velocity>200 threshold defeats programmatic swipes | TC-TRD-03 exercises the identical disposition code path via buttons; TC-TRD-06 (L3) |
| External `Linking.openURL` hops | TC-TRD-21 (queue "Send All"), TC-TRD-32 (calculator send fallback) | Leaves the app — unassertable in Maestro; Send All is also adjacent to real sends | TC-TRD-20 asserts up to button-enabled; TC-TRD-32 asserts tap-no-crash + no-propose (flask log); TC-TRD-21 (L3, QA account) |
| Sleeper WebView login | TC-SLC-01 | Live external auth on sleeper.com; real credentials; injected-JS token polling; unmockable + ToS-sensitive | TC-SLC-03 (L3, QA account); TC-SLC-02 (M) for the error overlay |
| OS share sheets | TC-CLC-12, TC-FBK-04 | Share sheet lives outside the app process | Tap-no-crash asserted in-flow; content checked manually |
| Push enable + registration; real APNs | (no Layer-1 case) | Simulator cannot: `Device.isDevice` guard, no APNs | TC-PU-02 / TC-PU-06 (L3); TC-PU-03/04/05 prove rendering + tap-routing via simctl |
| Haptics | (throughout) | No simulator observability | L3 spot-checks (TC-TRI-15, TC-XC-20) |
| iPad layouts beyond render smoke | (no cases) | Declared but zero users | TC-XC-19 render-only, report-only; revisit on demand |
| "In Main with no league" states | (deleted: ex-TC-CLC-14, ex-TC-LEA-12) | **UNREACHABLE BY NAV:** RootNav routes `!league` → LeaguePicker, so a signed-in user can never reach Calculator/League without a league | None needed — the state cannot occur; `hasLeague`-false tab-hiding logic is dead code from Main's perspective |

## Coverage audit — feature # → case IDs (all 82 covered)

| Feat# | Case IDs |
|---|---|
| 1 | TC-SGN-01, TC-SGN-02, TC-SGN-03, TC-SGN-10, TC-SGN-11 |
| 2 | TC-SGN-04 |
| 3 | TC-SGN-05, TC-SGN-07 |
| 4 | TC-SGN-06 |
| 5 | TC-SGN-08, TC-SGN-09, TC-XC-14 |
| 6 | TC-LPK-01, TC-LPK-03, TC-LPK-06 |
| 7 | TC-LPK-02, TC-LPK-04, TC-LPK-08, TC-LPK-09 |
| 8 | TC-LPK-05, TC-TRD-16 |
| 9 | TC-LPK-07, TC-SET-02 |
| 10 | TC-RKH-01, TC-RKH-02, TC-RKH-03 |
| 11 | TC-NAV-01, TC-NAV-02, TC-NAV-03 |
| 12 | TC-TRI-01, TC-TRI-02, TC-TRI-12, TC-TRI-13, TC-TRI-14, TC-TRI-15 |
| 13 | TC-TRI-03 |
| 14 | TC-TRI-04 |
| 15 | TC-TRI-05 |
| 16 | TC-TRI-06, TC-TIR-12 |
| 17 | TC-TRI-07 |
| 18 | TC-TRI-08 (NA → L3), TC-TRI-16 |
| 19 | TC-TRI-09, TC-TRI-10 |
| 20 | TC-TRI-11, TC-TRD-26 |
| 21 | TC-TIR-01, TC-TIR-09, TC-TIR-13, TC-TIR-15 (L3) |
| 22 | TC-TIR-02 |
| 23 | TC-TIR-04 |
| 24 | TC-TIR-05 |
| 25 | TC-TIR-06 |
| 26 | TC-TIR-07 |
| 27 | TC-TIR-08 (NA), TC-TIR-15 (L3) |
| 28 | TC-TIR-02, TC-TIR-03, TC-TIR-11 |
| 29 | TC-TIR-10 |
| 30 | TC-TIR-14, TC-ANC-01, TC-ANC-05, TC-ANC-06, TC-ANC-07 |
| 31 | TC-ANC-02, TC-ANC-03, TC-ANC-04, TC-ANC-08 |
| 32 | TC-MRK-01, TC-MRK-06, TC-MRK-07, TC-MRK-08 (L3) |
| 33 | TC-MRK-02 |
| 34 | TC-MRK-04, TC-TRN-03 |
| 35 | TC-MRK-03, TC-MRK-05 |
| 36 | TC-TRN-01, TC-TRN-04, TC-TRN-05, TC-TRN-06 |
| 37 | TC-TRN-02, TC-TRN-06 |
| 38 | TC-TRD-01, TC-TRD-02, TC-TRD-04, TC-TRD-22, TC-TRD-23, TC-TRD-24, TC-TRD-25 |
| 39 | TC-TRD-06 (L3; button equivalent TC-TRD-03) |
| 40 | TC-TRD-03, TC-TRD-05 |
| 41 | TC-TRD-07 |
| 42 | TC-TRD-08 |
| 43 | TC-TRD-09 |
| 44 | TC-TRD-10, TC-TRD-35, TC-MAT-08 |
| 45 | TC-TRD-11, TC-TRD-12, TC-TRD-34 |
| 46 | TC-TRD-13 |
| 47 | TC-TRD-14 |
| 48 | TC-TRD-15, TC-LEA-08 |
| 49 | TC-TRD-17 |
| 50 | TC-TRD-18 |
| 51 | TC-TRD-19 |
| 52 | TC-TRD-20, TC-TRD-21 (L3), TC-TRD-27 |
| 53 | TC-TRD-28, TC-TRD-29, TC-TRD-30 (L3), TC-TRD-31 (L3), TC-TRD-32, TC-TRD-33, TC-TRD-36 |
| 54 | TC-SLC-01 (NA), TC-SLC-02 (M), TC-SLC-03 (L3) |
| 55 | TC-CLC-01, TC-CLC-02, TC-CLC-06, TC-CLC-07, TC-CLC-13 |
| 56 | TC-CLC-03, TC-XC-14 |
| 57 | TC-CLC-04, TC-CLC-05 |
| 58 | TC-CLC-08, TC-CLC-09, TC-CLC-13 |
| 59 | TC-CLC-10, TC-CLC-11, TC-CLC-12 (M) |
| 60 | TC-MAT-01, TC-MAT-02, TC-MAT-03, TC-MAT-09, TC-MAT-10 |
| 61 | TC-MAT-04, TC-MAT-09 |
| 62 | TC-MAT-05, TC-MAT-06 |
| 63 | TC-MAT-07 |
| 64 | TC-LEA-01, TC-LEA-09, TC-LEA-10, TC-LEA-11 |
| 65 | TC-LEA-02, TC-LEA-03 |
| 66 | TC-LEA-04, TC-LEA-03 |
| 67 | TC-LEA-05 |
| 68 | TC-LEA-06 |
| 69 | TC-LEA-07 |
| 70 | TC-POR-01, TC-POR-02, TC-POR-03, TC-POR-04, TC-POR-05 |
| 71 | TC-PRO-01, TC-PRO-02, TC-PRO-03, TC-PRO-04, TC-XC-03 |
| 72 | TC-SET-04 |
| 73 | TC-SET-03, TC-LEA-08 |
| 74 | TC-SET-05 |
| 75 | TC-SET-06 |
| 76 | TC-PU-05 |
| 77 | TC-PU-01, TC-PU-02 (L3) |
| 78 | TC-PU-03, TC-PU-04, TC-PU-06 (L3) |
| 79 | TC-FBK-01, TC-FBK-02 |
| 80 | TC-FBK-03, TC-FBK-04 (M), TC-FBK-05, TC-FBK-06 |
| 81 | TC-XC-03, TC-XC-04, TC-XC-05 |
| 82 | TC-XC-01, TC-XC-02 |

---

## Drift ledger (features landed after the 2026-07-10 inventory — pending cases)

| Date noticed | Change | Action owed |
|---|---|---|
| 2026-07-11 | `QuickSetTiersScreen` added (entered from the Tiers header; not in the RankMenu sheet) — parallel session, in flight | When it merges: add TC-QST-* cases (render, entry from Tiers, save path), testIDs per the registry grammar, and re-audit feature coverage. Inventory §2/§7 need a row |
| 2026-07-11 | Pre-suite Maestro scaffolding exists (`mobile/.maestro/0*.yaml`, commit 56fcf91) using text-selector taps — fails `testid-lint.sh` by design. Maestro CLI already installed | Migrate/retire the six legacy flows as their TC-covered replacements land under `mobile/.maestro/flows/`; lint stays red-on-legacy until then (known) |
| 2026-07-12 | Smoke authoring discoveries: (a) OutlookSheet AUTO-OPENS on first Trades visit — TC-TRD-01/03 and any first-visit Trades case must dismiss it (`outlook.save-btn`); (b) calculator picker stays open after a pick — flows tap `calc.picker.done`; (c) TC-TRD/TC-CLC targets can sit below the fold — use scrollUntilVisible | Fold into the affected case rows' steps at the next test-cases revision |
| 2026-07-12 | Parallel session shipped: ESPN league linking (flag `espn.link`, own testID tranche in the registry), QuickSetTiers promoted to a first-class ranking method (`rankingMethodPref: 'quickset'`), Elo seed recalibration (#117, DP top value → ~Elo 1927), verified-writes auth gate (`auth.enforce_verified_writes`) | New TC groups needed: ESPN linking, QuickSetTiers; re-check seeder near-unlock/Elo assumptions against #117; inventory regeneration due |
