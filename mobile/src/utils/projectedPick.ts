// projectedPick.ts — the "projected draft slot" fields on a pick asset.
//
// WHY THIS EXISTS. The server prices next season's first-round picks by the
// original team's projected draft slot (docs/plans/pick-value-projected-slot/).
// The operator asked that the app say so, so users can see why a "2027 1st"
// is worth what it is: print the slot name ("2027 1.02") with a flare
// PROJECTED tag beside it.
//
// The wire contract: a pick priced by projection carries two optional
// strings on whatever object carries the pick —
//   proj_slot  "1.02"
//   proj_name  "2027 1.02" / "2027 1.02 (from dondags)"  (no projected marker)
// and its ordinary name/label becomes "… · projected". The app NEVER parses
// or composes those strings: it prints `proj_name` verbatim and renders the
// tag, or — when either field is absent or malformed — renders exactly as
// before. Both or neither: a tag without the slot name (or the reverse)
// would be a claim the screen can't back.
//
// WHERE THE VALIDATION LIVES. Not in the API normalizers: the wire objects
// already pass through `api/trades.ts`, `api/league.ts` and friends verbatim
// (a pick is a `Player`-shaped row, an `OwnedPick`, a power-rankings item),
// and `api/trades.ts` is pinned require-free beyond `./client` by a dozen
// guards. So every surface asks `projectedPick(asset)` at render time — ONE
// validator, run where the name prints. Malformed ⇒ null ⇒ the surface
// renders exactly as it does for an old server.
//
// Pure, ZERO runtime imports: `mobile/tests/check-projected-pick-tag.js`
// transpiles and RUNS this module.

/** `proj_slot` must look like a round.slot draft position: "1.02". */
export const PROJ_SLOT_RE = /^\d\.\d{2}$/;
/** Longest `proj_name` the app will print. */
export const PROJ_NAME_MAX = 60;

/** Tag text. The short form is for the narrow two-column rows (deck card,
 *  calculator columns), where the full word does not fit beside the row's
 *  controls — see mobile/src/components/CLAUDE.md `ProjectedPickTag`. */
export const PROJECTED_TAG_LABEL = 'PROJECTED';
export const PROJECTED_TAG_LABEL_SHORT = 'PROJ';

/** Optional wire fields, mixed into every pick-carrying type. */
export interface ProjectedPickFields {
  proj_slot?: string;
  proj_name?: string;
}

export interface ProjectedPick {
  slot: string;
  name: string;
}

/** The validated pair, or null. Null for anything that is not BOTH a
 *  well-formed slot and a 1..60-char name. */
export function projectedPick(asset: unknown): ProjectedPick | null {
  if (!asset || typeof asset !== 'object') return null;
  const a = asset as { proj_slot?: unknown; proj_name?: unknown };
  const slot = a.proj_slot;
  const name = a.proj_name;
  if (typeof slot !== 'string' || typeof name !== 'string') return null;
  if (!PROJ_SLOT_RE.test(slot)) return null;
  if (name.length < 1 || name.length > PROJ_NAME_MAX) return null;
  return { slot, name };
}

/** The name a surface prints: `proj_name` when the pair is valid, else the
 *  surface's ordinary name, untouched. */
export function pickDisplayName(asset: unknown, ordinary: string): string {
  const p = projectedPick(asset);
  return p ? p.name : ordinary;
}

/** The VoiceOver clause appended to a row's label. */
export function projectedPickA11y(p: ProjectedPick): string {
  return `projected draft slot ${p.slot}`;
}
