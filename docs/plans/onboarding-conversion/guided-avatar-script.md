# The Analyst — Guided Onboarding Script v1

*2026-07-19. Character: **The Analyst** (operator-selected from the avatar lab). Assets: `mockups/avatar-lab/analyst-poses.html` (6-pose sheet, verified). Ships as experiment arm `guided` behind `onboarding.guided_avatar` — see §7.*

---

## 1 · Principles (binding)

1. **Never trap.** Every bubble has an ✕; "Skip the tour" is offered at S0 and after any two consecutive skips. Skipping the tour sets `guideDismissed=true` (persisted) and falls back to the shipped v2.1 passive experience (chips/prompt card). The Analyst never blocks a tap target.
2. **One bubble at a time; system modals win.** The Analyst yields (fades to corner, silent) whenever a system surface is up: Apple sheet, push permission, format gate, error alerts. Never within 1s before/after a system modal (the F4 no-stacking rule extends to him).
3. **Honest data only.** The Analyst quotes numbers ("+14%", "N new trades") ONLY when the value comes from a live API response. No number available → neutral phrasing variant (each numbered line below has one). He inherits every ADR-006 copy rule — no false loss-framing, ever.
4. **Talk is tappable.** Dialogue-only steps advance on tap-anywhere. Action steps advance ONLY on the real action (the spotlight target's own handler) — the guide observes, it never simulates taps.
5. **Replaces, not stacks.** In the `guided` arm, The Analyst supersedes the passive guided-layer surfaces: swipe hint, coach marks, prompt card, celebration beats, and the diff banner (he delivers those lines himself). Same persisted gates in `ftf_onboarding_state`, same funnel events, plus `guide_*` events (§6).

## 2 · Stage directions (component contract)

- **AnalystGuide** overlay host mounts once (RootNav level, above tabs, below system modals). Renders: avatar (bottom-left default, 96px), speech bubble (attaches top-center of avatar, max 3 lines, tap-to-advance ripple), optional **spotlight** (dark scrim `scrim` token at 65%, cutout = target's measured frame + 8px radius, pulsing 2px ice stroke), optional ✕ + "Skip tour."
- **Bubble placement (operator review 2026-07-19):** the bubble may NEVER overlap the spotlight cutout or any primary CTA — placement solver keeps bubbles in the bottom band by default and picks the corner opposite the avatar; if the target lives in the bottom band, avatar + bubble relocate to the top. Spotlight cutouts frame the *content* being explained, never the action controls (S2: card body spotlit, ✕/✓ stay fully lit and free).
- **Bubbles carry CTAs.** When a scene asks the user to make a choice (S3, S5.5), the accept/decline buttons render INSIDE the bubble — his ask, his buttons. Advance fires from the bubble CTA; no duplicate on-screen button.
- **Spotlight targets are resolved by testID** via a ref-registry (`registerGuideTarget(testID, ref)` — 1-line addition at each target). Target unmounted/unmeasurable → skip the spotlight, keep the bubble (never a blank cutout).
- **Pose set:** `neutral · point (flip/rotate for direction) · celebrate · computing · thinking · oops`. Entrance: slide-up + one overshoot bounce (250ms). Idle: pupil blink ~4s. Exit: slide-down fade (180ms).
- Avatar relocates to bottom-RIGHT when the spotlight target is in the bottom-left quadrant (never covers his own target).

## 3 · The script

Slots: `{{first_name}}` (display name, else "coach"), `{{league}}`, `{{pos}}` (Quick Set position), `{{n_new}}` (regen diff count), `{{thin_pos}}` (lowest `need_fit` position when available), `{{n_opps}}` (opponents with rankings).

### S0 · Landing (signed-out, `onboarding.landing` on)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S0.1 | Landing mount +600ms (once ever: `guideSeen.s0`) | neutral | "Evening. I'm **The Analyst** — I model dynasty trades. You bring the roster, I bring the math." | tap |
| S0.2 | auto | point → username field (`signin.username-input`) | "Type your Sleeper username. No password — your rosters are public record, which is convenient for people like me." | user submits |
| S0.err-notfound | 404 | oops | "No such username. Common error: that's a *team* name. Sleeper profile → the @handle. I'll wait." | resubmit |
| S0.err-down | 5xx/timeout | oops | "Sleeper isn't answering. Statistically it comes back. Retry in a moment{{demo? — or browse my sample league while we wait}}." | resubmit |
| S0.skip | ✕ on S0.1/S0.2 | — | "Understood. I'll be around." → guide yields for the session; S2 may still offer once (see S2.re-entry) | — |

### S1 · League picker (multi-league only; auto-skip users jump to S2)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S1.1 | Picker mount | point → first league row | "Pick the league that matters most. Per my model, that's the one you check at work." | league tap |

### S2 · The deck (Trades tab, first run — lands here automatically per `a9fb54d`)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S2.wait | Deck empty, job running | computing | "Running {{n_opps}}-roster simulations… first cards land in seconds." | cards arrive |
| S2.1 | First card visible | celebrate → neutral | "Done. Every card is a trade my model thinks **both** sides say yes to. This isn't a wishlist — it's a market." | tap |
| S2.2 | auto | point → deck card | "Swipe **right** if you'd take it, **left** if you wouldn't. You're not just browsing — every swipe teaches me your taste. (Numeric variant: I re-fit after every swipe.)" | first swipe |
| S2.3 | after first swipe | neutral | "Logged. Also — see that label? **CONSENSUS VALUES** (point → `trades.provenance-chip`). These prices are the market's, not yours. We'll fix that shortly." | tap |
| S2.identity | Strip visible + 4s idle | thinking | "Verify the letterhead: trading as @{{username}}. Wrong analyst, wrong report — tap 'not you?' if that's not you." | tap / auto-dismiss 6s |
| S2.re-entry | User skipped S0 but reaches deck | neutral | One-shot: "Analyst. I made these for you. Swipe right to accept, left to pass — I'll explain more if you keep me around." + [Keep · Skip tour] | choice |

### S3 · The pitch (replaces the prompt card; trigger identical: first pass after swipe ≥2, else swipe 3 — one show/session, snooze semantics unchanged)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S3.1 | prompt trigger | thinking | "Per my model, you and consensus disagree — most GMs do. Right now I'm pricing your players with *everyone's* numbers." | tap |
| S3.2 | auto | point → `trades.provenance-chip` | "Two minutes on one position and I'll re-price the whole deck with **your** board. {{thin_pos? Your {{thin_pos}} room is the thin one.}}" + **in-bubble CTAs** [Fix {{pos}} →] [Not now] | bubble accept / snooze |
| S3.snooze | "Not now" | neutral | "Noted. The offer stands — that label is the door." (snooze bookkeeping identical to v2.1: session-2 re-offer, then chip-only) | — |

### S4 · Quick Set walk (onboarding-mode; The Analyst goes quiet-coach)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S4.1 | First tier step mount | point → chip grid | "Tap everyone worth the tier label, then Save. Gut calls beat overthinking — for most rosters, tier one is 0–3 names." | first Save |
| S4.2 | Tier 4 reached | neutral | "Halfway. This is already more signal than most leaguemates ever give me." | — (passive) |
| S4.idle | 12s no tap on any step | thinking | "Stuck? Skip the tier. A blank tier is data too." | tap |

### S5 · The reveal (return to Trades; replaces the diff banner)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S5.wait | forced regen running | computing | "Re-pricing {{league}} with your {{pos}} board… " | job complete |
| S5.1 | `n_new > 0` | **celebrate** | "There it is. **{{n_new}} new trades** that only exist because of *your* numbers. That's the product, {{first_name}}: your board, your market." | tap |
| S5.0 | `n_new == 0` | oops → neutral | "Honest result: same trades. Your {{pos}} board agrees with consensus more than you'd think. More positions = more edge — or your league is just efficient." | tap |

### S5.5 · Next position, directed (operator review 2026-07-19: the multi-position promotion must be explicit)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S5.5.1 | S5 reveal tapped, unranked positions remain | point → chip | "{{pos}} is done. Per my model, **{{next_pos}}** is your next-highest leverage — same drill, two minutes." + **in-bubble CTAs** [Rank {{next_pos}} next →] [Later] | bubble accept / later |
| S5.5.re | Later Trades focus, unranked positions remain | point | Same ask, once per session max. Order = `need_fit` leverage (thinnest room first). Retires permanently when all four positions are ranked. | — |

Accepting routes into the same onboarding-mode Quick Set (suppressed finish-prompt → return to Trades → regen → S5 reveal again) — the loop repeats per position with the reveal as its own reward each time.

### S6 · First like → save moment (celebration precedes the ask; Apple modal stays a system surface)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S6.1 | first like recorded | celebrate | "First target logged. If they accept, you'll hear it from me first." | auto 2s |
| S6.2 | eligible for Apple ask (unverified, class unshown) | neutral | "One admin item: sign in with Apple to **save your rankings to your account**. Takes five seconds." → hands off to the system modal | modal outcome |

> **Apple value prop (operator direction 2026-07-19, supersedes cross-device framing):** rankings-first — "save your rankings to your account," with the lock line ("so only you can change it") as support. Honesty check vs ADR-006: this framing is TRUE — Apple bind writes the board to a durable account (device-loss recovery) and mints verified-controller status (squatters read/write-blocked). What remains prohibited: implying the board is *lost without* Apple. The shipped passive prompt copy (voice doc #12/#13 "Keep your board on every device") gets the same rewrite in the guided-arm build; flag the voice-doc addendum to mkt-writer.
| S6.3 | after modal resolves (any outcome) | point → share button | "Leaguemates argue better with visual aids — send them the card if you want a reaction." | tap / 6s |

### S7 · Deck exhausted (trio ramp)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S7.1 | exhausted state | point → trio entry CTA | "You've cleared the market. Quick head-to-heads sharpen your board while we wait for new inventory — 30 seconds at a time." | tap CTA / dismiss |

### S8 · Sign-off (once, after S5 or S6 completes)

| # | Trigger | Pose | Line | Advance |
|---|---|---|---|---|
| S8.1 | next Trades focus after S5/S6 | celebrate → neutral | "That's the tour. I'll keep modeling in the background — you'll see me when the numbers say something worth hearing." | tap → guide retires to reactive-only |

**Reactive-only mode (post-tour):** The Analyst appears ONLY for S5-style reveals after later Quick Set sessions, S7 exhausted states, and error commentary (oops pose on `api_request_failed` bursts ≥3 in 30s: "Something's broken on my end. Not your fault. Investigating."). This is the standing surface a future AI chat assistant plugs into — the avatar becomes the chat entry point.

## 4 · Edge rules

- App backgrounded mid-scene → scene re-offers on next foreground at the same gate (never auto-replays a completed step).
- Existing-user treatment devices (like the operator's) with `firstSwipeDone=true` skip S0–S2 and enter at the first ungated scene.
- Verified/Apple-bound users never see S6.2 (same gate as the prompt itself).
- Demo sessions get the full script with `{{league}}` = sample league; S6 suppressed entirely (no Apple ask in demo).
- VoiceOver: bubble text is the accessibility announcement; spotlight adds `accessibilityHint` naming the target.

## 5 · Voice rules (The Analyst)

Deadpan, precise, dry. Short declaratives. Percentages and counts only when real (§1.3). Signature moves: "Per my model…", honest bad news delivered flat (S5.0 is the trust-builder — a guide that admits a null result is believed later), understated warmth at wins. Never: exclamation points outside celebrate scenes, hype adjectives, apology spirals, "AI" self-reference. He is an analyst who happens to be a football.

## 6 · Events (taxonomy additions required — default-deny, so these need the addendum PR first)

`guide_step_shown / guide_step_advanced / guide_step_skipped` — props `{step, pose, via}` · `guide_tour_dismissed` — props `{at_step}` · `guide_tour_completed`. All stamped with the experiment variant automatically (in-scope screens). Funnel events (`quickset_prompt_*`, `apple_prompt_*`, etc.) keep firing from the SAME underlying triggers so guided-vs-passive arms compare on identical metrics.

## 7 · Experiment plan

Phase 1 (operator smoke): add `onboarding.guided_avatar: true` to the treatment `client_config` of `onboarding_v2_rollout` via `/revise` (v2) — allowlist targeting unchanged, operator validates the tour end-to-end.
Phase 2 (powered): 3-arm `/revise` (v3) on new devices — `control` (old flow) / `passive` (v2.1 surfaces) / `guided` (The Analyst), weights 3334/3333/3333, primary metric `activation_rate`, PFO guardrails auto-attached; run the preview calculator against measured baseline before launch (no theater).

## 8 · Asset manifest

| Asset | Source | Status |
|---|---|---|
| 6 poses (neutral/point/celebrate/computing/thinking/oops) | `mockups/avatar-lab/analyst-poses.html` | ✅ drawn + verified |
| Speech bubble component (3-line max, tail, tap ripple, ✕) | spec §2 | to build |
| Spotlight scrim + cutout + pulse | spec §2 | to build |
| Foam-finger point variants | base flipped (scaleX −1) / rotated (−90°) at runtime | free |
| RN export | each pose → `react-native-svg` component (`mobile/src/components/analyst/`), shared part-kit (eyes/glasses/tie/laces as sub-components) so poses stay in sync | to build |
| Anchor metadata | bubble attach point (top-center, x=75), ground line, flip-safe margins | in pose sheet notes |

## 9 · Handoffs

- Taxonomy addendum (`guide_*` events) → backend (one-file change, pattern established 2026-07-19).
- AnalystGuide component + target registry + script table → eng-mobile (build spec is §2–§4; script table is data, not code — ships as a typed constant so copy edits don't touch logic).
- Voice consistency review of all lines → mkt-writer against the Assistant GM voice doc (The Analyst is its personification).
- Chalkline exception ADR (character art + scrim overlay in product UI) → drafts when Phase 2 ships `guided` as default; experiment arm rides without one.
