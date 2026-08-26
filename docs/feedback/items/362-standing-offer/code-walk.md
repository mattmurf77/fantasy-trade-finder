# #362 Standing offers — code-walk proof (merged tree, 2026-08-26)

> D-056 retired the simulator; this written walk is the required substitute for
> runtime evidence. Line numbers are the merged tree (branch `feat/jon-360-362`
> after the merge of `origin/main` @ 867c3baa). The PRD is `prd.md`; the
> item-scoped design decision is D-362-1 (`hld-delta.md` §9).

## 1. The flag is the perimeter (dark ⇒ byte-identical)

`backend/server.py:3044` — `_standing_offers_enabled()` reads
`trade.standing_offers` (default **false**, `config/features.json`). Every
surface checks it:

- Routes 404 `feature_disabled` before any session work:
  `POST /api/trades/standing-offer` (`:16688`, gate `:16708`),
  `GET /api/trades/standing-offers` (`:16793`, gate `:16808`),
  `POST /api/trades/standing-offer/revoke` (`:16852`, gate `:16865`).
- The injector loads offers only when on (`:3370-3371`; off ⇒ `[]`, and the
  `if not likes and not _offers` early-out `:3373` behaves exactly pre-#362).
- The sender-side chip stamp runs only when on (`:6244-6250`,
  `_stamp_own_standing_offers` def `:3090`).
- Serialization is key-only-when-set (`trade_card_to_dict`
  `:11726-11733`), so flag-off payloads carry no new key.
- Mobile: the prompt requires `standingOfferReady` =
  `trade.standing_offers` ∧ `trade.likes_you` ∧ `trade.picks_in_pool`
  (`mobile/src/screens/TradesScreen.tsx:669-673`, checked first at `:3810`);
  the Matches manage segment is gated at
  `mobile/src/screens/MatchesScreen.tsx:657`.

## 2. The post-like prompt (PRD: right-swipe on a 1-for-1 receiving a 1st)

`mobile/src/screens/TradesScreen.tsx:4985` — `maybeShowStandingOfferPrompt`
is called LAST in the post-like ladder (comment `:4980-4984`: the like is
already banked and the deck already advanced, so dismissing the sheet can
never cost the like). The gate (`:3808-3874`) requires, in order: all three
flags; once per app session and never over an open sheet; not the first like
(that moment belongs to the celebration chain); no competing surface
(quickset / guide / Apple ask); a real, unpinned, unscoped league deck; the
snooze→session-2→retired ladder; **a 1-for-1** (`:3836`); the received asset
an OWNED league pick (`:3843`) whose authoritative row in `all_picks` has
`round === 1` (`:3852-3853`); prefetches resolved FAIL-CLOSED (`:3847-3850`);
no live offer already covering (player, round) (`:3856-3863`); at least one
other member (`:3866`).

The sheet itself (`mobile/src/components/StandingOfferSheet.tsx`) is a true
sheet — an RN `<Modal transparent animationType="slide">` (`:250`) — so under
the CLAUDE.md FeedbackFAB rule it mounts no FAB (modals/sheets are exempt),
and its host `TradesScreen` is a tab-stack screen covered by the RootNav
global mount (no new FAB in this diff). It asks which OTHER seasons
(year pills derive from `all_picks` — never a hardcoded window, the #355/D-091
class) and which teams; posting calls `createStandingOffer`
(`:217`, api `mobile/src/api/trades.ts:811`) → the POST route.

## 3. The write (server-side validation)

`backend/server.py:16688-16790`: requires league/player/round/seasons/teams;
`round != 1` ⇒ 400 (v1 is firsts only); seasons outside the league's actual
round-1 pick horizon ⇒ 400 with `allowed_seasons`
(`league_pick_seasons`, `backend/database.py:5760`); non-member team ids ⇒ 400; at most ONE live offer
per (user, league, player, round) ⇒ 409. `expires_at` is STORED at
`created_at + standing_offer_days` (model_config, default 30 —
`backend/database.py` seed row `standing_offer_days`), never derived at read.
Storage: `standing_offers` table (`backend/database.py:1053`), writer
`create_standing_offer` (`:5653`, the 409 one-live-offer predicate inside it),
readers `load_standing_offers` (`:5703`) / `revoke_standing_offer` (`:5739`).
Knobs seeded at `backend/database.py:2551-2552`.

## 4. The read (those managers get prioritized for that card)

`backend/server.py:3538-3670` — the standing-offer branch of
`_inject_likes_you_cards_impl`, a SECOND candidate source sharing the organic
loop's `seen_keys` / `existing_by_key` / `boost_score` / `injected` state and
the identical filter sequence:

- cap: `so_cap = min(_LIKES_YOU_CAP - injected, standing_offer_inject_cap)`
  (`:3546`; the model_config knob at 0 is the deploy-free kill switch);
- **the selection test** (`:3558`): the viewer must be in the offer's
  `team_user_ids` — the ONLY place that list is read on a path that reaches a
  deck (R-19);
- staleness for free (`:3562`): the sender must still roster the player;
- the viewer's own matching give-pick: owned league picks of that round in the
  offered seasons (`:3568-3578`), chosen deterministically (season ASC,
  pick_id ASC, `:3581`);
- then the same guards as organic mirrors: untouchables, not-interested,
  #360 avoid (`:3590-3593`), seen-keys dedup, past-decision keys, G6 R4,
  the D-055 user-gain floor (`:3607`, the same `min_user_delta` the organic
  loop applies at `:3483`);
- the card is `likes_you = True` at `boost_score` with a server-composed
  `standing_offer_reason` (`:3613`) — prioritization IS the likes-you
  boost, shared cap and all;
- server-fired impression `standing_offer_card_shown` with COUNTS only
  (`:3658-3661` — `round` + number of seasons, never team ids; R-19).

Sender side: `_stamp_own_standing_offers` (`:3090`) decorates the deck
owner's own cards with `standing_offer_mine` `{round, seasons}` — display
only, never reorders/boosts/filters (call site `:6244-6250` is non-fatal).

## 5. Privacy (R-19) — team ids never leave the sender's own surfaces

`team_user_ids` appears in: the POST/GET payloads (the sender's own offers)
and the injector's selection test (`:3558`). The recipient-facing payload
carries only `standing_offer_reason` (a composed string) — `trade_card_to_dict`
`:11726-11729`. Analytics carry counts only: taxonomy rows
`backend/analytics_taxonomy.py` (`standing_offer_prompted/posted/skipped/
revoked` client-side with count props; `standing_offer_card_shown`
server-fired), classified in `backend/analytics_queries.py`
`NON_INTENT_EVENTS` in the same commit (prompted/skipped/card_shown
non-intent; posted/revoked intent). Pinned by
`check-standing-offer-362.js` SC-13/SC-15 and
`test_standing_offers.py` (31 tests, green 2026-08-26).

## 6. Post-merge deltas worth naming

- The organic likes-you loop the branch merged against had already absorbed
  D-096's quality-gate ladder on 2026-08-19; `origin/main` has not moved
  those lines since, and the standing branch consumes the SAME
  `min_user_delta` floor (`:3607` vs the organic `:3483`) — verified by the merged-tree
  suite rather than by eye.
- `origin/main`'s full sweep (`trade.full_sweep`, lit) removes the early
  exit in both opponent loops; the injector runs AFTER generation and is
  unaffected. The #384 fair-package deck builds cards client-side from
  `ideaToCard` and never passes through the injector — no interaction.
