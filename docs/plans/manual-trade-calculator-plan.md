# Manual Trade Calculator — Plan (2026-07-02)

*A standalone, **local** trade-value calculator: the user hand-assembles a trade (players on each side) and instantly sees each side's consensus value + a fairness verdict. No league required, no counterparty, no Sleeper send. Planning doc — no code yet. Grounded in `trade-engine-v2`. Companion: [auth-multiplatform-plan-2026-06-11.md](auth-multiplatform-plan-2026-06-11.md) (this is the "manually created trade" surface referenced there as the 4th home for a future Send-in-Sleeper button).*

---

## What "local calculator only" means (the product boundary)

This is deliberately **not** the trade *finder*. The distinction, pinned:

| | Trade **Finder** (exists) | Trade **Calculator** (this) |
|---|---|---|
| Input | your league + leaguemates | **you pick any players by hand** |
| Needs a league? | yes | **no** |
| Counterparty | a real leaguemate / mutual match | **none — hypothetical** |
| Output | ranked mutual-gain suggestions | **value + fairness for the exact trade you built** |
| Sends anywhere? | deep-link / (future) Sleeper API | **no — pure calculation** |

"Local" = **self-contained**: works with zero league context, no other user, no network write. You can value *any* trade — real, hypothetical, "should I do this?" — across the whole player universe. It's the "what's this worth?" tool that every competitor calculator (FantasyCalc, KeepTradeCut, Dynasty Daddy) offers as the front door, which FTF currently lacks as a standalone.

## Two modes (same screen, one toggle)

The calculator ships in **two modes**. Mode A is the standalone/local calculator above. Mode B (added 2026-07-02) makes it **league-aware and two-sided** — FTF's differentiator applied to a hand-built trade.

| | **Mode A — Consensus (local)** | **Mode B — In-league (both teams' rankings)** |
|---|---|---|
| Player pools | whole universe (universal pool) | **your roster** (give) + **a chosen opponent's roster** (receive) |
| Values used | consensus only | **both owners' own rankings** — your board *and* theirs (`member_rankings`) |
| Verdict | fair / lean / unfair (consensus) | **mutual-gain**: do you *and* they each come out ahead by your own boards? (`verdict_type: 'divergence'`) |
| Needs a league? | no | yes (active league) |
| Relationship to the finder | — | a **directed, manual counterpart to the finder** — the finder auto-*generates* mutual-gain trades; Mode B *evaluates the specific one you build* against a specific opponent |

### Mode B — In-league, both teams' rankings

- **Pick an opponent** from the league (`GET /api/league/members` already returns `{user_id, username, has_rankings}`). Show the `has_rankings` flag on each: an opponent *with* real rankings gives the true two-sided **divergence** read; one *without* falls back to a consensus read (see below).
- **Assemble the trade against their roster, from either direction** (the operator's ask — "select players to move away *or* players to receive"): the **Give** side picks from **your** roster, the **Receive** side picks from the **opponent's** roster. You can start from either — pick who you want to *acquire* from their team, or who you want to *move away* from yours; both build the same package.
- **Evaluate with both boards.** Reuse the finder's mutual-gain math ([trade_service.py:10–13](../../backend/trade_service.py)): for the give players use `opp_elo − user_elo` (what you give up vs. what they gain), for the receive players `user_elo − opp_elo` (what you gain vs. what they give up). Output shows **three numbers**: value by *your* board, value by *their* board, and the **mutual-gain / divergence verdict** — i.e., "you both win by your own rankings" (the pitch that actually gets trades accepted). Renders through the same `TradeCard` with `verdict_type: 'divergence'`, identical to a found trade.
- **Consensus fallback (grounded — the engine already does this).** The v2 engine "refuses to run divergence math against fabricated/seeded" rankings and falls back to consensus for opponents with no real `member_rankings` ([trade_service.py:1023–1060](../../backend/trade_service.py)). Mode B inherits that exactly: unranked opponent → consensus verdict + a clear "based on consensus — [opponent] hasn't ranked yet, invite them for a true two-sided read" note (ties into the existing ≥2-ranked-leaguemate cold-start watch item and the invite nudge).

## Guiding principle (the one that matters)

**The calculator's numbers MUST match the finder's.** A calculator that disagrees with FTF's own trade suggestions is worse than none — it destroys trust in both. So this **reuses the authoritative engine**, it does not re-implement valuation:
- `_consensus_packages(give_ids, recv_ids, seed_value)` → each side's package value ([trade_optimizer.py:91](../../backend/trade_optimizer.py)).
- `_fairness_v3(give_ids, recv_ids, seed_value, confidence, fairness_threshold)` → fairness ratio + the range-overlap gate ([trade_optimizer.py:101](../../backend/trade_optimizer.py)).
- `seed_value(player_id)` → per-player consensus value, from the universal pool for the active scoring format (the same `build_universal_pool` × DynastyProcess values the finder uses).

These already produce exactly what a calculator shows — they're just currently only callable *inside* full trade generation. The work is **exposing them**, not writing new math.

## User story + UX

> As a manager, I open **Calculator**, search and tap players onto the **Give** side and the **Receive** side, pick a **scoring format** (1QB PPR / SF TEP), and immediately see: each side's total value, who wins and by how much, and a fair / lean / unfair verdict — updating live as I add/remove players.

Flow:
1. **Format toggle** at top (defaults to the user's `activeFormat` if they have one, else 1QB PPR). Superflex/TEP changes valuations, so it's front-and-center.
2. **Two columns / stacked sections: Give ▸ and Receive ▸.** Each has an "＋ Add player" that opens the **player picker** (search the universal pool by name; show position + team + value). Tap to add; swipe/✕ to remove.
3. **Live verdict panel** (updates on every change): each side's total value (as a `StrengthBar`), the point ratio, and a verdict chip — reuse the finder's `verdict_type`/fairness treatment so it reads identically to a found trade.
4. **Empty/one-sided states:** value one side alone ("this player is worth X"); verdict only appears once both sides have ≥1 player.

## Backend

- **New route `POST /api/trade/evaluate`** — the only backend addition, serving both modes via one optional block.
  - **Mode A (consensus):** body `{ give_player_ids, receive_player_ids, scoring_format }`. Builds `seed_value` from the universal pool for that format (already loaded globally, no session/league needed — see [the Sleeper-less journey note](auth-multiplatform-plan-2026-06-11.md): `/api/players` + the universal pool are open, `_require_session`-free), calls `_consensus_packages` + `_fairness_v3`, returns:
    ```
    { give_value, receive_value, point_ratio, fairness, verdict, confidence,
      per_player: [{ player_id, value }], overlap }
    ```
  - **Mode B (in-league, both boards):** same body **+** `{ league_id, opponent_user_id }` and **authenticated** (needs the session's `user_elo` + the opponent's `member_rankings`). It loads the user's rankings and the opponent's `elo_ratings`, runs the finder's **mutual-gain scoring on the fixed package** (reuse `_generate_for_pair`'s per-package math rather than its generation loop — score the one give/receive the client sent, don't search), and returns the Mode-A fields **plus**:
    ```
    { basis: 'divergence'|'consensus',            # consensus if opponent unranked
      your_value_delta, their_value_delta,        # by each board
      mutual_gain, opponent_has_rankings }
    ```
    When `opponent_has_rankings` is false it degrades to the consensus computation and sets `basis:'consensus'` — mirroring the engine's existing fallback, no special-casing.
- **Auth:** Mode A needs none (pure public-value calc); Mode B requires a session (it reads the caller's + opponent's league rankings). Rate-limit both like the other open/cheap endpoints. **Zero new data or persistence** — reuses the global pool + existing `member_rankings`.
- **Refactor note (small, optional):** `_fairness_v3` currently lives in `trade_optimizer.py` with a `TODO refactor` twin in `trade_service.py`. Exposing it via this endpoint is a good moment to settle it in one shared home so finder + calculator provably share one implementation. Keep it behavior-identical (existing tests cover it).

## Mobile

- **New screen `TradeCalculatorScreen`** with a **mode toggle (Consensus | In-league)**. Reachable from the Rank/Trades area. Mode A needs no league (pre-league onboarding hook — "try valuing a trade before you connect"); Mode toggle only offers **In-league** when the user has an active league.
- **`PlayerPickerSheet`** (there is **no** player search/picker in the app today) — a reusable picker with a **source** prop:
  - Mode A: source = **universal pool** (search all players, filter by position).
  - Mode B: source = a **specific roster** — Give picks from **your** roster, Receive picks from the **opponent's** roster (both already available: `user_roster` + `league_members[].roster_data`). Constrained pickers, not free search.
- **`OpponentPicker` (Mode B only):** list league members from `getLeagueMembers`, each showing the **`has_rankings`** badge so the user knows whether they'll get a two-sided or consensus read (and nudge to invite the unranked ones).
- **Reuse for the verdict:** feed the `/api/trade/evaluate` result into the existing `TradeCardComp` shape (`give_players`/`receive_players`/`fairness`/`verdict_type`) so it renders *identically* to a found trade, plus `StrengthBar` for per-side value bars. Mode B additionally surfaces the **two boards** (your value / their value) + the mutual-gain line — the same treatment the finder uses for a divergence card, so a hand-built trade and a found one read the same.
- **State:** local screen state (mode, opponent, give list, receive list, format). Debounce evaluate ~250ms. No persistence in v1.

## Scope boundaries (v1)

- **Players only in v1; draft picks in v2.** The engine + `TradeCard` already carry `pick_value`, so picks are addable later — but pick valuation + a pick-picker are their own slice. v1 = players.
- **No Sleeper send, no counterparty, no league sync.** Pure calc. (The future Send-in-Sleeper button attaches here as the 4th surface once that feature ships — out of scope now.)
- **IDP / K / DEF:** value only what resolves in the universal pool; anything unvalued shows "—" and is excluded from the package total (same graceful-drop rule the engine already uses).
- **Mode B needs an active league + the opponent's roster** (from the already-loaded league members); if the opponent hasn't ranked, it degrades to a consensus read with an invite nudge (no error). Mode B is authenticated; Mode A is open.

## Server-authoritative vs. fully client-side (a decision to pin)

"Local" could be read as "runs on-device with no server call." **Recommendation: server-authoritative** (the thin `evaluate` endpoint), because:
- `package_value_v2`'s marginal valuation + the range-overlap gate + format weighting are non-trivial server code; re-implementing them in TS invites **divergence from the finder** — the exact failure this feature must avoid.
- The endpoint is cheap (pure in-memory math over the already-loaded pool) and needs no auth/league.

A client-only approximation is *possible* (the app already holds per-player values for ranking) and would work offline, but it would drift from the authoritative math. **Decision: server-authoritative for v1; revisit client-side only if offline calc becomes a requirement** — and if so, extract the valuation into a shared spec both sides implement against, not a hand-port.

## Open questions

1. **Entry point + naming:** standalone "Calculator" tab, or a mode inside the Trades area? (Recommend: an entry in the Rank/Trades hub — it's calculator-shaped, sits with the trade tools, and doubles as a no-league onboarding hook.)
2. **Confidence/ranges (#16):** show the value as a point or a range? The engine carries `confidence`; a range reads more honestly for dynasty. Pin whether v1 shows ranges or a single number + a confidence chip.
3. **Save/share:** v1 is ephemeral. Is a "share this trade" (image via #86 trade-card generator, or a link) wanted in v1, or later?
4. **Picks in v1?** Confirm players-only is acceptable for the first cut.

## Effort + sequencing

| Step | Scope | Risk |
|---|---|---|
| Backend `POST /api/trade/evaluate` — Mode A | Expose `_consensus_packages` + `_fairness_v3` over the global pool; no persistence | **Low** — pure reuse; math exists + tested |
| Backend Mode B branch | Add `league_id`/`opponent_user_id`; score the fixed package with the finder's mutual-gain math + `member_rankings`; consensus fallback | Low-Med — reuses `_generate_for_pair` math, but must score a *fixed* package (skip the search loop) cleanly |
| `PlayerPickerSheet` (mobile) | Reusable picker; universal-pool source (A) + roster source (B) | Low-Med — new but broadly reusable |
| `OpponentPicker` (mobile, Mode B) | League-member list + `has_rankings` badge | Low — data already on client |
| `TradeCalculatorScreen` (mobile) | Mode toggle + Give/Receive + verdict via TradeCard/StrengthBar; two-board display in B | Med — new screen, reuses render + engine |
| (v2) Draft picks | pick picker + pick valuation | Med — separate slice |

**Not gated on anything** — no Sleeper API, no auth, no league. It can ship independently and immediately; it also **strengthens onboarding** (a no-league value tool) and **pre-builds the "manually created trade" surface** the Send-in-Sleeper feature will later attach to. Reasonable to build now, in parallel with the Sleeper-capture spike.

*Code grounding: backend/trade_optimizer.py (`_consensus_packages`, `_fairness_v3`, `package_value_v2`), backend/trade_service.py, mobile/src/shared/types.ts (`TradeCard`), mobile/src/components/{TradeCard,StrengthBar}.tsx, on trade-engine-v2 @ 2026-07-02.*
