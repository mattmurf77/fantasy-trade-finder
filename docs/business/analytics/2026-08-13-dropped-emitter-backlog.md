# Tracking-plan addendum — dropped-emitter backlog registration (2026-08-13)

**Status:** built on branch `claude/elegant-mccarthy-ef63f8`; **awaiting operator
confirmation before ship** (taxonomy is a bright-line surface per root
CLAUDE.md).

## What this is

The remainder of the 2026-08-11 sweep (G-031; cross-client-invariants §events)
that found 33 of 73 emitted mobile names unregistered. P0 fixed three; this
addendum registers the remaining live emitters — **27 registrations + 1 client
emitter deletion**. Every registered name has a live `track()` call in
`mobile/src` that has been counted-and-dropped (`dropped_unknown_type`) behind
a 200 since it shipped. Most are teardown S3/S4 instrumentation (ADR-008; PRD
source `app-teardown-review/` is gitignored — flag names below are the durable
pointer) whose metrics have been dark since ship.

**No new emitter ships in this change.** Prop rows mirror what the shipped
emitters send today, verbatim — no reserved keys, no spelling reconciliation.

## Seam date

Rows for these names begin the day this ships. There is **no historical
series** for any of them — every prior envelope was dropped unrecoverably.
19 of the 27 are INTENT (real user decisions), so INTENT coverage widens at
the seam; DAU/WAU are protected by the eight NON_INTENT rows added in the
same commit (below), but any per-feature "actions per user" style read that
predates the seam undercounts. Do not trend across 2026-08-<ship-day>.

## The registrations

| Event | Emitter(s) | Props (as shipped) | Class | Source |
|---|---|---|---|---|
| `prompt_shown` | `useInterruptCoordinator.ts:91` | `surface` ∈ quickset_prompt \| coach_mark \| apple_banner \| outlook_banner | NON_INTENT (impression) | S4 PRD-04 `ux.prompt_arbiter` |
| `apple_banner_dismissed` | TradesScreen:2860 | — | NON_INTENT (dismissal) | S4 PRD-04 |
| `push_primer_shown` | usePushPriming.ts:66,74 | `trigger` ∈ session \| want_it | NON_INTENT (impression) | S4 PRD-04 |
| `push_primer_accepted` | PushPrimingModal.tsx:40 | — | INTENT | S4 PRD-04 |
| `push_primer_dismissed` | usePushPriming.ts:84 | `declines` | NON_INTENT (dismissal) | S4 PRD-04 |
| `help_opened` | MatchesScreen:675, TradesScreen:3959 | `topic` ∈ matching \| trade_pricing | INTENT | S4 PRD-01 `ux.help_surface` |
| `help_read_more_tapped` | HelpSheet.tsx:70 | `topic` | INTENT | S4 PRD-01 |
| `player_menu_opened` | MatchesScreen:750,841; TradesScreen:4900; RankScreen:612 | `surface` ∈ matches \| matches_awaiting \| trades \| trios, `side` (absent on trios) | INTENT | S3 PRD-02 `ux.player_context_menu` |
| `calc_clear_undone` | TradeCalculatorScreen:947 | — | INTENT | S3 PRD-03 (toast undo) |
| `match_dismiss_undone` | MatchesScreen:226 | `match_id` | INTENT | S3 PRD-03 |
| `suppression_undo_tapped` | TradesScreen:2134 | — | INTENT | S3 PRD-03 |
| `deck_summary_viewed` | TradesScreen:2800 | `passed`, `liked`, `proposed`, `deck_size` | NON_INTENT (impression) | deck exhausted summary |
| `demo_bridge_tapped` | TradesScreen:4622 | — | INTENT | demo → signin bridge |
| `trade_asset_removed` | TradesScreen:3117 | `side` | INTENT | card editing |
| `trade_edit_in_calculator_tapped` | TradesScreen:2154 | — | INTENT | card editing |
| `trade_keep_side_tapped` | TradesScreen:2091 | `side` | INTENT | #186 see-other-side |
| `trade_pin_cleared` | TradesScreen:2123 | `restored` | INTENT | pin lifecycle |
| `trade_swap_suggest_opened` | TradesScreen:3096 | `side` | INTENT | card editing |
| `untouchable_toggled` | MatchesScreen:337, TradesScreen:944 | `marked` (resulting state) | INTENT | asset prefs |
| `trio_entry_tapped` | TradesScreen:5111 | `from` (deck_exhausted today) | INTENT | trios entry |
| `trio_session_started` | RankScreen:92 | — | NON_INTENT (fires on mount; onboarding 8b retention metric — its retention read queries the name directly and is unaffected) | onboarding 8b |
| `notif_denied_settings_shown` | SettingsScreen:361 | — | NON_INTENT (impression) | notif honesty |
| `notif_denied_settings_tapped` | SettingsScreen:1034 | — | INTENT | notif honesty |
| `pick_pricing_mode_changed` | SettingsScreen:189 | `mode` | INTENT | M6b `trade.slot_pricing` |
| `stud_tax_mode_changed` | SettingsScreen:149 | `mode` | INTENT | #214/#215 |
| `guide_tour_reenabled` | useGuide.ts:134 | — | INTENT | guided tour |
| `rating_prompt_requested` | utils/ratingPrompt.ts:90 | `trigger`, `version` | NON_INTENT (system outcome — the OS may never show the dialog) | `growth.rating_prompt` |

## The deletion — client `quickset_completed`

`QuickSetTiersScreen.tsx` fired `quickset_completed
{position, onboarding}` on completing the full walk. The name is
**server-fired** (per completed position, on the scoped tier save) and the
taxonomy's client/server namespaces are disjoint by an import-time assert —
registering the client name is impossible (it would crash the app at boot),
and every client envelope has been dropped since ship anyway. **Removed, not
renamed**: the server row is the authoritative completion signal.

**Accepted loss:** the `onboarding` prop (was this walk an onboarding
return?). The server cannot see it. If the onboarding-return split is ever
needed, the honest path is a NEW client name (e.g.
`quickset_walk_finished`) via a fresh addendum — not resurrecting a
colliding one.

## Deliberately NOT registered

Nothing else. This addendum zeroes the known dropped-emitter backlog; the
G-031 "29 remaining" note in cross-client-invariants is updated to 0 in the
same commit.
