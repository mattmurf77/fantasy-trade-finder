import { api } from './client';
import type { TradeCard, TradeJobSnapshot, TradeMatch, AwaitingTrade, Player } from '../shared/types';
import type { CalcGap } from './calc';

export interface GenerateBody {
  league_id: string;
  fairness_threshold?: number;      // 0.5 – 1.0
  pinned_give_players?: string[];
  // FB-47 finder targeting: specific players the user wants to ACQUIRE.
  // Honored by the backend only when flag trade.finder_targeting is on;
  // every returned card's receive side then includes at least one of them.
  pinned_receive_players?: string[];
  // #174 package constraint: 'all' ⇒ every returned card's give side must
  // include EVERY pinned give player ("trade this package away"). Absent
  // or 'any' keeps the historical ≥1 semantics. Only meaningful alongside
  // pinned_give_players (the server normalizes it away otherwise).
  pinned_give_mode?: 'all' | 'any';
  // FB #156 (Trade-Finding Hub, "Specific Team" mode): scope generation to a
  // single league-mate. Absent ⇒ the full league-wide sweep. Opponent-scoped
  // jobs bypass the shared server cache (like pinned jobs).
  opponent_user_id?: string;
  // Onboarding item 7: skip the server's complete-fresh job cache (a Quick
  // Set save changes the board but not the cache key). Running jobs are
  // still shared server-side.
  force?: boolean;
  // #172 (flag trades.intent_modes): the SHAPE of trade the user wants —
  // "I want to consolidate / tier up / tier down". Honored by the backend
  // only when the flag is on; a post-generation filter over the deck. Also
  // part of the server's cache-freshness key, so a changed intent always
  // regenerates rather than serving a deck filtered for a different shape.
  trade_intent?: 'consolidate' | 'tier_up' | 'tier_down';
}

// NOTE: backend returns BARE ARRAYS for the trade endpoints — not
// `{trades: [...]}` / `{matches: [...]}` envelopes. The wrappers below
// normalize either shape so a future backend cleanup that adds an envelope
// won't break us either.

function asArray<T>(res: any): T[] {
  if (Array.isArray(res)) return res as T[];
  if (Array.isArray(res?.trades)) return res.trades as T[];
  if (Array.isArray(res?.matches)) return res.matches as T[];
  return [];
}

// ── Trade-card normalizer ────────────────────────────────────────────
// Backend (server.py:trade_card_to_dict) returns:
//   { trade_id, league_id, target_username, give[], receive[],
//     mismatch_score, fairness_score, composite_score, basis,
//     decision, expires_at, likes_you?, sweetener?, reasons? }
// Frontend (shared/types#TradeCard) wants:
//   { trade_id, league_id, give_player_ids[], receive_player_ids[],
//     give_players[], receive_players[], opponent_user_id,
//     opponent_username, match_score, fairness, reasons? }
// This adapter bridges the two so screen code never has to know about
// the legacy field names.
function normalizeTradeCard(raw: any): TradeCard {
  const give: Player[]    = Array.isArray(raw?.give_players) ? raw.give_players
                          : Array.isArray(raw?.give)         ? raw.give
                          : [];
  const receive: Player[] = Array.isArray(raw?.receive_players) ? raw.receive_players
                          : Array.isArray(raw?.receive)         ? raw.receive
                          : [];
  // Backend's `mismatch_score` is the human-facing "deal compellingness"
  // value — same field the legacy web reads. `match_score` was the type
  // we picked when scaffolding; keep that name internal.
  //
  // The web renders the raw mismatch as a number (e.g. "Match score 247"),
  // but the mobile UI treats `match_score` as a 0–100 percentage and feeds
  // it to a clamped StrengthBar. Without scaling, anything with a raw
  // mismatch ≥ 100 (i.e. essentially every surfaced trade — threshold is
  // 40 and good deals are 100–300+) renders as a maxed-out 100% bar.
  // Scale by /300 to match the same ceiling the backend's composite-score
  // math already uses (trade_service.py: `min(mismatch, 300) / 300`).
  const matchScore =
    typeof raw?.match_score    === 'number' ? raw.match_score
  : typeof raw?.mismatch_score === 'number' ? Math.min(100, Math.max(0, (raw.mismatch_score / 300) * 100))
  : 0;
  // `fairness_score` (0–1) is always serialized by the v2 backend; keep
  // the defensive fallback so cached/legacy snapshots without it still
  // render (UI hides the row when undefined).
  const fairness =
    typeof raw?.fairness       === 'number' ? raw.fairness
  : typeof raw?.fairness_score === 'number' ? raw.fairness_score
  : undefined as unknown as number;
  // v2 sweetener marker — { player_id, side } identifying a low-value
  // player (already present in give/receive) added to balance the deal.
  // Strictly validated so a malformed payload degrades to "no callout".
  const rawSweetener = raw?.sweetener;
  const sweetener =
    rawSweetener
    && typeof rawSweetener.player_id === 'string'
    && (rawSweetener.side === 'give' || rawSweetener.side === 'receive')
      ? { playerId: rawSweetener.player_id, side: rawSweetener.side as 'give' | 'receive' }
      : undefined;
  // FB-47 — counterparty positional fit (0–1). Backend serializes it only
  // when trade.finder_targeting is on AND the user expressed targets;
  // undefined hides the fit line entirely.
  const partnerFit =
    typeof raw?.partner_fit === 'number' ? raw.partner_fit : undefined;
  // Structured match context — only the string-array fields the fit-line
  // copy reads are kept; a malformed payload degrades to undefined.
  const rawCtx = raw?.match_context;
  const matchContext =
    rawCtx && typeof rawCtx === 'object'
      ? {
          user_needs: Array.isArray(rawCtx.user_needs)
            ? rawCtx.user_needs.filter((x: unknown) => typeof x === 'string')
            : undefined,
          opponent_surplus: Array.isArray(rawCtx.opponent_surplus)
            ? rawCtx.opponent_surplus.filter((x: unknown) => typeof x === 'string')
            : undefined,
        }
      : undefined;
  // Phase-2 lane — only the two known enum values pass; anything else
  // (missing, typo, legacy) degrades to undefined and hides the lane UI.
  const lane: 'window' | 'value' | undefined =
    raw?.lane === 'window' || raw?.lane === 'value' ? raw.lane : undefined;
  // Phase-2 fit premium — validated so a malformed payload degrades to
  // "no badge" rather than rendering bogus numbers.
  const rawFitPremium = raw?.fit_premium;
  const fitPremium =
    rawFitPremium && typeof rawFitPremium.value_paid === 'number'
      ? {
          value_paid: rawFitPremium.value_paid,
          position:
            typeof rawFitPremium.position === 'string'
              ? rawFitPremium.position
              : undefined,
        }
      : undefined;
  // Phase-2 aggression variant — opaque string, passed through as-is.
  const aggressionVariant =
    typeof raw?.aggression_variant === 'string' ? raw.aggression_variant : undefined;
  // Pick-denominated value verdict (feedback #157 value-bar). Backend stamps
  // give_value/receive_value/favors/gap on every generated card (same shape as
  // /api/trade/evaluate); the deck renders TradeValueBar off these. Validated
  // defensively so a legacy/echo-rebuilt payload without them degrades to
  // "no bar" (TradeCard gates on give_value/receive_value being present).
  const giveValue =
    typeof raw?.give_value === 'number' ? raw.give_value : undefined;
  const receiveValue =
    typeof raw?.receive_value === 'number' ? raw.receive_value : undefined;
  const favors: 'give' | 'receive' | 'even' | null | undefined =
    raw?.favors === 'give' || raw?.favors === 'receive' || raw?.favors === 'even'
      ? raw.favors
      : raw?.favors === null
        ? null
        : undefined;
  // gap is the CalcGap shape or null; passed straight to TradeValueBar which
  // already renders correctly with gap === null. Only the object/null cases
  // are accepted; anything else degrades to undefined.
  const gap =
    raw?.gap && typeof raw.gap === 'object'
      ? (raw.gap as CalcGap)
      : raw?.gap === null
        ? null
        : undefined;

  return {
    trade_id:           String(raw?.trade_id ?? ''),
    league_id:          String(raw?.league_id ?? ''),
    give_players:       give,
    receive_players:    receive,
    give_player_ids:    give.map((p) => p.id),
    receive_player_ids: receive.map((p) => p.id),
    opponent_user_id:   String(raw?.opponent_user_id ?? raw?.target_user_id ?? ''),
    opponent_username:  String(raw?.opponent_username ?? raw?.target_username ?? ''),
    match_score:        matchScore,
    fairness:           fairness,
    reasons:            Array.isArray(raw?.reasons) ? raw.reasons : undefined,
    // Backend injects `real_opponent` on streaming snapshots (generate +
    // status). Coerce to a strict boolean if present; leave undefined so
    // the card can distinguish "unknown" from a real "false" in legacy
    // response shapes that don't include the field.
    real_opponent:      typeof raw?.real_opponent === 'boolean' ? raw.real_opponent : undefined,
    // v2 fields — all defensively defaulted so legacy payloads behave
    // exactly as before:
    //   basis     — 'consensus' only when explicitly sent; anything else
    //               (missing, typo, legacy) is 'divergence'.
    //   likesYou  — backend serializes `likes_you` only when true.
    //   sweetener — validated above; undefined when absent/malformed.
    basis:              raw?.basis === 'consensus' ? 'consensus' : 'divergence',
    likesYou:           raw?.likes_you === true,
    // #362 — standing-offer provenance. Same posture as `likesYou`: the
    // server serializes each key only when set, so flag-off payloads carry
    // neither and both degrade to undefined.
    standingOfferReason: typeof raw?.standing_offer_reason === 'string'
      ? raw.standing_offer_reason
      : undefined,
    standingOfferMine:
      raw?.standing_offer_mine
      && typeof raw.standing_offer_mine === 'object'
      && Number.isFinite(Number(raw.standing_offer_mine.round))
      && Array.isArray(raw.standing_offer_mine.seasons)
        ? {
            round: Number(raw.standing_offer_mine.round),
            seasons: raw.standing_offer_mine.seasons
              .map((s: any) => Number(s))
              .filter((s: number) => Number.isFinite(s)),
          }
        : undefined,
    // F1 signal spine (flag deck.signal_v2): server sends impression_id per
    // card only when the flag is on; absent → undefined and nothing changes.
    impression_id:      typeof raw?.impression_id === 'string' ? raw.impression_id : undefined,
    // F3 retest marker (serialized only when true) + F7's wildcard marker
    // (flag deck.exploration, serialized only when true) — both position-
    // locked by F4's session re-rank; wildcard also drives TradeCard's
    // "WILDCARD — OUTSIDE YOUR USUAL" provenance chip.
    retest:             raw?.retest === true ? true : undefined,
    wildcard:           raw?.wildcard === true ? true : undefined,
    sweetener,
    partner_fit:        partnerFit,
    match_context:      matchContext,
    lane,
    fitPremium,
    aggressionVariant,
    give_value:         giveValue,
    receive_value:      receiveValue,
    favors,
    gap,
  };
}

// Backend returns a TradeJobSnapshot for both /api/trades/generate and
// /api/trades/status. Both run cards through the same normalizer so
// downstream code keeps using the unified TradeCard shape.
function normalizeJobSnapshot(raw: any): TradeJobSnapshot {
  const cards = Array.isArray(raw?.cards) ? raw.cards.map(normalizeTradeCard) : [];
  // F3 (flag deck.fatigue) — additive honoring note; validated defensively so
  // a malformed payload degrades to "no note" (banner hidden).
  const rawNote = raw?.suppression_note;
  const suppressionNote =
    rawNote && typeof rawNote.count === 'number' && rawNote.count > 0
      ? {
          count: rawNote.count,
          latest_declined_at:
            typeof rawNote.latest_declined_at === 'string'
              ? rawNote.latest_declined_at
              : null,
        }
      : undefined;
  // F9 (flag deck.first_session) — additive first-deck marker + board-
  // refreshed header payload; both validated defensively so a malformed
  // payload degrades to "absent" (nothing renders / no events fire).
  const rawBr = raw?.board_refresh;
  const boardRefresh =
    rawBr && rawBr.updated_since_last_deck === true
      ? {
          updated_since_last_deck: true as const,
          ranked_player_count:
            typeof rawBr.ranked_player_count === 'number'
              ? rawBr.ranked_player_count
              : undefined,
          basis:
            rawBr.basis === 'personal' || rawBr.basis === 'consensus'
              ? (rawBr.basis as 'personal' | 'consensus')
              : undefined,
        }
      : undefined;
  return {
    job_id:          String(raw?.job_id ?? ''),
    status:          raw?.status === 'complete' ? 'complete'
                   : raw?.status === 'error'    ? 'error'
                   : 'running',
    cards,
    opponents_done:  Number(raw?.opponents_done ?? 0)  || 0,
    opponents_total: Number(raw?.opponents_total ?? 0) || 0,
    error:           raw?.error ?? null,
    ...(suppressionNote ? { suppression_note: suppressionNote } : {}),
    ...(raw?.first_deck === true ? { first_deck: true } : {}),
    ...(boardRefresh ? { board_refresh: boardRefresh } : {}),
  };
}

// POST /api/trades/generate — kicks off trade discovery for the active league.
// Returns a job snapshot; if status==='running', poll getTradeStatus(job_id).
export async function generateTrades(body: GenerateBody): Promise<TradeJobSnapshot> {
  const res = await api.post<any>('/api/trades/generate', body);
  return normalizeJobSnapshot(res);
}

// GET /api/trades/status?job_id=X — cheap dict lookup; the request thread
// just reads the in-memory job state and returns the current cards.
export async function getTradeStatus(jobId: string): Promise<TradeJobSnapshot> {
  const res = await api.get<any>(
    `/api/trades/status?job_id=${encodeURIComponent(jobId)}`,
  );
  return normalizeJobSnapshot(res);
}

// ── Asset-centric trade ideas (#172/#189 follow-up, flag trade.asset_ideas) ──
// POST /api/trades/asset-ideas — grouped Upgrade / Lateral / Downgrade ideas
// for ONE pinned asset (player or pick), consensus basis, synchronous.
// direction 'give' = pin leaves the roster (ideas = the return);
// direction 'receive' = pin is acquired (ideas = what the user gives).

export interface AssetIdea {
  counterparty_user_id: string;
  counterparty_username: string;
  give: Player[];
  receive: Player[];
  give_player_ids: string[];
  receive_player_ids: string[];
  give_value: number;
  receive_value: number;
  difference: number;         // receive − give (consensus); + = user ahead
  fairness: number;           // 0–1 min/max package ratio
  relaxed?: boolean;          // #189 convention: outside the strict band
  relaxed_reason?: string;
  // #216 featured-trade window — pick-denominated verdict per idea, same
  // shape as evaluate / deck cards (server single-sources the construction).
  // Undefined on old servers ⇒ the window's TradeValueBar hides.
  favors?: 'give' | 'receive' | 'even' | null;
  gap?: CalcGap | null;
  // #384 W6-B — set only by POST /api/trades/fair-packages, whose ideas are
  // DECK CARDS rather than window decoration. `trade_id` is the server's
  // deterministic `fairpk_…`, which is the row key a swipe / queue / flag on
  // the card reconstructs under (FB-46); `basis` makes the consensus caveat
  // render. Asset ideas carry neither, so their cards are unchanged.
  trade_id?: string;
  basis?: 'divergence' | 'consensus';
}

export interface AssetIdeasResponse {
  asset: Player | null;
  direction: 'give' | 'receive';
  basis: 'consensus';
  groups: {
    upgrade: AssetIdea[];
    lateral: AssetIdea[];
    downgrade: AssetIdea[];
  };
}

function normalizeAssetIdea(raw: any): AssetIdea {
  const give: Player[] = Array.isArray(raw?.give) ? raw.give : [];
  const receive: Player[] = Array.isArray(raw?.receive) ? raw.receive : [];
  return {
    counterparty_user_id: String(raw?.counterparty_user_id ?? ''),
    counterparty_username: String(raw?.counterparty_username ?? ''),
    give,
    receive,
    give_player_ids: Array.isArray(raw?.give_player_ids)
      ? raw.give_player_ids.map(String)
      : give.map((p) => p.id),
    receive_player_ids: Array.isArray(raw?.receive_player_ids)
      ? raw.receive_player_ids.map(String)
      : receive.map((p) => p.id),
    give_value: typeof raw?.give_value === 'number' ? raw.give_value : 0,
    receive_value: typeof raw?.receive_value === 'number' ? raw.receive_value : 0,
    difference: typeof raw?.difference === 'number' ? raw.difference : 0,
    fairness: typeof raw?.fairness === 'number' ? raw.fairness : 0,
    ...(raw?.relaxed === true
      ? {
          relaxed: true,
          ...(typeof raw?.relaxed_reason === 'string'
            ? { relaxed_reason: raw.relaxed_reason }
            : {}),
        }
      : {}),
    // #216 — validated like normalizeTradeCard's favors/gap so an old
    // server (fields absent) degrades to undefined and the featured
    // window's value bar simply hides.
    ...(raw?.favors === 'give' || raw?.favors === 'receive' || raw?.favors === 'even'
      ? { favors: raw.favors as 'give' | 'receive' | 'even' }
      : raw?.favors === null
        ? { favors: null }
        : {}),
    ...(raw?.gap && typeof raw.gap === 'object'
      ? { gap: raw.gap as CalcGap }
      : raw?.gap === null
        ? { gap: null }
        : {}),
    // #384 W6-B — fair packages only. Validated rather than coerced so an
    // asset-ideas payload (which carries neither) stays byte-identical.
    ...(typeof raw?.trade_id === 'string' && raw.trade_id
      ? { trade_id: raw.trade_id }
      : {}),
    ...(raw?.basis === 'consensus' || raw?.basis === 'divergence'
      ? { basis: raw.basis as 'consensus' | 'divergence' }
      : {}),
  };
}

export async function fetchAssetIdeas(body: {
  league_id: string;
  asset_id: string;
  direction: 'give' | 'receive';
  fairness_threshold?: number;
  // #250 — Specific Team mode: scope the sweep to this league-mate so every
  // idea's counterparty (and its acquire side) is that team.
  opponent_user_id?: string;
  // #403 W2, widened by rev-3 (rev3-spec.md §2) — when present, constrains
  // ALL THREE groups: the lateral swap position, and the incoming headline
  // piece's position for upgrade/downgrade. Uppercase tokens from
  // {QB,RB,WR,TE}; the server 400s anything else, including "PICK". The
  // key must be OMITTED — never sent as undefined or [] — when the user
  // has selected nothing, so the no-selection request body stays
  // byte-identical to today over the wire (lld-delta.md §2.4; `api.post`
  // forwards this object verbatim; absent ⇒ all three groups behave
  // exactly as before rev-3).
  swap_positions?: string[];
  // #402/#403 rev-3 (rev3-spec.md §3) — how wide the `lateral` group's
  // pool is. "band" (the default when omitted — every pre-rev-3 caller,
  // including the single-pin panel, keeps it by not sending the field) =
  // the ±10% fairness band + the #108 gain gate, exactly as today. "tier"
  // = every asset in the pinned asset's tier of the 8-tier valuation
  // ladder (`tier_for_elo` / tier_config.json); the band and the gain gate
  // do NOT apply. The shop client ALWAYS sends "tier" (operator ruling
  // R-2026-08-28b-4: "present all players in the same tier of pick
  // valuations rather than the fairness gate").
  lateral_scope?: 'band' | 'tier';
}): Promise<AssetIdeasResponse> {
  const res = await api.post<any>('/api/trades/asset-ideas', body);
  const g = res?.groups ?? {};
  const norm = (arr: any) =>
    Array.isArray(arr) ? arr.map(normalizeAssetIdea) : [];
  return {
    asset: res?.asset ?? null,
    direction: res?.direction === 'receive' ? 'receive' : 'give',
    basis: 'consensus',
    groups: {
      upgrade: norm(g.upgrade),
      lateral: norm(g.lateral),
      downgrade: norm(g.downgrade),
    },
  };
}

// ── #384 W6-B — fair packages for a hand-built give side ─────────────────
//
// D-153, operator: "this type of request shouldn't go through our models. It
// should be a much simpler set of cards solving for fairness only." So Find a
// Trade with a FILLED canvas calls this — one synchronous sweep, no job, no
// polling — and Find a Trade with an EMPTY canvas still runs the model deck.
//
// The give side is an ANCHOR: every idea gives away exactly `givePlayerIds`.
// `receivePlayerIds` is a PREFERENCE — ideas containing all of them sort
// first, ideas that cannot are still returned, which is what stops a canvas
// pick outside `picks_pool_cap` from emptying the deck.
//
// The ideas are DECK CARDS (`ideas.map(ideaToCard)` → `setDeck`), which is why
// each carries a server-minted `trade_id`: the deck's swipe / queue / flag
// routes all reconstruct an unknown card from the echoed context (FB-46) and
// key the row under that id.

export interface FairPackagesResult {
  basis: 'consensus';
  anchor: {
    give_player_ids: string[];
    receive_player_ids: string[];
    opponent_user_id: string | null;
  };
  ideas: AssetIdea[];
  /** #189 — the whole list came from the widened fairness band. */
  relaxed: boolean;
  /** Present only alongside an EMPTY list: `give_untouchable` |
   *  `unknown_asset` | `no_partner` | `unknown_league`. */
  reason?: string;
}

export async function getFairPackages(body: {
  league_id: string;
  give_player_ids: string[];
  receive_player_ids?: string[];
  opponent_user_id?: string;
  fairness_threshold?: number;
}): Promise<FairPackagesResult> {
  const res = await api.post<any>('/api/trades/fair-packages', body);
  const anchor = res?.anchor ?? {};
  return {
    basis: 'consensus',
    anchor: {
      give_player_ids: Array.isArray(anchor.give_player_ids)
        ? anchor.give_player_ids.map(String)
        : body.give_player_ids,
      receive_player_ids: Array.isArray(anchor.receive_player_ids)
        ? anchor.receive_player_ids.map(String)
        : body.receive_player_ids ?? [],
      opponent_user_id: anchor.opponent_user_id
        ? String(anchor.opponent_user_id)
        : null,
    },
    ideas: Array.isArray(res?.ideas) ? res.ideas.map(normalizeAssetIdea) : [],
    relaxed: res?.relaxed === true,
    ...(typeof res?.reason === 'string' ? { reason: res.reason } : {}),
  };
}

// GET /api/trades?league_id=X — cached most-recent generated trades.
// Separate from the streaming job snapshots; this is the long-tail "show
// me undecided cards" view used outside the Find-a-Trade flow.
export async function getRecentTrades(leagueId: string): Promise<TradeCard[]> {
  const res = await api.get<any>(
    `/api/trades?league_id=${encodeURIComponent(leagueId)}`,
  );
  return asArray<any>(res).map(normalizeTradeCard);
}

// F1 signal spine (flag deck.signal_v2) — optional per-disposition signal
// fields, sent ONLY when TradesScreen passes them (flag on AND the served
// card carried an impression_id). Additive body fields on the existing
// endpoint; old servers ignore them.
export interface SwipeSignal {
  impression_id: string;
  dwell_ms?: number;          // card fronted → disposition, bg-paused, ≤120s
  detail_expanded?: boolean;  // opened player menu / swap sheet / keep-side
  calc_opened?: boolean;      // edit-in-calculator (#190) from this card
}

// Propose-label spine — which surface produced the disposition. Server
// validates against the same closed enum (server._SWIPE_SURFACES) and
// records it into the server-fired trade_proposed / match_swiped props as
// `source`; omitted/unknown records null. Cross-client value set —
// docs/cross-client-invariants.md.
export type SwipeSurface = 'deck' | 'browse' | 'today' | 'shop';

// POST /api/trades/swipe  body: { trade_id, decision: 'like' | 'pass' }
export async function swipeTrade(
  card: TradeCard,
  decision: 'like' | 'pass',
  signal?: SwipeSignal,
  surface?: SwipeSurface,
) {
  // FB-46: echo the card context so the server can reconstruct the card
  // when its in-memory deck was lost (Render deploy / session re-init)
  // instead of failing every swipe with "Unknown trade_id".
  return api.post<any>('/api/trades/swipe', {
    trade_id:           card.trade_id,
    decision,
    league_id:          card.league_id || undefined,
    give_player_ids:    card.give_player_ids,
    receive_player_ids: card.receive_player_ids,
    target_user_id:     card.opponent_user_id || undefined,
    target_username:    card.opponent_username || undefined,
    ...(surface ? { surface } : {}),
    ...(signal ?? {}),
  });
}

// POST /api/trades/flag — "this is a bad trade" (feedback #85). Distinct
// from a pass: a flag means "the engine got this one wrong" and lands in a
// review table the owner uses to iterate on the trade logic. Server-side
// idempotent per (user, league, give set, receive set), so re-flagging the
// same package is safe. Card context + telemetry are echoed so the server
// can persist a reviewable snapshot even after its in-memory deck is gone.
export async function flagBadTrade(
  card: TradeCard,
  reason?: string,
  // F1 (deck.signal_v2): joins the flag to its deck_impressions row as a
  // `not_interested` outcome. Only passed when the flag is on.
  impressionId?: string,
) {
  return api.post<any>('/api/trades/flag', {
    trade_id:           card.trade_id,
    league_id:          card.league_id || undefined,
    give_player_ids:    card.give_player_ids,
    receive_player_ids: card.receive_player_ids,
    target_user_id:     card.opponent_user_id || undefined,
    target_username:    card.opponent_username || undefined,
    fairness_score:     typeof card.fairness === 'number' ? card.fairness : undefined,
    basis:              card.basis,
    reason:             reason || undefined,
    impression_id:      impressionId || undefined,
  });
}

// ── #384 ✓ cell — queue a hand-built package for the counterparty ────
//
// D-152. The merged calculator's confirm control. The server records the
// package as the caller's LIKE (the same row a deck swipe writes) ONLY when
// the likes-you injector would actually mirror it into the counterparty's
// deck — so a `queued: false` means nothing was recorded and the reason says
// why. Idempotent per (user, league, opponent, give set, receive set): a
// second identical call answers `already_queued: true` and moves no Elo.
//
// The reason vocabulary is a cross-client invariant
// (docs/cross-client-invariants.md § Trade-queue refusal reasons) — the
// server's `CALC_QUEUE_REASONS`. `detail` is diagnostic free text; never
// switch UI on it.
export type CalcQueueReason =
  | 'likes_you_off'
  | 'not_league_member'
  | 'assets_not_on_roster'
  | 'opponent_untouchable'
  | 'opponent_not_interested'
  | 'fails_fairness_floor';

export interface CalcQueueResult {
  queued: boolean;
  /** true when this exact package was already queued (no second record). */
  already_queued?: boolean;
  trade_id?: string;
  reason?: CalcQueueReason;
  detail?: string;
}

// POST /api/trades/queue  {league_id, opponent_user_id, give_player_ids,
//                          receive_player_ids}
export async function queueTradeForOpponent(args: {
  leagueId: string;
  opponentUserId: string;
  giveIds: string[];
  receiveIds: string[];
}): Promise<CalcQueueResult> {
  const res = await api.post<any>('/api/trades/queue', {
    league_id:          args.leagueId,
    opponent_user_id:   args.opponentUserId,
    give_player_ids:    args.giveIds,
    receive_player_ids: args.receiveIds,
  });
  return {
    queued:         !!res?.queued,
    already_queued: !!res?.already_queued,
    trade_id:       typeof res?.trade_id === 'string' ? res.trade_id : undefined,
    reason:         typeof res?.reason === 'string' ? (res.reason as CalcQueueReason) : undefined,
    detail:         typeof res?.detail === 'string' ? res.detail : undefined,
  };
}

// ── Trade-match normalizer ───────────────────────────────────────────
// Backend (database.py:load_matches + server.py enrichment) returns:
//   { match_id (int), league_id, league_name?, partner_id, partner_name,
//     my_give[], my_receive[], my_give_names?[], my_receive_names?[],
//     matched_at, status, my_decision, my_decided_at,
//     their_decision, their_decided_at }
// Frontend (shared/types#TradeMatch) wants:
//   { match_id (string), league_id, league_name?, my_side_player_ids[],
//     their_side_player_ids[], my_side_player_names?[],
//     their_side_player_names?[], counterparty_user_id,
//     counterparty_username, created_at, my_disposition, their_disposition }
// Backend uses 'accept'/'decline'; frontend type uses 'accepted'/'declined'
// — we translate both ways here so each layer keeps its native vocabulary.
function normalizeTradeMatch(raw: any): TradeMatch {
  const decisionToDisposition = (
    d: unknown,
  ): 'pending' | 'accepted' | 'declined' | undefined => {
    if (d === 'accept'   || d === 'accepted') return 'accepted';
    if (d === 'decline'  || d === 'declined') return 'declined';
    if (d === 'pending')                      return 'pending';
    return undefined;
  };
  return {
    match_id:                    String(raw?.match_id ?? ''),
    league_id:                   String(raw?.league_id ?? ''),
    league_name:                 raw?.league_name || undefined,
    my_side_player_ids:          Array.isArray(raw?.my_give)    ? raw.my_give    : [],
    their_side_player_ids:       Array.isArray(raw?.my_receive) ? raw.my_receive : [],
    my_side_player_names:        Array.isArray(raw?.my_give_names)        ? raw.my_give_names        : undefined,
    their_side_player_names:     Array.isArray(raw?.my_receive_names)     ? raw.my_receive_names     : undefined,
    my_side_player_teams:        Array.isArray(raw?.my_give_teams)        ? raw.my_give_teams        : undefined,
    their_side_player_teams:     Array.isArray(raw?.my_receive_teams)     ? raw.my_receive_teams     : undefined,
    my_side_player_positions:    Array.isArray(raw?.my_give_positions)    ? raw.my_give_positions    : undefined,
    their_side_player_positions: Array.isArray(raw?.my_receive_positions) ? raw.my_receive_positions : undefined,
    counterparty_user_id:        String(raw?.partner_id ?? ''),
    counterparty_username:       String(raw?.partner_name ?? raw?.partner_id ?? ''),
    created_at:                  String(raw?.matched_at ?? raw?.created_at ?? ''),
    // Mobile READS dispositions and does not write them (audit P0-6): the
    // client wrapper was unused and is gone; the writer is web/js/app.js
    // (POST /api/trades/matches/<id>/disposition). Accept/decline UX on
    // mobile is a NEXT.md item, not a missing call site.
    my_disposition:              decisionToDisposition(raw?.my_decision),
    their_disposition:           decisionToDisposition(raw?.their_decision),
    // Propose-label spine: server-recovered originating impression (flag
    // deck.signal_v2) — threads into the send button so a propose from the
    // Matches tile appends the `propose` deck outcome.
    impression_id:               typeof raw?.impression_id === 'string' ? raw.impression_id : undefined,
  };
}

// GET /api/trades/matches/all — matches across EVERY league the user is in,
// enriched with league_name + player display names. Used by the mobile
// Matches tab; the legacy single-league /api/trades/matches still exists
// for the web app.
export async function getAllMatches(): Promise<TradeMatch[]> {
  const res = await api.get<any>('/api/trades/matches/all');
  return asArray<any>(res).map(normalizeTradeMatch);
}

// GET /api/trades/matches  — single-league mutual-match inbox (legacy).
export async function getMatches(): Promise<TradeMatch[]> {
  const res = await api.get<any>('/api/trades/matches');
  return asArray<any>(res).map(normalizeTradeMatch);
}

// POST /api/trades/suppressions/undo — F3 (flag deck.fatigue). Lifts the
// NEWEST decline suppression for this league (the deck note's "Undo"); the
// caller then regenerates so the previously-hidden trades can return. 404s
// when the flag is off — callers only reach this behind useFlag('deck.fatigue').
export async function undoDeckSuppression(leagueId: string) {
  return api.post<any>('/api/trades/suppressions/undo', { league_id: leagueId });
}

// POST /api/trades/matches/:id/dismiss
// Archives a mutual match from the caller's inbox — persisted, per-user, and
// ELO-neutral (NOT a decline). Powers the "Dismiss" CTA on the Matches tab.
export async function dismissMatch(matchId: string) {
  return api.post<any>(`/api/trades/matches/${matchId}/dismiss`, {});
}

// GET /api/trades/liked — liked trades. Backend returns a bare array of
// trade dicts; we expose both the count (what badges care about) and the
// raw list (so a future inbox screen can render them).
export async function getLikedTrades(): Promise<{ liked_count: number; trades: TradeCard[] }> {
  const res = await api.get<any>('/api/trades/liked');
  const trades = asArray<any>(res).map(normalizeTradeCard);
  return { liked_count: trades.length, trades };
}

// ── Awaiting-trade normalizer ────────────────────────────────────────
// Backend (server.py: /api/trades/awaiting) returns:
//   { trade_id, league_id, league_name?, partner_id, partner_name,
//     my_give[], my_receive[], my_give_names?[], my_receive_names?[],
//     liked_at }
// Frontend (shared/types#AwaitingTrade) uses the same vocabulary as
// TradeMatch so the same tile component can render either.
function normalizeAwaitingTrade(raw: any): AwaitingTrade {
  return {
    trade_id:                String(raw?.trade_id ?? ''),
    league_id:               String(raw?.league_id ?? ''),
    league_name:             raw?.league_name || undefined,
    my_side_player_ids:      Array.isArray(raw?.my_give)    ? raw.my_give    : [],
    their_side_player_ids:   Array.isArray(raw?.my_receive) ? raw.my_receive : [],
    my_side_player_names:    Array.isArray(raw?.my_give_names)    ? raw.my_give_names    : undefined,
    their_side_player_names: Array.isArray(raw?.my_receive_names) ? raw.my_receive_names : undefined,
    counterparty_user_id:    String(raw?.partner_id ?? ''),
    counterparty_username:   String(raw?.partner_name ?? raw?.partner_id ?? ''),
    liked_at:                String(raw?.liked_at ?? ''),
    // Propose-label spine: server-recovered originating impression (flag
    // deck.signal_v2) — threads into the send button so a propose from the
    // awaiting tile appends the `propose` deck outcome.
    impression_id:           typeof raw?.impression_id === 'string' ? raw.impression_id : undefined,
  };
}

// GET /api/trades/awaiting — trades the user liked that haven't matured
// into mutual matches yet. Used by the "Awaiting them" segment on the
// Matches tab so users can see their one-sided likes.
export async function getAwaitingTrades(): Promise<AwaitingTrade[]> {
  const res = await api.get<any>('/api/trades/awaiting');
  return asArray<any>(res).map(normalizeAwaitingTrade);
}

// #318 — dismiss a one-sided like from the "Awaiting them" inbox.
// Contract (wave-backend, 2026-08-13):
//   POST /api/trades/awaiting/dismiss
//   { league_id, my_give: [ids], my_receive: [ids], partner_id }   all required
//   → 200 {"status":"ok","dismissed_likes":<int ≥ 0>}   0 is still ok — never 404
//   → 400 {"error":"league_id, my_give, my_receive, partner_id are required"}
// The row carries no single server id — the like is keyed on the tuple the
// awaiting payload itself is keyed on (load_awaiting_trades): my_give /
// my_receive are the CALLER's perspective, which is exactly how the
// normalizer above stored them (my_side_player_ids ← raw.my_give,
// their_side_player_ids ← raw.my_receive), so the wrapper maps them back.
// Success is `status === "ok"` regardless of dismissed_likes; the route is
// idempotent (repeat → 200 {"dismissed_likes":0}), which is what makes the
// delayed-POST undo pattern retry-safe. The server fires
// `awaiting_trade_dismissed` itself — the client fires no event here.
// Receiver-deck suppression is entirely server-side.
export async function dismissAwaitingTrade(row: AwaitingTrade) {
  return api.post<{ status: string; dismissed_likes: number }>(
    '/api/trades/awaiting/dismiss',
    {
      league_id: row.league_id,
      my_give: row.my_side_player_ids,
      my_receive: row.their_side_player_ids,
      partner_id: row.counterparty_user_id,
    },
  );
}

// ── Standing offers (#362, flag trade.standing_offers) ────────────────
// "I will send player P for any round-R pick, in seasons Y, from teams T,
// in this league, until expires_at." Written after a right-swipe on a
// 1-for-1 where the user receives a first; widens the match rule feeding
// the EXISTING likes-you injector, so the selected teams see that trade
// near the top of their own deck.
//
// FLAG-OFF CONTRACT: all three routes return 404 {"error":"feature_disabled"}
// before any session work — not a bare Flask 404. Callers must treat that as
// "the feature is not on", never as "the request was wrong".
//
// SESSION WINDOW: create and list take `_require_initialized_session` and
// will 409 during the sign-in → session-init window; revoke takes
// `_require_session` and needs no league. Callers on the deck surface
// fail-closed rather than blocking on either.
//
// PRIVACY (R-19): `team_user_ids` and `team_count` are SENDER-OWNED. They
// appear on these payloads because they are the caller's own data, and must
// never be rendered from, or forwarded onto, a recipient-facing surface.

export interface StandingOffer {
  offer_id: number;
  league_id: string;
  /** Present only for rows in the session's CURRENT league — the server
   *  omits it for cross-league rows rather than guessing a name. */
  league_name?: string;
  player_id: string;
  player_name: string;
  round: number;
  seasons: number[];
  /** Sender-owned. Never present on a deck card (R-19). */
  team_user_ids: string[];
  team_count: number;
  created_at: string;
  expires_at: string;
  days_left: number;
  revoked_at: string | null;
  /** True when the offered player has left the sender's roster — the offer
   *  is dead regardless of the clock, and the injector enforces the same
   *  test. Computed ONLY for the session's current league; cross-league
   *  rows always report `false`, which means "not checked here", NOT
   *  "verified live". Do not render it as a positive validity claim. */
  stale: boolean;
}

function normalizeStandingOffer(raw: any): StandingOffer {
  return {
    offer_id:      Number(raw?.offer_id ?? 0),
    league_id:     String(raw?.league_id ?? ''),
    league_name:   typeof raw?.league_name === 'string' ? raw.league_name : undefined,
    player_id:     String(raw?.player_id ?? ''),
    player_name:   String(raw?.player_name ?? raw?.player_id ?? ''),
    round:         Number(raw?.round ?? 1),
    seasons:       Array.isArray(raw?.seasons)
      ? raw.seasons.map((s: any) => Number(s)).filter((s: number) => Number.isFinite(s))
      : [],
    team_user_ids: Array.isArray(raw?.team_user_ids)
      ? raw.team_user_ids.map((t: any) => String(t))
      : [],
    team_count:    Number(raw?.team_count ?? 0),
    created_at:    String(raw?.created_at ?? ''),
    expires_at:    String(raw?.expires_at ?? ''),
    days_left:     Number(raw?.days_left ?? 0),
    revoked_at:    raw?.revoked_at ? String(raw.revoked_at) : null,
    stale:         raw?.stale === true,
  };
}

/** POST /api/trades/standing-offer.
 *  → 200 {status, offer} · 400 validation · 409 a live offer already exists
 *    for this (player, round) · 404 feature_disabled.
 *  Validation order is round → season horizon → membership, and only the
 *  FIRST failure is reported: a league with no draft picks answers 400 with
 *  `allowed_seasons: []` BEFORE membership is ever checked, so a 400 here
 *  never proves the team ids were accepted. */
export async function createStandingOffer(body: {
  league_id: string;
  player_id: string;
  round: number;
  seasons: number[];
  team_user_ids: string[];
  source_trade_id?: string;
}): Promise<{ status: string; offer: StandingOffer }> {
  const res = await api.post<any>('/api/trades/standing-offer', body);
  return {
    status: String(res?.status ?? 'ok'),
    offer: normalizeStandingOffer(res?.offer),
  };
}

/** GET /api/trades/standing-offers — the CALLER's own offers (live, expired
 *  and revoked), newest first. Unwraps `res.offers`; a malformed payload
 *  degrades to `[]` (the getAwaitingTrades posture) rather than throwing on
 *  a manage screen. */
export async function getStandingOffers(leagueId?: string): Promise<StandingOffer[]> {
  const qs = leagueId ? `?league_id=${encodeURIComponent(leagueId)}` : '';
  const res = await api.get<any>(`/api/trades/standing-offers${qs}`);
  const rows = Array.isArray(res?.offers) ? res.offers : Array.isArray(res) ? res : [];
  return rows.map(normalizeStandingOffer);
}

/** POST /api/trades/standing-offer/revoke.
 *  → 200 {status, revoked} — `revoked:false` on an idempotent repeat or an
 *  offer the caller does not own. Still 200, never 404 (the
 *  awaiting/dismiss contract sets this precedent). */
export async function revokeStandingOffer(
  offerId: number,
): Promise<{ status: string; revoked: boolean }> {
  const res = await api.post<any>('/api/trades/standing-offer/revoke', {
    offer_id: offerId,
  });
  return { status: String(res?.status ?? 'ok'), revoked: res?.revoked === true };
}
