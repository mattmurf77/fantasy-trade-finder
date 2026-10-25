# ADR-025: Pack evidence for unseen cards; write full rows only for delivered cards

Date: 2026-10-20
Status: Accepted (head-eng, 2026-10-25; models-lead accepted it with edits E1–E7, folded in). It supersedes
ADR-021's "preserve all cards and core evidence" **for new writes only**. Stage 1 (deferred evidence written at
first delivery) is built on #370; the packed writer follows (`deck_evidence_packs`).

## Context

The 200 ms launch target (`launch-readiness-eng.md` §3a, the agent org's working record, kept outside the repo; cited for provenance) pre-builds each user-league's
first page in the background and pages the deck to the client. Today every generated card writes a full
`deck_impressions` row of about 7.6–10.8 KB, about 17.8 MB per job. Background pre-builds would multiply jobs and
fill the 5 GB database within days at modest usage (`db-capacity.md`, the agent org's working record, kept outside the repo; cited for provenance).

Replay/OPE and the ghost holdout need every **served** position, viewed or not: the exposure model e(k),
counterfactual re-ranking of the whole deck, and the never-displayed ghost controls. Calibration's current arm needs
the first 20 cards of the newest served job with assets (C2, C4). So unseen cards can't simply be dropped.

The decision was the operator's, 2026-10-20, relayed by the coordinator and head-bizops (verbatim): "yes, with
tiny rows for unseen trades. get models-lead to confirm it." models-lead confirmed it the same day, under
conditions C1–C9.

## Decision

- **Never-served pre-builds write no evidence (C2).** A background build superseded before any tap writes no
  impression, pack or candidate-set rows.
- **Full rows on view (C3, revised by models-lead R4.2, 2026-10-23) and the build-time snapshot (C6).**
  - A card gets a full row when it is **viewed or acted on** (its first outcome of any kind: `viewed`, `like`,
    `pass`, `propose`, `undo`, `not_interested`; late events still upgrade), or when it's in the first 30 (C4), or in
    a C8 archive deck.
  - Every other generated card of a served deck, **delivered or not**, is packed, with its delivery recorded.
  - The full row uses the features and valuation frozen at build time, held in the page store, and never
    recomputed.
  - **The snapshot must outlive any display:** at least a deck's 24 h display cap (PRD #339 §5.1). A display past
    retention is impossible by construction; if it happens, the outcome still joins the packed card, and the miss is
    counted.
  - **Delivery is recorded in the pack (U1):** per run, `[(last_card_index, delivered_at), …]`. The exposure model's
    served set under paging is the **delivered** positions, and the ghost comparator's delivered range comes from
    here.
  - **Outcomes join packed cards (U2):** each delivered card carries a deterministic `impression_id`
    (`run_id:card_index`). Replay's e(k), its IPS weights and every estimate are identical whether a viewed card was
    upgraded or not, which a test checks.
  - **About −60% of full rows** per served deck (about 30 plus the viewed cards past 30, against about 90). Re-measure
    after the change (U8).
- **Always-full rows:**
  - the first 30 cards of every served deck (C4);
  - a 2% whole-deck archive sample, chosen by deck, for 90 days, then packed (C8).
- **Ghost rows (C5) are never packed.** Each is an individual narrow `deck_impressions` row at every rank, carrying:
  - `impression_id`;
  - `assets_json`;
  - the compact inputs (the pack's per-card fields, in row form).
  It has no wide `features_json` or `valuation_json`. A ghost inside the first 30 also stays narrow: it's withheld,
  not delivered.
- **Every other card of a served deck is packed (C1).** **Every packed field is frozen at build time, when the card is
  built and ranked, and never recomputed.**
  - **Per-run part, once per served job:** user, league, served time, policy version, values snapshot, config
    reference, candidate set, board state, code dictionaries, pack version, and a SHA-256 checksum of the
    canonical unpacked form.
  - **Per-card part:** arrays in `card_index` order holding the trade hash, propensity, scores, the
    `extract_features` inputs **and the `_inject` inputs `partner_user_id` (a dictionary code) and `taste_attrs` (a
    bitset over the per-run vocabulary)**, ranks, and the dictionary codes and flags. That's about 92 B raw per card, versus
    about 9 KB today: about −99% per served job. Final field sizes follow models-eng's measurement.
    - **Position lists are dictionary-coded whole lists** (exact, order included), 1 B per side. A set or bitmask
      isn't bit-exact: the taste fallback divides by the list length, duplicates included
      (`taste_service.py:266-273`). A bitmask changed 447 of 1,200 cards in models-eng's test.
    - **`policy_version` is per card** (bake-off arms append `/bo:<arm>`), as a dictionary code.
    - **Exact encodings:**
      - float8 for propensity, `base_score`, `final_score` and the four value features;
      - the trade hash as its 8 raw bytes;
      - dictionary codes that map back to the exact strings.
      A lossy encoding needs models-lead's sign-off and a re-run of C7 (ii).
    - **Measured** (models-eng prototype `eng/evidence-pack-codec` @ `aef16261`, 1,700 cards):
      - about 86 B raw and 58 B compressed per card;
      - a header of about 10 KB per run, mostly the position-list and centerpiece dictionaries;
      - **about 109 KB per run, about 64 B per card all-in**, −99.4% against about 17.8 MB today.
    - The checksum covers the header's shared fields and the run metadata, not the cards only (models-eng format
      decision (a), pending models-lead).
    - **Both `shape` and `shape_bucket`, and both `lane` and `archetype`, are kept** wherever they can differ.
      `extract_features` falls back from one to the other (`value_model.py` ~`:151-156`).
  - **`values_snapshot_id` is `vsn1`:** one id shared by the pack's per-run part and the page store. It's a hash of
    the format's seed values with player ages, plus the league's pick `pool_value`s (models-eng's definition in the
    S0 contract). A background build stamps the global pool it actually used.
- **Reader and contract first (C7).** No packed write ships before all of these:
  - `eval/data.py` unpacks runs into complete decks;
  - a golden test proves every registered scorer's output and every replay estimate is **bit-identical** between
    the full and packed forms;
  - a scorer-input contract test;
  - replay **excludes** (never sinks) a deck whose pack is missing or fails its checksum;
  - account deletion and export cover the pack table.
  - models-eng owns the pure pack/unpack codec in `eval/`; trades-eng's writer calls it.
  - **The contract is code:** `backend/eval/contract.py` declares `COMPACT_KEYS` (exactly what `extract_features`
    reads), `INJECTED_KEYS`, and `PERMITTED_LOGGED` per scorer. "Bit-identical" is defined over those keys.
  - **Tests** (final names come with the diffs): `test_eval_scorer_contract.py` (contract, guard, registry),
    `test_evidence_pack.py` (golden, integrity), `test_deck_contracts.py` (AC-9 and P2 page identity).
  - **Replay exclusion reasons:** `missing_scorer_inputs` and `pack_integrity`.
- **The C8 archive sample, specified.**
  - **Selection is deterministic by deck:** `sha256("c8-archive-v1|" + deck_job_id) mod 10000 < 200`. No RNG, and
    no dependence on the user or the content.
  - **Every served deck gets a pack, archive decks included.** An archive deck also gets full rows for its
    undelivered cards. At 90 days those extra rows are deleted. Nothing converts, because the pack already exists.
  - A marker on `deck_impressions` (e.g. `evidence_tier`) tells archive rows from delivered, first-30 and ghost
    rows. Eval reads archive decks through a `load_decks` filter, for new-feature backtests only.
  - **Cost:** 2% × about 17.8 MB, or about +0.36 MB per served deck averaged over the 90-day window. That's the
    largest evidence term while it lasts; the pack is about 0.15 MB.
- **Never served:** a value-core run that hit the safety ceiling (partial pool) is refused and never served.
  **Served but incomplete:** a served deck whose generation or pack write didn't complete has its delivered rows
  tagged `evidence_tier='partial_run'`. It gets no pack, and replay excludes it (`partial_run`). (models-lead A1,
  2026-10-22.)
- **Fallback.** If C7 (i)–(ii) can't land by launch, write separate narrow rows (about 0.55–0.8 KB per card) with
  the same compact inputs, then switch to packed once C7 is green. No unseen card is ever written without its
  compact inputs.
- **Retention.** Packed cards live as long as their deck's full rows; a deck can only be replayed whole. Both are
  cold-packed under O9 past at least 90 days. Any hard cap must be at least 365 days, and the deck is then marked
  non-replayable. Debug diagnostics keep ADR-021's 14 days.

## Alternatives considered

- **Displayed cards only** (DEC-2 (b)): rejected. It deletes the denominators replay, the ghost holdout and the
  D-016 gate need.
- **Separate narrow rows per card:** valid, but about 6–8× larger than packed because of repeated per-run columns,
  tuple overhead and indexes. It's kept only as the fallback.
- **Retroactive slimming of existing history:** rejected (models-lead §D5). Existing rows are untouched, and O9
  handles cold packing.
- **More disk alone:** it defers the growth; it doesn't fix it.

## Consequences

- A future scorer that needs a feature outside the packed set can't be backtested on packed cards from before the
  feature was added, except on the 2% archive. Adding a scorer input means adding it to the pack first.
- Unseen non-ghost cards keep only `trade_hash`, so their asset ids and valuation detail can't be recovered,
  except in the archive. Matching executed trades to unseen cards ends; models-lead's matcher rule already says so.
- Raw SQL over unseen cards must go through the unpacker. `deck_impressions` alone no longer holds every card.
- The incrementality analysis restricts ghosts to would-have-been ranks inside the delivered range. It's an
  analysis rule, not a code change.
- **Readers that see only full rows from now on:**
  - the executed-trade matcher (`was_recommended` now means **viewed** or first 30, per R4.2 U6);
  - `bakeoff_readout.sql` §7f and §7h, and the B-DK-4 to B-DK-7 production audit (all on "viewed" plus the first 30);
  - receipts;
  - `eval/scorecard_evidence.py`.
  Each says so in its doc or header, with the build.
- **Receipts can grade only full-row cards** (packed cards carry no assets). Receipts move to **viewed** cards (plus
  the first 30), per R4.2 U6, which supersedes E5's "delivered". Its owner (trades-eng) and analytics-lead accept and
  document it before the first packed write.
- Schema: a pack table (per-run part plus per-card arrays) and the page store's frozen snapshot. Both are
  documented in `docs/data-dictionary.md` with the build.
- Building it needs models-lead's model-change packet sign-off: 13a on the plan before the build starts, 13b on
  the result.
