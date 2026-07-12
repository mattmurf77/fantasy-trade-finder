# mobile/src/utils/

Pure helpers. No React, no I/O.

- `relativeTime.ts` — "2h ago"–style formatting
- `tierBands.ts` — maps Elo / value → tier key and label (8-tier pick-value ladder, #117: 4+ 1sts / 3 1sts / 2 1sts / 1st / 2nd / 3rd / 4th / Waivers). The former `pickTerms.ts` sublabel helper was removed 2026-07-11 — tier labels ARE pick terms now.
- `playerValue.ts` — 0–10k display value from Elo (inverse of the #117 value-affine consensus seed map — keep in lockstep with `backend/data_loader.seed_elo_for_value`).
