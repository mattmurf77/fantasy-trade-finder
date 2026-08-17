# Plan — dismissed ("pass") suggestions come back

> Operator report 2026-08-17: *"Users are reporting that they're getting the
> exact same suggestions between sessions in the same order. There needs to be
> a cool down process after a 'pass' decision."*
> Base: `origin/main` @ `ac71a67`. Branch `fix/pass-cooldown`.

## Vocabulary (three different actions, easily conflated)

| UI label | API | Meaning |
|---|---|---|
| **Dismiss** (swipe-left on a deck card) | `POST /api/trades/swipe` `decision:'pass'` | Rejecting an engine-invented *suggestion*. Private, cheap, high-volume. **This plan's subject.** |
| **Decline** | `POST /api/trades/matches/<id>/disposition` `decision:'decline'` | Backing out of a **mutual match** a real league-mate already agreed to. Heavy: K=20 corrective Elo + 30-day near-duplicate suppression. |
| **Dismiss** (awaiting) | `POST /api/trades/awaiting/dismiss` | Retracting a trade you sent that's pending the other owner. Got windowless exclusion in #336. |

The UI word "dismiss" maps to the API's `pass`, and a *different* endpoint is
literally named `dismiss`. Anyone reading this code will conflate them at least
once; that is why this table is first.

## Diagnosis (evidence, 2026-08-17)

**Dispositions save correctly — that is not the bug.** Prod `trade_decisions`:
496 passes, 314 likes, newest same-day. `save_trade_decision` fires on every
swipe (`server.py:10739`); `load_trade_decisions` applies **no** decision filter
so passes are loaded; `_dedup_and_sort` (`trade_service.py:2884`) correctly drops
any card whose `(frozenset(give), frozenset(recv))` key matches a past decision.
Only 8 duplicate-decision groups exist across 810 decisions.

**What actually happens.** `deck.fatigue` is ON in prod, but it has two tiers and
a dismiss only earns the weak one:

- **Decline** → durable hard suppression row (`deck_suppressions`), 30 days,
  kills near-duplicates (centerpiece + shape bucket + value band).
  `_save_decline_suppression` is reached **only** under
  `decision == "decline"` (`server.py:13977`).
- **Dismiss/pass** → a **score multiplier only**, floored at
  `fatigue_floor = 0.25`. It demotes; it never removes.

`deck_suppressions` has **0 rows in prod** — the hard path has never fired for
any user.

**Three ways a dismiss fails to stick:**

1. **Soft demotion, not removal.** A dismissed card keeps ≥25% of its score and
   can resurface at the top of a thin league.
2. **The one hard filter expires at 7 days.** `past_decision_keys` loads with
   `since_days=7` (`server.py:15735`). **495 of 810 prod decisions (61%) are
   already outside that window** and suppress nothing. Declines get 30 days.
3. **A dismiss does not bind until the next `session_init`.** The swipe route
   writes the DB row but never updates the live `TradeService`'s in-memory
   `_past_decision_keys`. Regenerating inside one session can re-serve the card
   just dismissed (prod trace: one trade decided 5× in 6 minutes).

**Why the order is identical.** The final sort is
`sorted(cards, key=composite_score, reverse=True)` — no randomization, rotation
or shuffle anywhere in `trade_service.py`, and `deck_impressions` is written on
every serve but **never read back at generation**. Same league state ⇒ same
candidate set ⇒ same order.

**Scope decision (operator, 2026-08-17):** re-showing a card that was *served
but never acted on* is acceptable and stays as-is. Only dismissed cards are in
scope. (Context for why that matters: the reporting user logged 4,003
impressions against 61 decisions in 14 days — 98.5% of repetition is un-acted
cards, deliberately left alone.)

## Fix

Three surgical changes. **No new table, no schema change, no new flag** — the
existing exact-pair mechanism is widened, made live, and given a knob.

### R-1 — Dismiss cooldown gets its own window (default 14 days)

`server.py:15733-15742` partitions `load_trade_decisions` rows by
`td["decision"]` and applies a per-type window:

- `pass` → new knob **`pass_cooldown_days`** (default **14.0**)
- `like` → unchanged 7-day behavior (a like that matured into a match/awaiting
  is already excluded windowlessly by #336's R4; this window only covers likes
  that never matched)

The DB read widens to `since_days = max(pass_cooldown_days, 7)` and the
per-row cut happens in Python, so one query still serves both.

**Why 14 and not 30:** a dismiss is a far cheaper signal than a decline — it is
one swipe against an invented hypothesis, not a rejection of a deal a
league-mate agreed to. 14 days lets a genuinely changed market resurface a name
without the user seeing it again this week or next.

### R-2 — A dismiss binds immediately, in every format

In the swipe route after `save_trade_decision`, add the key to the in-memory set
of **every** service in `sess["trade_svcs"]` (not just `sess["trade_svc"]`).

`sess["trade_svc"]` aliases `trade_svcs[active_format]` (`server.py:2308`,
`:7034`), so updating only that handle leaves a stale set on every *other*
scoring format's service — the card returns after a format switch. Applies to
`pass` only; `like` keeps today's behavior.

### R-3 — The knob is the kill switch

`pass_cooldown_days` lands in `trade_service._DEFAULT_CFG` and
`database._MODEL_CONFIG_DEFAULTS` (the G6 pattern), so the cooldown is tunable
— and revertible to today's behavior by setting it to `7` — via
`PUT /api/admin/config/<key>` with no deploy. No new feature flag: this is a
bug fix, and a flag would add a surface with no rollback value the knob doesn't
already give.

### Explicitly NOT doing: near-duplicate suppression

Declines kill near-duplicates (same centerpiece + shape + value band). Applying
that to dismisses would let one dismissive swipe silence a player's entire trade
space, and dismisses outnumber declines by orders of magnitude (496 vs 0 rows).
Exact-pair matching is sufficient for the reported symptom — the 41-job repeat
was the *same* `trade_hash`, i.e. byte-identical assets. If repetition persists
as near-variants after this ships, widening is a follow-up with its own
evidence, not a guess bundled in now.

## Tests (D-056 — no Maestro/simulator; every test proven-to-fail on a sabotage)

| ID | Assertion | Sabotage that must turn it RED |
|---|---|---|
| T-1 | A pass 3 days old is excluded from a fresh generation | restore `since_days=7` → still passes (control); set window to 1 day → RED |
| T-2 | A pass 20 days old **is** re-served (two-sided — the cooldown expires) | make the window unbounded → RED |
| T-3 | `pass_cooldown_days = 7` reproduces today's exact behavior (revert path) | ignore the knob, hardcode 14 → RED |
| T-4 | Swipe→regenerate **within one session** excludes the card, no `session_init` | drop the in-memory update → RED |
| T-5 | Same, **after a scoring-format switch** | update only `sess["trade_svc"]`, not the dict → RED |
| T-6 | A `like` is unaffected by `pass_cooldown_days` | apply the pass window to likes → RED |
| T-7 | Likes-you injection unchanged (Q21: quality rules never applied there) | route the injector through the pass filter → RED |

Plus: full backend pytest, `import backend.server` smoke. Runtime proof is an
operator TestFlight checklist (dismiss a card → regenerate → confirm absent;
repeat after switching scoring format).

## Risk

**Deck thinning.** Every exclusion mechanism competes for the same finite
candidate pool, and G6's presentment rules already kill 18.4% of cards. Doubling
the dismiss window will thin decks further for heavy swipers in small leagues.
Mitigation: measure before/after empty-deck rate against the D-055 bar (<5%)
during the build, and report it — the knob is the lever if it breaches.

---

## Build record — 2026-08-17

**Shipped as specced.** Decision record: **D-067**. Branch `fix/pass-cooldown`.

| Req | Where |
|---|---|
| R-1 per-type window | `backend/server.py` session_init — one query at the widest window, per-row cut by `td["decision"]`; unparseable stamp **fails closed** (keeps excluding) |
| R-2 immediate bind | `backend/server.py` swipe route, gated `decision == "pass"`, traverses every service in `sess["trade_svcs"]` plus the aliased handle; best-effort try/except so a swipe never fails on bookkeeping |
| R-3 knob | `trade_service._DEFAULT_CFG` + `database._MODEL_CONFIG_DEFAULTS` (`pass_cooldown_days = 14.0`) |

**Tests:** `backend/tests/test_pass_cooldown.py` — 10 passing. Full backend
suite **3060 passed / 1 skipped / 0 failed** (was 3050 pre-change).

**Sabotages — each applied, observed RED, reverted:**

| Sabotage | Caught by | Result |
|---|---|---|
| `unbounded-window` (drop the age comparison) | 3 tests incl. the two-sided expiry bar | RED |
| `one-window` (apply the dismiss window to likes too) | like-independence | RED |
| `fail-open` (treat a bad timestamp as expired) | fail-closed test | RED |
| `db-only` (no in-memory update) | both R-2 tests | RED |
| `alias-only` (update `trade_svc` alone, not the dict) | **only** the format-switch test | RED |

The `alias-only` result is the one worth keeping: it REDs exactly one test —
the format-switch case — proving that test catches the alias trap and isn't
redundant with the same-session test.

**Operator principle recorded in D-067** — *"accuracy, not volume; bad
suggestions are worse than limited suggestions."* This governs the deck-thinning
tradeoff: when a cooldown and the D-055 empty-deck bar conflict, report the
number and keep the exclusion.

**Owed at ship:** the empty-deck measurement named in §Risk (deck-eval before/
after), and an operator TestFlight pass — dismiss a card, regenerate, confirm
absent; repeat after switching scoring format (the R-2 path that unit tests
cover structurally but not on-device).
