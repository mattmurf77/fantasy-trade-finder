# Negative-results memory — operator TestFlight checklist

> Spec: [LLD.md](LLD.md) §8.5 (the steps), §7.1 (the readout fields every step
> checks against), §8.2/§8.4 (rollout + runbook). PRD evidence scope: this is the
> **only runtime evidence** negmem gets. D-056 retired Maestro and the simulator
> entirely — there is no flow to run, no capture to diff. Everything mechanically
> checkable is already covered by `backend/tests/test_negmem.py` (unit) and
> `backend/tests/test_negmem_seams.py` (seams + through-the-runner). What is left
> is the thing only a human with a real league can see: **does the deck still look
> right, and did only the named partners move?**

Everything here is verified against **numbers from `negmem_readout`**, never against
a feeling about the deck. That is the point of the readout existing.

- [Before you start](#before-you-start)
- [Step 0 — baseline, BEFORE the flip](#step-0--baseline-before-the-flip)
- [Step 1 — the flip (round boundary only)](#step-1--the-flip-round-boundary-only)
- [Step 2 — the map is healthy](#step-2--the-map-is-healthy)
- [Step 3 — soft, not hidden](#step-3--soft-not-hidden)
- [Step 4 — netting is visible](#step-4--netting-is-visible)
- [Step 5 — stamps in the readout SQL](#step-5--stamps-in-the-readout-sql)
- [Step 6 — rollback rehearsal](#step-6--rollback-rehearsal)
- [If something is wrong](#if-something-is-wrong)
- [Sign-off](#sign-off)

---

## Before you start

Three facts that will otherwise cost you an hour:

1. **The flag is only half the switch.** `trade.negmem` ON does nothing until your
   league id is in `config/negmem_leagues.json` (or `FTF_NEGMEM_LEAGUES`). That file
   ships as `[]`. A non-allowlisted league is *deliberately indistinguishable* from
   flag-off — same decks, same rows, no stamps. The wildcard entry `["*"]` means every
   league; do not use it for this pass.
2. **Flips land at bake-off ROUND BOUNDARIES only** (GR3 / ADR-014). A mid-round flip
   censors the measurement window. This applies to the flag *and* to every
   `negmem_*` / `gen2_accept_prior_*` knob move.
3. **Knob flips go through `scripts/set_knob.py`**, never a direct DB write. The
   script writes through `PUT /api/admin/config/<key>`, which logs a
   `model_config_changes` row (so the window can be censored at the logged timestamp)
   and triggers the live `reload_config()`. A direct DB write logs nothing and changes
   nothing until restart.

Commands used below (run from the repo root):

```bash
# the readout — local DB
python3 -m backend.scripts.negmem_readout --user <YOUR_USER_ID> --league <LEAGUE_ID>
# the readout — production, READ-ONLY (creds from secrets.local.env)
python3 -m backend.scripts.negmem_readout --user <YOUR_USER_ID> --league <LEAGUE_ID> --prod
# a knob flip
python3 scripts/set_knob.py negmem_strength 0
```

---

## Step 0 — baseline, BEFORE the flip

Run the readout **before** allowlisting anything. The builder bypasses the allowlist
check on purpose, so it works on a dark league and reports `allowlisted` as data.

- [ ] `allowlisted` reads **false** (nothing is on yet).
- [ ] The `cells` list matches your memory: partners you have repeatedly
      reasoned-passed on show `n_raw > 0`. A partner you have never passed on with a
      reason should have **no cell at all**.
- [ ] Save this output. It is your before-picture, and step 3 compares against it.

> A completely empty `cells` list here is a legitimate outcome, not a bug — it means
> no admitted evidence exists yet (evidence must post-date the clean epoch
> `2026-08-20`, be a **viewed** pass carrying a **value** or **fit** reason, and not be
> undone). If cells are empty, do step 3 first to create evidence, then come back.

## Step 1 — the flip (round boundary only)

- [ ] Add your league id to `config/negmem_leagues.json`, deploy.
- [ ] At a **round boundary**, flip `trade.negmem` to true.
- [ ] Re-run the readout: `allowlisted` now reads **true**.

## Step 2 — the map is healthy

Generate a deck in the app, then re-run the readout.

- [ ] `degraded: false` — a degraded map multiplies nothing and stamps
      `{m: 1.0, degraded: true}` everywhere.
- [ ] `parse_errors: 0`.
- [ ] `build_ms < 250` (the S6 budget; `> 500` auto-degrades the map).
- [ ] `m2` reads `"live"` (or `"killed (…)"` if you deliberately zeroed
      `gen2_accept_prior_strength` — know which).

## Step 3 — soft, not hidden

This is the check the whole feature's ruling rests on (D-067, NG1): a repeatedly
rejected family gets **down-weighted, never silenced**.

- [ ] Pick a league-mate **P**. Swipe pass **with a reason** (value or fit) on a card
      toward P, three separate times, across sessions.
- [ ] Regenerate the deck.
- [ ] Cards toward P **still appear**. If P has vanished entirely, that is a
      **stop-and-report** result, not a tuning issue.
- [ ] Cards toward P **lead less often** — they sit lower than they did in your step-0
      deck.
- [ ] In the readout, P's (P, family) cell has crossed `negmem_min_evidence`
      (`below_min_evidence` flips to `false`) and its `mult` is now `< 1.0`.

> Expect the change to arrive as a **step**, not a slide: the curve is identity below
> the threshold and takes its first bite exactly at it. A partner whose cards move once
> and then settle is the threshold crossing, not a bug (runbook line 8).

## Step 4 — netting is visible

- [ ] **Like** a card toward P.
- [ ] Re-run the readout: `partner_likes` shows P, `likes_net` on P's cell moved, and
      the cell's `n_decayed` dropped by roughly 1.

> `likes_net` is **pre-clamp and readout-only**. Do not expect
> `n_decayed + likes_net` to reconstruct the gross evidence — the fold clamps at zero
> after every step, so a like may have cancelled less mass than it carries.

## Step 5 — stamps in the readout SQL

Every row written while the flag is on for an allowlisted league carries a
`features_json.negmem` key — served and ghost, every arm, influenced or not.

- [ ] Run `scripts/negmem-stamp-rate.sql` (bind `:flag_on_day` = the day you flipped;
      the runner substitutes the allowlist from the same loader the build uses).
      **`stamp_rate` is 1.0000 on every row.**
- [ ] Spot-check one influenced row: its `m` matches the readout's `partner_mult` for
      that partner under the current `negmem_strength`.
- [ ] Optional, and the one to run if decks feel over-damped:
      `scripts/negmem-gr4-joint.sql` → p5 of the joint multiplier must stay **≥ 0.15**.

> **Zero rows is not "no stamps."** An empty result while the flag is ON means the
> allowlist is missing, unparseable, or empty — check the readout's `allowlisted` field
> and the build warning log before concluding builds are failing (runbook line 7).

## Step 6 — rollback rehearsal

Rehearse the revert **before** you need it. This is a required step, not an optional one.

- [ ] `python3 scripts/set_knob.py negmem_strength 0` (at a round boundary).
- [ ] Regenerate: deck order reverts to the step-0 shape, and **every** stamp now reads
      `{m: 1.0, ver: 1}` — present, uninfluenced. Stamps do not disappear at strength 0;
      that is deliberate.
- [ ] Set `negmem_strength` back to 1.0 and confirm the influence returns.
- [ ] Flip `trade.negmem` **off**. Regenerate: the `negmem` key is now **absent** from
      every new row, and the deck is byte-identical to pre-negmem.
- [ ] Flip it back on if you are continuing the window.

> `negmem_strength` does **not** govern M2. If a problem plausibly originates in the
> acceptance prior, the additional kill is `gen2_accept_prior_strength = 0`, set
> **GLOBALLY** — never as an arm overlay. An arm overlay leaves the feed populated
> (the guard fires on the job-level global read) and looks like it worked (runbook
> line 4).

---

## If something is wrong

Triage order, from the runbook (`docs/runbook.md` § negmem):

1. **stamp rate** — < 100% on an allowlisted league while the flag is ON ⇒ map builds
   are failing silently.
2. **degraded notes** — `negmem_note` on the job dict; `{degraded: true}` stamps.
3. **the knob triple** — `negmem_strength` / `negmem_floor` /
   `gen2_accept_prior_strength`.

Any PRD §8.3 guardrail breach at any time ⇒ `negmem_strength = 0` (deploy-free), and
the measurement window is censored at the flip timestamp.

Rollback ladder, bluntest last: shrink/empty the allowlist file (per-league,
deploy-free) → `negmem_strength = 0` (+ `gen2_accept_prior_strength = 0` for M2) →
flag off → revert the commit. Nothing persisted needs cleanup: `features_json.negmem`
blobs are inert serve-time facts, never re-stamped, never backfilled.

## Sign-off

| Field | Value |
|---|---|
| Operator | |
| Date | |
| League id | |
| Build / TestFlight version | |
| Flip timestamp (round boundary) | |
| Steps 0–6 all checked | ☐ |
| Anything surfaced | |

Record the result in `living-memory/TEST_LEDGER.md` — a manual pass is evidence and
belongs in the ledger like any other run.
