# Shared brief — #403 "Shop a player" (Phase 1 dual-agent doc round)

Read this first. Every agent working this item reads this file, then the
pointers below, then does its own verification. **Nothing in this brief is
established fact until you re-verify it against the code** — it is a
starting point assembled by the orchestrator, and at least one prior batch
was nearly derailed by trusting a summary over the tree.

## The report, verbatim

> **#403** · `Boston Brawlers` · screen `TradeCalculator` · v1.16.8 · filed 2026-08-26T21:54Z · severity `polish`
>
> Idea, not design consideration quite yet.. I want to give users the option to "shop" a player. When launched, the user is offered a few options, trade options to tier up, tier down, explore position specific swaps of similar value. If position swap, the user should be able to select the position (or positions) we suggest in the swap ideas. I want a similar response to the current tier up/ tier down UI which presents the ideas as small tiles (so multiple offers presented at once or trade cards with a 1/X indication for them to see the different cards. They can swipe left and right on the cards to go back and forth between them (different from the current ship to like feature. Each card should have a like/ dismiss button.

Note the operator's own hedge: **"idea, not design consideration quite yet."**
The doc round's job is to make it buildable, and to say plainly where the
report under-specifies rather than inventing a decision and burying it.

## The single most important thing to check first

**Most of this may already exist and ship today.** `POST /api/trades/asset-ideas`
(`backend/server.py:12024`, flag `trade.asset_ideas` — **`true` in
`config/features.json`, i.e. LIVE**) takes a pinned asset and returns ideas in
three groups: **`upgrade` / `lateral` / `downgrade`**, built by
`TradeService.generate_asset_ideas` (`backend/trade_service.py:~5011-5360`).
The band that separates "lateral" from the other two is the `model_config`
knob `asset_ideas_lateral_band` (0.10, `trade_service.py:202`).
`mobile/src/components/AssetIdeasPanel.tsx` (271 lines) already renders those
three groups, labelled "Upgrade at {pos}" / "Lateral moves at {pos}" /
downgrade.

Map that onto the report and the overlap is close to exact:
tier up = `upgrade`, tier down = `downgrade`, "position specific swaps of
similar value" = `lateral`. **Before proposing any new engine work, establish
what the delta actually is.** The plausible genuinely-new asks are:

1. **Position selection** for the lateral case — the user picks which
   position(s) they want offered back.
2. **A card presentation** with a `1 / X` counter and left/right swipe between
   cards, explicitly **NOT** the existing swipe-to-like deck.
3. **Per-card like / dismiss buttons.**
4. An **entry point** — how a user launches "shop this player" at all.

If the delta is mostly presentation, say so loudly. A PRD that specs a new
engine on top of a live one is the expensive failure mode here.

## Hard constraint: #403 overlaps #402, and #402 comes first

**#402** (`Boston Brawlers`, same session, filed 64 minutes earlier) asks:

> Let's change the "more offers" button. This is a two part change. When
> clicking "more offers" the user goes to below the trade chip where "tier up",
> "tier down" options are presented in line.

#403 explicitly says it wants "a similar response to the current tier up/tier
down UI". So #402 sets the pattern #403 must match. **#402's decisions win on
any shared surface or shared copy.** A prior batch shipped divergent copy
("Win-now moves" vs "Team-fit moves") because a mockup agent and a fix agent
designed the same surface independently — do not repeat it. Where #403 needs
something #402 hasn't decided yet, state the dependency explicitly rather than
deciding for #402.

Today's "more offers" is `Keep · more offers` at
`mobile/src/components/TradeCard.tsx:443`, and `TradesScreen.tsx` carries pin /
deck-snapshot logic keyed off that exact tap (see the `#288` comments around
`TradesScreen.tsx:515`, `:2902`, `:5868`). Treat that logic as load-bearing.

## Pointers

- Architecture: `docs/architecture.md` · API: `docs/api-reference.md`
- Coding rules: `docs/coding-guidelines.md` (think first · simplicity · surgical · goal-driven)
- **UI rules are enforced, not advisory:** `docs/design/design-system.md` +
  `docs/design/components.md` (Chalkline). No emoji, no gradients, no
  glassmorphism, no Inter/Roboto/system stacks, no radius >8px except true
  pills, ice = actions and flare = informational highlights only.
- Cross-client encodings: `docs/cross-client-invariants.md` (tier + position
  colors are data encodings and are governed there — never restyle them)
- Feature gates: `CLAUDE.md` §Conventions → scope block
  (`docs/templates/feature-scope.md`), D-056 evidence, docs table, ship gate
- Existing surfaces: `mobile/src/components/AssetIdeasPanel.tsx`,
  `mobile/src/components/TradeDnaSheet.tsx` (`TradeIntent` =
  `consolidate | tier_up | tier_down`), `mobile/src/api/trades.ts`,
  `mobile/src/components/TradeCard.tsx`, `mobile/src/screens/TradesScreen.tsx`,
  `mobile/src/components/InLeagueCalculator.tsx` (the merged calculator, live
  behind `calc.merged_layout: true` — #403 was filed against `TradeCalculator`)

## Working rules for every agent on this item

- **Verify every cite.** File:line references must be re-checked against the
  current tree; `origin/main` is `30070f36` at brief time and moves during a
  session. Any endpoint you cite either exists (give file:line) or is marked
  **NEW** explicitly.
- **No self-satisfying tests.** Every behavioral test in the plan must be
  mapped to a deliberate sabotage that would make it fail. A sabotage that
  hardcodes the expected value does not count. Distributional bars must be
  two-sided. Recompute every worked example against its own formula — a worked
  example is a claim, and one survived two review rounds while contradicting
  its own predicate.
- **Never end a turn waiting** on a monitor, a build, a subagent, or a
  notification. Run test suites synchronously in one foreground call with a
  generous timeout.
- Do **not** symlink the main checkout's `mobile/node_modules` into a
  worktree — it goes stale and produces phantom `tsc` errors. Run `npm ci`.
- This is a **doc round only**. Write no production code.
