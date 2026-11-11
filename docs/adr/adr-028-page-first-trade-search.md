# ADR-028: Page-first trade search — bound, verify, stop

Date: 2026-11-10
Status: Accepted; serving superseded by [ADR-030](adr-030-rules-first-deck.md) (2026-11-11):
the 150-card fast deck and its flags (`trade.fast_deck`, `trade.fast_deck_shadow`) are retired,
and the search now builds the whole rules-admitted inventory. Originally wired into the trade
worker as the **fast deck**, behind two flags that shipped off. Publishing a first page
and then appending the rest of the inventory is still a separate decision (recommendation R3).

## Context

The owner-bilateral constructors evaluate every candidate and rank every survivor before a
first card can be shown: about 45,000 exact evaluations and 3,900 survivors for a 12-team
league, 3–4 s of construction on a laptop and longer in production. The first page is a
delivery prefix of finished work, so cold latency scales with the inventory, not the page.
Latency is currently bought with preparation (app-open warm-up, device pages, prepared
inventories), which misses exactly when inputs have just changed.

An exact speed-up of the full solve was tried first and measured 1.15–1.18×. After removing
redundant work, what remains is unique per candidate. A byte-identical full inventory cannot
be made several times cheaper in Python.

## Decision

Add `backend/trade_first_page.py`, a search that returns the first k cards without building
the rest:

1. Give every candidate an **admissible upper bound** on `weaker_support`, the leading term
   of the rank's quality tuple. Three levels, each cheaper and looser than the next: before
   pricing (a proven envelope on market package price), after pricing (lineup need bounded),
   and the exact two-sided support.
2. **Verify best-first with the unchanged evaluator.** The bound only orders work. Gates,
   price and the frozen proof still come from the constructor's own `evaluate`, so a page
   card is exactly the card the full generator would emit for that package.
3. **Stop with a proof.** `bilateral._rank` chooses each output from a 32-item lookahead of
   the quality-sorted list, so its first k outputs depend only on the sorted prefix of
   length k + 31. Once k + 31 eligible cards are held and the last of them beats every
   remaining bound, that prefix is exact and the tail cannot change the page.

Three further choices keep one search cheap enough to wait behind another:

4. **Serialise only what leaves.** The constructor's search runs as a private subclass.
   Ineligible results keep only their reason, and an eligible proof's final serialisation
   is deferred until a card is actually returned, when the incumbent's own method builds it
   from the same dict. Ordering reads that dict, which equals the decode of the final bytes.
5. **Memoise by content, never by identity.** Two bounded process-wide memos serve repeated
   work across searches: roster lineup assignments, and tier coordinates used in search
   construction. Each key is everything the function reads (slots, asset values, positions;
   position, Elo, format and the tier bands), so an entry cannot go stale: a changed input
   is a different key. No league or user id appears in a key.
6. **Resume instead of restart.** `PageSearch(**kwargs).take(n)` returns the first n proven
   cards and can be called again for more without repeating setup, pools or the screen.

7. **Revision 2 is exact through family completion.** Revision 2 ranks by the baseline
   order and then delays a card behind any cheaper alternative in its two families (same
   partner and the same exact give side, or the same exact receive side), which the full
   solve finds across the whole inventory. The page search picks a horizon L ≥ k, proves the
   baseline's first L, exactly evaluates every family member that is cheaper than each of
   those L cards, and ranks the union with the unchanged revision-2 ranker. The outputs
   before the first card from outside the first L are the full solve's; if there are fewer
   than k, L grows and the search resumes.

The module is a leaf, takes the same keyword arguments as the generators, and returns `None`
for requests it does not cover (pinned or exact-give searches), which fall back to the full
solve.

### Serving: the fast deck

`backend/trade_fast_deck.py` puts the search on the worker's owner-generator call
(`server._run_trade_job`). With `trade.fast_deck` on, an interactive owner-serve job gets the
proven first 150 cards as its whole deck and runs the unchanged final checks, evidence and
publication on them, in one pass. It was built as one pass because the worker's final checks
have side effects (exposure events, suppression grants, one candidate set and one evidence
seal per job), so running them once for a page and again for the inventory is not safe
without changing those contracts.

- **The deck ends at 150 cards.** The rest of the inventory is not built for it. In
  production the deepest card acted on between 2026-09-01 and 2026-11-10 was index 65.
- **The full solve still runs** for prepared inventories, replenishment and Calibration's
  refresh; for generators without a parity suite; for pinned and exact-give requests; when
  the page is not proven within 12,000 exact evaluations; when the incumbent's stream
  budgets would bind; and on any error.
- **`trade.fast_deck_shadow`** serves the full solve and logs one comparison per job. It
  exists to confirm agreement and timing on production before the serve flag is turned on.

## Consequences

- On the synthetic 12-team league the first 30 cards take about 41–46 ms once the process
  has seen the league and 73–82 ms the first time, against 3–4 s for the full solve, after
  100–140 exact verifications of 45,056 candidates. The first 5 cards take about 31–34 ms
  and 60–65 ms. Peak memory is about 16 MB per search against about 252 MB.
- One process completes about 20 searches a second under load, against 6.3 for the first
  version of this module ([scale](../plans/realtime-trade-engine/scale.md)).
- For both generators the page is the full generator's first k, with identical proofs,
  whenever the report says `complete` and the incumbent's stream budgets do not bind. On 247
  recorded production requests the 150-card deck matched on all 247
  ([real leagues](../plans/realtime-trade-engine/real-leagues.md)). For revision 2 the
  argument rests on two tested properties: the same candidate universe, and a card's market
  loss being a pure function of its terms.
- Exactness for revision 2 costs work. On recorded production requests a 30-card page takes
  about 0.28 s and the 150-card deck about 0.55 s (medians, one process), against about 5.9 s
  for the full solve: roughly ten times faster, not the thirty to eighty times the synthetic
  league showed. More than half of the exact evaluations are family members.
- "Identical" means inside one process. The full generators' own output varies between
  processes with Python's hash seed (the same request gave 2,609 and 2,616 cards), so a page
  and a full solve from different processes can differ exactly as two full solves can.
- The pre-pricing bound depends on the shape of `trade_service._package_value_market`. It is
  pinned by a property test and disables itself outside its proven config range; **a change
  to market package pricing must re-run `test_trade_first_page.py`**.
- The lineup-need bound rests on the roster assignment being a maximum-weight assignment
  with a unique optimum. Ties are checked empirically by an exhaustive audit, not proved.
  The cost of a violation would be a slightly better card missing from the page, never an
  invalid card.
- Deferred serialisation relies on the constructor not touching a proof's dict after
  enriching it, and the coordinate memo on `_coordinate` reading only position, Elo, format
  and the tier bands. Both are pinned by exhaustive tests; a constructor or ranking-service
  change that breaks either assumption fails those tests rather than the page.
- The module now holds process memory between requests: the two memos are capped at about
  30 MB and 17 MB.
- It is intricate. About 1,220 lines and 172 tests; the plain version is recoverable from
  this branch's history if the trade is ever judged not worth it.
- `_run_trade_job` changed, so `DECK_PIPELINE_VERSION` moved 15 → 16 and stored first pages
  rebuild once after deploy. The two modules are in the stored-page engine hash.
- Publishing a page and then appending the inventory would change the owner publication
  contract (published prefix equals the head of the finished inventory; global impression
  ordinals; one evidence seal per job) and is deliberately left to its own scope.

## Alternatives considered

- **Exact fast kernel for the full solve.** Built, byte-identical, 1.15–1.18×, about 75% more
  peak memory. Removed.
- **Approximate first page (show the first survivors found).** Rejected: it changes which
  trades lead the deck, which the acceptance audit already ruled out.
- **A NumPy screen.** Measured in a scratch experiment at 5–7 ms against about 9–12 ms in
  plain Python, roughly 10% of a search. Not taken: it adds a runtime dependency the backend
  does not have, a second copy of the bound arithmetic to keep admissible, and needs lazy
  materialisation to realise the gain.
- **More preparation.** Already built; it cannot cover a scope that did not exist before the
  tap.

Evidence and limits: [scope](../plans/realtime-trade-engine/scope.md) ·
[recommendation](../plans/realtime-trade-engine/recommendation.md) ·
[scale](../plans/realtime-trade-engine/scale.md).
