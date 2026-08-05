# #245 — Acquire tab: rename + Trade / Free Agency sections on the hub

**Status:** built, tsc-clean, committed on the worktree branch (2026-08-05).
**Operator ask (TradesHome):** rebrand the Trades tab as **Acquire**, and restructure the hub page into two labeled sections — **Trade** (top, the existing hub content) and **Free Agency** (below it; its only link right now is the Free Agent finder that today lives on the League tab).

## What changed

### 1. Tab rename — presentation-level only (`mobile/src/navigation/TabNav.tsx`)
- The Trades `Tab.Screen` gains `tabBarLabel: 'Acquire'` + `tabBarAccessibilityLabel: 'Acquire'`.
- **Route name stays `Trades`** — deep links (`utils/deepLinks.ts` v2 table), analytics events, `requestScrollToTop('Trades')`, and the `tab.trades` testID all keep working untouched.
- Diff deliberately confined to the tab's `options` block (a concurrent session owns the RankMenu sheet in the same file).

### 2. Hub restructure (`mobile/src/screens/TradeFinderHubScreen.tsx`)
- **In-page title:** "Find a Trade" → **"Acquire"**, matching the tab; the TRADE section label now carries the trade context.
- **TRADE section:** a 14pt `TickLabel` ("TRADE") inserted directly under the page title, heading the existing hub content (Trade DNA panel + "How do you want to find trades?" label + four mode cards — all unchanged). Interpretation note: the operator sketch describes the Trade section as "the existing hub content", so the label heads the whole block (DNA panel included) rather than sitting between the DNA panel and the cards.
- **FREE AGENCY section:** a second `TickLabel` ("FREE AGENCY") below the mode cards, followed by **one** row card (`finder-hub.card.free-agents`, plus icon, mode-card styling) that navigates to the existing root-stack `FreeAgents` route (#143). The navigate call bubbles up from the tab screen to RootNav — the screen is **not** moved or duplicated, and the **League tab's "Free agents" entry row stays in place** (per the operator note, "only link right now" describes the FA section's contents, not an exclusivity claim; LeagueScreen untouched).
- No new FeedbackFAB concerns: the hub stays a tab-stack screen (RootNav global mount, #188/#196), and `FreeAgentsScreen` already mounts its own root-stack FAB.

## Viewport / height math (#218 density budget)

Budget: **658pt** usable viewport (iPhone 15/16-class, per `docs/feedback/items/243-scroll-audit/trades-surfaces.md`). That audit's recomputed hub baseline (post-#212/#236, which superseded the stale #218 numbers): **mid-state 468pt → 190pt spare** (untouchables-shown state 498pt → 160pt spare).

Additions (ScrollView stack gap = `space.sm` 8pt; each inserted sibling costs its height + one gap):

| Element | Height | + gap | Total |
|---|---|---|---|
| TRADE TickLabel | 14pt | 8pt | 22pt |
| FREE AGENCY TickLabel | 14pt | 8pt | 22pt |
| Free Agent Finder row (mode-card style: 9pt pad ×2 + max(icon 34, two text lines ~43) + border ≈ 61pt, matching the audit's ~61pt card figure) | 61pt | 8pt | 69pt |
| **Added** | | | **≈113pt** |

Result: mid-state ≈ **581pt (77pt spare)**; untouchables state ≈ **611pt (47pt spare)**. Both stay inside the 658pt budget with no scroll in the nominal states — well within the ~190pt the audit said the hub had to give.

## "Trades tab" copy elsewhere (noted, not changed)

User-facing strings that still say "Trades tab" (out of scope per the build note; candidates for a follow-up copy pass to "Acquire tab"):
- `mobile/src/screens/RankScreen.tsx:654-655` — unlock toast: "Your board now prices your trades — see the Trades tab" / "Trade Finder unlocked — check the Trades tab"
- `mobile/src/screens/MatchesScreen.tsx:657` — "Swipe more in the Trades tab."

(Other hits — TabNav/deepLinks/FeedbackFAB/usePushNotifications/tradePregen/QuickSetTiersScreen — are code comments only.)

## Docs updated
- `docs/glossary.md` — new **Acquire tab** entry.
- `mobile/src/navigation/CLAUDE.md` — TabNav row notes the label rename (route unchanged).
- `mobile/src/screens/CLAUDE.md` — both `TradeFinderHubScreen` registry rows note #245.
- `mobile/src/components/CLAUDE.md` — testID registry tranche: `tab.trades` unchanged semantics + new `finder-hub.card.free-agents`.

## Verification
- `cd mobile && npx tsc --noEmit` — clean.
- Not visually verified (no simulator run in this worktree session); the new row reuses the shipped mode-card styles and the existing `FreeAgents` root-stack route, whose reachability from tab screens is the same mechanism LeagueScreen and TradesScreen already use.
