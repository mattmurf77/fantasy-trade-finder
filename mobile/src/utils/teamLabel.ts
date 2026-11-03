// A team's label on a surface leaguemates see: its real name, never a member
// id (head-eng, 2026-11-03). The fallbacks are the labels the server writes
// for a nameless member (#497, `database.pick_slot_team_name`): `Team <slot>`
// when the member's slot is known, else `Unnamed team`.
//
// Zero runtime imports: `tests/check-no-raw-id-labels.js` transpiles and
// executes this file under plain node.

type MaybeName = string | null | undefined;

/** A member id the backend mints, sitting where a name should be:
 *  `espn:{SWID}`, `espn:<league>.t<team>`, `mfl:<league>.f<fid>`, `acct_<n>`.
 *  Matched at the start or after a space, so `Team espn:{…}` (the name a
 *  pre-#497 assignment stored) is caught too. */
const MINTED_ID_RE = /(?:^|\s)(?:espn:|mfl:|acct_)/;

/** `mfl:<league>.f<franchise>`, kept in step with `server.py:_MOCK_MFL_MEMBER_RE`. */
const MFL_MEMBER_RE = /^mfl:.*\.f(\w+)$/;

/** The first candidate that is a real name, trimmed; `null` when none is.
 *  Blank, whitespace-only, a minted id, the member's own id and
 *  `Team <their id>` are not names. */
export function realName(names: readonly MaybeName[], userId?: string | null): string | null {
  const id = String(userId ?? '').trim();
  for (const candidate of names) {
    const name = String(candidate ?? '').trim();
    if (!name || MINTED_ID_RE.test(name)) continue;
    if (id && (name === id || name === `Team ${id}`)) continue;
    return name;
  }
  return null;
}

/** A team's label: its real name, else `Team <fid>` for an MFL franchise (the
 *  fid as it appears in the id, zero-padding intact, as the backend writes
 *  it), else `Team <slot>`, else `Unnamed team`. Never an id, never blank. */
export function teamLabel(
  names: readonly MaybeName[],
  userId?: string | null,
  slot?: number | string | null,
): string {
  const name = realName(names, userId);
  if (name) return name;
  const mfl = MFL_MEMBER_RE.exec(String(userId ?? ''));
  if (mfl) return `Team ${mfl[1]}`;
  const s = String(slot ?? '').trim();
  return s ? `Team ${s}` : 'Unnamed team';
}

/** Each member's slot on the pick-assignment grid, by `seed_pick_grid`'s rule
 *  (backend/database.py): a member already on the grid keeps their
 *  `original_roster_id`; everyone else takes the next free integer, in
 *  `order`. Pass the server's round-1 order (`settings.order`), then any
 *  other member ids; a repeated id is skipped. The slots are distinct, and
 *  they come from server data only, so a label never moves with a drag. */
export function assignmentSlots(
  order: readonly string[],
  grid: readonly { original_user_id: string; original_roster_id: string }[],
): Map<string, string> {
  const slots = new Map<string, string>();
  for (const row of grid) {
    if (row.original_user_id && row.original_roster_id && !slots.has(row.original_user_id)) {
      slots.set(row.original_user_id, row.original_roster_id);
    }
  }
  const used = new Set(slots.values());
  let next = 1;
  for (const id of order) {
    if (!id || slots.has(id)) continue;
    while (used.has(String(next))) next += 1;
    slots.set(id, String(next));
    used.add(String(next));
  }
  return slots;
}
