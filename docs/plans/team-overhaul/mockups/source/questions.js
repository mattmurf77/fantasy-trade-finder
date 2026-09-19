window.OverhaulQuestions = [
  {
    id: 'launch_scope',
    page: 'outlook',
    title: 'First release',
    question: 'Which app and league platforms should the first release cover?',
    context: 'Offer sending and response tracking may need different flows for each league platform.',
    recommendation: 'Recommendation: start with iOS and Sleeper, then expand once the full execution flow is proven.',
    options: ['iOS and Sleeper first', 'iOS and all currently connected league platforms', 'iOS and web, across currently connected league platforms']
  },
  {
    id: 'preference_scope',
    page: 'outlook',
    title: 'Roadmap settings',
    question: 'Should the outlook and position choices made here also change the user’s regular trade-finder settings?',
    context: 'The existing guided Team Review saves these choices for the whole league. A saved roadmap could instead keep its own choices.',
    recommendation: 'Recommendation: keep choices with this roadmap and offer an explicit option to apply them to the regular finder.',
    options: ['Roadmap only, with an option to apply to the finder', 'Always update the regular finder too', 'Roadmap only, with no shared-settings action']
  },
  {
    id: 'selected_pool',
    page: 'assets',
    title: 'Available or must move?',
    question: 'Does selecting an asset make it available for the overhaul, or mean every complete roadmap should move it?',
    context: 'More Offers currently adds other roster assets as sweeteners. This flow needs a clear boundary around the user’s selected pool.',
    recommendation: 'Recommendation: selected assets are eligible, unused assets are shown clearly, and unselected assets are protected unless the user adds them to the pool.',
    options: ['Eligible pool; some selected assets may remain', 'Every selected asset must be included', 'Let users mark individual selected assets as “must move”']
  },
  {
    id: 'pick_budget',
    page: 'assets',
    title: 'All-in pick budget',
    question: 'How far into the future should we recommend spending draft picks when the user pushes all in?',
    context: 'Users can still change individual selections. This decides the initial recommendation and whether we should offer a spending limit.',
    recommendation: 'Recommendation: initially recommend picks from the next two drafts, with a visible control to include later years or protect first-round picks.',
    options: ['Next two drafts by default, with an editable limit', 'All owned future picks are eligible recommendations', 'Ask the user for a draft-year and first-round-pick budget first']
  },
  {
    id: 'recover_first',
    page: 'assets',
    title: 'Recovering their own first',
    question: 'If a rebuilding user does not own their next-season first, must they recover it before other sell-offs can be sent?',
    context: 'The warning and priority to trade for that exact pick are already part of the feature. The open decision is whether recovery blocks the rest of the plan.',
    recommendation: 'Recommendation: make recovery the first execution step; let the user explicitly continue without it after reviewing the consequence.',
    options: ['Recover it first, with an explicit override to continue', 'Prioritize recovery but send other sell-offs alongside it', 'Require recovery before any other sell-offs, with no override']
  },
  {
    id: 'draft_order_rules',
    page: 'assets',
    title: 'When draft position improves',
    question: 'How should the rebuild flow handle leagues whose draft-order rules are unknown or do not reward a weaker roster?',
    context: 'Owning the first-round pick is only one condition. Standings, maximum potential points, lotteries, or custom rules can change whether reducing production helps.',
    recommendation: 'Recommendation: explain a draft-position benefit only when confirmed league rules support it; otherwise show the uncertainty without promising that benefit.',
    options: ['Tailor the guidance to confirmed rules; show uncertainty otherwise', 'Ask users to confirm draft-order rules before building the plan', 'Omit draft-position guidance until that league’s rules are supported']
  },
  {
    id: 'rebuild_returns',
    page: 'assets',
    title: 'The rebuild’s return',
    question: 'Within “blow it up,” how should we balance draft picks against younger players in the returns?',
    context: 'Pick-only returns are allowed. Young productive players can retain future value while doing less to reduce current production.',
    recommendation: 'Recommendation: offer a simple picks-first versus young-core preference, with picks-first as the initial recommendation.',
    options: ['Let users choose picks-first or a young core', 'Always favor picks, using young players when the deal is stronger', 'Optimize future value without a separate picks-versus-players preference']
  },
  {
    id: 'position_constraints',
    page: 'positions',
    title: 'Preferences or requirements?',
    question: 'When users select positions to acquire, should those be strict requirements or preferences for the overall roadmap?',
    context: 'A strong multi-trade plan could include a useful deal at another position. The existing finder treats chosen positions as candidate filters.',
    recommendation: 'Recommendation: treat them as preferences across the full roadmap, with an optional “required” setting for a position the user must address.',
    options: ['Plan-level preferences, with an optional required setting', 'Strict: every proposed trade must include a selected return position', 'Soft preferences only; no strict setting']
  },
  {
    id: 'review_completion',
    page: 'review',
    title: 'Finishing the trade review',
    question: 'Should users finish a fixed deck of trade chips before seeing roadmaps, or be able to finish early once enough compatible trades are liked?',
    context: 'The normal flow still ends with liking or disliking the generated chips. This decides the deck’s size and whether an early exit is available.',
    recommendation: 'Recommendation: start with a manageable deck of about 20–30 ideas, allow “Build my roadmaps” when enough compatible likes exist, and offer more ideas when needed.',
    options: ['A bounded deck, with early completion when enough compatible likes exist', 'Require all chips in a fixed deck to be reviewed', 'Generate small batches; users decide when to build roadmaps']
  },
  {
    id: 'asset_grouping',
    page: 'roadmaps',
    title: 'What changes between roadmaps?',
    question: 'Should alternative roadmaps keep the same groups of sell assets, or may they regroup those assets into different trades?',
    context: 'For example, one roadmap could sell A + B together, while another sells A and B separately. Backups within a chosen group would still share that group’s outgoing assets.',
    recommendation: 'Recommendation: allow regrouping between alternative roadmaps, then keep the chosen roadmap’s groups stable while ranking and sending their backups.',
    options: ['Allow regrouping between roadmaps; keep groups stable during execution', 'Use identical sell-asset groups in every roadmap', 'Let users choose or edit the sell-asset groups before generating ideas']
  },
  {
    id: 'quality_vs_count',
    page: 'roadmaps',
    title: 'When there are too few compatible likes',
    question: 'If the liked trades cannot make four or five strong, compatible trades, what should the roadmap page do?',
    context: 'Four or five trades and four or five alternative roadmaps remain the target. A small pool or overlapping likes may produce fewer useful combinations.',
    recommendation: 'Recommendation: show the best smaller plan with an explicit shortfall, plus a focused way to review more ideas for the uncovered assets.',
    options: ['Show a smaller plan and offer focused additional ideas', 'Return to the trade review until at least four compatible trades are liked', 'Let the user expand the asset pool before generating any roadmap']
  },
  {
    id: 'same_counterparty',
    page: 'roadmaps',
    title: 'Several trades with one manager',
    question: 'Can one roadmap send multiple trades to the same opposing team when their assets do not overlap?',
    context: 'The combined effect still needs to make sense for both rosters. Several individually appealing trades may compete for the same manager’s needs or roster space.',
    recommendation: 'Recommendation: prefer one active trade per opposing team, while allowing multiple only after checking their combined fit and making that repetition visible.',
    options: ['Prefer one per team; allow validated exceptions', 'Strictly one active trade per opposing team', 'Allow multiple whenever the outgoing and incoming assets are distinct']
  },
  {
    id: 'fallback_execution',
    page: 'priorities',
    title: 'Sending the next priority',
    question: 'After an offer is declined, should the next ranked offer be sent automatically or wait for the user to send it?',
    context: 'Equal-priority offers already go out together with the first-come, first-served warning. This question concerns moving from one priority level to the next.',
    recommendation: 'Recommendation: start with a “Send next offer” action after refreshing availability; add automatic progression only as an explicit user choice.',
    options: ['User reviews and sends the next offer', 'User can enable automatic progression for each asset group', 'Always send the next valid priority automatically after a decline']
  },
  {
    id: 'pending_offers',
    page: 'priorities',
    title: 'Offers with no response',
    question: 'How should an unanswered offer affect the next priority for the same sell assets?',
    context: 'A pending offer can remain open for days. Sending a later priority while it remains active would turn the group into a concurrent race.',
    recommendation: 'Recommendation: keep the next priority on hold, surface the offer’s age, and let the user choose whether to wait or withdraw and move on.',
    options: ['Hold and let the user choose when to withdraw and advance', 'Use a user-selected timeout, then ask before advancing', 'Allow an explicit timeout that withdraws and advances automatically where supported']
  },
  {
    id: 'combined_roster',
    page: 'summary',
    title: 'A plan that works together',
    question: 'Should every trade in a roadmap be executable in any acceptance order, or may the plan include steps that depend on an earlier move?',
    context: 'Unique sell assets prevent double-selling, but combined trades can still create roster-limit or lineup problems. Tied alternatives remain explicitly competing offers.',
    recommendation: 'Recommendation: make the initial batch independently executable in any order, validate the combined roster, and show any required roster moves before sending.',
    options: ['Require order-independent execution for the initial batch', 'Allow dependent steps, clearly separated into later batches', 'Offer both an independent batch and a staged plan as distinct choices']
  },
  {
    id: 'counteroffers',
    page: 'tracking',
    title: 'When an offer is countered',
    question: 'How should a counteroffer become part of the active roadmap?',
    context: 'A counter can add or remove sell assets, which may conflict with another planned trade. Platform support determines whether it can be imported automatically.',
    recommendation: 'Recommendation: show the counter for review and recheck it against the remaining roadmap before the user accepts or promotes it.',
    options: ['Review the counter in the roadmap and revalidate affected groups', 'Handle counters on the league platform and record the outcome here', 'Treat the counter as a new idea to like and rank among backups']
  },
  {
    id: 'roadmap_refresh',
    page: 'tracking',
    title: 'Keeping an active roadmap current',
    question: 'When an accepted trade or another roster change invalidates part of the roadmap, how much should we rebuild?',
    context: 'Completed trades should stay visible. The remaining plan may need fresh offers, and some platforms may require users to confirm status changes.',
    recommendation: 'Recommendation: preserve completed and pending work, flag stale offers, and refresh only affected groups with a visible review of any changes.',
    options: ['Refresh affected groups while preserving the rest', 'Regenerate the whole unexecuted portion after user confirmation', 'Keep the plan unchanged until the user explicitly requests a rebuild']
  },
  {
    id: 'resume_entry',
    page: 'tracking',
    title: 'Returning to the plan',
    question: 'Where should users reopen an active roadmap, and should they be able to save multiple alternatives for the same team?',
    context: 'The package page must remain available as responses arrive. A single active roadmap is simpler; saved alternatives make it easier to compare or change direction.',
    recommendation: 'Recommendation: show an active-roadmap card on the Trades page and keep saved alternatives in a Roadmaps view, with only one executing roadmap per league.',
    options: ['Trades card plus saved alternatives; one executing roadmap per league', 'A single active roadmap reopened from the Trades page', 'A dedicated Roadmaps view with multiple independently active plans']
  }
];

// Explicit owner decisions received in this task after the initial review.
const overhaulOwnerDecisions = {
  preference_scope: 'Keep roadmap settings separate from the regular trade finder.',
  selected_pool: 'Selected assets are available to trade; every selected asset does not have to be moved.',
  pick_budget: 'The user decides the all-in draft-pick budget.',
  recover_first: 'Include an offer for the user’s exact next-season first and highlight it as Priority 1 across the overhaul. The user decides whether to execute it first; other offers are not blocked.',
  rebuild_returns: 'Let the user decide the balance between draft picks and younger players.',
  position_constraints: 'Treat selected positions as preferences.',
  asset_grouping: 'Alternative roadmaps may group outgoing assets differently.',
  quality_vs_count: 'Generate more offers for review and prompt the user to reconsider the available asset pool.',
  fallback_execution: 'Wait for the user before sending the next offer so they can negotiate. Optional automatic progression is a possible later enhancement.'
};
window.OverhaulQuestions.forEach(question => {
  if (overhaulOwnerDecisions[question.id]) question.ownerDecision = overhaulOwnerDecisions[question.id];
});
