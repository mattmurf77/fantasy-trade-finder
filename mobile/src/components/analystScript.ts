import type { GuideStep } from '../state/useGuide';

// The Analyst — dialogue script table (source of truth: PRD
// docs/plans/guided-onboarding-v2/PRD.md §5.2 verdicts + §5.3/§5.3-A beats;
// v1 lineage: docs/plans/onboarding-conversion/guided-avatar-script.md §3).
// This file is DATA: copy edits land here without touching engine or screen
// logic. Slots are resolved by the small builder functions; every number
// quoted must come from a live value (script §1.3 honesty rule) — each
// numbered line has a no-number variant.
//
// ── Copy budget (PRD §5.0; enforced by mobile/tests/check-guide-script.js) ──
//   auto   12 words AND autoMs ≥ words/4.17×1000 + 800
//   action 16 words
//   tap    20 words
//   cta    16 words + ≤4-word button labels, at most one primary
// The class is the step's `advance` value. Word count ignores bare
// punctuation tokens (em dashes, the CTA arrow); a `{slot}` counts as the
// one word it always resolves to (positions, counts — never a phrase).
//
// ── CLIENT RECEIPTS — the exact strings screens must record ────────────────
// Retirement (`retireAfter` / `invalidateOn`) reads CLIENT receipts only,
// via `recordGuideReceipt(...)` from mobile/src/state/useGuide.ts. A receipt
// wired to a server-fired analytics event never fires and is worse than none
// (PRD FR-E3; DELTA-2026-08-15 §E — `quickset_completed` and `trio_swipe`
// are both server-only). Screen agents: import GUIDE_RECEIPTS and call
// `recordGuideReceipt(GUIDE_RECEIPTS.x)` at the REAL moment (the save
// landed, the pin was written) — never off a `track()` call.
//
//   outlook_saved             TradeDnaSheet — a preference write persisted
//   finder_target_pinned      targeting board — a pin recorded
//   quickset_completed_local  QuickSetTiersScreen — a Quick Set save landed
//   trio_started              Trios — first trio VOTE submitted (not mount)
//   import_completed          rankings import — an import landed
//   league_filter_applied     LeagueSummaryScreen — a position pill tapped
//   send_attempted            Send-in-{Sleeper,MFL,ESPN}/copy — send tapped
//   calc_tour_completed       utils/calcTour — the #384 walkthrough finished
//
// Each name is ALSO the analytics event where one exists, but the receipt is
// the local write; the two are recorded independently.
//
// ── v2 beats ───────────────────────────────────────────────────────────────
// New beats use `n`-prefixed ids (`isV2NewStepId`, useGuide.ts) so the
// FR-E9 v1-upgrader release cap can find them. Retained v1 steps keep their
// `s` ids. Every `n` step declares retirement, a display cap, an
// adoptionEvent, and a degrade contract (a `degradeLine`, `degrade:
// 'suppress'`, or a line with no deixis to degrade).

/** Client receipt ids — the retirement vocabulary. Screens record these. */
export const GUIDE_RECEIPTS = {
  outlookSaved: 'outlook_saved',
  finderTargetPinned: 'finder_target_pinned',
  quicksetCompletedLocal: 'quickset_completed_local',
  trioStarted: 'trio_started',
  importCompleted: 'import_completed',
  leagueFilterApplied: 'league_filter_applied',
  sendAttempted: 'send_attempted',
  /** #384 — the merged-calculator walkthrough ran to its last beat. Written
   *  by the runner, not a screen: only it knows the tour finished rather
   *  than being abandoned. It is what gates the auto-start to first visit. */
  calcTourCompleted: 'calc_tour_completed',
} as const;

const R = GUIDE_RECEIPTS;

/** #384 device feedback (report 6) — "Progression needs to be more graceful.
 *  Right now it's based on screen tap. The dialogue boxes that the user isn't
 *  expected to take action should get a 'next' button in the dialogue box."
 *
 *  Two consequences, both wanted: the user gets an explicit control instead of
 *  guessing that a tap anywhere advances, and the overlay stops mounting the
 *  full-screen tap-catcher for these beats — which is what was eating the
 *  scroll gesture on the deck (report 5). `advance: 'tap'` survives in the
 *  engine for older beats; no #384 beat uses it. */
const NEXT = { label: 'Next', kind: 'primary', action: 'accept' } as const;
/** The last beat of the walkthrough — the button says so. */
const DONE = { label: 'Done', kind: 'primary', action: 'accept' } as const;

/** Any board-building receipt: a user who has ranked by ANY method has
 *  answered the questions `n1`/`s3.2`/`n8` exist to ask. */
const BOARD_RECEIPTS = [
  R.quicksetCompletedLocal,
  R.importCompleted,
  R.trioStarted,
];

export const S = {
  s0_1: (): GuideStep => ({
    id: 's0.1', screen: 'SignIn', pose: 'neutral', advance: 'tap', once: true,
    line: "I'm The Analyst. I model dynasty trades — you bring the roster.",
    // D-155 — Fleeced introduces himself in character. Rendered only under
    // `onboarding.mascot_ram`; flag off keeps the line above verbatim.
    lineRam: "I'm Fleeced, the ram. Good to see another sheep here for me to take advantage of.",
  }),
  s0_2: (): GuideStep => ({
    id: 's0.2', screen: 'SignIn', pose: 'point', flip: true, side: 'right',
    advance: 'action', target: 'signin.username-input', once: true,
    line: 'Type your Sleeper username. No password needed.',
  }),
  s0_err_notfound: (): GuideStep => ({
    id: 's0.err-notfound', screen: 'SignIn', pose: 'oops', advance: 'tap',
    line: "No Sleeper account by that name. Check the spelling — caps don't matter.",
  }),
  s0_err_down: (): GuideStep => ({
    id: 's0.err-down', screen: 'SignIn', pose: 'oops', advance: 'tap',
    line: "Sleeper isn't answering. Statistically it comes back. Retry in a moment.",
  }),
  s1_1: (): GuideStep => ({
    id: 's1.1', screen: 'LeaguePicker', pose: 'point', flip: true, side: 'right',
    advance: 'action', once: true,
    line: "Pick the league you check at work. That's the one that matters.",
  }),
  s2_wait: (nOpps: number | null): GuideStep => ({
    id: 's2.wait', screen: 'Trades', pose: 'computing', advance: 'action', once: true,
    line: nOpps
      ? `Reading ${nOpps} rosters, scoring candidate trades. First cards land in seconds.`
      : 'Reading the league rosters, scoring candidate trades. First cards land in seconds.',
  }),
  s2_1: (): GuideStep => ({
    id: 's2.1', screen: 'Trades', pose: 'celebrate', advance: 'tap', once: true,
    // Softened per PRD §5.2 R1: a market claim, not a warranty on this card.
    line: 'These are trades both sides should want. Not a wishlist — a market.',
  }),
  s2_2: (): GuideStep => ({
    id: 's2.2', screen: 'Trades', pose: 'point', advance: 'action',
    target: 'trades.card-body', once: true,
    line: 'Swipe right to take it, left to pass. Every swipe teaches me.',
  }),
  /** @deprecated REPLACED by `n1` (PRD §5.2). Retained only so the tree
   *  compiles until the screens agent removes the `s2.3` request site in
   *  TradesScreen; delete this builder with that call site. */
  s2_3: (): GuideStep => ({
    id: 's2.3', screen: 'Trades', pose: 'neutral', advance: 'tap',
    target: 'trades.provenance-chip', once: true,
    line: "Logged. Also — see that label? CONSENSUS VALUES. These prices are the market's, not yours. We'll fix that shortly.",
  }),
  // `s3.1` is CUT — merged into `s3.2` (PRD §5.2). Safe by construction:
  // `setGuidedS3Pending(true)` runs unconditionally after the old s3.1
  // request and `s3.2` chains off `guidedS3Pending`, never off
  // `guideSeen['s3.1']` (DELTA-2026-08-15 §D, re-verified).
  s3_2: (pos: string, _thin?: boolean): GuideStep => ({
    id: 's3.2', screen: 'Trades', pose: 'point', advance: 'cta',
    target: 'trades.provenance-chip', side: 'right',
    // `_thin` (the "your {pos} room is the thin one" tail) is dropped by the
    // §5.2 trim; the parameter stays so the existing call site compiles.
    line: `Two minutes on ${pos} and I'll re-price every card with your numbers.`,
    ctas: [
      { label: `Fix ${pos} →`, kind: 'primary', action: 'accept' },
      { label: 'Not now', kind: 'ghost', action: 'dismiss' },
    ],
    maxDisplayCount: 2,           // initial + one re-offer, then permanent
    invalidateOn: BOARD_RECEIPTS,
    retireAfter: { event: R.quicksetCompletedLocal, count: 1 },
    // Analysis-side join only (server-fired; never a client receipt).
    adoptionEvent: 'quickset_completed',
  }),
  s4_1: (): GuideStep => ({
    id: 's4.1', screen: 'QuickSetTiers', pose: 'point', advance: 'tap', once: true,
    line: 'Tap everyone worth the tier label, then Save. Gut calls beat overthinking.',
    // No `target` today, so this never renders (DELTA §D flagged the
    // mismatch); it ships with the copy so a later pill registration is
    // covered without a second binary.
    degradeLine: 'Tap every player worth the tier, then Save. Gut calls beat overthinking.',
  }),
  s5_1: (nNew: number, _pos?: string): GuideStep => ({
    id: 's5.1', screen: 'Trades', pose: 'celebrate', advance: 'tap',
    // N=1 plural fix (S-43 handoff): the engine can honestly return
    // `fresh === 1`, and "1 new trades" is the tell that nobody read it.
    line: nNew === 1
      ? '1 new trade that exists only because of your numbers.'
      : `${nNew} new trades that exist only because of your numbers.`,
  }),
  s5_0: (pos: string): GuideStep => ({
    id: 's5.0', screen: 'Trades', pose: 'oops', advance: 'tap',
    line: `Same trades — your ${pos} board agrees with consensus. More positions, more edge.`,
  }),
  s5_5: (donePos: string, nextPos: string): GuideStep => ({
    id: 's5.5', screen: 'Trades', pose: 'point', flip: true, side: 'right',
    advance: 'cta',
    line: `${donePos} is done. ${nextPos} is your next-highest leverage — same drill, two minutes.`,
    ctas: [
      { label: `Rank ${nextPos} next →`, kind: 'primary', action: 'accept' },
      { label: 'Later', kind: 'ghost', action: 'dismiss' },
    ],
    // PRD asks for `all_positions_ranked`; there is no such receipt and an
    // unfired condition is worse than none (FR-E3). The all-ranked case
    // self-terminates: `nextUnrankedPosition` returns null and the screen
    // never requests the step. An import ranks everything at once, so that
    // receipt is the one that has to kill it explicitly.
    invalidateOn: [R.importCompleted],
    retireAfter: { event: R.importCompleted, count: 1 },
    adoptionEvent: 'quickset_completed',
  }),
  /** @deprecated REPLACED by `n6_1` (PRD §5.2/O-1) — the passive toast
   *  becomes an active router. Retained until the screens agent re-points
   *  the first-like site; `autoMs` corrected to the FR-E7 reading floor
   *  meanwhile, since it is shipping to users today. */
  s6_1: (): GuideStep => ({
    id: 's6.1', screen: 'Trades', pose: 'celebrate', advance: 'auto', autoMs: 3700, once: true,
    line: "First target logged. If they accept, you'll hear it from me first.",
  }),
  s6_2: (): GuideStep => ({
    id: 's6.2', screen: 'Trades', pose: 'neutral', advance: 'auto', autoMs: 3700, once: true,
    line: 'Quick admin: sign in with Apple to save your rankings. Five seconds.',
  }),
  // `s7.1` is CUT as a pushed beat (PRD §5.2/§2.1): its target
  // `trades.trio-entry` mounts only under `onboarding.rank_routing` (false)
  // and is displaced by the live `deck.replenishment` summary card anyway,
  // so it fired pointing at nothing. The exhausted-deck boundary now belongs
  // to the summary card + `n4`; Trios stay a pull surface plus `n8`'s ghost
  // CTA. Revival needs `rank_routing` shipped AND a free boundary.
  s8_1: (): GuideStep => ({
    id: 's8.1', screen: 'Trades', pose: 'celebrate', advance: 'tap', once: true,
    line: "That's the tour. I'll surface when the numbers say something worth hearing.",
  }),

  // ── v2 beats (PRD §5.3 / §5.3-A) ─────────────────────────────────────────

  /** N1 — prices, and where yours come from (replaces `s2.3` + `s3.1`).
   *  Calibration-framed: claims teaching, never board generation (NG-2). */
  n1: (): GuideStep => ({
    id: 'n1', screen: 'Trades', pose: 'neutral', advance: 'tap',
    target: 'trades.provenance-chip', once: true,
    line: "These prices are the market's. Your swipes are already teaching me yours.",
    degradeLine: 'Card prices are consensus for now. Your swipes are already teaching me your values.',
    maxDisplayCount: 1,
    invalidateOn: BOARD_RECEIPTS,
    retireAfter: 'never', // reason: fires once at the third disposition of session one — a boundary that cannot recur; invalidateOn carries the behavioral death.
    adoptionEvent: 'quickset_started',
  }),

  /** N2 form A — the outlook receipt is mounted (a direction resolved), so
   *  the change control exists to point at. */
  n2a: (): GuideStep => ({
    id: 'n2a', screen: 'Trades', pose: 'point', advance: 'action',
    target: 'trades.outlook-receipt.change', side: 'right',
    line: "Not your kind of deal? Set your outlook — I'll re-aim these.",
    // "these" + a pointer: with nothing to measure the line is incoherent,
    // so form A retracts and the call site requests form B instead (the
    // request returned true, so `onComplete` still fires — chain there).
    degrade: 'suppress',
    maxDisplayCount: 2,
    // PRD spells this `invalidateOn: [outlook_saved]`; `retireAfter` on the
    // same receipt is the identical refusal and satisfies FR-E3's mandatory
    // field — one declaration, not two.
    retireAfter: { event: R.outlookSaved, count: 1 },
    adoptionEvent: 'find_trades_tapped',
  }),

  /** N2 form B — no receipt mounted (the common no-outlook case). Bubble
   *  with one primary CTA; nothing deictic, nothing to degrade. */
  n2b: (): GuideStep => ({
    id: 'n2b', screen: 'Trades', pose: 'thinking', advance: 'cta',
    line: "Not your kind of deal? Tell me what you're hunting for.",
    ctas: [{ label: 'Set outlook →', kind: 'primary', action: 'accept' }],
    maxDisplayCount: 2,
    retireAfter: { event: R.outlookSaved, count: 1 },
    adoptionEvent: 'find_trades_tapped',
  }),

  /** N4 — the empty deck. NOT a bubble: the shipped `trades.deck-summary`
   *  card renders this line and CTA itself (PRD §5.3 — one boundary, one
   *  surface). The step object is the copy + eligibility contract the card
   *  consumes; `Pin targets →` is primary there and demotes `Done` to
   *  ghost, keeping the card's one-primary budget. */
  n4: (): GuideStep => ({
    id: 'n4', screen: 'Trades', pose: 'point', advance: 'cta',
    line: "Cleared the market. Pin who you want — I'll ping you on matches.",
    ctas: [{ label: 'Pin targets →', kind: 'primary', action: 'accept' }],
    maxDisplayCount: 2,
    retireAfter: { event: R.finderTargetPinned, count: 1 },
    adoptionEvent: 'finder_target_pinned',
  }),

  /** N6.1 — first like → "Awaiting them" (replaces `s6.1`, per O-1).
   *
   *  `routable` is decided ONCE, in `swipeMutation.onSuccess`, from the
   *  awaiting fetch that the same handler issues: true only when the list
   *  came back non-empty. Empty / failed / timed out → the router-less
   *  variant. The copy is chosen before render and never swaps after.
   *
   *  Honesty bound: a one-sided like creates no notification and no row on
   *  the counterparty's side. The line must never imply they were pinged or
   *  are deciding.
   *
   *  `lifetimeMs` bounds the CTA variant so it cannot hold the interrupt
   *  slot across further swipes; expiry is terminal, writes `guideSeen`,
   *  and reports `via:'timeout'`. */
  n6_1: (routable: boolean): GuideStep =>
    routable
      ? {
          id: 'n6.1', screen: 'Trades', pose: 'celebrate', advance: 'cta', once: true,
          line: "Logged — they haven't seen it yet. Send it to them now?",
          ctas: [
            { label: 'See it →', kind: 'primary', action: 'accept' },
            { label: 'Later', kind: 'ghost', action: 'dismiss' },
          ],
          lifetimeMs: 8000,
          maxDisplayCount: 1,
          retireAfter: { event: R.sendAttempted, count: 1 },
          adoptionEvent: 'sleeper_send_attempted',
        }
      : {
          id: 'n6.1', screen: 'Trades', pose: 'celebrate', advance: 'tap', once: true,
          line: "Logged — I'll flag it the moment they like it back.",
          maxDisplayCount: 1,
          retireAfter: { event: R.sendAttempted, count: 1 },
          adoptionEvent: 'sleeper_send_attempted',
        },

  /** N8 — the import question (O-6): the first thing The Analyst asks when
   *  the ranking process launches. `Upload →` (accept) opens RankHome's
   *  existing import entry; `No — start simple` (dismiss) navigates nested
   *  to Trios. Never names a premium source while `ranks.source.*` is dark. */
  n8: (): GuideStep => ({
    id: 'n8', screen: 'RankHome', pose: 'thinking', advance: 'cta', once: true,
    line: "Do you pay for rankings — or keep your own? Upload them, I'll use yours.",
    ctas: [
      { label: 'Upload →', kind: 'primary', action: 'accept' },
      { label: 'No — start simple', kind: 'ghost', action: 'dismiss' },
    ],
    maxDisplayCount: 1,
    invalidateOn: BOARD_RECEIPTS,
    retireAfter: 'never', // reason: a one-shot device question capped at a single display; any board receipt invalidates it, and the guided-entry trigger cannot recur.
    // The "start simple" arm is the measurable one; the import arm has no
    // registered completion event yet (D1), so it is deliberately unclaimed.
    adoptionEvent: 'trio_session_started',
  }),

  /** N9 — Matches first visit (O-7 floor). Non-deictic: per-card spotlights
   *  are Phase 2 (`n6.2` / `n3`). Suppressed when arrival came via `n6.1`'s
   *  CTA — that chain already taught the segment. */
  n9: (): GuideStep => ({
    id: 'n9', screen: 'Matches', pose: 'neutral', advance: 'tap', once: true,
    line: 'Mutual matches land here. Awaiting them holds your likes — send either anytime.',
    maxDisplayCount: 1,
    invalidateOn: [R.sendAttempted],
    retireAfter: 'never', // reason: a first-visit trigger cannot fire twice, and the single display cap plus the send receipt close it permanently.
    adoptionEvent: 'awaiting_segment_viewed',
  }),

  /** N5 — where you stand (O-7 pulls it to Phase 1). Content-gated by the
   *  screen: ≥3 ranked members, `league.pos_candidates` on, a median
   *  present. Gates fail closed — a first visit that fails shows nothing
   *  and the beat stays armed for a later visit that passes. */
  n5: (): GuideStep => ({
    id: 'n5', screen: 'LeagueRankings', pose: 'point', advance: 'action',
    target: 'league-summary.pos-pills', side: 'right',
    line: "Filter one position — I'll split the league into buyers and sellers.",
    degradeLine: "Filter to one position on the league board — I'll split it into buyers and sellers.",
    maxDisplayCount: 2,
    retireAfter: { event: R.leagueFilterApplied, count: 1 },
    adoptionEvent: 'league_pos_candidates_viewed',
  }),

  // ── #384 W4 — the merged calculator tour (beats n10–n24) ───────────────
  //
  // The report wrote fifteen prose beats. THIRTEEN survive: W6-B (D-153)
  // deleted n14 (Clear) and n17 (Include players) along with the toggle and
  // the sequencing they existed for. They could not ship as prose: this
  // file is under a CI copy budget (auto 12 / action 16 / tap 20 / cta 16
  // words, enforced by mobile/tests/check-guide-script.js), so the work was
  // compression, not writing. Its step 11 — "the clear button has become the
  // X, the X records your decision, the check does as before" — is carried by
  // n19 on the deck.
  //
  // Retirement: every beat below is part of ONE scripted walkthrough that
  // the user either finishes or re-runs deliberately from "Show me around".
  // There is no behavioural receipt that means "this person now understands
  // the calculator", so inventing one would be dishonest — they decline to
  // retire behaviourally, each with the reason stated inline, and the
  // display cap is what bounds them. (This sentence deliberately avoids the
  // literal field-and-value pair: the lint's justification check is
  // line-based, so prose quoting it reads as an unjustified declaration.)
  // n11 is the exception: setting an outlook IS the
  // thing it asks for, so it retires on that receipt like N2 does.
  //
  // Ordering and the tour hold live in the runner (utils/calcTour.ts), not
  // here — this file stays DATA.

  n10: (): GuideStep => ({
    id: 'n10', screen: 'TradeCalculator', pose: 'point', advance: 'action',
    target: 'calc.mode-tab.league', side: 'right',
    line: 'Two ways to build a trade. Tap In league to use your real roster.',
    degradeLine: 'Two ways to build a trade — In league uses your real roster.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: opens a walkthrough the user re-runs on purpose; the display cap is the bound, and no receipt means "understands the calculator".
    adoptionEvent: 'calc_mode_switched',
  }),

  // Device feedback 2026-08-22 (report 2): the beat opened the sheet but
  // highlighted nothing, because it carried no `target`. `calc.outlook-row`
  // wraps whichever outlook row rendered — the receipt or its fallback.
  n11: (): GuideStep => ({
    id: 'n11', screen: 'TradeCalculator', pose: 'thinking', advance: 'cta',
    target: 'calc.outlook-row', side: 'left',
    line: 'Set your outlook first — it aims every suggestion at your plan.',
    degradeLine: 'Setting an outlook aims every suggestion at your plan.',
    ctas: [{ label: 'Set outlook', kind: 'primary', action: 'accept' }],
    maxDisplayCount: 2,
    retireAfter: { event: R.outlookSaved, count: 1 },
    adoptionEvent: 'outlook_saved',
  }),

  // Device feedback 2026-08-22 (report 6): every beat the user is not asked to
  // ACT on carries a Next button instead of advancing on a screen tap. A tap
  // beat mounts a full-screen catcher, which also swallowed the scroll — so
  // this is the same change as report 5's second half.
  n12: (): GuideStep => ({
    id: 'n12', screen: 'TradeCalculator', pose: 'neutral', advance: 'cta',
    ctas: [NEXT], target: 'calc.trade-columns',
    line: 'This is your canvas. Both rosters side by side — build any trade by hand.',
    degradeLine: 'Both rosters sit side by side here — build any trade by hand.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    adoptionEvent: 'calc_asset_added',
  }),

  n13: (): GuideStep => ({
    id: 'n13', screen: 'TradeCalculator', pose: 'point', advance: 'cta',
    ctas: [NEXT], target: 'calc.action.find-a-trade',
    line: "Find a Trade searches for you. We'll come back to it in a moment.",
    degradeLine: "Find a Trade searches for you — we'll come back to it.",
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    adoptionEvent: 'calc_find_a_trade_tapped',
  }),

  n15: (): GuideStep => ({
    id: 'n15', screen: 'TradeCalculator', pose: 'neutral', advance: 'cta',
    ctas: [NEXT], target: 'calc.action.confirm',
    line: 'The check queues this trade for the other manager, if it fits their preferences.',
    degradeLine: 'Confirming queues a trade for the other manager, if it fits their preferences.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    // #384 W6-A / D-152 — the ✓ is wired (POST /api/trades/queue), so the beat
    // has its own adoption event at last. The copy above is unchanged because
    // the built mechanism is exactly what it already described: the like is
    // recorded only when the counterparty's likes-you gates would surface it.
    adoptionEvent: 'calc_trade_queued',
  }),

  // W6-B (D-153) — n16 INFORMS rather than commands. The operator's reshape:
  // "the tour mentions they can add players and we'll find trades with those
  // players included, and then the user is pushed to find a trade with the
  // calc empty." An action beat here could only advance on a real pick, which
  // is exactly the canvas state the tour must NOT end in — the run has to
  // reach the modeled deck. (It was a tap beat until the 2026-08-22 device
  // pass; it is a Next beat now, which changes the control, not the contract.)
  n16: (): GuideStep => ({
    id: 'n16', screen: 'TradeCalculator', pose: 'point', advance: 'cta',
    ctas: [NEXT], target: 'calc.league-give-add',
    line: "Add players you'd move and we'll find trades that include them.",
    degradeLine: 'Adding players to a side finds trades that include them.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    adoptionEvent: 'calc_asset_added',
  }),

  n18: (): GuideStep => ({
    id: 'n18', screen: 'TradeCalculator', pose: 'point', advance: 'action',
    target: 'calc.action.find-a-trade',
    // The second clause is the whole point of the reshape: an empty canvas is
    // what routes this tap to the MODELED deck, where n19-n24 live.
    line: 'Now tap Find a Trade — start with the canvas empty.',
    degradeLine: 'Tap Find a Trade with the canvas empty when you are ready.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    adoptionEvent: 'find_trades_tapped',
  }),

  // The operator's step 11 in full: "the clear button has become the X, the
  // X records your decision, the check does as before". The calculator's
  // Clear IS the deck's cross — naming that continuity is the beat's job.
  n19: (): GuideStep => ({
    id: 'n19', screen: 'Trades', pose: 'point', advance: 'cta',
    ctas: [NEXT], target: 'trades.pass-btn',
    line: 'Clear became this cross. It records why you passed; the check still accepts.',
    degradeLine: 'Clear became the cross — it records why you passed. The check accepts.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    adoptionEvent: 'trade_pass_layer1',
  }),

  // Was untargeted "because the swap affordance is per-player-row". Device
  // feedback 2026-08-22 (report 4): the avatar came back for this beat and
  // pointed at nothing. Per-row is true, but ONE row is enough to teach the
  // control — the top card's first give row registers `trades.swap-first`.
  n20: (): GuideStep => ({
    id: 'n20', screen: 'Trades', pose: 'neutral', advance: 'cta',
    ctas: [NEXT], target: 'trades.swap-first',
    line: 'Swap arrows change any player without leaving the card.',
    degradeLine: 'Every player row carries a swap arrow that changes that piece.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    adoptionEvent: 'trade_swap_suggest_opened',
  }),

  n21: (): GuideStep => ({
    id: 'n21', screen: 'Trades', pose: 'neutral', advance: 'cta',
    ctas: [NEXT], target: 'trades.package-toggle',
    line: 'Package shows every piece in a multi-player deal.',
    degradeLine: 'Multi-player deals expand to show every piece.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    // Toggling the package re-runs generation, so the regeneration IS the
    // adoption signal — there is no dedicated package-toggle event.
    adoptionEvent: 'deck_regenerated',
  }),

  n22: (): GuideStep => ({
    id: 'n22', screen: 'Trades', pose: 'point', advance: 'cta',
    ctas: [NEXT], target: 'trades.fairness-help',
    line: 'Tap the meter to see how we judged this trade fair.',
    degradeLine: 'The fairness meter explains how a trade was judged.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    // The ⓘ this beat points at fires help_opened{topic:'trade_pricing'}.
    adoptionEvent: 'help_opened',
  }),

  // The send control is platform-resolved (Sleeper / MFL / ESPN), so no INNER
  // button id could be right for more than one of the three — which is why
  // this beat shipped untargeted, and why the operator's device pass found the
  // send button off-screen with nothing pointing at it (report 5). The target
  // is the stable WRAPPER the deck mounts the router in, `trades.send-btn`;
  // the overlay scrolls it into view before it draws the ring.
  //
  // TWO BEATS, one slot. The password sentence is true on Sleeper (the JWT is
  // captured in a WebView and kept on-device) and FALSE elsewhere: MFL POSTs
  // the password to /api/mfl/auth-link and ESPN stores espn_s2/SWID
  // server-side. The operator vouched for the Sleeper claim only, so the
  // runner picks by `resolveSendPlatform` (utils/calcTour.ts) rather than
  // shipping one line that is a lie for two platforms.
  n23: (): GuideStep => ({
    id: 'n23', screen: 'Trades', pose: 'neutral', advance: 'cta',
    ctas: [NEXT], target: 'trades.send-btn',
    line: 'Sending goes straight to your league. Passwords never leave your phone.',
    degradeLine: 'Sending a trade goes straight to your league. Passwords stay on your phone.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    adoptionEvent: 'sleeper_send_attempted',
  }),

  /** Off-Sleeper sibling of `n23` — same slot, no password claim. */
  n23b: (): GuideStep => ({
    id: 'n23b', screen: 'Trades', pose: 'neutral', advance: 'cta',
    ctas: [NEXT], target: 'trades.send-btn',
    line: 'Sending goes straight to your league.',
    degradeLine: 'Sending a trade goes straight to your league.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: part of the re-runnable walkthrough; capped, not retired.
    // The registered send event is Sleeper's; MFL/ESPN sends fire no client
    // event yet (P0-7 parity is carried, not landed). Naming the one that
    // exists keeps the field greppable against the taxonomy — the join for
    // this beat's platforms lands when their events do.
    adoptionEvent: 'sleeper_send_attempted',
  }),

  n24: (): GuideStep => ({
    id: 'n24', screen: 'Trades', pose: 'celebrate', advance: 'cta',
    // The closing beat, so its button says so rather than promising a next.
    ctas: [DONE],
    line: 'Take it from here. Decide, and the next trade comes up automatically.',
    maxDisplayCount: 3,
    retireAfter: 'never', // reason: closes the re-runnable walkthrough; capped, not retired.
    // The claim is literally "the next card comes up" — deck_card_viewed is
    // that card being seen, which is the only honest downstream event here.
    adoptionEvent: 'deck_card_viewed',
  }),
} as const;

/** Fixed leverage order for the S5.5 next-position ask (client-side proxy
 *  for need_fit leverage — thinnest-first ordering ships with the powered
 *  arm once per-position need is exposed to the client). */
export function nextUnrankedPosition(done: string[]): string | null {
  const order = ['QB', 'RB', 'WR', 'TE'];
  return order.find((p) => !done.includes(p)) ?? null;
}
