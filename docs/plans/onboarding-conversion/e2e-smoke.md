# Onboarding v2 — Operator E2E Smoke Script (build 48, treatment device)

*2026-07-19. For the operator device (`dev_loc-mrpy6qog-2t72t6`, treatment in `onboarding_v2_rollout` v1). Verified server-side: treatment + all 10 flags resolve for this device; strangers get nothing; global flags dark.*

## Why "sign in with my username" appeared to do nothing

1. **Build-48 gap (fix coded, ships next build):** nothing routed a treatment user to the **Trades tab** — you land on Rank as always, and every onboarding surface (skeleton deck, identity strip, provenance chip, swipe hint, prompt card) lives on Trades. **In build 48: tap the Trades tab manually.** Next build lands first-session treatment users on Trades automatically.
2. The new **landing** exists only signed-out — signed in, you never see it.
3. Timing: treatment went live in prod *after* the first force-quit attempt. It is live now.

## Phase 0 — Treatment check (30s)

Sign out (Settings → Sign out). If the sign-in screen shows a primary **"See trades for your team →"** button with Apple demoted to a quiet text link at the bottom → treatment flags are live on-device. If you still see the big Apple button on top → flags haven't refetched; relaunch once.

## Phase 1 — Landing (signed out)

| Do | Expect |
|---|---|
| Look at the screen | Field placeholder `Sleeper username`; subline "No password. Your league's rosters do the talking."; CTA "See trades for your team →"; quiet "Already have an account? Sign in with Apple" |
| Type a garbage username (`zzqknope123`) | Not-found copy: `No "@zzqknope123" on Sleeper. Usernames aren't team names…` |
| Airplane mode → submit | "Sleeper isn't responding." (the sample-league escape stays **hidden** — `landing.try_before_sync` is globally off by design; not a bug) |
| Tap the Apple link | Normal Apple sheet (re-entry path) — cancel it |
| Sign in with your real username | Normal auth → league picker |

**Expected non-behavior:** "Just looking? Browse a sample league" is absent (global backend flag; smoke the demo path locally only).

## Phase 2 — League picker

You have multiple leagues → picker shows (auto-skip fires only for single-league users; to test it, sign in with a one-league username). Pick a league.

## Phase 3 — Trades-first hook (**tap the Trades tab** in build 48)

| Expect | Notes |
|---|---|
| Skeleton card "Scouting your league…" OR cards already streaming | Pregen kicked at session init |
| Collapsed first-run chrome (single control row, no invite banner) | Returns to normal after first swipe (next mount) |
| Identity strip: avatar + "Trading as @yourname — not you?" | "not you?" → confirm dialog → sign-out path. X dismisses for the session |
| "CONSENSUS VALUES" chip above the deck | Tappable → jumps straight to Quick Set |
| Swipe-gesture nudge on card 1 (once ever) | Guided layer; any touch dismisses |
| Coach mark near the chip ("These are consensus values…") on a later mount | Never stacks with the swipe hint |
| First card quality | The consolidation raw-loss sanity gate (bc3ccd7) is now live — no lopsided 2-for-1 "insult" cards should headline |

## Phase 4 — Quick Set prompt → the "aha"

1. Swipe 2 cards, then **pass** the 3rd (or just swipe 3) → inline prompt card: *"These trades use consensus values."*
2. Tap **"Fix one position →"** → Quick Set walk for one position (8 tiers, tap-save each).
3. On finish: **no Quick Rank offer** (suppressed in this mode) — you bounce back to Trades, the deck **force-regenerates**, and a banner shows: *"Re-ranked with your QB board — N new trades."* (suppressed if N=0). Chip now reads **"YOUR BOARD."**
4. Alternate path: "Not now" = snooze → re-offered once in session 2; the chip remains the evergreen entry.

## Phase 5 — Apple save moment (needs a *borrowed* identity)

Your own account is Apple-verified, so the prompt **correctly suppresses itself** for you. To see it: sign out → sign in with any public Sleeper username → swipe → **like** a card → expect celebration beat, then the Apple modal (*"Keep your board on every device."* — honest cross-device copy, no "save your board"). Tap **Not now** (don't complete Apple on a foreign identity; sticky binding would conflict-toast anyway). Expect: no immediate re-ask; **share button** appears on the liked card afterward. Session-2 banner: relaunch with ≥5 lifetime swipes unbound → non-modal banner above the deck, not a modal.

## Phase 6 — Trio ramp + routing

- Swipe out the whole deck → deck-exhausted state: *"You've seen every trade. Sharpen your board with quick head-to-heads →"* → Trios.
- Rank tab → lands directly in Quick Set with "More ways to rank" in the header (the 5-way chooser is demoted, reachable from that link).

## Server-side review (the experiment itself)

```bash
# 1. Assignment (expect treatment + 10 overlay flags; stranger expects {}):
curl -s https://fantasy-trade-finder.onrender.com/api/feature-flags -H "X-Device-Id: dev_loc-mrpy6qog-2t72t6" | python3 -m json.tool

# 2. Ingest health (accepted rising, rejected/dropped ~0):
curl -s https://fantasy-trade-finder.onrender.com/api/admin/analytics/health -H "X-Cron-Secret: $CRON_SECRET"

# 3. Experiment readout — the HONESTY check: expect verdict:null + banner
#    (n=1, below min-n). A verdict here would be a stats-policy bug:
curl -s https://fantasy-trade-finder.onrender.com/api/admin/experiments/onboarding_v2_rollout/readout -H "X-Cron-Secret: $CRON_SECRET"
```

DB checks (events lineage): your funnel events (`quickset_prompt_shown/accepted`, `apple_prompt_*`, `trade_card_viewed` with `ms_since_open`) should appear in `user_events` with `experiments` stamped `{"onboarding_v2_rollout":"treatment"}` on in-scope rows, `device_type/os_version/app_version` populated, and `user_id` = your id (identity-stitched).

## Known gaps & expected non-behaviors (build 48)

| Item | Status |
|---|---|
| Auto-landing on Trades tab (treatment first session) | **Fix coded** (TabNav initial tab + boot-gated state hydration), ships next build; manual tab-tap until then |
| Demo/sample-league path | Dark globally (`landing.try_before_sync`) — local smoke only |
| `api_request_failed` / `screen_left` events | Code on main; emit from the NEXT build |
| Apple prompt on your own account | Suppressed by design (verified identity) |
| League auto-skip for you | Won't fire (multi-league account) |
| Baseline | Other testers emit baseline events only once they update to build ≥48 |

## Exit criteria for the smoke

All Phase 1–6 behaviors observed (with build-48 caveats) + server checks clean → operator validation complete → decide: cut the trades-landing fix into build 49, then graduate the experiment (`/revise` → v2 powered activation test per the experiment doc).
