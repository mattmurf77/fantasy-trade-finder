# Decline reason capture — build spec (operator-approved 2026-08-17)

> Tester-only diagnostic replacing the trade-card ✕ with a two-layer reason capture.
> Design settled interactively with the operator; the approved prototype is
> [`mockups/decline-reason-capture/07-two-step-diagnostic.html`](../../../mockups/decline-reason-capture/07-two-step-diagnostic.html)
> (open it — it is the visual + interaction source of truth). Research basis:
> [`docs/research/matchmaking/round-3/01-counteroffer-and-negotiation-loop.md`](../../research/matchmaking/round-3/01-counteroffer-and-negotiation-loop.md),
> [`round-2/03`](../../research/matchmaking/round-2/03-sparse-data-learning-and-evaluation.md) §1.5,
> [`round-2/04`](../../research/matchmaking/round-2/04-closed-communities-and-fantasy-analogs.md).

## 1. What changes, in one paragraph

On a suggested trade the ✓ stays and **the ✕ is removed**. Beneath the card sit three
tiles on one row — **Value · Fit · Neither**. Tapping a tile *is* the pass: it writes the
disposition and the layer-1 reason in one gesture. Layer 2 then opens full-width beneath
the tiles (notched to the tapped tile) with that category's specific options; picking one
writes and advances to the next trade. There is **no receipt screen** — the next trade is
the confirmation.

## 2. Taxonomy (exact — do not improvise labels)

| Layer 1 | Layer 2 option | Code |
|---|---|---|
| **Value** (sub-label "the price") | Giving up too much | `value_giving` |
| | Getting too much | `value_getting` |
| | Other → free text | `value_other` |
| **Fit** (sub-label "my roster") | Doesn't meet my team outlook | `fit_outlook` |
| | Creating a new weakness | `fit_new_weakness` |
| | Addressing the same need twice | `fit_duplicate` |
| | Other → free text | `fit_other` |
| **Neither** (sub-label "tell us") | Won't trade one of my players | `other_player_keep` |
| | Don't want one of their players | `other_player_avoid` |
| | Other → free text | `other_text` |

Layer-1 codes are `value` · `fit` · `other`. **Ten** layer-2 codes.

**"Other → free text" is one code, not two.** An "Other" row banks its own code
(`value_other` / `fit_other` / `other_text`) and the free text then lands in the
row's `free_text` column — the stored `detail` never changes. Earlier revisions
of this table wrote the free-text step as a second arrow (`value_other` to a
`value_other_text`), which reads as a second code; no such code exists and the
route 400s it (`invalid_detail`). Corrected 2026-08-19 alongside the amendment
below.

### 2a. Amendment 2026-08-19 — "Neither" gains player preference (D-079)

**Operator decision, from production evidence.** The 19 pass reasons of the
first burst (2026-08-17, 9 minutes) landed 9 of 19 — **47%** — on **Neither**,
which at the time offered free text and nothing else. It was the single largest
bucket, and reading it showed one reason dominating:

> "Don't like Troy" · "No need to move kelce" (`switched_from = fit`) ·
> "Just not players worth my time" · "I just traded marshawn Lloyd away. It
> doesn't make sense to try and trade back for him."

None of those are price judgements and none are roster-construction judgements.
They are **player-level preference**, a third axis the taxonomy did not have.

**Two codes, not one.** The taxonomy's existing axes split by *whose side is
wrong* (Value) and *what role is wrong* (Fit); player preference splits by side
too, and the free text runs in both directions at n=4:

| Code | Means | The engine fix behind it |
|---|---|---|
| `other_player_keep` | "won't trade one of **my** players" (Kelce) | give-side **keep-list**: stop building packages that send that player out |
| `other_player_avoid` | "don't want one of **their** players" (Troy, Lloyd) | receive-side **avoid-list**: stop sourcing that player for this user |

Those are different code paths — package construction vs. candidate sourcing —
so a single merged code would force reading free text to route the fix, which is
the exact failure that made "Neither" a black box in the first place. Both poles
are already attested in the smallest possible sample, and the operator's
standing instruction for this feature is that it "should be treated as high
accuracy and precision exercise", conversion explicitly not a driver. The two
codes share a stem, so the axis stays selectable as one
(`detail LIKE 'other_player_%'`) while the suffix keeps the direction.

**Elo (§4) is unchanged and both new codes suppress.** `other_player_keep` is
the near-miss worth naming: "won't give up my guy" *looks* adjacent to
`value_giving`, but it is attachment, not a market-value assertion — "not this
player at any price" is the opposite of a claim about price.
`PASS_REASON_ELO_KEEP` is an allow-list, so the suppression is structural.

**`other_text` keeps its meaning and its rows — but not its population.**
Before this change it was *every* Neither answer; after, it is the Neither
answers the two player codes did not absorb. Any before/after comparison of
`other_text` must be cohorted on 2026-08-19. No migration and no backfill: the
`detail` column is free-form `String`, so the vocabulary lives in
`database.PASS_REASON_LAYER2` and nowhere in the schema.

## 3. Persistence — the load-bearing requirement

**Every tap commits; nothing waits for a submit.** Upsert keyed on `impression_id`:

1. **Layer-1 tile tap** → writes the pass disposition **and** `reason` together. A tester
   who stops here leaves a complete row (passed, on value). This is non-negotiable —
   it is why there is no ✕.
2. **Layer-2 option tap** → writes `detail`.
3. **"Other" tap** → writes its code (`value_other`/`fit_other`) *before* the box opens,
   then the text upgrades it on send. A tester who opens the box and bails still leaves
   "none of the listed reasons".
4. **Free text** → stored on the row; never sent as an analytics property.

Switching tiles updates layer 1 and records `switched_from`; it is a refinement, not a reset.

## 4. Elo consequence — REQUIRES OPERATOR CONFIRMATION BEFORE MERGE

Today every pass fires `record_trade_signal(winner=give_ids, loser=receive_ids, decision="pass")`
(`backend/server.py` ~L10714) — i.e. it asserts "I value my players more than theirs."
That is only true for one reason code. Proposed rule, to be built behind a knob:

| Code | Elo write |
|---|---|
| `value_giving` | **keep** — the user did say their side is worth more |
| `value_getting` | **suppress** — the user said the opposite; writing it inverts the signal |
| `fit_*`, `other*`, layer-1-only `value` | **suppress** — no value claim was made |

Knob `pass_reason_elo_suppression` (default ON). This touches ranking math — flag it in the
scope block and do not merge without the operator's explicit yes.

## 5. Gating

**Superseded 2026-08-17 by operator decision:** ships **live for ALL users** — flag
`feedback.decline_reasons` lands **true**, with **no tester-allowlist scoping**. The flag
remains the one-line kill switch: false ⇒ the current ✓/✕ row renders byte-identically.

*(Original spec said default OFF + allowlist-scoped. The change is coherent rather than a
reversal of intent: the app is TestFlight-only today, so "all users" and "all testers" are
the same population. The design's precision-over-friction posture — many options, no
conversion concern — is calibrated to that. **Revisit before App Store launch**: in front
of consumers the tradeoff inverts, and the low-friction variant explored as approach B in
`mockups/decline-reason-capture/` is the intended successor.)*

## 6. Analytics (every value enumerated — the NULL-platform incident is why)

- `trade_pass_layer1` — fires on the tile tap; carries the disposition (there is no separate pass event).
  Props: `reason` (`value|fit|other`), `switched_from` (prior reason or literal `none`),
  `impression_id`, `trade_id`, `ms_since_render`, `platform` (`ios|android|web`, set explicitly).
- `trade_pass_layer2` — fires on the option tap or free-text send.
  Props: `reason`, `detail` (the 10 layer-2 codes), `has_free_text` (bool), plus the shared props above.
  The 2026-08-19 amendment widened the `detail` enum only — **no new event and no new
  property**, so the emitter in `TradesScreen` is untouched and the registry rows in
  `analytics_taxonomy.py` change only in their enumerating comment.

Layer-1-without-layer-2 must be directly measurable — it is the signal that a category's
options are wrong or missing.

## 7. Gates

User-visible mobile change ⇒ **full gates, no waiver**: feature-scope block, `testID`s
passing `mobile/scripts/testid-lint.sh`, docs updates (api-reference, data-dictionary,
config-reference, glossary), and evidence logged in `living-memory/TEST_LEDGER.md`.

*(Written 2026-08-17 against the Maestro + simulator regime. **[D-056] retired both on
2026-08-15** — this section's Maestro flow and pre-ship sim-gate tier are dead letters and
were struck on 2026-08-19. Evidence is now: the `mobile/tests/check-decline-reasons.js`
structural suite, `backend/tests/test_decline_reasons.py`, a file:line code-walk proof,
and a manual TestFlight checklist for the operator. The two flows under
`mobile/.maestro/flows/decline-reasons-*.yaml` are kept as historical artifacts and are
never run.)*
