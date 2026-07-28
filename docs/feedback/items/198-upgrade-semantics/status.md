# #198 — Upgrade ideas semantics: position-centric — status

**Status: fixed (backend semantics + panel copy)** · 2026-07-27 · branch
`teardown-remediation` worktree · flag `trade.asset_ideas` (unchanged)

## Operator report (verbatim)

> "Upgrade ideas seem to be off.. the intent is the upgrade ideas add more
> assets to what you're giving away to upgrade the specific position you're
> trying to upgrade."

Filed 2026-07-28T00:57Z from `TradeDeck` (v1.11.0, iOS). Feature under
correction: the 2026-07-26 asset-ideas engine
(`docs/feedback/items/2026-07-26-asset-trade-ideas/status.md`), which
classified counterparts by VALUE bands only — a cross-position asset above
the band surfaced as an "upgrade" for the pinned asset.

## Semantics now (position-centric, #198)

For a **player pin** at position P (`TradeService.generate_asset_ideas`,
`backend/trade_service.py`):

- **Upgrade** — returns constrained to PLAYERS AT P above the
  ±`asset_ideas_lateral_band` band: a better player at the same position,
  funded by the pin plus own-roster sweeteners (sweeteners may be ANY
  position, picks included — they fund the upgrade, they aren't its target).
  Straight 1-for-1 when the gates pass, else the closest sweetened 2-for-1.
- **Lateral** — same-position 1-for-1 within the band. (Documented choice:
  the operator's mental model is position-centric, so any-position laterals
  were dropped rather than kept alongside.)
- **Downgrade** — stays VALUE-BASED (the operator didn't constrain it, and a
  spread-out return is inherently multi-positional): 2-3 lesser pieces of
  any position, but combos headlined by a same-position piece are
  **preferred** — both in the per-opponent best-2 selection (after the
  strict-band split, before deal closeness) and in the final group ordering
  (same-position headliners first, then |difference|). Documented choice.
- **The position constraint is a semantic, not a gate knob** — like the #108
  gates it is NEVER relaxed; the #189 refill widens only the fairness band,
  within the same position. A group with no same-position candidates is
  honestly empty.
- **PICK pins** — "same position" doesn't apply; all three groups keep the
  pure value-band behavior (better picks/value up, band swaps across).
  Injected owned picks (position `PICK`) therefore never satisfy the
  Upgrade/Lateral constraint for a player pin, but remain eligible as
  sweeteners and downgrade pieces.

**`direction: "receive"` mirror** (acquiring the pin at P): the tier-up
headliner (the lesser own asset that leads the Upgrade package) and the
Lateral swap must play P — you upgrade/swap AT the position you're
acquiring; the optional second tier-up piece may be any position. The
Downgrade give (a single better own asset for the pin + owner sweeteners)
stays any-position with same-position ordered first, mirroring the give
side's downgrade rule.

Everything else — valuation reuse set, #108/#141 gates, untouchable /
not-interested exclusions, #189 relaxed refill, caps, determinism, the
route contract — is unchanged.

## Client

`mobile/src/components/AssetIdeasPanel.tsx` — group headers name the pin's
position ("Upgrade at WR", "Lateral moves at WR"; Downgrade keeps the
neutral header since it's value-based), and the subtitle copy is
position-aware in both directions. PICK pins (and the not-yet-loaded state)
fall back to the previous generic labels. Position comes from the response's
`asset.position` — no new client plumbing. `TradesScreen` untouched (other
agent's file).

## Files

- `backend/trade_service.py` — `generate_asset_ideas` position constraint +
  downgrade preference + docstrings; `_DEFAULT_CFG` comment
- `backend/server.py` — `/api/trades/asset-ideas` docstring
- `mobile/src/components/AssetIdeasPanel.tsx` — position-centric headers/copy
- Docs: `docs/glossary.md` ("Asset ideas"), `docs/api-reference.md`

## Tests (`backend/tests/test_asset_ideas.py`, 17 total — 4 new)

- `test_upgrade_and_lateral_are_position_locked` — the operator's complaint
  case: a HIGHER-value cross-position asset (WR 1705 vs the RB pin) never
  surfaces as an upgrade; in-band cross-position assets never surface as
  laterals.
- `test_downgrade_prefers_same_position_headliner` — an RB-headlined combo
  leads the group even though a WR-headlined combo lands a closer
  |difference| (proves the preference did real work).
- `test_pick_pin_keeps_value_bands` — PICK pin: any better asset upgrades,
  any band asset is lateral.
- `test_receive_direction_position_locked` — mirror: value-twin WRs never
  headline the tier-up or the lateral for an RB acquire pin.
- All 13 pre-existing tests pass unchanged (their fixtures are single-
  position, so the value-band expectations are also the position-centric
  expectations).

## Verification

- `python3 -m pytest backend/tests -q` → **1352 passed, 1 skipped**
  (branch baseline before this change: 1346 passed, 1 skipped).
- `cd mobile && npx tsc --noEmit` → clean (exit 0).
