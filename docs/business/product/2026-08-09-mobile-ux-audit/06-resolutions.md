# Resolutions — every finding, typed and with a proposed fix

> Companion to [04-priority-backlog.md](04-priority-backlog.md). That file ranks the findings; this one says what to do about each.

---

## The labels

| Label | Meaning |
|---|---|
| **Bug** | Incorrect or broken. Fix it — there is no version worth testing. |
| **Polish** | Existing behaviour that works but could work better. Low blast radius. |
| **Idea** | New capability or a real product decision. Higher blast radius. |
| **Ship as-is** | Clearly directional, or there is no meaningful control arm. Build and move on. |
| **A/B candidate** | Reasonable people could disagree, and it touches a measurable funnel step. |

**Counts:** 15 Bugs · 4 Polish · 13 Ideas. 10 ship-as-is, 8 A/B candidates.
**Eight of the nine launch blockers are Bugs** — the gate to launch is mostly repair, not redesign.

## Before you read the A/B labels

**You cannot currently power an A/B test.** Production is 16 users. Your own experiment doc's power calculator returned ~174 per arm — about 348 weeks at beta scale — and `onboarding_v2_rollout` shipped with `override_underpowered: true` recorded permanently.

As a rough rule: **below ~400 completions per arm on the metric you're testing, an A/B is a directional read, not a decision.**

So until you have volume: ship the better-reasoned arm, instrument it (P0-7), and compare pre/post cohorts. Treat the A/B labels as a queue for when traffic justifies it, not a reason to delay shipping now. The one exception worth building the harness for early is **P0-9**, because it is the change I am least certain about.

---

# Launch blockers

### P0-1 · Unlock coherence break — **Bug**
Write the method at the point of *use*, not the point of choice. In each save handler, if the user has no stored `ranking_method`, set it from the action: `/api/tiers/save` → `quickset`/`tiers` per the `via` tag, `/api/rank3` → `trio`, `/api/rankings/reorder` → `manual`, `/api/anchor/save` → `anchor`. Four one-line additions.

Then backfill: any existing user with saved tiers but a null method gets `quickset`, so nobody stays stuck. Verify by confirming the push primer fires for a fresh account that only ever touches Quick Set.

### P0-2 · Generation errors invisible — **Bug**
Branch the deck empty-state ladder on `job?.status === 'error'` *before* the never-searched case, and render the backend message with a Retry that re-fires the mutation. Add the poll-abandoned case too — after four consecutive failures the job is cleared and the user lands in the same ambiguous state.

Copy should name cause and action: "We couldn't finish that search — the server may still be waking up. Try again." The error mapping already exists in the toast handler; reuse it.

### P0-3 · Invite loop broken — **Bug** · *additive half ships as-is*
**The bug:** change `buildInviteUrl` to emit a real path — `/app/league/join/<leagueId>?ref=<user>` — and add the matching `V2_SCREENS` entry so the router stops short-circuiting. Parse the league id, stash it alongside `invitedBy`, pin it as active once auth completes.

**The additive half:** when a referral is present, name the inviter and league on sign-in. Don't A/B a loop that converts zero — get it working, instrument it, then test framing later. Your growth doc's altruistic-vs-selfish finding is the hypothesis for that test.

### P0-4 · ~~Mock Draft dead end~~ — **WITHDRAWN 2026-08-09**

**The operator corrected this and was right. Mocks are enabled and work.**

`CPU_MODEL_VALIDATED = True` at `backend/mock_draft_service.py:294`, flipped by explicit operator override on 2026-08-06. `start_refusal` therefore never returns `cpu_model_unvalidated`, and the create route serves a real mock.

**How the error happened**, since the cause matters more than the finding: I trusted two secondary sources instead of the authority. The `_comment_draft_extensions` block in `config/features.json` still says the mock "stays OFF" and that "with the flag ON the create route answers the typed-empty `cpu_model_unvalidated`" — both untrue since the override. I saw the client's refusal branch existed and inferred it fired. `mock_draft_service.py` was outside my pinned snapshot, so I never read the constant that actually decides it.

A finding resting on a comment rather than the code is not a finding. Retained here rather than deleted so the correction stays on the record.

**Residual, now tracked as A-33:** the config comment asserts the opposite of runtime behaviour, and the code comment directly above the constant still reads "the verdict is still FAILED, so this stays False and the routes still refuse."

### P0-5 · Apple account-only strands users — **Bug**
Route account-only sessions to `LeaguePicker` instead of `Main` in `onAccountSignedIn`. The picker needs a companion state, since these users have no Sleeper id and therefore no leagues to list: show the platform-link options directly — "Connect Sleeper, ESPN or MFL to see your leagues" — reusing the footer buttons already on that screen.

Alternative, if you'd rather not touch routing: land on Main and mount a non-dismissible link-a-league sheet. I'd prefer the routing fix; the picker already knows how to do this job.

### P0-6 · ESPN matches have no action — **Bug**
Replace the silent `null` for non-Sleeper platforms with an explanatory state and a real fallback: "Sending is Sleeper-only for now — copy this trade to propose it in ESPN," with a copy-to-clipboard action formatting both sides as plain text. Free Agents already does this pattern for its dimmed Add button — mirror it rather than inventing a second idiom.

Separately, decide the dead accept/decline path: `setMatchDisposition` is wired server-side and never called. Surface it as the primary action on a match, or delete it.

### P0-7 · Analytics blindness — **Bug**
Three targeted additions, not a programme:
1. A `tab_selected` event in the tab-press handlers — screen-view events already exist in RootNav, so this is the missing navigation primitive.
2. Mount and interaction events on both League screens — view, basis toggle, subset change, team drill-in.
3. `send_in_sleeper_tapped` / `_succeeded` / `_failed` with error code, on the highest-intent action in the product.

**Do this first or the work is wasted:** register every new name in the server taxonomy allowlist before wiring the calls. It's default-deny, and your growth doc records an event fired by the client and silently dropped for exactly this reason.

### P0-8 · False tour completion — **Bug**
Gate the sign-off step on having actually delivered a tour: require a minimum number of seen steps, or specifically require that the swipe-coaching beat was shown, before `s8.1` may fire and call `completeTour()`.

While you're in there: `err.burst` has zero call sites. Delete it or wire it — a script with dead entries makes the live entries harder to trust.

### P0-9 · 32-tap first session — **Idea** · **A/B candidate**
Everything needed exists behind off flags. `onboarding.trades_first` lands a new user on a consensus-priced deck, collapses first-run chrome, shows the provenance chip explaining those values aren't yet theirs, and — with `onboarding.quickset_prompt` — offers the ranking detour contextually after two or three swipes rather than as an unexplained opening chore.

**Why this is the one to actually test.** It changes the primary funnel, it's reversible in a flag flip, and it's my least-certain finding. Build the harness even though you can't power it yet: run it as a directional read and let first real traffic settle it.

If you'd rather not wait: ship trades-first. The argument that a user should see the product before doing data entry is strong enough to act on, and the flag makes reverting cheap.

---

# Launch window (P1)

| ID | Finding | Type | Rollout | Fix |
|---|---|---|---|---|
| **A-10** | Shared images carry no URL | Bug | — | Render a short link into the PNG footer and the share message body. OG infrastructure exists; this is a text layer and a string concat. |
| **A-11** | Share landings have zero callers | Bug | — | Call `POST /api/share/package` from the calculator's share action; link `/s/tiers/<pos>/<user>` from the tier board's completion state. Delete the stale comment claiming the package route doesn't exist — it does, and that comment is why nobody wired it. |
| **A-12** | No email capture | Idea | **Ship as-is** | Turn on `auth.email_capture`, store the Apple relay address at bind time, update the privacy policy in the same release. Nothing user-visible to test. Apple shares the address on first authorisation only, so existing users can't be backfilled — every week this stays off is permanently lost reach. |
| **A-13** | Adjustments never itemized | Polish | **A/B candidate** | Extend the collapsed "Why?" disclosure to list each applied adjustment by name with its contribution. The server already computes them. A/B because it adds density to the most important card in the app; shipping unilaterally is defensible since every competitor does it. |
| **A-14** | Invite buried and unmeasured | Polish | **A/B candidate** | Promote invite to a primary button on League Home and the Matches empty state. Use `load_league_member_unlock_states`, which already returns per-member join status — "8 of your 11 leaguemates haven't joined" ships today with no new endpoint. A/B the copy: generic vs named, altruistic vs self-interested. |
| **A-15** | Streaks reward nothing | Idea | **A/B candidate** | Attach a payoff: cosmetic badge, capability unlock, or — best fit — a quality signal, since more ranking days means a better board. Reward design is what you test rather than reason about. Until then pick the quality framing; it's the only one that stays honest if the reward is removed. |
| **A-16** | Anchors can't unlock; labels contradict ladder | Bug | — | Add `anchor` to the tiers/quickset unlock branch, or increment the interaction counter in `apply_anchor` (more consistent). Then reconcile `ANCHOR_ROWS` to `TIER_LABEL` — "4 1sts" vs "4+ 1sts", "No value" vs "FA" are the same bands wearing two names in the vocabulary the product is built on. |
| **A-17** | Manual one-tap unconditional unlock | Bug | — | Require evidence of use — at minimum one completed reorder — before the manual branch returns unlocked. Today selecting the chooser card unlocks the finder before the screen mounts. |
| **A-18** | No new-trade notification | Idea | **A/B candidate** | Add a quality-gated `trade_found` push on the existing cap/quiet-hours machinery. The gate matters more than the feature. A/B threshold and cadence, not existence — your own doc has it right: one great push a week builds a habit, three mediocre ones a day costs the permission permanently. |
| **A-19** | Sleeper Connect has no analytics | Bug | — | Mirror the four events its ESPN twin fires — opened, captured, abandoned, OTP step. This flow gates Send-in-Sleeper and verification; its drop-off is among the most valuable curves in the product and is invisible. |
| **A-20** | Draft tab out of season; "Acquire" naming | Polish | **A/B candidate** | Draft tab is a manual annual toggle sitting on in August — turn it off, no code needed, ship as-is. The label is the testable half: "Acquire" is presentation-only over a route still called Trades, so switching costs nothing. Users, competitors and App Store search all say "trades." A tab-label test is about as clean as experiments get. |
| **A-21** | Sleeper write ToS-adverse and live | Idea | **Ship as-is** | A business decision needing an owner, not a test. The flag is on, the route reproduces an undocumented private API, four docs describe it as default-off. Reconcile: accept the exposure and correct the docs, or gate it. Either way write down the fallback now — Send-in-Sleeper is the only path from a match to a real trade, so its failure mode is the product's failure mode. |

---

# Backlog (P2–P4)

| ID | Finding | Type | Rollout | Fix |
|---|---|---|---|---|
| **A-22** | No public web calculator | Idea | Ship as-is | The "Real values" mode already works without a session; the constraint is that reaching it requires an install. Expose the same evaluation on the web, unauthenticated, with an install prompt after a result. No control arm worth running. |
| **A-23** | Playoff odds built and dark | Idea | Ship as-is | Pipeline and mobile section both exist; the flag is in neither launch defaults nor config, so the endpoint is unreachable. Register and enable, or delete. It already appears in your own queue as dead weight. |
| **A-24** | No starters/bench dimension | Idea | Ship as-is | Add a starter/bench dimension to roster valuation and let it re-rank the whole league chart, not one roster. The strongest competitor idea FTF lacks entirely, extending the best-built screen in the app. |
| **A-25** | No player detail pages | Idea | Ship as-is | Start with what you uniquely have: the player's value on the user's own board next to consensus, their tier, 30-day movement, and who in their league is high or low on them. That last one nobody else can render. |
| **A-26** | Public profiles unreachable | Idea | **A/B candidate** | Turn on `profiles.public_pages`, add the opt-in toggle already behind its own flag, link from contrarian leaderboards and match rows. A/B the default and framing, not the feature — publishing a user's opinions is privacy-sensitive and opt-in vs opt-out will move adoption more than page design. |
| **A-27** | 1,656 lines of dead code | Bug | — | Remove the unrouted hub screen, the placeholder, and the orphaned meter component. Add a lint rule failing on any screen file no navigator registers — this debt regrows silently and made every part of this audit more expensive. |
| **A-28** | Trends buried | Polish | **A/B candidate** | The only surface whose content changes without user action, three taps deep behind a collapsed disclosure. Surface on League Home or as a tab destination. Navigation placement is inherently testable and being wrong costs IA clarity. |
| **A-29** | No trade history feed | Idea | Ship as-is | Trade capture is built and has recorded zero rows because no synced league has traded. Phase it: the league's own history first (useful at any scale), before the cross-league database larger competitors have. |
| **A-30** | No Discord presence | Idea | Ship as-is | A read-only bot answering value and fairness questions inside the room where dynasty trades are argued. Your channel analysis ranks this second only to the league loop and notes one competitor is alone there. Measured by adoption, not split test. |
| **A-31** | Seven screens without Maestro coverage | Bug | — | Settings, Profile, Feedback Inbox, Test Stages, Pick Assignment, Mock Draft, Record Picks have no flow; three ship flag-on. Also reconcile the trades smoke flows, which assert against a layout the finder-hub flag suppresses — they may test a screen no user sees. |
| **A-32** | Only one calendar-aware mechanism | Idea | Ship as-is | A season-start push pinned to 25 August is the only date-aware code in the app. Dynasty interest is bimodal — May rookie peak, late-August draft peak — and nothing else knows what month it is. Start with the two peaks you can name. |
| **A-34** | Feedback FAB clips primary content on data-dense screens | Bug | — | *(P1 — found only by looking at the app; four independent visual agents hit it across seven screens.)* The floating feedback button sits over content rather than beside it. Confirmed damage: truncates a mutual match card's button to **"Send in Sleepe"** — the label of the highest-intent action in the product; covers the last player card on Quick Set, the default landing screen; clips a tier chip to "3 1S…" on Overall Ranks, a trade-value badge in the calculator, a leaderboard score on League Rankings, and coverage copy on League Home. The FAB already has a pinned-bar height registry under `ux.touch_polish`, so the offset mechanism exists — extend it to reserve bottom inset on scroll containers rather than letting content run under the button. |
| **A-33** | Config comments assert the opposite of runtime behaviour | Bug | — | *(P1 — raised by the P0-4 withdrawal.)* `_comment_draft_extensions` in `config/features.json` says the mock "stays OFF" and refuses; `mock_draft_service.py:294` says `True`. The code comment directly above that constant still reads "the verdict is still FAILED, so this stays False and the routes still refuse." Reconcile both to runtime truth. Not cosmetic — that contradiction produced a false launch blocker in this audit, and the next reader will draw the same wrong conclusion. General rule worth adopting: when an operator override flips a constant, the comment above it is part of the change. |

---

## If you only do the Bugs

Fifteen findings, most of them small, and they include eight of the nine launch blockers. That set alone closes the unlock break, makes failures visible, repairs the invite loop, removes the dead-end door, un-strands account-only users, gives ESPN matches an action, restores launch-day visibility, stops the false tour completion, wires two finished share loops, fixes both broken unlock paths, instruments the highest-value flow, and deletes 1,656 lines of dead code.

That is a launch-ready product. Everything labelled Polish or Idea is what you do next, not what you do first.
