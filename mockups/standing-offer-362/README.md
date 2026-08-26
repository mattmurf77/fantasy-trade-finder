# standing-offer-362 — broaden a liked 1-for-1 into a standing offer

**Item:** feedback #362 (jonbonjourvi, TradesHome, v1.15.0, 2026-08-19)
**Question this lab answers:** what does the post-like prompt look like when a user
likes a 1-for-1 where they receive a pick, and how do the resulting years × teams
selections surface to everyone else?
**Status:** in flight — mocked **and specced**. Build contract: [`docs/feedback/items/362-standing-offer/`](../../docs/feedback/items/362-standing-offer/) (`prd.md`, `scope.md`, `lld-delta.md`, `hld-delta.md`). Not built. **§6 item 2 was corrected 2026-08-19 — see "Correction" below before trusting this page.**

Open [`index.html`](index.html).

## The ask

> "If you accept hey I'm willing to trade Malik Willis for a 2028 1st maybe you just add
> a label so the rest of the league knows he's willing to trade for a first. Or a pop up
> after you say yes … I'll sell Willis for a 27 or 28 first but not 29 or maybe like a
> first from any of these rosters but not xyz"

Operator framing (2026-08-19): prompt for **all other teams** and **all other years**;
the two selections are **independent**; completing the flow **prioritizes that card** for
users on the selected teams.

## Frames

| § | Frame | Provenance |
|---|---|---|
| 1 | Today's deck card | **Real capture** — `screens/mobile/trades/populated.png`, 2026-08-10 |
| 2 | The post-like prompt (years pills × teams grid) | Reconstruction |
| 3 | Confirmation toast + `Open to 1sts · '27–'28` chip on your own cards | Reconstruction |
| 4 | What a selected league-mate sees (shipped likes-you card, wider match rule) | Reconstruction |
| 5 | Matches → Standing offers (list / edit / revoke) | Reconstruction |
| 6 | Open questions, trigger conditions, files touched | — |

## Capture provenance (D-056 freeze)

`screens/` is frozen at 2026-08-11. `TradesScreen.tsx` and `TradeCard.tsx` have both moved
since the embedded capture — `f8acd71` (#297/#298/#299/#302 batch) and `586dbba`
(liked-but-unmatched share wiring). §1 embeds the real 2026-08-10 PNG as the screen-identity
anchor; §2–§5 are labelled reconstructions on the page. Per `mockups/CLAUDE.md` interim
posture, no capture run was requested.

## What the lab concluded

**Smaller than it looks on the receiving end.** The likes-you machinery already exists:
`load_recent_league_likes()` (`backend/database.py:4425`) → `_inject_likes_you_cards()`
(`backend/server.py:2807`) → the flare "They're interested" pill (`TradeCard.tsx:363`),
capped at 3 injections. #362 widens the *match rule* feeding that injector. No new
recipient-side surface is needed.

> **Line numbers corrected 2026-08-19.** The three citations above were taken from an older
> tree. Current: `backend/database.py:5228`, `backend/server.py:2931` (impl at `:2943`),
> `mobile/src/components/TradeCard.tsx:375-378`. The conclusion is unchanged and was
> re-verified.

**Bigger than it looks on the sending end.** Three decisions are not obvious and are
called out in §6 rather than resolved here:

1. **Default selection** — pre-checking every team turns the sheet into a confirm and
   lets a tap-through blast the league; source-only pre-check buries the value. Lab
   proposes source-only + a prominent "All" per group.
2. ~~**Asset-class granularity** — "any 1st" isn't one asset; FTF's own 8-tier pick ladder
   prices a rebuilder's 2027 1st far from a contender's. An unbounded offer generates
   cards the sender would refuse. Lab proposes binding to the originating pick's value
   ±1 ladder tier.~~ **CORRECTED 2026-08-19 — the premise is false and the proposal was
   rejected. See "Correction" below.**
3. **Injection cap** — standing-offer cards and organic likes-you cards compete for the
   same 3 slots, and the drop is currently silent.

**Trigger must be narrow** (1-for-1 **and** received asset is a pick **and** no active
offer for that player **and** not dismissed twice this session) or it becomes a nag on a
swipe surface whose whole value is speed.

## Correction — 2026-08-19 (after the build spec was written)

The lab's **asset-class granularity** conclusion (§6, item 2 above) was **wrong on its
facts**, and its ±1-ladder-tier proposal is **rejected**. The original text is struck
through rather than deleted — this lab is read for its reasoning, and a silently-rewritten
premise teaches nothing.

FTF does **not** price a rebuilder's 2027 1st differently from a contender's. In the
shipped model every first in a league carries **exactly the same engine value**:

- **Slot is not a pricing input.** `pick_pool_value` prices every league pick at the
  generic ladder's **Mid** rung of its round (`backend/pick_values.py:264-286`). D-090
  re-examined this and did not overturn it; per-slot pricing is logged **unbuilt** as
  Q-023. Slot labels are display-only.
- **Year is not a pricing input for firsts.** D-079 set round-1 year decay to **1.00**
  (`backend/pick_values.py:159-163`, knob `pick_year_decay_r1`). A 2029 1st prices
  identically to a 2026 1st.

A ±1-tier band over a set of identical values admits everything — there is nothing for it
to be relative to. **No value gate is built.** The offer is bounded by round, by the
seasons and teams the user selects, and by the pre-existing D-055 user-gain floor on the
receiving side, which standing-offer cards inherit by reusing the injector loop.

Revisit only if Q-023 is ever built. Ruling recorded as **D-362-1**; build contract in
[`docs/feedback/items/362-standing-offer/`](../../docs/feedback/items/362-standing-offer/).

The other two open questions were also ruled, and the lab's instincts on both held up:
**default selection** ships as **source-only** (operator-confirmed 2026-08-19), and the
**injection cap** becomes one `model_config` knob (`standing_offer_inject_cap`, default 2)
rather than a second hardcoded constant.

## Gate posture

New `standing_offers` table + new routes + new flag (`trade.standing_offers`) + new
analytics events. Per CLAUDE.md §Feature gates this is the **bright line** — not express
lane, and it needs the full scope block (`docs/templates/feature-scope.md`) before any
code is written.
