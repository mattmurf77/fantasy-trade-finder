// Calculator asset types — the shape every calculator surface speaks.
//
// Extracted from the retired `tradeCalcMock.ts` (2026-08-22, feedback #384,
// operator: "let's also remove the demo calc, it's pointless"). The mock
// LEAGUE went with it; these two types did not, because they were never
// demo-only — the live calculator, the In-league calculator, the deck's
// target picker and `utils/tradeCalcMath.ts` all speak them.
//
// Nothing in here is fixture data. If you are looking for the seeded demo
// rosters, they are gone — see docs/feedback/items/384-calc-finder-merge/.

import type { PickSource } from '../api/pickAssignment';
import type { Position } from '../shared/types';

/** Tradable-asset position: the four player positions plus draft picks. */
export type CalcPos = Position | 'PICK';

export interface CalcPlayer {
  id: string;
  name: string;
  pos: CalcPos;
  nflTeam: string;
  age: number;
  /** Consensus dynasty value on an Elo-like scale (~900–2600). */
  base: number;
  /** Draft pick rather than a player.
   *
   *  Retained after the demo board's removal because `PlayerPickerModal`'s
   *  pick filter still reads it for rows that reach it without the server
   *  field below. Prefer `isPick`. */
  pick?: true;
  /** Server-supplied pick identity, mapped from `CalcValueRow.is_pick`.
   *  The backend's canonical verdict and the field consumers should prefer
   *  (docs/cross-client-invariants.md § "Pick identity on the wire").
   *  Undefined when the row predates the field — consumers must fall back
   *  to the `pos`/`nflTeam` check, never treat undefined as false. */
  isPick?: boolean;
  /** draft-extensions W3 M-C (D17) — provenance for an owned league pick,
   *  copied verbatim off `GET /api/league/picks`. Only the In-league
   *  calculator ever sets these (it is the only mount with a real league);
   *  the open calculator and the deck's target picker leave them undefined,
   *  so `MemberEnteredMarker` renders nothing there. */
  pickSource?: PickSource | null;
  pickSeason?: number | null;
}
