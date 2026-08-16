// rankPresets.ts — premium rank-set CSV presets (Connected Rankings addendum
// §3.2, [D-058]). PURE FUNCTIONS ONLY: no React, no network, no storage.
//
// What this module does, and deliberately does not do:
//
//   • Detects the SOURCE (Dynasty Nerds / DLF) from ANCHOR COLUMNS in the
//     header — never whole-header equality. DN's header carries optional
//     Trend/PPG columns; DLF's header is DYNAMIC (one column per analyst the
//     user has selected), so only the anchors can be relied on.
//   • Infers the SET (dynasty vs contender) and the FORMAT from the FILENAME
//     when one survives intake. DN's CSV columns are byte-identical across
//     all four formats AND across Dynasty vs Contender — the distinction
//     lives ONLY in the filename (addendum §3.2, risk R16). An inference is
//     never applied silently: `ImportRankingsSheet` always shows the
//     confirmation step before anything reaches the API.
//   • Extracts ORDER ONLY. `PresetRow` has exactly three fields — name, team,
//     pos — and `FORBIDDEN_COLUMNS` names the premium columns
//     (Value/Trend/PPG) that must never be read, sent, or persisted. The
//     ordinal import pipeline (`apply_reorder`) has no slot for a foreign
//     value anyway; this keeps that true at the parser boundary too (R14).
//   • Returns `null` from `detectSource()` for anything it does not
//     recognize. The caller routes those into the existing generic paste
//     flow — the preset NEVER guesses (R16).

export type PremiumSource = 'dynasty_nerds' | 'dlf';

/** How a CSV reached the preset pipeline. Mirrors the `via` property on
 *  `rankings_preset_detected` / `rankings_preset_fallback`. */
export type PresetVia = 'browser' | 'file';

/** FTF's two boards. Mirrors `ScoringFormat` in shared/types. */
export type BoardFormat = '1qb_ppr' | 'sf_tep';

/** Dynasty Nerds scoring tokens as they appear in the export filename. */
export type DnScoring = 'ppr' | 'std' | 'sflex' | 'sflextep';

/** DN ships two value systems under an identical header. `contender` is the
 *  win-now set and must never seed a dynasty board without an explicit
 *  override (addendum §3.2). */
export type PresetSet = 'dynasty' | 'contender';

/** The ONLY per-row fields a preset may read. Matches the backend's optional
 *  `rows: [{name, team, pos}, …]` import-preview contract exactly. */
export interface PresetRow {
  name: string;
  team: string | null;
  pos: string | null;
}

/** Premium columns that must never be read out of a preset CSV. Exported so
 *  the structural test can assert the extractor never indexes them. */
export const FORBIDDEN_COLUMNS: readonly string[] = ['value', 'trend', 'ppg'];

/** Header cells that must ALL be present for a DN match (research
 *  2026-08-15-dynasty-nerds.md §2: `Rank, Player, Team, Position, Age, Exp,
 *  Value[, Trend, PPG], Pos Rank`). Trend/PPG are optional ⇒ not anchors. */
const DN_ANCHORS = ['rank', 'player', 'team', 'position', 'age', 'exp', 'value'];

/** DLF anchors. `Avg` is the consensus column — used for DETECTION CONTEXT
 *  only; v1 imports consensus order from Rank/Player and never reads a
 *  per-analyst column (addendum §3.2, "consensus only in v1"). */
const DLF_ANCHORS = ['rank', 'player', 'avg'];

export interface ParsedPreset {
  source: PremiumSource;
  via: PresetVia;
  /** Ordered rows, file order (which is the site's rendered rank order). */
  rows: PresetRow[];
  filename: string | null;
  /** DN only, from the filename. `null` = unknown (no filename, or DLF). */
  set: PresetSet | null;
  scoring: DnScoring | null;
  /** Inferred board, or null when the filename could not settle it. */
  format: BoardFormat | null;
  /** `exact` — the site's format maps 1:1 onto an FTF board.
   *  `nearest` — it does not; the confirmation copy must SAY SO by name.
   *  `unknown` — nothing to infer from; the user picks. */
  formatMatch: 'exact' | 'nearest' | 'unknown';
  /** Filename subset markers, surfaced in the confirmation copy. */
  positionFilter: string | null;
  rookiesOnly: boolean;
}

// ── CSV ────────────────────────────────────────────────────────────────
// Tolerant RFC-4180-ish reader. Both sites serialize a rendered HTML table,
// so quoting is simple, but DLF prefixes a UTF-8 BOM and player cells can
// carry commas inside quotes ("Smith, Jr.").
export function parseCsv(text: string): string[][] {
  const src = text.replace(/^﻿/, '');
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;

  for (let i = 0; i < src.length; i += 1) {
    const c = src[i];
    if (quoted) {
      if (c === '"') {
        if (src[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        cell += c;
      }
      continue;
    }
    if (c === '"') {
      quoted = true;
    } else if (c === ',') {
      row.push(cell);
      cell = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && src[i + 1] === '\n') i += 1;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else {
      cell += c;
    }
  }
  if (cell !== '' || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }
  return rows.filter((r) => r.some((v) => v.trim() !== ''));
}

const norm = (s: string) => s.replace(/^﻿/, '').trim().toLowerCase();

/** Source detection on ANCHOR COLUMNS. Returns null for anything not
 *  recognized — the caller must fall back to the generic paste flow. */
export function detectSource(header: string[]): PremiumSource | null {
  const cells = new Set(header.map(norm));
  if (DN_ANCHORS.every((a) => cells.has(a))) return 'dynasty_nerds';
  if (DLF_ANCHORS.every((a) => cells.has(a))) return 'dlf';
  return null;
}

// ── Filename inference (DN) ────────────────────────────────────────────
// `dynasty_rankings_[contender_]<scoring>[_<pos>][_rookies].csv`
const DN_POSITIONS = ['qb', 'rb', 'wr', 'te', 'flex', 'idp', 'k', 'df'];

export interface FilenameInfo {
  set: PresetSet | null;
  scoring: DnScoring | null;
  positionFilter: string | null;
  rookiesOnly: boolean;
}

export function parseDnFilename(filename: string | null | undefined): FilenameInfo {
  const empty: FilenameInfo = {
    set: null,
    scoring: null,
    positionFilter: null,
    rookiesOnly: false,
  };
  if (!filename) return empty;
  const base = filename.split('/').pop() || filename;
  const stem = base.replace(/\.csv$/i, '').toLowerCase();
  if (!stem.startsWith('dynasty_rankings')) return empty;

  const parts = stem.split('_').filter(Boolean);
  // Drop the "dynasty" "rankings" prefix tokens.
  const rest = parts.slice(2);
  const info: FilenameInfo = { ...empty, set: 'dynasty' };
  for (const tok of rest) {
    if (tok === 'contender') info.set = 'contender';
    else if (tok === 'ppr' || tok === 'std' || tok === 'sflex' || tok === 'sflextep') {
      info.scoring = tok;
    } else if (tok === 'rookies') info.rookiesOnly = true;
    else if (DN_POSITIONS.includes(tok)) info.positionFilter = tok.toUpperCase();
  }
  return info;
}

/** DN scoring token → FTF board. `exact` mappings are 1:1; `nearest` ones
 *  are NOT and must be named in the confirmation copy (addendum §3.2). */
export function formatForScoring(
  scoring: DnScoring | null,
): { format: BoardFormat | null; match: 'exact' | 'nearest' | 'unknown' } {
  switch (scoring) {
    case 'ppr':
      return { format: '1qb_ppr', match: 'exact' };
    case 'sflextep':
      return { format: 'sf_tep', match: 'exact' };
    case 'sflex':
      return { format: 'sf_tep', match: 'nearest' };
    case 'std':
      return { format: '1qb_ppr', match: 'nearest' };
    default:
      return { format: null, match: 'unknown' };
  }
}

/** Human-readable label for the nearest-format warning. */
export const SCORING_LABEL: Record<DnScoring, string> = {
  ppr: 'PPR',
  std: 'Standard',
  sflex: 'Superflex',
  sflextep: 'Superflex TE-premium',
};

export const SOURCE_LABEL: Record<PremiumSource, string> = {
  dynasty_nerds: 'Dynasty Nerds',
  dlf: 'DLF',
};

export const FORMAT_LABEL: Record<BoardFormat, string> = {
  '1qb_ppr': '1QB PPR',
  sf_tep: 'Superflex TE-premium',
};

// ── Row extraction ─────────────────────────────────────────────────────
// ORDER ONLY. This function reads exactly three header positions — the
// player-name column and the optional team/position hint columns. It never
// looks up a FORBIDDEN_COLUMNS index, so a premium Value can't reach the
// wire even by accident.
function columnIndex(header: string[], names: string[]): number {
  const cells = header.map(norm);
  for (const n of names) {
    const i = cells.indexOf(n);
    if (i >= 0) return i;
  }
  return -1;
}

export function extractRows(header: string[], body: string[][]): PresetRow[] {
  const nameAt = columnIndex(header, ['player', 'name']);
  const teamAt = columnIndex(header, ['team', 'tm']);
  const posAt = columnIndex(header, ['position', 'pos']);
  if (nameAt < 0) return [];

  const out: PresetRow[] = [];
  for (const r of body) {
    const name = (r[nameAt] ?? '').trim();
    if (!name) continue;
    // A stray repeated header row (both sites re-emit one per page section
    // in some exports) is not a player.
    if (norm(name) === 'player' || norm(name) === 'name') continue;
    const team = teamAt >= 0 ? (r[teamAt] ?? '').trim() : '';
    const pos = posAt >= 0 ? (r[posAt] ?? '').trim() : '';
    out.push({
      name,
      team: team || null,
      pos: pos || null,
    });
  }
  return out;
}

/** Full pipeline: raw CSV text (+ filename when intake preserved one) →
 *  ParsedPreset, or null when the header signature is unrecognized. */
export function parsePreset(
  text: string,
  filename: string | null,
  via: PresetVia,
): ParsedPreset | null {
  const table = parseCsv(text);
  if (table.length < 2) return null;
  const header = table[0];
  const source = detectSource(header);
  if (!source) return null;

  const rows = extractRows(header, table.slice(1));
  if (rows.length === 0) return null;

  const info = source === 'dynasty_nerds'
    ? parseDnFilename(filename)
    : { set: null, scoring: null, positionFilter: null, rookiesOnly: false };
  const { format, match } = formatForScoring(info.scoring);

  return {
    source,
    via,
    rows,
    filename: filename ?? null,
    set: info.set,
    scoring: info.scoring,
    format,
    formatMatch: match,
    positionFilter: info.positionFilter,
    rookiesOnly: info.rookiesOnly,
  };
}

/** `contender_` files are DN's WIN-NOW set. They are excluded from applying
 *  by default; the user must explicitly override in the confirmation step. */
export function isContender(p: ParsedPreset): boolean {
  return p.set === 'contender';
}

/** Newline-joined names — the payload for the graceful fallback to the
 *  existing text path when the backend rejects `rows` with a 400, and for
 *  prefilling the generic paste flow on an unknown signature. */
export function rowsToLines(rows: PresetRow[]): string[] {
  return rows.map((r) => r.name);
}
