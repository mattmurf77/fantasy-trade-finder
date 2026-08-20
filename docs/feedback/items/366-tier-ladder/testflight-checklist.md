# Manual TestFlight checklist — #366

**Date written:** 2026-08-20 · **Run by:** operator · **Status:** not yet run

Both flags ship **OFF**, so steps 1–2 are the release-safety check and can run
against the current build. Steps 3–6 need the flags lit *and* a client build
carrying this branch's `TeamReviewScreen`.

Under [D-056](../../../../living-memory/DECISIONS.md) this is the only runtime
evidence mobile gets, so each step names what would count as a **failure**, not
just what to look at.

**Flag control (deploy-free, no build):** edit `config/features.json`, then
`POST /api/feature-flags/reload` with the `CRON_SECRET` header. Flipping a flag
back off removes its effect from the **next fetch** — no client release needed,
because the screen renders on key presence.

---

### 1. Flags off — nothing moved (run first, on the CURRENT build)

1. Both flags `false`. Open **Trades → Team Review** on a Sleeper league.
2. The **depth** beat reads exactly as before: `QB  1 elite · 2 starter  ok`.
   No "Replacement" column, no handcuff line.
3. Generate a deck on the same league. Note the top 3 cards.

**FAIL if:** the depth beat shows a Replacement count or a handcuff sentence
while the flags are off. That would mean the flag gate leaks and every claim in
this batch about deck safety is void.

### 2. Flags off — the deck is unchanged (the real release gate)

Same league, same session as step 1. Re-generate the deck twice more.

**FAIL if:** the cards differ from step 1's in a way the deck's own
non-determinism (Thompson sampling, diversity) does not explain. The
byte-identity claim is about `position_needs` / `position_surplus`, which
reshape *every* deck — a change here means the flag-off path is not the legacy
path, and nothing else on this list matters until it is.

### 3. `trade.rb_handcuff` ON — check it against a real depth chart

This is the step that catches a wrong tag rather than a missing one.

1. Light `trade.rb_handcuff` only. Reload flags. Re-open Team Review.
2. Read the handcuff sentence under "Startable bodies by position".
3. **Open nfl.com (or Sleeper's own player pages) and list your RBs.** Count
   how many are their team's **RB2**.

**PASS:** the two counts match.
**FAIL if:** they differ. Report *which* player was mis-tagged and his team —
a mismatch is either a stale sync (see step 4) or a bug in `_is_handcuff`, and
which one it is depends on the specific player.
**Also FAIL if:** the sentence claims a handcuff for an RB who is his team's
clear RB1. Sleeper occasionally leaves an order stale after a depth-chart
change; that is the staleness surface D-121 documents and is worth knowing
about even though it is not our bug.

### 4. Handcuff — the zero case says the right thing

Switch to a league (or a roster) where you own no RB2.

**PASS:** the line reads *"No handcuffs — none of your RBs is the RB2 on his
NFL depth chart."*
**FAIL if:** the line disappears entirely. Absent means "we did not look";
zero means "we looked". If zero renders as absent, the honesty distinction the
whole design rests on is not actually working.

### 5. `trade.position_tiers` ON — Elite stops meaning four things

1. Light `trade.position_tiers` as well. Reload flags. Re-open Team Review.
2. Each position row now reads `N Elite · N Starter · N Replacement`.
3. **Sanity-check the TE row against your own roster.** Under the old logic a
   top-10 TE was frequently *not* elite while your RB3 was. Under the new one,
   an elite TE should be someone you would call a genuine top-6 dynasty TE.

**PASS:** the Elite counts feel like they mean the same thing at QB, RB, WR and
TE — that is the entire ask in #366.
**FAIL if:** a position shows an implausible Elite count (e.g. 5 elite TEs on
one roster), or if `Replacement` counts look identical to `Starter` counts
across the board.
**In a superflex league**, expect the QB Elite count to be more generous than
in your 1QB league — that is `_POS_TIER_CUTS_SF_QB` and it is intended.

### 6. `trade.position_tiers` ON — the deck moves, and you decide whether you like it

**Do this last, and do it deliberately.** This flag changes
`position_needs` / `position_surplus`, so it changes the deck.

1. Re-generate the deck on the league from step 1.
2. Compare against the cards you noted there.

**Expected:** the deck DOES change. That is not a bug — it is the reason this
flag exists and the reason it ships off.
**The judgement call, which is yours and not the builder's:** are the new
cards better targeted at your actual holes? If the chase/shop suggestions now
point somewhere you disagree with, **turn the flag back off** and say so — the
bands are a modelling choice, and the honest response to "the decks got worse"
is a re-tune, not persuasion.

Whatever you decide, note it in `living-memory/TEST_LEDGER.md` — the flag
should not graduate on a green test suite. The pre-existing engine tests were
measured during the build and are **completely insensitive** to this change
(their fixture pools are too small to distinguish the bands), so your read
here is the only real evidence the deck side has.

---

**Leave both flags OFF when you are done** unless you are consciously
graduating one.
