"""Page-first exact top-K retrieval for the owner bilateral constructors.

The full constructors evaluate every candidate and rank all survivors before a
first card can be shown. This module returns the same first page while
evaluating a small fraction of them: each candidate gets an admissible upper
bound on ``bilateral.weaker_support`` (the leading term of the rank's quality
tuple), candidates are verified with the UNCHANGED exact evaluator in
descending-bound order, and the search stops once M = k + 31 eligible cards are
held whose M-th exact ``weaker_support`` exceeds every remaining bound by more
than 1e-9 (ties keep going). ``bilateral._rank`` picks each output from a
32-item lookahead of the quality-sorted list, so its first k outputs depend
only on the sorted prefix of length k + 31, which is then proven exact.
Eligibility is not monotone and no bound predicts it: bounds only order work
and prove the stop; the exact evaluator decides.

Universe (un-pinned requests only): exactly what ``bilateral._Search.candidates``
yields per opponent — every focal 1x1 of the two ``_pool``s, plus single-companion
2x1/1x2 expansions of a focal parent whose exact proof is eligible or was
rejected for a curable reason. A package reachable from two parents keeps the
id order of whichever (focal, companion) ordering sorts first in the incumbent's
``expansion`` list among ADMITTED parents. Parents are evaluated lazily, only
when one of their expansions is about to be verified. The incumbent's stream
budgets are ignored; the report says whether they could bind (if so the two
universes may differ).

Bound levels, each admissible (exact <= bound + 1e-9 up to float summation):

* support: ``bilateral._Search._owner`` recomputed from the search's own
  ``_features``, ``_plan_asset``, ``_package``, ``_lineup`` and
  ``_need_utility`` — the exact min of the two support scores.
* priced: the same with ``need = clip(4 * _need_utility)`` bounded (each support
  term is monotone in its input). Removing assets never raises the usable-depth
  total and adding asset a raises it by at most its lineup value v_a, because
  ``trade_roster.assign`` is a maximum-weight (occupancy-first) assignment, i.e.
  a weighted transversal-matroid basis: removal keeps every other starter and
  only shrinks the bench; an addition displaces at most one starter x (gain
  v_a - v_x) whose 15% backup credit is at most v_x. So one received asset gains
  at most its exact full-roster gain and a second at most its own value. This
  assumes the optimum is unique (ties could flip the bench); the audit test
  checks it empirically. Native position-range teams pick among templates and
  get the trivial need <= 1.
* pre (no pricing): ``mg`` is bounded by ``_Bounds.side_price``, an envelope of
  ``trade_service._package_value_market`` (the only pricing path inside the
  generators' ``stud_tax_override("market")``) per side. Low: a one-asset side
  is never discounted; a multi-asset side's depth total max(contrib,
  naive (1 - cap)) is recomputed as written for its values (same trade-wide
  benchmark rule), and exempt first-round picks only raise it (face value,
  cap on the taxable rest). High: the depth total is <= naive (every factor
  floor + (1 - floor)(v / bench)^gamma is <= 1 since v <= bench) plus a crown
  credit <= crown_rate x the side's elite (>= crown_elite_value) market value
  (phase <= 1, flag on or off). +- .05 rounding and 1e-9 relative slack.
  Valid only while 0 <= cap <= 1, 0 <= package floors <= 1, gamma >= 0 and
  rate >= 0; otherwise the envelope is disabled and every candidate is
  priced. The looser [naive (1 - cap), naive (1 + crown_rate)] form gives a
  contiguous market window of companions that can clear the floor, so most
  expansions are never enumerated. ``test_trade_first_page`` pins both.
  Independently the counterparty's ``mg`` is exactly minus the viewer's, so the
  two market components sum to one: min <= max_t min(Av + .35 t, Ac + .35 (1 - t)).

Cost structure (12-team synthetic league, k = 30; first_page_bench prints it):
``_Member.screen`` enumerates ~16k focal pairs and windowed expansions, drops
the ~8k that ``can_clear`` proves below the floor (envelope ratio cap) and
computes ~7-8k pre bounds with ``_Member.pre``'s float operations inlined
(bit-identical, pinned) into flat heap entries; ~300-500 candidates are then
priced and ~100-140 verified. The generator's search runs as a private
subclass (``_private_search``): ineligible results carry only their reason,
and an eligible proof's enrichment (``_with_data``) is deferred, so only the
cards a take returns are ever serialised; ordering reads the dict the
generator itself built, which equals the decode of the final bytes (pinned
exhaustively). Two process-wide memos keyed by content, never by league or
user, serve repeated work: ``_LINEUP_MEMO`` (lineup assignments) and
``_COORDINATE_MEMO`` (tier coordinates in search construction). ``PageSearch``
keeps the state so the first few cards can be shown and the same search
continued.

Revision 2 (``term_precedence``) is exact too, with ``complete`` true and the
budgets not binding. Its ``_rank`` is the baseline (bilateral-1's) followed by
a min-index topological merge: card c waits for every predecessor, a cheaper
(``worst_adjusted_market_loss``, size) member among the 32 cheapest of c's own
two families (same partner and exact give set, or exact receive set). With a
horizon L >= k: prove the quality prefix of length L + 31, so the baseline's
first L over any held superset are the true first L and every other held card
has true baseline index >= L; then make every family of those L cards hold all
eligible universe members cheaper than the card (``_complete``; members are
enumerated like the screen, ``can_clear`` and a price-envelope floor on the
market loss |rv - gv| / max(rv, gv) dismiss most, the exact loss comes from
the very pricing call the proof's own loss uses, 1e-9 slack, and survivors are
resolved through the admitted-parent rule), so each of the first L has its
exact predecessor set, transitively. Rank the union with the unchanged
revision-2 ranker; the outputs before the first one outside the first L are
the full solve's: by induction the same cards are emitted, so cards in the
first L are available in both merges or in neither, and any card outside can
only be popped once none of them is. If that exact prefix is shorter than k,
L grows (the search resumes). A cap hit while completing reports ``complete``
false. The argument is a proof given the same universe and that cost is a pure
function of a card's terms (both pinned against the full solve in
``test_trade_first_page``).

Leaf module: no server, database, flag reload, provider or network access.
Scores are interpretable support, never acceptance probabilities.
"""

import copy
import heapq
import math
import threading
import uuid
import weakref
from bisect import bisect_left, bisect_right, insort
from collections import Counter, OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from time import perf_counter

from . import trade_gen_owner as owner


PAGE_FIRST_VERSION = "page-first-4"
BOUND_VERSION = "support_upper_bound_v1"
_EPS = 1e-9
_LOOKAHEAD = 31  # bilateral._rank: 32-item window => first k use a k + 31 prefix
_FLOOR_SLACK = 1e-12  # pricing order may differ from the served order by ulps
_REL = 1e-9  # outward relative slack on envelope arithmetic
_COST_SLACK = 1e-9  # family members' market loss is recomputed from the viewer-side pricing call
_ROUND = .05  # package_value_v2 rounds to one decimal
_CURABLE = ("market_floor", "market_overpay", "viewer_no_benefit", "counterparty_no_benefit",
            "known_preference_harm", "tanking_rb_without_long_term_exception")
_UNSUPPORTED = ("pinned_give_players", "pinned_receive_players", "exact_give", "require_all_give")


def _clip(value, low=-1.0, high=1.0):
    return max(low, min(high, value))


def _gain(q):
    """Market gain (in - out) / max(in, out) as a function of q = in / out."""
    return 1 - 1 / q if q >= 1 else q - 1


class _LineupMemo:
    """Bounded, thread-safe, process-wide memo of ``owner._Search._lineup``.

    The key is the CONTENT the function reads, never a league or user id, so an
    entry can never be stale: change a roster, value, slot, injury or position
    and the key changes. ``_lineup(roster, team)`` reads exactly:

    * ``team["slots"]`` (``assign``'s slots, ``len`` for native templates, and
      the backup-eligibility test) and ``team.get("native_bounds")`` (the
      native branch, ``choose`` and ``templates``);
    * ``team["inactive"]`` and ``search._lineup_assets`` only to form
      ``usable``, so the ordered ``usable`` list replaces both;
    * per usable asset its ``id``, ``positions`` and ``value`` (the only
      ``Asset`` fields ``_lineup``, ``assign`` and ``choose`` read;
      ``_lineup_value`` overrides are already folded into ``value``) and
      ``search._position(asset.id)``, as one tuple of builtins per asset
      (hashing and equality stay in C; a search's keys share them; positions
      as a sorted tuple, so a key holds only atomic values and the cyclic GC
      untracks it instead of traversing every entry on each full collection). These are
      read once per search at ``install``: the incumbent builds
      ``_lineup_assets`` in ``__init__`` and ``_position`` memoises immutable
      player data, so neither changes during a search; a changed input is a
      new search with new tuples and new keys.

    ``usable`` is kept in roster ITERATION order: ``assign``'s bonus and the
    per-position sums are float additions in that order, so two equal rosters
    iterated differently could differ in the last ulp. Keying by order keeps
    every cached result bit-identical to what the incumbent would compute.
    Module constants (``trade_roster.ELIGIBILITY``, ``assign``, ``choose``,
    ``templates``) are code, not data, and are not keyed. A search whose class
    overrides ``_lineup`` is never memoised (``install``).

    Values are stored as an immutable tuple and every call returns a fresh dict
    (``team["lineup_before"]`` and proofs embed it), so no caller can corrupt an
    entry. LRU eviction at ``cap`` entries; a lock guards the dict, and the
    computation runs outside it (two threads may both compute a missing key;
    the results are identical and the second write is harmless).
    """

    def __init__(self, cap):
        self.cap = cap
        self._entries = OrderedDict()
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def clear(self):
        with self._lock:
            self._entries.clear()
            self.hits = self.misses = 0

    def __len__(self):
        return len(self._entries)

    def install(self, search):
        """Shadow ``search._lineup`` with the memoised version (instance only)."""
        if type(search)._lineup is not owner._Search._lineup:
            return
        # Weak: the shadow lives on the search, so a strong reference would
        # make a cycle and keep every finished search until a full GC.
        owner_ref = weakref.ref(search)
        # One (id, positions, value, position) tuple per lineup asset, built
        # once: a search's _lineup_assets and _position answers are fixed after
        # construction (built from its immutable inputs), and its keys share
        # the tuples. Per team, the inactive ids are dropped (cached by the
        # identity of the team's inactive set).
        signatures = {pid: (asset.id, tuple(sorted(asset.positions)), asset.value, type(search)._position(search, pid))
                      for pid, asset in search._lineup_assets.items()}
        usable = {}

        def lineup(roster, team):
            inactive = team["inactive"]
            known = usable.get(team["uid"])
            if known is None or known[0] is not inactive:
                known = usable[team["uid"]] = inactive, (
                    {pid: sig for pid, sig in signatures.items() if pid not in inactive} if inactive else signatures)
            key = team["slots"], team.get("native_bounds"), tuple(filter(None, map(known[1].get, roster)))
            with self._lock:
                values = self._entries.get(key)
                if values is not None:
                    self._entries.move_to_end(key)
                    self.hits += 1
            if values is None:
                values = tuple(owner._Search._lineup(owner_ref(), roster, team).values())
                with self._lock:
                    self.misses += 1
                    self._entries[key] = values
                    if len(self._entries) > self.cap:
                        self._entries.popitem(last=False)
            return dict(zip(owner._POSITIONS, values))

        search._lineup = lineup


# About 850 distinct rosters per 12-team search and ~600 bytes an entry measured
# (keys share per-asset tuples), so the cap bounds the memo near 30 MB.
_LINEUP_MEMO = _LineupMemo(cap=50_000)


class _Bounds:
    """Bound terms for one request, kept in sync with the search's own methods.

    A candidate's "row" is the elementwise sum over its assets of (market,
    viewer preference, viewer plan, counterparty preference, counterparty plan),
    preference/plan already market-weighted and signed (+ when received).
    """

    def __init__(self, search):
        from . import trade_gen_bilateral as bilateral
        self.search = search
        weights = bilateral._WEIGHTS
        self.w_pref = weights["preference_fulfillment"]
        self.w_market = weights["market_acceptability"]
        self.w_plan = weights["team_plan"]
        self.tol = max(1 - search.floor, .05)
        self.floor = search.floor - _EPS - _FLOOR_SLACK
        # _need_utility is linear in the usable-depth delta sum over the gross.
        self.need_rate = {uid: search._need_utility(team, {"unit": 1.0}, 1.0)
                          for uid, team in search.teams.items()}
        self.native = {uid for uid, team in search.teams.items() if team["native_bounds"]}
        c = search.ts._c
        self.envelope = (search.ts.current_stud_tax_mode() == "market"
                         and 0 <= c("package_discount_cap") <= 1 and c("crown_rate_market") >= 0
                         and 0 <= c("package_floor_market") <= 1 and 0 <= c("package_floor_cross") <= 1
                         and c("package_adj_gamma_market") >= 0)
        self.keep = 1 - c("package_discount_cap") if self.envelope else 0.0
        self.crown = 1 + c("crown_rate_market") if self.envelope else math.inf
        self.crown_rate, self.elite_ref = c("crown_rate_market"), c("crown_elite_value")
        self.gamma, self.trade_wide = c("package_adj_gamma_market"), c("package_bench_trade_wide") > 0
        self.floor_market, self.floor_cross = c("package_floor_market"), c("package_floor_cross")

    def price_range(self, naive, count):
        """(lo, hi) of a side's market package price; see the module docstring."""
        if not self.envelope:
            return 0.0, math.inf
        lo = naive * (1 if count == 1 else self.keep) * (1 - _REL) - _ROUND
        return lo, naive * self.crown * (1 + _REL) + _ROUND

    def elite(self, value):
        """The part of an asset's market value that can earn a crown credit."""
        return value if self.elite_ref > 0 and value >= self.elite_ref else 0.0

    def side_price(self, values, other_max):
        """(lo, hi) of a side's market package price, tighter than ``price_range``.

        ``_package_value_market`` with ``exempt`` None is the depth total
        max(contrib, naive (1 - cap)), computed here as written for this side
        (benchmark and floor chosen by the same trade-wide rule); an exemption
        only raises a side (exempt pieces at face, cap on the taxable rest), so
        that is a lower bound for every mask. The depth total is <= naive and
        the crown credit is <= rate x the side's elite (>= crown_elite_value)
        market value, phase <= 1, whether or not the flag is on. Same validity
        conditions as the envelope; outward slack covers summation order and
        the .05 rounding.
        """
        if not self.envelope:
            return 0.0, math.inf
        naive = sum(values)
        if len(values) == 1:
            low = naive
        else:
            top = max(values)
            bench, floor = ((other_max, self.floor_cross) if self.trade_wide and other_max > top
                            else (top, self.floor_market))
            low = max(sum(v * (floor + (1.0 - floor) * (v / bench) ** self.gamma) for v in values),
                      naive * self.keep)
        elite = sum(self.elite(v) for v in values)
        return low * (1 - _REL) - _ROUND, (naive + self.crown_rate * elite) * (1 + _REL) + _ROUND

    def can_clear(self, g_lo, g_hi, r_lo, r_hi):
        """See ``_Member.can_clear``; inconclusive (True) unless both lows are known."""
        low = g_lo if g_lo > r_lo else r_lo
        return low <= 0 or (g_hi if g_hi < r_hi else r_hi) >= self.floor * low

    def window(self, base, single):
        """Companion market values c for which base + c against a one-asset side
        of value ``single`` can clear the floor under the envelope."""
        low, high = self.window_terms(single)
        low, high = low - base, high - base
        return low - _REL * (abs(low) + 1), high + _REL * (abs(high) + 1)

    def window_terms(self, single):
        """``window`` before subtracting ``base`` (one pair per single asset)."""
        if not self.envelope or self.floor <= 0:
            return -math.inf, math.inf
        s_lo, s_hi = self.price_range(single, 1)
        return ((self.floor * s_lo - _ROUND) / (self.crown * (1 + _REL)),
                (s_hi / self.floor + _ROUND) / (self.keep * (1 - _REL)) if self.keep > 0 else math.inf)

    def rows(self, viewer, other, pool, sent_by_viewer):
        s, sign = self.search, (-1 if sent_by_viewer else 1)
        out = {}
        for pid in pool:
            m = s.market[pid]
            out[pid] = (m, sign * m * (s._features[viewer["uid"], pid]["direction"] or 0),
                        sign * m * s._plan_asset(viewer, pid),
                        -sign * m * (s._features[other["uid"], pid]["direction"] or 0),
                        -sign * m * s._plan_asset(other, pid))
        return out

    def _need(self, uid, usable_ratio):
        rate = self.need_rate[uid]
        if rate <= 0:
            return 0.0
        if uid in self.native:
            return 1.0
        return _clip(4 * rate * usable_ratio)

    def _side(self, pref, plan, need):
        """One side's support excluding the market term."""
        return (self.w_pref * _clip(.5 + pref, 0, 1)
                + self.w_plan * _clip(.5 + .5 * _clip(plan + need), 0, 1))

    def _market(self, gain):
        return self.w_market * _clip(.5 + .5 * gain / self.tol, 0, 1)

    def pre(self, uids, row, gains, q):
        """Bound before pricing: sides without market, then the market split."""
        g = row[0]
        a = (self._side(row[1] / g, row[2] / g, self._need(uids[0], gains[0] / g)),
             self._side(row[3] / g, row[4] / g, self._need(uids[1], gains[1] / g)))
        g_lo = _gain(q[0]) if q[0] > 0 else -1.0
        g_hi = _gain(q[1]) if q[1] < math.inf else 1.0
        return min((a[0] + a[1] + self.w_market) / 2, a[0] + self._market(g_hi),
                   a[1] + self._market(-g_lo)), a

    def priced(self, a, priced):
        _, gv, rv = priced
        gain = (rv - gv) / max(rv, gv)
        return min(a[0] + self._market(gain), a[1] + self._market(-gain))

    def support(self, viewer, other, give, receive, row, priced):
        """The exact two-sided support (up to float summation order)."""
        s, g = self.search, row[0]
        _, gv, rv = priced
        gain = (rv - gv) / max(rv, gv)
        out = []
        for team, roster, pref, plan, market in (
                (viewer, (viewer["roster"] - set(give)) | set(receive), row[1], row[2], gain),
                (other, (other["roster"] - set(receive)) | set(give), row[3], row[4], -gain)):
            after = s._lineup(roster, team)
            deltas = {pos: after[pos] - team["lineup_before"][pos] for pos in owner._POSITIONS}
            need = _clip(s._need_utility(team, deltas, g) * 4)
            out.append(self.w_pref * _clip(.5 + pref / g, 0, 1) + self._market(market)
                       + self.w_plan * _clip(.5 + .5 * _clip(plan / g + need), 0, 1))
        return min(out)


class _Member:
    """One opponent: pools, per-asset rows and single-asset usable-depth gains."""

    def __init__(self, search, bounds, member):
        search.checkpoint()
        viewer, other = search.teams[search.user_id], search.teams[member.user_id]
        self.search, self.bounds = search, bounds
        self.member, self.viewer, self.other = member, viewer, other
        self.uids = viewer["uid"], other["uid"]
        # _pool's asset interest computes every one-asset-added lineup; the
        # lineup memo serves them again below.
        self.give_pool = search._pool(viewer, other)
        self.receive_pool = search._pool(other, viewer)
        self.rows = {**bounds.rows(viewer, other, self.give_pool, True),
                     **bounds.rows(viewer, other, self.receive_pool, False)}
        self.by_market = {}
        for side, pool in (("give", self.give_pool), ("receive", self.receive_pool)):
            ordered = sorted(pool, key=lambda p: (search.market[p], p))
            self.by_market[side] = ([search.market[p] for p in ordered], ordered)
        self.gain, self.usable = {}, {}
        for team, pool in ((viewer, self.receive_pool), (other, self.give_pool)):
            for pid in pool:
                asset = search._lineup_assets.get(pid)
                self.usable[pid] = asset.value if asset is not None and pid not in team["inactive"] else 0.0
            if bounds.need_rate[team["uid"]] > 0 and team["uid"] not in bounds.native:
                for pid in pool:
                    after = search._lineup(team["roster"] | {pid}, team)
                    self.gain[pid] = sum(after[p] - team["lineup_before"][p] for p in owner._POSITIONS)

    def potential(self):
        ng, nr = len(self.give_pool), len(self.receive_pool)
        return ng * nr + nr * ng * (ng - 1) // 2 + ng * nr * (nr - 1) // 2

    def expansions(self, give, receive, *, windowed=True, canonical=False):
        """Single-companion expansions of a focal pair, optionally envelope-windowed.

        ``canonical`` keeps only companions whose id sorts after the focal id,
        so each package is enumerated once (the window depends only on the
        pair's market sum, so its other parent would admit it identically).
        """
        market = self.search.market
        for side, base, single in (("give", give[0], receive[0]), ("receive", receive[0], give[0])):
            values, ordered = self.by_market[side]
            low, high = self.bounds.window(market[base], market[single]) if windowed else (-math.inf, math.inf)
            for pid in ordered[bisect_left(values, low):bisect_right(values, high)]:
                if pid > base if canonical else pid != base:
                    yield ((give + (pid,), receive) if side == "give" else (give, receive + (pid,)))

    def row(self, give, receive):
        m = vp = vs = op = os = 0.0
        for pid in give + receive:
            r = self.rows[pid]
            m, vp, vs, op, os = m + r[0], vp + r[1], vs + r[2], op + r[3], os + r[4]
        return m, vp, vs, op, os

    def gains(self, give, receive):
        """Upper bounds on the (viewer, counterparty) usable-depth delta sums."""
        out = []
        for received in (receive, give):
            if received[0] not in self.gain:
                out.append(0.0)  # need rate 0, or native (bounded as 1 by _need)
            elif len(received) == 1:
                out.append(self.gain[received[0]])
            else:
                a, b = received
                out.append(min(self.gain[a] + self.usable[b], self.gain[b] + self.usable[a]))
        return out

    def can_clear(self, give, receive):
        """False when the price envelope proves the market ratio is below the floor.

        ratio = min(gv, rv) / max(gv, rv) <= min(g_hi, r_hi) / max(g_lo, r_lo).
        Such a package fails the evaluator's market_floor gate (and the
        search's own floor check) whatever its other terms.
        """
        market = self.search.market
        gv, rv = [market[p] for p in give], [market[p] for p in receive]
        return self.bounds.can_clear(*self.bounds.side_price(gv, max(rv)), *self.bounds.side_price(rv, max(gv)))

    def pre(self, give, receive):
        row, b, market = self.row(give, receive), self.bounds, self.search.market
        gv, rv = [market[p] for p in give], [market[p] for p in receive]
        g_lo, g_hi = b.side_price(gv, max(rv))
        r_lo, r_hi = b.side_price(rv, max(gv))
        q = (r_lo / g_hi if g_hi < math.inf else 0.0, r_hi / g_lo if g_lo > 0 else math.inf)
        bound, a = b.pre(self.uids, row, self.gains(give, receive), q)
        return bound, (row, a)

    def screen(self, index, heap):
        """Append a heap entry for every focal pair and windowed canonical
        expansion that ``can_clear`` the floor (``first_page``'s screened
        universe): ``(-pre, tie, side, index, g, r, c, a0, a1)`` (see
        ``_screened_package``) with ``a0, a1`` the market-free side terms and
        ``tie`` the entry's position in ``heap``. Flat tuples of atomics: no
        per-candidate package or payload tuples. A focal pair ``can_clear``
        rejects gets no entry either: below the floor it can never be eligible,
        and as a parent it is evaluated on demand when an expansion is.

        Bit-identical to ``self.pre`` (pinned by a parity test): the same
        float operations in the same order, inlined, without per-candidate
        rows or method calls. Uses ``pre`` itself when the envelope is off.
        """
        b, rows, gain, usable, market = self.bounds, self.rows, self.gain, self.usable, self.search.market
        append = heap.append
        if not b.envelope:
            for g in self.give_pool:
                for r in self.receive_pool:
                    for give, receive in [((g,), (r,)), *self.expansions((g,), (r,), canonical=True)]:
                        bound, (_, a) = self.pre(give, receive)
                        side, c = (("give", give[1]) if len(give) == 2 else ("receive", receive[1])
                                   if len(receive) == 2 else ("focal", None))
                        append((-bound, len(heap), side, index, g, r, c, *a))
            return
        inf, rlo, rhi, rnd = math.inf, 1 - _REL, 1 + _REL, _ROUND
        keep, tol, wp, wm, wpl = b.keep, b.tol, b.w_pref, b.w_market, b.w_plan
        gamma, wide, fm, fc, crown_rate = b.gamma, b.trade_wide, b.floor_market, b.floor_cross, b.crown_rate
        floor = b.floor

        def need_term(uid):  # _Bounds._need as (constant, 4 * rate) for one side
            rate = b.need_rate[uid]
            return (0.0, None) if rate <= 0 else (1.0, None) if uid in b.native else (None, 4 * rate)

        (n0, k0), (n1, k1) = need_term(self.uids[0]), need_term(self.uids[1])
        elite = {pid: b.elite(market[pid]) for pid in rows}
        # b.side_price([x], _) per asset; b.side_price([x, y], other) below.
        lo1 = {pid: market[pid] * rlo - rnd for pid in rows}
        hi1 = {pid: (market[pid] + crown_rate * elite[pid]) * rhi + rnd for pid in rows}
        terms = {pid: b.window_terms(market[pid]) for pid in rows}  # b.window, inlined below
        rel = _REL

        def two_low(x, y, other):  # b.side_price([x, y], other)[0]; [1] is inlined below
            top = x if x >= y else y
            bench, f = (other, fc) if wide and other > top else (top, fm)
            low = x * (f + (1.0 - f) * (x / bench) ** gamma) + y * (f + (1.0 - f) * (y / bench) ** gamma)
            keep_low = (x + y) * keep
            return (low if low >= keep_low else keep_low) * rlo - rnd

        def push(m, vp, vs, op, os, gl, gh, rl, rh, gv, gc, side, g, r, c):
            # _Bounds.pre after side_price: g* the give side, r* the receive side.
            q0 = rl / gh if gh < inf else 0.0
            q1 = rh / gl if gl > 0 else inf
            if n0 is None:
                need = k0 * (gv / m)
                need = -1.0 if need < -1.0 else 1.0 if need > 1.0 else need
            else:
                need = n0
            x = .5 + vp / m
            plan = vs / m + need
            plan = .5 + .5 * (-1.0 if plan < -1.0 else 1.0 if plan > 1.0 else plan)
            a0 = (wp * (0 if x < 0 else 1 if x > 1 else x)
                  + wpl * (0 if plan < 0 else 1 if plan > 1 else plan))
            if n1 is None:
                need = k1 * (gc / m)
                need = -1.0 if need < -1.0 else 1.0 if need > 1.0 else need
            else:
                need = n1
            x = .5 + op / m
            plan = os / m + need
            plan = .5 + .5 * (-1.0 if plan < -1.0 else 1.0 if plan > 1.0 else plan)
            a1 = (wp * (0 if x < 0 else 1 if x > 1 else x)
                  + wpl * (0 if plan < 0 else 1 if plan > 1 else plan))
            lo = (1 - 1 / q0 if q0 >= 1 else q0 - 1) if q0 > 0 else -1.0
            hi = (1 - 1 / q1 if q1 >= 1 else q1 - 1) if q1 < inf else 1.0
            x = .5 + .5 * hi / tol
            up = a0 + wm * (0 if x < 0 else 1 if x > 1 else x)
            x = .5 + .5 * -lo / tol
            down = a1 + wm * (0 if x < 0 else 1 if x > 1 else x)
            append((-min((a0 + a1 + wm) / 2, up, down), len(heap), side, index, g, r, c, a0, a1))

        values_g, ordered_g = self.by_market["give"]
        values_r, ordered_r = self.by_market["receive"]
        for g in self.give_pool:
            mg, vg1, vg2, vg3, vg4 = rows[g]
            ng, g_lo, g_hi, terms_g = gain.get(g), lo1[g], hi1[g], terms[g]
            for r in self.receive_pool:
                mr, vr1, vr2, vr3, vr4 = rows[r]
                nr, r_lo, r_hi = gain.get(r), lo1[r], hi1[r]
                # A focal pair that cannot clear the floor needs no entry: it is
                # only ever useful as a parent, evaluated when an expansion is.
                low = g_lo if g_lo > r_lo else r_lo  # b.can_clear
                if low <= 0 or (g_hi if g_hi < r_hi else r_hi) >= floor * low:
                    push(mg + mr, vg1 + vr1, vg2 + vr2, vg3 + vr3, vg4 + vr4, g_lo, g_hi, r_lo, r_hi,
                         0.0 if nr is None else nr, 0.0 if ng is None else ng, "focal", g, r, None)
                # give + (c,): summed in order g, c, r; the counterparty receives two.
                low, high = terms[r]
                low, high = low - mg, high - mg
                low, high = low - rel * (abs(low) + 1), high + rel * (abs(high) + 1)
                for c in ordered_g[bisect_left(values_g, low):bisect_right(values_g, high)]:
                    if c > g:
                        mc = market[c]
                        hi2 = (mg + mc + crown_rate * (elite[g] + elite[c])) * rhi + rnd
                        if hi2 < floor * r_lo:  # b.can_clear, decided before the costlier low
                            continue
                        lo2 = two_low(mg, mc, mr)
                        low = lo2 if lo2 > r_lo else r_lo  # b.can_clear
                        if low > 0 and (hi2 if hi2 < r_hi else r_hi) < floor * low:
                            continue
                        mc, c1, c2, c3, c4 = rows[c]
                        push(mg + mc + mr, vg1 + c1 + vr1, vg2 + c2 + vr2, vg3 + c3 + vr3, vg4 + c4 + vr4,
                             lo2, hi2, r_lo, r_hi, 0.0 if nr is None else nr,
                             0.0 if ng is None else min(ng + usable[c], gain[c] + usable[g]), "give", g, r, c)
                # receive + (c,): summed in order g, r, c; the viewer receives two.
                low, high = terms_g
                low, high = low - mr, high - mr
                low, high = low - rel * (abs(low) + 1), high + rel * (abs(high) + 1)
                for c in ordered_r[bisect_left(values_r, low):bisect_right(values_r, high)]:
                    if c > r:
                        mc = market[c]
                        hi2 = (mr + mc + crown_rate * (elite[r] + elite[c])) * rhi + rnd
                        if hi2 < floor * g_lo:  # b.can_clear, decided before the costlier low
                            continue
                        lo2 = two_low(mr, mc, mg)
                        low = g_lo if g_lo > lo2 else lo2  # b.can_clear
                        if low > 0 and (g_hi if g_hi < hi2 else hi2) < floor * low:
                            continue
                        mc, c1, c2, c3, c4 = rows[c]
                        push(mg + mr + mc, vg1 + vr1 + c1, vg2 + vr2 + c2, vg3 + vr3 + c3, vg4 + vr4 + c4,
                             g_lo, g_hi, lo2, hi2,
                             0.0 if nr is None else min(nr + usable[c], gain[c] + usable[r]),
                             0.0 if ng is None else ng, "receive", g, r, c)


_SCREENED = ("focal", "give", "receive")


def _screened_package(entry):
    """(give, receive) of a screen entry ``(-pre, tie, side, index, g, r, c, a0, a1)``:
    the focal pair (g, r), or it plus companion c on ``side``. Packages are
    rebuilt on pop so the ~10k entries hold no inner tuples."""
    side, g, r, c = entry[2], entry[4], entry[5], entry[6]
    return ((g, c), (r,)) if side == "give" else ((g,), (r, c)) if side == "receive" else ((g,), (r,))


def _supported(kwargs):
    return not any(kwargs.get(name) for name in _UNSUPPORTED)


def _expansion_key(search, member, side, pid, g, r):
    """The incumbent's ``expansion`` sort key for one (focal, companion) ordering."""
    viewer, other = search.teams[search.user_id], search.teams[member.user_id]
    recipient, sender = (other, viewer) if side == "give" else (viewer, other)
    joint = search._asset_interest(recipient, pid, 1) + search._asset_interest(sender, pid, -1)
    gap = abs(sum(search.market[p] for p in g) - sum(search.market[p] for p in r))
    cost = gap / max(sum(search.market[p] for p in g + r), 1)
    return -(joint - cost), g, r


def _orderings(give, receive):
    """Both (side, companion, give, receive) orderings of an expansion signature."""
    if len(give) == 2:
        a, b = sorted(give)
        return (("give", b, (a, b), receive), ("give", a, (b, a), receive))
    a, b = sorted(receive)
    return (("receive", b, give, (a, b)), ("receive", a, give, (b, a)))


def _card(search, member, give, receive):
    return search.ts.TradeCard("", search.league.league_id, search.user_id, member.user_id,
                               member.username, list(give), list(receive), 0, 0, 0)


def screened_universe(search):
    """Audit hook: every potential candidate ordering that clears the floor.

    Yields ``((screened, pre, priced, support), give, receive, member)`` for
    each focal pair and each (focal, companion) expansion ordering, enumerated
    without the envelope window; ``screened`` says whether ``first_page``'s
    screen (``_Member.screen``: window, canonical order, ``can_clear``)
    reaches the package. Run inside the generator's config context.
    """
    bounds = _Bounds(search)
    for m in [_Member(search, bounds, member) for member in search.members]:
        entries = []
        m.screen(0, entries)
        screened = {tuple(map(frozenset, _screened_package(entry))) for entry in entries}
        for g in m.give_pool:
            for r in m.receive_pool:
                for give, receive in [((g,), (r,)), *m.expansions((g,), (r,), windowed=False)]:
                    priced = search._package(give, receive, search.market)
                    if priced is None or priced[0] < bounds.floor:
                        continue
                    pre, (row, a) = m.pre(give, receive)
                    yield (((frozenset(give), frozenset(receive)) in screened, pre,
                            bounds.priced(a, priced), bounds.support(m.viewer, m.other, give, receive, row, priced)),
                           give, receive, m.member)


@dataclass(frozen=True, slots=True)
class _Rejected:
    """A private search's ineligible result: status and reason, never a proof."""
    reason: str

    @property
    def eligible(self):
        return False

    def as_dict(self):
        raise RuntimeError("an ineligible page-first result has no proof payload")


class _CoreProof(owner.OwnerDecisionContext):
    """Private stand-in for an eligible core proof the generator just froze.

    Same frozen fields; ``as_dict`` is the real proof's. ``_with_data`` (how
    revision 2 adds term efficiency, and bilateral-1 marks a dominated card)
    returns a ``_Deferred`` instead of serialising at once.
    """

    @classmethod
    def of(cls, real):
        proof = cls(*(getattr(real, f.name) for f in fields(owner.OwnerDecisionContext)))
        object.__setattr__(proof, "_real", real)
        return proof

    def as_dict(self):
        return self._real.as_dict()

    def _with_data(self, data, **changes):
        return _Deferred(self._real, data, changes)

    def final(self):
        """The proof the incumbent returns for this card: the core itself."""
        return self._real

    def decoded(self):
        return self._real.as_dict()

    def twin(self):
        return replace(self._real)


class _Deferred:
    """``core._with_data(data, **changes)``, run only when a card leaves.

    The generator builds ``data`` from a fresh decode of the core proof plus
    JSON-native fields (revision 2's ``term_efficiency``) and never touches it
    after this call, so ``final()`` - the same incumbent method on the same
    plain core proof with the same dict - produces the exact proof (bytes,
    fields, fast-JSON marker) evaluation would have, and ``data`` itself is
    what decoding those bytes returns (pinned for every eligible candidate of
    the audit worlds). Only cards a take returns are ever serialised.
    """

    __slots__ = ("core", "data", "changes", "_final")

    def __init__(self, core, data, changes):
        self.core, self.data, self.changes, self._final = core, data, changes, None

    @property
    def eligible(self):
        return self.changes.get("eligible", self.core.eligible)

    @property
    def reason(self):
        return self.changes.get("reason", self.core.reason)

    def final(self):
        if self._final is None:
            self._final = self.core._with_data(self.data, **self.changes)
        return self._final

    def decoded(self):
        return self.data

    def twin(self):
        return replace(self.core, **self.changes)


class _CoordinateMemo:
    """Process-wide memo of ``bilateral._Search._coordinate``, keyed by content.

    ``_coordinate(pid, elo)`` reads only ``self._position(pid)`` (as a tier
    position), ``elo``, ``self.fmt`` and the tier bands of
    ``ranking_service.TIER_CONFIG`` (through ``RankingService.tier_for_elo``
    and ``tier_bands_for``). A search reads its table under ``repr`` of the
    whole TIER_CONFIG, taken once at construction, so any change to the bands
    (in place or not) selects a different table; within a table the key is
    (position, elo, format). Results are immutable (coordinate, tier) tuples
    of atomics, so the cyclic GC untracks them. Bounded: a search that starts
    with more than ``cap`` entries recorded drops every table first (personal
    boards make Elo values open-ended); ~1.7k new entries per 12-team search
    at ~175 bytes each, so about 17 MB at the cap. Dict reads and writes are
    atomic under the interpreter lock; a race can only recompute a value or
    miscount the size.
    """

    def __init__(self, cap):
        self.cap, self._tables, self._size = cap, {}, 0

    def clear(self):
        self._tables, self._size = {}, 0

    def table(self, fingerprint):
        if self._size > self.cap:
            self.clear()
        table = self._tables.get(fingerprint)
        if table is None:
            table = self._tables.setdefault(fingerprint, {})
        return table

    def added(self):
        self._size += 1


_COORDINATE_MEMO = _CoordinateMemo(cap=100_000)
_PRIVATE_SEARCH = {}


def _private_search(cls):
    """``cls`` for page-first use: eligible proofs wrapped as ``_CoreProof``,
    ineligible results reduced to ``_Rejected`` (never serialised; only the
    reason is read) and, unless the class overrides it, ``_coordinate``
    served from ``_COORDINATE_MEMO``. Evaluation itself is the class's own."""
    private = _PRIVATE_SEARCH.get(cls)
    if private is None:
        from . import ranking_service, trade_gen_bilateral as bilateral
        memoise = getattr(cls, "_coordinate", None) is bilateral._Search._coordinate

        class private(cls):
            def __init__(self, **kwargs):
                if memoise:
                    self._coordinate_table = _COORDINATE_MEMO.table(repr(ranking_service.TIER_CONFIG))
                super().__init__(**kwargs)

            if memoise:
                def _coordinate(self, pid, elo):
                    key = self._position(pid), elo, self.fmt
                    known = self._coordinate_table.get(key)
                    if known is None:
                        known = self._coordinate_table[key] = bilateral._Search._coordinate(self, pid, elo)
                        _COORDINATE_MEMO.added()
                    return known

            def _freeze_decision(self, card, data, reason, eligible):
                if not eligible:
                    return _Rejected(reason)
                proof = super()._freeze_decision(card, data, reason, eligible)
                return _CoreProof.of(proof) if type(proof) is owner.OwnerDecisionContext else proof
        private.__name__ = private.__qualname__ = "PageFirst" + cls.__name__
        private = _PRIVATE_SEARCH.setdefault(cls, private)
    return private


def _hand_out(card):
    """A take's own copy of an internal card: real proof, own mutable fields."""
    out = copy.copy(card)
    out.owner_evaluation = card.owner_evaluation.final()
    out.give_player_ids, out.receive_player_ids = list(card.give_player_ids), list(card.receive_player_ids)
    out.reasons = list(card.reasons)
    out.match_context = {key: list(value) if isinstance(value, list) else value
                         for key, value in card.match_context.items()}
    return out


class PageSearch:
    """One resumable page-first search: ``take(n)`` returns the proven first n.

    Construction does the per-request work once (search setup, pools, the
    pre-pricing screen); each ``take`` continues the SAME best-first
    verification until n + 31 eligible cards beat every remaining bound, then
    ranks that prefix (revision 2: a horizon L >= n, plus family completion).
    ``take(n)`` returns exactly what ``first_page(k=n)`` would: for
    bilateral-1 the verification order is deterministic and the stop test does
    not change state, so the search passes through exactly the state a
    one-shot call would stop in, and cards verified after it have weaker
    support below its cut; for revision 2 both are the full solve's first n
    (work counts may differ: family members verified early can let a later
    proof stop sooner).

    Prefix stability across takes: every complete take is the full solve's
    first n, so a later, larger take extends an earlier one for both
    generators. ``prefix_stable`` (whether every earlier take's cards are a
    prefix of this one) still reports it, which can only fail after an
    incomplete take. For revision 2 the horizon only grows across takes.

    Each eligible card is decorated once, so an offer keeps its ``trade_id``
    across takes; each take returns its own shallow card copies numbered for
    that page and never touches cards or proofs an earlier take handed out.
    One thread at a time per object (the lineup memo it uses is shared and
    thread-safe). ``elapsed_ms`` is cumulative work: setup, pools and screen
    once, verify and rank summed over takes. Raises ``ValueError`` for
    requests ``first_page`` answers with None.

    ``admit(target_user_id, give, receive) -> bool`` (rules-first construction,
    ``deck_rules.DeckRules.admits``): the deck's per-card rules as an admission
    predicate. Screened entries whose terms fail are dropped before pricing,
    family completion skips failing members, and only admitted eligible proofs
    are held, so bounds, the stop test and the ranker see only admitted cards.
    Parents are still evaluated on demand for expansions, so the universe is
    unchanged. The report adds ``rules_version`` and ``rules_rejected`` (screened
    entries dropped) and ``rules_unheld`` (eligible proofs not held).
    ``admit=None`` is byte-identical to the search without the hook.
    """

    def __init__(self, *, generator=None, max_verifications=4000, admit=None, rules_version=None,
                 **kwargs):
        if not _supported(kwargs):
            raise ValueError("unsupported page-first request")
        if generator is None:
            from . import trade_gen_bilateral_candidate as generator
        started = perf_counter()
        self.generator, self.max_verifications = generator, max_verifications
        self.admit, self.rules_version = admit, rules_version
        self.timings = timings = {}
        search_class = getattr(generator, "_GenerationSearch", None) or generator._Search
        search = self.search = _private_search(search_class)(**kwargs)
        _LINEUP_MEMO.install(search)
        timings["setup"] = perf_counter() - started
        self.counts = counts = Counter()
        with self._context():
            mark = perf_counter()
            bounds = self.bounds = _Bounds(search)
            members = self.members = [_Member(search, bounds, member) for member in search.members]
            timings["pools"] = perf_counter() - mark

            mark = perf_counter()
            heap = self.heap = []
            for index, m in enumerate(members):
                counts["universe"] += m.potential()
                m.screen(index, heap)
            counts["bounded"] = len(heap)
            self.bind = (any(m.potential() > search.pair_budget for m in members)
                         or counts["universe"] > search.total_budget)
            self.tie = len(heap)
            if admit is not None:
                uids = [m.member.user_id for m in members]
                kept = [e for e in heap if admit(uids[e[3]], *_screened_package(e))]
                counts["rules_rejected"] = len(heap) - len(kept)
                heap[:] = kept
            heapq.heapify(heap)
            timings["screen"] = perf_counter() - mark
        timings["verify"] = timings["rank"] = 0.0
        self.proofs, self.done, self.capped = {}, set(), []
        # signature -> (weaker, card, decoded proof); ascending weaker supports
        self.eligible, self.weakers = {}, []
        self.served = []
        # Revision 2 (term_precedence): family members by key, families held up
        # to a market loss, and the current horizon L.
        self.terms = getattr(generator, "term_precedence", None) is not None
        self.families, self.losses, self.covered, self.horizon, self.exact = {}, {}, {}, 0, None

    @contextmanager
    def _context(self):
        """The generators' config scope (thread-local), entered per call."""
        ts = self.search.ts
        with ts._cfg_override(self.search.config), ts.stud_tax_override("market"):
            yield

    def _evaluate(self, index, give, receive):
        key = index, give, receive
        if key not in self.proofs:
            if self.counts["verified"] >= self.max_verifications:
                self.capped.append(key)
                return None
            search = self.search
            search.checkpoint()
            card = _card(search, self.members[index].member, give, receive)
            proof = self.proofs[key] = search.evaluate(card)
            self.counts["verified"] += 1
            if proof.eligible and self.admit is not None and not self.admit(
                    self.members[index].member.user_id, give, receive):
                self.counts["rules_unheld"] += 1
            elif proof.eligible:
                data = proof.decoded()  # reused by quality, decorate and rank
                weaker = data["bilateral"]["weaker_support"]
                card.owner_evaluation = proof
                # Decorated once, before any ranking (as the full loop does:
                # revision 2's term_precedence only trusts proofs that match
                # their card's terms), so trade_id is stable across takes.
                _decorate(card, data)
                self.eligible[index, frozenset(give), frozenset(receive)] = weaker, card, data
                insort(self.weakers, weaker)
        return self.proofs[key]

    def _proven(self, m_target):
        return len(self.weakers) >= m_target and self.weakers[-m_target] > -self.heap[0][0] + _EPS

    def _verify(self, m_target):
        """Advance best-first until the top ``m_target`` are proven; True if proven."""
        search, bounds, heap, done, counts = self.search, self.bounds, self.heap, self.done, self.counts
        while heap:
            if self._proven(m_target):
                return True
            if self.capped:
                return False
            entry = heapq.heappop(heap)
            stage, index = entry[2], entry[3]
            if stage in _SCREENED:
                (give, receive), payload, stage = _screened_package(entry), entry[7:], "pre"
            else:
                give, receive, payload = entry[4:]
            m = self.members[index]
            signature = index, frozenset(give), frozenset(receive)
            if signature in done:
                continue
            focal = len(give) + len(receive) == 2
            if stage == "pre":
                row, a = m.row(give, receive), payload
                priced = search._package(give, receive, search.market)
                counts["priced"] += 1
                if priced is None or priced[0] < bounds.floor:
                    if not focal:  # a below-floor focal pair may still be a parent
                        done.add(signature)
                    continue
                counts["floor_pass"] += 1
                heapq.heappush(heap, (-bounds.priced(a, priced), self.tie, "priced", index, give, receive,
                                      (row, priced)))
            elif stage == "priced":
                counts["support_bounded"] += 1
                heapq.heappush(heap, (-bounds.support(m.viewer, m.other, give, receive, *payload), self.tie,
                                      "support", index, give, receive, None))
            else:
                self._resolve(index, give, receive)
            self.tie += 1
        return False

    def _resolve(self, index, give, receive):
        """Exactly evaluate one universe package; False if the cap stopped it.

        An expansion is served in the best-sorting ordering whose focal parent
        is admitted, and is outside the universe if neither parent is."""
        if len(give) + len(receive) > 2:
            member = self.members[index].member
            for side, _, g, r in sorted(_orderings(give, receive),
                                        key=lambda o: _expansion_key(self.search, member, *o)):
                parent = self._evaluate(index, *((g[:1], r) if side == "give" else (g, r[:1])))
                if parent is None:
                    return False
                if parent.eligible or parent.reason in _CURABLE:
                    if self._evaluate(index, g, r) is None:
                        return False
                    break
        elif self._evaluate(index, give, receive) is None:
            return False
        self.done.add((index, frozenset(give), frozenset(receive)))
        return True

    def _family(self, key):
        """Every universe package of a ``term_precedence`` family that ``can_clear``
        the floor, as ``(loss floor, give, receive)`` sorted: the loss floor
        bounds the market loss |rv - gv| / max(rv, gv) from below with the
        same price envelope (0 when it is off)."""
        known = self.families.get(key)
        if known is None:
            index, side, ids = key
            m, bounds, market = self.members[index], self.bounds, self.search.market
            ids = tuple(sorted(ids))
            if side == "give":
                packages = [(ids, (r,)) for r in m.receive_pool]
                if len(ids) == 1:  # plus every 1x2 with this give, once
                    packages += [(g, r) for r0 in m.receive_pool for g, r in m.expansions(ids, (r0,), canonical=True)
                                 if len(r) == 2]
            else:
                packages = [((g,), ids) for g in m.give_pool]
                if len(ids) == 1:
                    packages += [(g, r) for g0 in m.give_pool for g, r in m.expansions((g0,), ids, canonical=True)
                                 if len(g) == 2]
            known = []
            for give, receive in packages:
                gv, rv = [market[p] for p in give], [market[p] for p in receive]
                g_lo, g_hi = bounds.side_price(gv, max(rv))
                r_lo, r_hi = bounds.side_price(rv, max(gv))
                if bounds.can_clear(g_lo, g_hi, r_lo, r_hi):
                    known.append((1 - g_hi / r_lo if r_lo > g_hi > 0 else 1 - r_hi / g_lo if g_lo > r_hi > 0
                                  else 0.0, give, receive))
            known.sort()
            if self.admit is not None:
                uid = m.member.user_id
                known = [entry for entry in known if self.admit(uid, entry[1], entry[2])]
            self.families[key] = known
        return known

    def _loss(self, give, receive):
        """The market loss |rv - gv| / max(rv, gv) of the pricing call the proof's
        ``worst_adjusted_market_loss`` comes from (``bilateral._Search._owner``),
        or None below the floor (never eligible)."""
        key = give, receive
        if key not in self.losses:
            priced = self.search._package(give, receive, self.search.market)
            self.losses[key] = (None if priced is None or priced[0] < self.bounds.floor
                                else abs(priced[2] - priced[1]) / max(priced[2], priced[1]))
        return self.losses[key]

    def _complete(self, index, card, data):
        """Hold every eligible member of ``card``'s two families that is cheaper
        than it (all ``term_precedence`` can make its predecessor); False if capped."""
        terms = data.get("term_efficiency") or {}
        loss = terms.get("worst_adjusted_market_loss")
        if not isinstance(loss, (int, float)) or not math.isfinite(loss):
            return True  # not a term record: never in a family, never delayed
        for key in ((index, "give", frozenset(card.give_player_ids)),
                    (index, "receive", frozenset(card.receive_player_ids))):
            if self.covered.get(key, -math.inf) >= loss:
                continue
            for floor, give, receive in self._family(key):
                if floor > loss + _COST_SLACK:
                    break  # strictly costlier, as is every later member
                if (index, frozenset(give), frozenset(receive)) in self.done:
                    continue
                exact = self._loss(give, receive)
                if exact is None or exact > loss + _COST_SLACK:
                    continue  # ineligible, or strictly costlier: never a predecessor of this card
                before = self.counts["verified"]
                resolved = self._resolve(index, give, receive)
                self.counts["family_verified"] += self.counts["verified"] - before
                if not resolved:
                    return False
            self.covered[key] = loss
        return True

    def _exact_terms(self, k):
        """Revision 2's first k: grow the horizon L until its exact prefix covers k.

        Returns (complete, ranked cards); see the module docstring for the proof."""
        from . import trade_gen_bilateral as bilateral
        horizon = self.horizon = max(self.horizon, k)
        while True:
            if not self._verify(horizon + _LOOKAHEAD):
                if not self.heap and not self.capped:  # the whole inventory is held
                    held = [(card, data) for _, card, data in self.eligible.values()]
                    ranked = _rank_decoded(self.generator._rank, held)
                    self.exact = len(ranked)
                    return True, ranked
                return False, _rank_decoded(self.generator._rank, self.prefix(horizon))
            held = self.prefix(horizon)
            first = _rank_decoded(bilateral._rank, held)[:horizon]
            index_of = {m.member.user_id: i for i, m in enumerate(self.members)}
            data_of = {id(card): data for card, data in held}
            complete = all(self._complete(index_of[card.target_user_id], card, data_of[id(card)])
                           for card in first)
            union = {signature: (card, data) for signature, (_, card, data) in self.eligible.items()
                     if (signature[0], "give", signature[1]) in self.covered
                     or (signature[0], "receive", signature[2]) in self.covered}
            for card, data in held:
                union[index_of[card.target_user_id], frozenset(card.give_player_ids),
                      frozenset(card.receive_player_ids)] = card, data
            ranked = _rank_decoded(self.generator._rank, list(union.values()))
            if not complete:
                return False, ranked
            inside = {id(card) for card in first}
            exact = next((i for i, card in enumerate(ranked) if id(card) not in inside), len(ranked))
            self.exact = exact
            if exact >= k:
                return True, ranked
            horizon = self.horizon = horizon + max(8, k // 8)

    def prefix(self, n):
        """The proven quality-sorted prefix of length n + 31 (after ``take(n)``)."""
        held = [(card, data) for _, card, data in self.eligible.values()]
        return sorted(held, key=lambda item: _quality(*item))[:max(int(n), 0) + _LOOKAHEAD]

    def take(self, n):
        """The proven first ``n`` cards plus a report (see ``first_page``)."""
        k = max(int(n), 0)
        timings, search = self.timings, self.search
        with self._context():
            mark = perf_counter()
            if self.terms:
                complete, ranked = self._exact_terms(k)
            else:
                proven = self._verify(k + _LOOKAHEAD)
                complete = proven or (not self.heap and not self.capped)
            timings["verify"] += perf_counter() - mark

            mark = perf_counter()
            search.checkpoint()
            if not self.terms:
                ranked = _rank_decoded(self.generator._rank, self.prefix(k))
            page = [_hand_out(card) for card in ranked[:k]]
            for index, card in enumerate(page):
                card.composite_score = card.mismatch_score = float(len(page) - index)
            search.checkpoint()
            timings["rank"] += perf_counter() - mark
        identities = [(c.target_user_id, tuple(c.give_player_ids), tuple(c.receive_player_ids)) for c in page]
        stable = all(identities[:len(earlier)] == earlier[:len(identities)] for earlier in self.served)
        self.served.append(identities)
        timings["total"] = sum(timings[name] for name in ("setup", "pools", "screen", "verify", "rank"))
        counts, generator = self.counts, self.generator
        report = {"generator": generator.ARM, "generator_version": generator.VERSION,
                  "page_first_version": PAGE_FIRST_VERSION, "bound": BOUND_VERSION,
                  "score_kind": "interpretable_support_not_probability", "k": k, "returned": len(page),
                  "universe": counts["universe"], "bounded": counts["bounded"], "priced": counts["priced"],
                  "floor_pass": counts["floor_pass"], "support_bounded": counts["support_bounded"],
                  "verified": counts["verified"], "eligible_verified": len(self.eligible),
                  "complete": complete, "incumbent_budgets_bind": self.bind,
                  "price_envelope": self.bounds.envelope, "max_verifications": self.max_verifications,
                  "takes": len(self.served), "prefix_stable": stable,
                  "term_horizon": self.horizon if self.terms else None,
                  "term_exact_prefix": self.exact if self.terms else None,
                  "families_completed": len(self.covered), "family_verified": counts["family_verified"],
                  "elapsed_ms": {name: round(value * 1000, 3) for name, value in timings.items()}}
        if self.admit is not None:
            report.update(rules_version=self.rules_version, rules_rejected=counts["rules_rejected"],
                          rules_unheld=counts["rules_unheld"])
        return page, owner.OwnerGenerationReport(owner._dump(report))


def first_page(*, k=30, generator=None, max_verifications=4000, **kwargs):
    """Return the proven first ``k`` cards plus a report, or None if unsupported.

    ``None`` means the caller should run full generation: pinned assets,
    ``exact_give`` and ``require_all_give`` are out of scope for v1. One-shot
    wrapper over ``PageSearch``; use that directly to deliver a page in parts.
    """
    if not _supported(kwargs):
        return None
    return PageSearch(generator=generator, max_verifications=max_verifications, **kwargs).take(k)


def _rank_decoded(rank, held):
    """``rank`` (a generator's ``_rank``) over ``held`` (card, decoded proof) pairs, no re-decoding.

    The rankers call ``proof.as_dict()`` (bilateral-1 once per card, revision 2
    twice more in ``term_precedence``). They rank private twins instead: a
    shallow card copy whose proof is an equal ``OwnerDecisionContext`` (same
    frozen fields and bytes) with ``as_dict`` answering the dict this search
    already decoded from those bytes. The ranker code is unchanged, the real
    proofs (possibly already handed out by an earlier take) are never touched
    or serialised, and the result is mapped back to the real cards. Rankers
    only read.
    """
    twins = {}
    for card, data in held:
        twin = copy.copy(card)
        twin.owner_evaluation = card.owner_evaluation.twin()
        object.__setattr__(twin.owner_evaluation, "as_dict", (lambda data: lambda: data)(data))
        twins[id(twin)] = twin, card
    return [twins[id(twin)][1] for twin in rank([twin for twin, _ in twins.values()])]


def _quality(card, data=None):
    """bilateral._rank's quality tuple (it re-derives the same from the proof)."""
    s = (data or card.owner_evaluation.as_dict())["bilateral"]
    return (-s["weaker_support"], -s["total_support"], -s["preference_fulfillment"],
            len(card.give_player_ids) + len(card.receive_player_ids), card.target_user_id,
            tuple(card.give_player_ids), tuple(card.receive_player_ids))


def _decorate(card, data):
    """Replicates the survivor block of bilateral._generate_with_search (organic only)."""
    card.owner_group, card.owner_groups = data["direction"], tuple(data["compatible_groups"])
    card.give_value, card.receive_value = data["market"]["give"], data["market"]["receive"]
    card.fairness_score = data["market"]["ratio"]
    card.trade_id = "bilateral_" + uuid.uuid4().hex
    card.basis = "consensus" if data["viewer"]["preference_evidence"]["state"] == "unknown" else "divergence"
    card.lane = "window" if data["viewer"]["team_plan_gain"] > .01 else "value"
    card.reasons = []
    if not data["construction"]["small"]:
        card.reasons.append("Larger package to include your selected assets.")
    if data["counterparty"]["preference_evidence"]["state"] == "unknown":
        card.reasons.append("Other manager’s preferences are unknown; fit uses market and team context.")
    card.match_context = {"owner_benefits": data["viewer"]["benefits"],
        "counterparty_benefits": data["counterparty"]["benefits"],
        "counterparty_preference_evidence": data["counterparty"]["preference_evidence"]["state"],
        "support_kind": "interpretable_support_not_probability"}
    return card
