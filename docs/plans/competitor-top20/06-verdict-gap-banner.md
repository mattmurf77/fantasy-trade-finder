# 6. Verdict & gap quantification on trade cards

> Tier 1 · #6 · ENH · Effort S · Sources: DD (Dynasty Daddy verdict banner), OP (advocate framing)

## Summary

Every trade card today communicates *scores* (a fairness meter, a composite). It should communicate a *position*: a one-line verdict banner that names the favored side, quantifies the gap in value units, and suggests the fix — "Fair — within 6%, edge to you" / "Favors them by ~480 — ask for a sweetener." Dynasty Daddy's calculator banner ("Favors DynastyDaddyFF — Add a player with 1,478 value to even trade → View in Player Comparison") is the precedent; FTF's twist is tone. Every competitor referees fairness; FTF is the user's agent, so the copy says "you could ask for more," never "this trade is unfair."

This is the smallest Tier 1 item, but it is not purely client-side: the backlog assumed "numbers already in the trade payload," and reading `trade_card_to_dict` (backend/server.py:3195) shows that's only partly true. `fairness_score` (0–1 consensus package-value ratio) and the v3 `sweetener` annotation are serialized; the per-side package values needed to print "~480" exist at scoring time inside `trade_service.py` (`package_value_v2`) but are thrown away before serialization. So the work is: serialize two numbers + a computed verdict object on the backend, then render one banner component per client from a shared copy matrix. Ships with #4 (fairness control + ask-for-more), whose "ask for more" candidates become the banner's suggested-fix link.

## PRD

### Problem & user story

> As a user reading a trade card, I can see a 78% fairness meter but I can't answer the three questions I actually have: *who wins this, by how much, and what should I do about it?* I want the card to take my side and tell me.

The fairness meter forces mental math and reads as referee output. Users screenshot cards into league chats; a named verdict is the line that gets quoted.

### Goals / Non-goals

**Goals**
- Every trade card (web, mobile, and the #19 extension overlay) carries a verdict banner: favored side + quantified gap + suggested action.
- Advocate tone throughout — copy is written from the user's corner.
- Verdict logic lives server-side once; clients render, never recompute (cross-client-invariants rule).

**Non-goals**
- No change to engine scoring, ranking, or the fairness gate (that's #4).
- No new sweetener search — reuse the v3 sweetener annotation and #4's ask-for-more candidates when present.
- Not a replacement for the fairness meter; the meter stays (it's the "show your work" detail under the verdict).

### Functional requirements

- **FR1** Backend serializes `give_value`, `receive_value` (consensus-unit package values, the same numbers fairness is computed from), and a `verdict` object on every card.
- **FR2** `verdict` contains: `band` (`fair` | `slight` | `lopsided`), `favored` (`you` | `them` | `even`), `gap_value` (absolute, consensus units, rounded to nearest 10), `gap_pct`, and optional `fix` (`{type: "ask_sweetener"|"add_sweetener", player_id?}`).
- **FR3** Band thresholds come from `model_config` keys (`verdict_fair_max_gap_pct`, default 0.08; `verdict_lopsided_min_gap_pct`, default 0.20) — tunable without deploy, documented in config-reference.md.
- **FR4** Clients render the banner from the copy matrix below, keyed by `band × favored`. No client-side threshold math.
- **FR5** `basis: "consensus"` cards prepend the existing "Fair-value idea" framing; divergence cards may append the dual-lens line (see UX notes).
- **FR6** When `verdict.fix` references a sweetener candidate, the banner's action chip deep-links to that player row (and, once #3 ships, opens the swap builder).
- **FR7** Banner presence is flag-gated; payload additions are unconditional (additive fields are safe per the existing serializer convention).

### UX notes (per client)

**Copy matrix** (the spec — `~N` is `gap_value`; band × favored):

| | **Favors you** | **Even / fair** | **Favors them** |
|---|---|---|---|
| **Fair** (gap ≤ 8%) | "Fair — within {pct}%, edge to you. Send it." | "Dead even by league values. Clean send." | "Fair — within {pct}%. Worth a nudge for a kicker anyway." |
| **Slight** (8–20%) | "Leans your way by ~{N}. Send it before they do the math." | — | "Favors them by ~{N} — ask for a sweetener." [+ fix chip: "Ask for {player}"] |
| **Lopsided** (>20%) | "Heavily favors you (~{N}). Expect a decline — add a kicker if you really want him." [+ fix chip] | — | "Favors them by ~{N}. Don't send this without getting more back." |

Tone rules: verbs aimed at the user's next move; never "unfair," never moralizing; "lopsided × you" is honest about acceptance odds (that's advocacy too — wasted offers cost goodwill).

- **Web** (`web/js` trade rendering): banner strip at the top of the card, color by band (reuse tier color tokens — green/amber/red family; add to cross-client-invariants.md).
- **Mobile** (`mobile/src/.../TradeCard.tsx`): same strip above the give/receive columns; fix chip is tappable.
- **Extension** (#19): the overlay renders the identical banner from the same `verdict` object — this doc's copy matrix is the single source.
- Dual-lens footnote on divergence-basis cards (info icon, not inline): "Gap measured in league consensus values. By *your* rankings, both sides still gain — that's why we found it." This prevents the banner from appearing to contradict the mutual-gain pitch.

### Success metrics

- Like-rate (and like→match conversion) on cards with banners vs. the pre-ship baseline, via existing `/api/admin/engine-metrics`.
- Fix-chip tap-through rate (new `verdict_fix_tapped` event via `record_event`).
- Qualitative: "why this trade?" feedback notes (app_feedback) mentioning confusion should drop.

### Acceptance criteria

- [ ] `give_value` / `receive_value` / `verdict` present on every card from `/api/trades`, `/api/trades/status`, `/api/trades/liked`.
- [ ] Verdict bands match `model_config` thresholds exactly (unit test on the classifier function).
- [ ] All 7 copy-matrix cells render correctly on web + mobile (storybook/fixture pass).
- [ ] Consensus-basis cards show the "Fair-value idea" frame; divergence cards show the dual-lens footnote.
- [ ] Fix chip appears only when a sweetener/ask-for-more candidate exists; tap is event-logged.
- [ ] docs updated: api-reference.md (card shape), config-reference.md (new keys), cross-client-invariants.md (band thresholds, enum strings, banner colors).

## HLD

### Components touched

- `backend/trade_service.py` — retain per-side `package_value_v2` outputs on the `TradeCard` object (fields exist transiently during scoring; persist them onto the card).
- `backend/server.py` — `trade_card_to_dict`: serialize the two values + computed `verdict` (one pure function, `_classify_verdict(give_value, receive_value, sweetener, ask_for_more)`).
- `web/js` trade card renderer; `mobile/src` TradeCard component; (later) `extension/` overlay (#19) — render-only consumers.

### Data flow

Engine scores candidate → card already carries consensus package values internally → serializer computes verdict from the two values + thresholds → clients map `band × favored` to copy. No new queries, no per-request engine work; the classifier is arithmetic on numbers already in hand.

### Flags & config interplay

- New flag `trade.verdict_banner` in `config/features.json`, consumed by clients via `/api/feature-flags` (banner hidden when off; payload fields ship regardless).
- `model_config`: `verdict_fair_max_gap_pct` (0.08), `verdict_lopsided_min_gap_pct` (0.20) — admin-tunable via existing `PUT /api/admin/config/<key>`.
- Interplay with #4: when the user's `fairness_threshold` is loosened, more `slight`/`lopsided` cards surface — the banner is what makes that loosening safe to use.

## LLD

### API changes (routes + example payloads)

No new routes. Additive fields on the trade card object:

```json
{
  "trade_id": "a1b2c3d4",
  "fairness_score": 0.91,
  "give_value": 5240,
  "receive_value": 4760,
  "verdict": {
    "band": "slight",
    "favored": "them",
    "gap_value": 480,
    "gap_pct": 9.2,
    "fix": { "type": "ask_sweetener", "player_id": "8136" }
  }
}
```

`favored` is computed from the user's perspective: `receive_value > give_value` → `you`. `even` when `gap_pct` < 1.

### Schema changes

None. (Thresholds live in existing `model_config`; events in existing `user_events`.)

### Client changes

- `web/js/` trade card module: `renderVerdictBanner(card.verdict)` + copy table; CSS band classes in `web/css`.
- `mobile/src/.../TradeCard.tsx` + `mobile/src/shared/types.ts` (extend the TradeCard type); copy table in a shared `verdictCopy.ts`.
- `extension/`: none now; #19 imports the same copy table.

### Sleeper integration notes

None — fully internal. No read-only-boundary exposure.

### Rollout

Flag `trade.verdict_banner`, default **false**; flip after fixture QA on both clients. Payload fields ship dark (additive, ignored by old clients per existing serializer conventions).

### Open questions

1. Should gap be displayed in consensus units (cross-user-comparable, matches fairness math) or the user's own value space (matches "advocate" framing)? Proposal: consensus units with the dual-lens footnote; revisit if feedback says the number feels alien.
2. Rounding/units copy: raw "~480" vs. humanized "~a late 2nd's worth"? Start raw; humanized variant is a copy-only follow-up once #15's pick values give us the conversion.
3. Does the legacy engine path (flag-off fallback) get banners? Proposal: yes — it has package values too — but verify field availability before promising.

## Dependencies & sequencing

- **Ships with #4** (fairness control + ask-for-more): #4 supplies the `ask_sweetener` candidates; the banner is #4's primary UI surface. Backlog says "pair, ship together."
- **Feeds #19** (extension overlay) and #27 (open calculator): both render this exact `verdict` object — build the classifier as a pure function so the rescore endpoint (#3, `POST /api/trades/rescore` per 03-swap-player-counter.md) returns it too.
- **Feeds #12**: the share-card image and link page print the verdict line as the headline.
- No dependency on #1/#8; verdicts work identically on consensus-basis cards.
