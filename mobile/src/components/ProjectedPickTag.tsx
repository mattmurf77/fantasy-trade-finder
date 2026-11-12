import React from 'react';
import { Badge } from './chalkline';
import { flare } from '../theme/chalkline';
import { PROJECTED_TAG_LABEL, PROJECTED_TAG_LABEL_SHORT } from '../utils/projectedPick';

// The PROJECTED tag beside a pick priced by its projected draft slot
// (utils/projectedPick.ts). Badge construction (docs/design/components.md →
// Badges & chips): 1px border + label text, both `flare.base` — the
// RookieBadge / OTB / NEED treatment, because this is an informational
// highlight, not an action (ADR-005: flare = what's worth noticing).
//
// Hosts render it ONLY when `projectedPick(asset)` returned a pair, and fold
// "projected draft slot X" into their row's accessibility label: the badge
// carries no label of its own.
//
// `short` is for the narrow two-column rows: "PROJECTED" measures ~90pt in
// `type.label` (Archivo 600 11pt, +0.88 tracking) with the badge padding,
// wider than the ~84pt content column of a deck-card row beside its
// controls, so those rows print "PROJ" instead.
export default function ProjectedPickTag({ short = false }: { short?: boolean }) {
  return (
    <Badge
      label={short ? PROJECTED_TAG_LABEL_SHORT : PROJECTED_TAG_LABEL}
      color={flare.base}
      colorText
    />
  );
}
