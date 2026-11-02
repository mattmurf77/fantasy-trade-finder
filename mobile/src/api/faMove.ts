// D1 free-agent moves: the client half of the wire contract
// (docs/plans/sleeper-fa-write/contract.md, authoritative for the wire), and
// the pure pieces the claim sheet runs on. Product behaviour is the scope
// block's (docs/plans/sleeper-fa-write/scope.md on plan/fa-moves-launch,
// §B–§C; analytics §1 C1–C6).
//
// The 11-06 binary ships this dark. Nothing here reads a feature flag (F1):
// the server's per-league capability, `move` on GET /api/league/free-agents,
// decides everything, and an old server that sends none of it gets today's
// hand-off unchanged (`faMoveGate` → 'legacy'). Nothing here holds consent
// text either (F11): the consent step renders only what the consent GET or a
// 409 `consent_required` carries, and echoes its {copy_version, locale} back
// exactly as received. Every other word is a server slot (`move.copy`, or the
// response's `title` / `lines` / `message`) with a neutral, platform-free
// fallback from FA_MOVE_FALLBACK_COPY.
//
// Pinned by tests/check-fa-move.js (F1–F17).

import NetInfo from '@react-native-community/netinfo';

import { apiRequest, ApiError, getBaseUrl } from './client';
import { track } from './events';
import { getFreeAgents } from './league';

// ── Wire types (contract §1–§3) ─────────────────────────────────────────────

export const LEAGUE_PLATFORMS = ['sleeper', 'mfl', 'espn'] as const;
export type LeaguePlatform = (typeof LEAGUE_PLATFORMS)[number];
export type MoveMode = 'submit' | 'handoff' | 'unsupported';
export type MoveKind = 'add' | 'claim';
/** The closed set; any other value is the plain connect step, never Ready. */
export type MoveConnect = 'ok' | 'not_linked' | 'expired' | 'unverified' | 'other_account';

export type MoveCopyKey =
  | 'header_add'
  | 'header_claim'
  | 'cta_add'
  | 'cta_add_drop'
  | 'cta_claim'
  | 'cta_claim_drop'
  | 'cta_claim_no_bid'
  | 'cta_claim_drop_no_bid'
  | 'league_line'
  | 'finality'
  | 'waiver_line'
  | 'waiver_line_no_drop'
  | 'bid_line'
  | 'window_line'
  | 'turn_off'
  | 'do_in_platform'
  // Reserved and unread in this binary: the hand-off CTA keeps #509's approved
  // literal "Open in Sleeper to claim", which check-sleeper-handoff S2 pins.
  | 'open_platform'
  | 'handoff_footer'
  | 'connect_line'
  | 'verify_line'
  | 'other_account_line'
  | 'not_sent_line'
  | 'unknown_title'
  | 'unknown_body'
  | 'unavailable_line'
  | 'still_sending';

/** Pre-tap slots (contract §7). Every key is optional. */
export type MoveCopy = Partial<Record<MoveCopyKey, string>>;

/** `move` on GET /api/league/free-agents. Absent on today's server. */
export interface FaMoveCapability {
  mode: MoveMode;
  claims: boolean;
  league_platform: LeaguePlatform | null;
  connect: MoveConnect | string;
  consent_until: string | null;
  copy?: MoveCopy;
}

/** The per-row fields of the same read. All optional. */
export interface FaMoveRow {
  /** null = the server can't tell; in `submit` mode the CTA names an add. */
  move_kind?: MoveKind | null;
  /** 'handoff' = this row is held in hand-off (claims off, §B6's block). */
  move_mode?: string;
  /** The server's reason for the row's override. */
  move_line?: string;
}

/** The text to show when the user must consent now (contract §2). */
export interface ConsentBlock {
  copy_version: string;
  locale: string;
  title: string;
  body: string[];
  checkbox_label: string;
  /** Template with {cta} and {league} (R15.8 D10(d)). */
  this_move: string;
  button_label: string;
  /** Legal's "Terms · Privacy" row. Absent: the app's own pages. */
  links?: ConsentLink[];
  /** For fa_move_consent_shown. Absent: the client infers it. */
  reason?: ConsentReason;
}

export interface ConsentLink {
  label: string;
  url: string;
}

export interface ConsentStatus {
  platform: LeaguePlatform;
  valid: boolean;
  until: string | null;
  consent?: unknown;
  status_line: string | null;
  stop_label: string | null;
}

export interface ConsentWithdrawal {
  platform: LeaguePlatform;
  valid: false;
  notice: string;
}

/** What the move request echoes back: exactly the shown block's pair. */
export interface ConsentEcho {
  copy_version: string;
  locale: string;
}

export interface MoveRequest {
  league_id: string;
  add_player_id: string;
  drop_player_id?: string;
  move_kind: MoveKind;
  faab_bid?: number;
  consent?: ConsentEcho;
  attempt_id: string;
  /** The sheet's host (contract §3); the server records it on consent. */
  surface?: FaMoveSurface;
}

export interface MoveResponse {
  status: 'complete' | 'pending';
  move_kind: MoveKind;
  result: 'accepted' | 'partial';
  league_platform: LeaguePlatform;
  attempt_id: string;
  title: string;
  lines: string[];
  platform_transaction_id?: string;
}

// ── Routes (contract §2–§3) ─────────────────────────────────────────────────

/** Also in utils/devicePage.ts's discardsDevicePages (K-F5, §B10). */
export const FA_MOVE_PATH = '/api/league/free-agents/move';
const CONSENT_PATH = '/api/platform-write-consent';

// ── Timing (contract §5) ────────────────────────────────────────────────────
// The server's worst case for one move, request receipt to response: a 30 s
// preflight budget checked right before the platform write (the
// _SEND_PREFLIGHT_BUDGET_S pattern), plus the write path's own timeouts,
// which sum to ≤ 46 s. The server enforces it and a server test pins the sum.
export const FA_MOVE_SERVER_WORST_CASE_S = 76;
// Margin: one default request timeout (DEFAULT_TIMEOUT_MS in api/client.ts,
// 15 s) for the round trip and the server's database work around the
// platform calls, as PLATFORM_SEND_TIMEOUT_MS does for the ESPN/MFL sends.
export const FA_MOVE_TIMEOUT_MARGIN_S = 15;
/** Request timeout for POST /api/league/free-agents/move: (76 + 15) s = 91 s.
 *  iOS may drop an idle request near 60 s; that surfaces as status 0, which
 *  is outcome unknown (state 12), the safe reading. */
export const FA_MOVE_TIMEOUT_MS = (FA_MOVE_SERVER_WORST_CASE_S + FA_MOVE_TIMEOUT_MARGIN_S) * 1000;
/** State 7's "still sending" line appears this long after the tap. */
export const FA_MOVE_STILL_SENDING_MS = 8_000;

export function getConsent(
  platform: LeaguePlatform,
  opts: { quietStatuses?: readonly number[] } = {},
): Promise<ConsentStatus> {
  return apiRequest<ConsentStatus>(`${CONSENT_PATH}?platform=${encodeURIComponent(platform)}`, opts);
}

export async function withdrawConsent(platform: LeaguePlatform): Promise<ConsentWithdrawal> {
  const out = await apiRequest<ConsentWithdrawal>(
    `${CONSENT_PATH}?platform=${encodeURIComponent(platform)}`,
    { method: 'DELETE' },
  );
  _withdrawnHere.add(platform);
  return out;
}

/** The move itself. Through the shared client, never a bare fetch (F13): its
 *  _noteWrite discards the held trade page on this non-GET (K-F5, §B10). The
 *  ONLY caller is attemptMove below (F7). */
export function submitMove(body: MoveRequest): Promise<MoveResponse> {
  return apiRequest<MoveResponse>(FA_MOVE_PATH, {
    method: 'POST',
    body,
    timeoutMs: FA_MOVE_TIMEOUT_MS,
  });
}

// ── The capability ─────────────────────────────────────────────────────────

function isLeaguePlatform(p: unknown): p is LeaguePlatform {
  return typeof p === 'string' && (LEAGUE_PLATFORMS as readonly string[]).includes(p);
}

/** A `move` the client can honour. Absent, malformed, an unknown `mode`, or
 *  `submit` with no (or an unknown) `league_platform`: legacy (contract §1). */
export function isMoveCapability(move: unknown): move is FaMoveCapability {
  if (!move || typeof move !== 'object') return false;
  const m = move as { mode?: unknown; league_platform?: unknown };
  if (m.mode !== 'submit' && m.mode !== 'handoff' && m.mode !== 'unsupported') return false;
  return m.mode !== 'submit' || isLeaguePlatform(m.league_platform);
}

/** True when the sheet runs the in-app move layout for this capability. */
export function isSubmitCapability(move: unknown): move is FaMoveCapability & { league_platform: LeaguePlatform } {
  return isMoveCapability(move) && move.mode === 'submit';
}

// Platforms whose connect screen this binary can open from the sheet
// (contract §6). MFL has none in the 11-06 binary: `submit` there with a
// connect that isn't `ok` is shown as `unsupported`.
const CONNECTABLE: readonly LeaguePlatform[] = ['sleeper', 'espn'];
export function hasConnectScreen(platform: LeaguePlatform | null | undefined): boolean {
  return !!platform && CONNECTABLE.includes(platform);
}

export type GateStep =
  | 'legacy'
  | 'unsupported'
  | 'handoff'
  | 'connect'
  | 'verify'
  | 'consent'
  | 'submit'
  | 'submit_with_consent';

/** The pure gate (scope §B1, §C). Only 'submit' and 'submit_with_consent'
 *  may reach the move API (F7); connect and verify beat consent; an unticked
 *  box never submits (F2).
 *  - `connect`: the sheet's current knowledge, when a refusal has overridden
 *    the capability's (a 409 not_linked, say). Omitted: `move.connect`.
 *  - `consentValid`: whether a grant is known to be valid right now. */
export function faMoveGate(input: {
  move: unknown;
  row?: FaMoveRow | null;
  connect?: string | null;
  consentValid: boolean;
  ticked: boolean;
}): GateStep {
  const { move } = input;
  if (!isMoveCapability(move)) return 'legacy';
  if (move.mode === 'unsupported') return 'unsupported';
  if (move.mode === 'handoff') return 'handoff';
  const connect = input.connect ?? move.connect;
  if (connect !== 'ok' && !CONNECTABLE.includes(move.league_platform as LeaguePlatform)) {
    return 'unsupported';
  }
  // Any per-row move_mode holds the row in hand-off, not only exactly
  // 'handoff' ('HANDOFF', say): the conservative reading.
  if (input.row?.move_mode != null) return 'handoff';
  // §B7: a waiver player while claims are off is a hand-off (state 14),
  // whether or not the server set the row's override.
  if (input.row?.move_kind === 'claim' && move.claims !== true) return 'handoff';
  if (connect === 'expired' || connect === 'unverified') return 'verify';
  if (connect !== 'ok') return 'connect';
  if (input.consentValid) return 'submit';
  return input.ticked ? 'submit_with_consent' : 'consent';
}

/** Host routing (scope §B1: `move.mode` first). True when the capability
 *  opens the in-app move flow for this row, so a non-Sleeper league opens
 *  the sheet with no build. False means: route by resolveAddPlatform, as
 *  today (hand-off and unsupported are decided there, and the hand-off this
 *  binary has is Sleeper's). */
export function faMoveOpensSheet(move: unknown, row?: FaMoveRow | null): boolean {
  // In `submit` mode every step opens the sheet, a held row included: on a
  // non-Sleeper league it shows the server's move_line (this binary has no
  // other platform's opener), never NO_ADD_REASON's read-only text.
  return isSubmitCapability(move) && faMoveGate({ move, row, consentValid: false, ticked: false }) !== 'unsupported';
}

/** The capability, or null when it's absent, malformed or an unknown mode:
 *  then nothing of it is used, `move.copy` included (fully legacy). */
export function capabilityOrNull(move: unknown): FaMoveCapability | null {
  return isMoveCapability(move) ? move : null;
}

/** A row's D1 fields, only under a usable capability: with none, every
 *  row's move_kind / move_mode / move_line is ignored. */
export function rowMoveFields(move: unknown, row: FaMoveRow | null | undefined): FaMoveRow {
  if (!isMoveCapability(move) || !row) return {};
  return { move_kind: row.move_kind, move_mode: row.move_mode, move_line: row.move_line };
}

/** Valid until a moment strictly after `nowMs`. */
export function consentValidAt(until: unknown, nowMs: number): boolean {
  // Only an ISO string counts: a number (or anything else) is not a grant.
  if (typeof until !== 'string' || !until) return false;
  const t = Date.parse(until);
  return Number.isFinite(t) && t > nowMs;
}

/** The consent block from a GET or a 409 body, or null when any field the
 *  step renders is missing (then the client goes to hand-off, scope F4). */
export function readConsentBlock(raw: unknown): ConsentBlock | null {
  if (!raw || typeof raw !== 'object') return null;
  const c = raw as Record<string, unknown>;
  const str = (k: string) => typeof c[k] === 'string' && (c[k] as string).trim() !== '';
  if (!['copy_version', 'locale', 'title', 'checkbox_label', 'this_move', 'button_label'].every(str)) {
    return null;
  }
  const body = c.body;
  if (!Array.isArray(body) || body.length === 0 || !body.every((p) => typeof p === 'string')) return null;
  // Optional. A link is kept only with a label and an https URL; none left
  // means the app's own Terms and Privacy (consentLinks).
  const links = Array.isArray(c.links)
    ? c.links.filter(
        (l): l is ConsentLink =>
          !!l && typeof l === 'object' &&
          typeof (l as ConsentLink).label === 'string' && (l as ConsentLink).label.trim() !== '' &&
          typeof (l as ConsentLink).url === 'string' && /^https:\/\/\S+$/.test((l as ConsentLink).url),
      ).map((l) => ({ label: l.label, url: l.url }))
    : [];
  const reason = (CONSENT_REASONS as readonly unknown[]).includes(c.reason) ? (c.reason as ConsentReason) : undefined;
  return {
    copy_version: c.copy_version as string,
    locale: c.locale as string,
    title: c.title as string,
    body: body as string[],
    checkbox_label: c.checkbox_label as string,
    this_move: c.this_move as string,
    button_label: c.button_label as string,
    ...(links.length ? { links } : {}),
    ...(reason ? { reason } : {}),
  };
}

/** The consent step's links row (R15.8's "Terms · Privacy"): the block's own
 *  links when it carries any, else the app's Terms and Privacy pages, built
 *  as PaywallScreen's openLegal builds them (the API origin serves the web
 *  app, so the pages live at the API base; no second base URL). */
export function consentLinks(block: ConsentBlock): ConsentLink[] {
  // Per link: Terms and Privacy are always both present, the server's valid
  // one when it sent one, else the app's own. Any other valid server link
  // follows them.
  const base = getBaseUrl();
  const sent = block.links ?? [];
  const named = (re: RegExp) => sent.find((l) => re.test(l.label) || re.test(l.url));
  const terms = named(/terms/i) ?? { label: FA_MOVE_FALLBACK_COPY.terms_link, url: `${base}/terms` };
  const privacy = named(/privacy/i) ?? { label: FA_MOVE_FALLBACK_COPY.privacy_link, url: `${base}/privacy` };
  return [terms, privacy, ...sent.filter((l) => l !== terms && l !== privacy)];
}

/** What a consent GET at the tap leads to. NetInfo is read first: offline
 *  sends no GET at all. A GET that fails at the network level (status 0, the
 *  client's timer) is "not sent" (state 11), like the move itself. A 403
 *  `verification_required` (the route needs a verified session, contract §2)
 *  is state 4, Verify, like the move route's 403. Only another server-side
 *  failure or an incomplete block is F4's hand-off. */
export type ConsentStep =
  | { kind: 'offline' }
  | { kind: 'not_sent' }
  | { kind: 'verify'; message?: string }
  | { kind: 'valid' }
  | { kind: 'consent'; block: ConsentBlock }
  | { kind: 'unavailable' };

export async function fetchConsentStep(platform: LeaguePlatform): Promise<ConsentStep> {
  if (await isOffline()) return { kind: 'offline' };
  let status: ConsentStatus;
  try {
    status = await getConsent(platform);
  } catch (err) {
    if (!(err instanceof ApiError) || err.isTimeout || err.status === 0) return { kind: 'not_sent' };
    if (err.isVerificationRequired) {
      const message = (err.body as { message?: unknown }).message;
      return { kind: 'verify', ...(typeof message === 'string' && message ? { message } : {}) };
    }
    return { kind: 'unavailable' };
  }
  if (status && status.valid === true) return { kind: 'valid' };
  const block = readConsentBlock(status?.consent);
  return block ? { kind: 'consent', block } : { kind: 'unavailable' };
}

/** Settings' consent read answers these as "no row", every visit while
 *  dark (404) or unverified (403): not failures worth an event. */
export const CONSENT_QUIET_STATUSES: readonly number[] = [403, 404];

/** Settings' read (contract §2): 200 with `valid: false` when there's no
 *  grant. A 404 (an older server) and a 403 `verification_required` (the
 *  route needs a verified session) read as `valid: false` too: no row. */
export async function readConsentStatus(platform: LeaguePlatform): Promise<ConsentStatus> {
  try {
    // Routine on a dark or unverified visit, so no api_request_failed for them.
    return await getConsent(platform, { quietStatuses: CONSENT_QUIET_STATUSES });
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.isVerificationRequired)) {
      return { platform, valid: false, until: null, status_line: null, stop_label: null };
    }
    throw err;
  }
}

/** F5 / review round 2: the "terms changed" line shows when the server says
 *  the version changed, or the sheet already showed another copy_version. */
export function termsChanged(block: ConsentBlock, shownVersion: string | null): boolean {
  return block.reason === 'version' || (shownVersion != null && shownVersion !== block.copy_version);
}

/** The pair the move request echoes: the shown block's, as received (F11). */
export function consentEcho(block: ConsentBlock): ConsentEcho {
  return { copy_version: block.copy_version, locale: block.locale };
}

// Platforms the user withdrew from in this app run (Settings' Stop roster
// moves). The next consent step reports `withdrawn`, once.
const _withdrawnHere = new Set<LeaguePlatform>();
export function consumeWithdrawal(platform: LeaguePlatform): boolean {
  return _withdrawnHere.delete(platform);
}

/** `fa_move_connect_shown.reason` (analytics-lead, round 3): the capability's
 *  connect value, and `unknown` for any value outside the closed set. The UI
 *  shows the plain connect step for an unknown value either way. */
export const CONNECT_SHOWN_REASONS = ['not_linked', 'expired', 'unverified', 'other_account', 'unknown'] as const;
export type ConnectShownReason = (typeof CONNECT_SHOWN_REASONS)[number];
export function connectShownReason(connect: unknown): ConnectShownReason {
  return connect === 'not_linked' || connect === 'expired' || connect === 'unverified' || connect === 'other_account'
    ? connect
    : 'unknown';
}

export const CONSENT_REASONS = ['first', 'lapsed', 'version', 'withdrawn'] as const;
export type ConsentReason = (typeof CONSENT_REASONS)[number];

/** `fa_move_consent_shown.reason`. The contract carries no reason, so this
 *  is the client's best reading: a 409 whose copy_version differs from the
 *  one shown is `version`; a withdrawal made in this app run is `withdrawn`;
 *  a known grant that no longer holds is `lapsed`; otherwise `first`. */
export function consentReason(input: {
  consentUntil: string | null | undefined;
  shownVersion: string | null;
  offeredVersion: string;
  withdrawnHere: boolean;
}): ConsentReason {
  if (input.shownVersion && input.shownVersion !== input.offeredVersion) return 'version';
  if (input.withdrawnHere) return 'withdrawn';
  if (input.consentUntil) return 'lapsed';
  return 'first';
}

/** `fa_move_consent_shown.reason`: the block's own `reason` when the server
 *  sends one (contract §2), else the client's reading above. */
export function consentShownReason(
  block: ConsentBlock,
  inference: Parameters<typeof consentReason>[0],
): ConsentReason {
  const inferred = consentReason(inference);
  return block.reason ?? inferred;
}

// ── Codes → states (contract §4) ────────────────────────────────────────────

/** Analytics C3: `error_code`'s closed set of 21, platform-free (C2). */
export const FA_MOVE_ERROR_CODES = [
  'feature_disabled',
  'bad_request',
  'verification_required',
  'not_linked',
  'expired',
  'unconfigured',
  'consent_required',
  'roster_full_drop_required',
  'asset_not_owned',
  'player_unavailable',
  'waiver_bid_over_budget',
  'waiver_claim_unsupported',
  'move_kind_changed',
  'rejected',
  'write_failed',
  'outcome_unknown',
  'move_in_progress',
  'internal_error',
  'network',
  'timeout',
  'unknown',
] as const;
export type FaMoveErrorCode = (typeof FA_MOVE_ERROR_CODES)[number];

// Codes the server sends without a platform prefix.
const BARE_CODES: readonly FaMoveErrorCode[] = [
  'feature_disabled',
  'bad_request',
  'verification_required',
  'consent_required',
  'roster_full_drop_required',
  'asset_not_owned',
  'player_unavailable',
  'waiver_bid_over_budget',
  'waiver_claim_unsupported',
  'move_kind_changed',
  'move_in_progress',
  'internal_error',
];
// `{platform}_<suffix>` codes, mapped by suffix so MFL and ESPN need no build.
const PLATFORM_SUFFIX = new RegExp(
  `^(?:${LEAGUE_PLATFORMS.join('|')})_(not_linked|expired|unconfigured|rejected|write_failed|outcome_unknown)$`,
);

/** A server code → its platform-free C3 value, or null when unrecognised. */
export function moveCodeSuffix(code: unknown): FaMoveErrorCode | null {
  if (typeof code !== 'string' || !code) return null;
  if ((BARE_CODES as readonly string[]).includes(code)) return code as FaMoveErrorCode;
  const m = PLATFORM_SUFFIX.exec(code);
  return m ? (m[1] as FaMoveErrorCode) : null;
}

/** The §C state a failed move lands in. */
export type MoveFailureState =
  | 'handoff' // 1
  | 'connect' // 3
  | 'verify' // 4
  | 'consent' // 5
  | 'roster_full' // 10a
  | 'drop_gone' // 10b
  | 'player_taken' // 10c
  | 'over_budget' // 10d
  | 'kind_changed' // 10e
  | 'platform_refused' // 10f
  | 'unavailable' // 10g
  | 'not_sent' // 11
  | 'unknown' // 12
  | 'neutral' // 12-style, nothing to retry (400, an unrecognised 4xx)
  | 'rejected' // 13
  | 'claims_off'; // 14

const STATE_BY_CODE: Record<FaMoveErrorCode, MoveFailureState> = {
  feature_disabled: 'handoff',
  bad_request: 'neutral',
  verification_required: 'verify',
  not_linked: 'connect',
  expired: 'verify',
  unconfigured: 'unavailable',
  consent_required: 'consent',
  roster_full_drop_required: 'roster_full',
  asset_not_owned: 'drop_gone',
  player_unavailable: 'player_taken',
  waiver_bid_over_budget: 'over_budget',
  waiver_claim_unsupported: 'claims_off',
  move_kind_changed: 'kind_changed',
  rejected: 'rejected',
  write_failed: 'platform_refused', // 'not_sent' when the body carries a kind
  outcome_unknown: 'unknown',
  move_in_progress: 'unknown',
  internal_error: 'unknown',
  network: 'unknown',
  timeout: 'unknown',
  unknown: 'unknown',
};

export interface MoveFailure {
  state: MoveFailureState;
  /** Analytics: the platform-free C3 value (C2, C4). */
  errorCode: FaMoveErrorCode;
  /** HTTP status; 0 for the client's timer and for no answer at all. */
  status: number;
  /** C6: only when the body carries `network` or `roster_read`. */
  kind?: 'network' | 'roster_read';
  /** The server's own code, as sent. */
  code?: string;
  title?: string;
  message?: string;
  remaining?: number;
  consent?: ConsentBlock | null;
}

/** Any failure of the move request → its §C state and analytics fields. */
export function classifyMoveError(err: unknown): MoveFailure {
  // fetch's network TypeError (POSTs are never retried, api/client.ts): the
  // request may have gone out before the drop.
  if (!(err instanceof ApiError)) return { state: 'unknown', errorCode: 'network', status: 0 };
  if (err.isTimeout) return { state: 'unknown', errorCode: 'timeout', status: 0 };
  if (err.status === 0) return { state: 'unknown', errorCode: 'network', status: 0 };
  const body = err.body && typeof err.body === 'object' ? (err.body as Record<string, unknown>) : {};
  const code = typeof body.error === 'string' && body.error ? body.error : undefined;
  const text = (k: string) => (typeof body[k] === 'string' && body[k] ? (body[k] as string) : undefined);
  const kind: MoveFailure['kind'] =
    body.kind === 'network' || body.kind === 'roster_read' ? body.kind : undefined;
  const base = {
    status: err.status,
    ...(kind ? { kind } : {}),
    ...(code ? { code } : {}),
    ...(text('title') ? { title: text('title') } : {}),
    ...(text('message') ? { message: text('message') } : {}),
  };
  const suffix = moveCodeSuffix(code);
  if (!suffix) {
    // No usable code: a 5xx may have landed (12); any other 4xx is the
    // 12-style panel with the server's message and no retry.
    return { ...base, state: err.status >= 500 ? 'unknown' : 'neutral', errorCode: 'unknown' };
  }
  let state = STATE_BY_CODE[suffix];
  if (suffix === 'write_failed' && kind) state = 'not_sent';
  return {
    ...base,
    state,
    errorCode: suffix,
    ...(suffix === 'waiver_bid_over_budget' && typeof body.remaining === 'number'
      ? { remaining: body.remaining }
      : {}),
    ...(suffix === 'consent_required' ? { consent: readConsentBlock(body.consent) } : {}),
  };
}

/** The move may have reached the platform: state 12, never a retry (F3).
 *  `*_outcome_unknown`, `move_in_progress`, `internal_error`, the client's
 *  timer, status 0, and a 5xx with no usable code. */
export function isMoveOutcomeUnknown(err: unknown): boolean {
  return classifyMoveError(err).state === 'unknown';
}

// ── Bounded reads ───────────────────────────────────────────────────────────

/** The sheet's own re-reads (after Connect, on 10e) give up after this, so
 *  the sheet never stays busy offline; the server's 409s are the net. */
export const FA_MOVE_REREAD_WAIT_MS = 5_000;

/** `p`'s value, or undefined if it rejects or takes longer than `ms`. */
export function withTimeout<T>(p: Promise<T>, ms: number): Promise<T | undefined> {
  return new Promise((resolve) => {
    const t = setTimeout(() => resolve(undefined), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      () => {
        clearTimeout(t);
        resolve(undefined);
      },
    );
  });
}

// ── A host's prefetched capability (Usage Trends) ─────────────────────────
// Usage Trends prefetches each listed league's capability in the background
// when an availability list opens, so an Add tap can route by it without
// waiting; an Add whose league isn't cached routes exactly as #509 did. Its
// own key, never the sheet's ['free-agents', …]: the sheet reads its own list
// after the league switch.

export function faMoveCapabilityKey(leagueId: string): readonly unknown[] {
  return ['fa-move-capability', leagueId];
}
export const FA_MOVE_CAPABILITY_STALE_MS = 60_000;

/** One league's capability, kept as `move` plus each row's move_* fields
 *  only (the cache holds nothing else of the list). */
export interface LeagueCapability {
  move: FaMoveCapability | null;
  rows: Record<string, FaMoveRow>;
}

export async function readLeagueCapability(leagueId: string): Promise<LeagueCapability> {
  const data = await getFreeAgents(leagueId, 'ALL');
  const move = capabilityOrNull(data?.move);
  const rows: Record<string, FaMoveRow> = {};
  if (move) {
    for (const r of data?.free_agents ?? []) {
      const f = rowMoveFields(move, r);
      const kept = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== undefined)) as FaMoveRow;
      if (Object.keys(kept).length) rows[r.player_id] = kept;
    }
  }
  return { move, rows };
}

/** At the Add tap: the cached capability and this row's fields, or none
 *  (then the host routes the legacy way, at once). */
export function capabilityForRow(
  cached: LeagueCapability | null | undefined,
  playerId: string,
): { move: FaMoveCapability | null; row: FaMoveRow } {
  const move = capabilityOrNull(cached?.move);
  return { move, row: move ? cached?.rows?.[playerId] ?? {} : {} };
}

// ── Analytics (scope §1, C1–C6) ─────────────────────────────────────────────

export type FaMoveSurface = 'free_agents' | 'usage_trends';
export type FaMoveEvent =
  | 'fa_move_connect_shown'
  | 'fa_move_consent_shown'
  | 'fa_move_write_attempted'
  | 'fa_move_write_failed';

/** C1: only in `submit` mode, where `league_platform` is set; anything else
 *  emits nothing. Never a prop named `platform` (that column is the device's). */
export function trackFaMove(move: unknown, event: FaMoveEvent, props: Record<string, unknown>): boolean {
  if (!isSubmitCapability(move)) return false;
  track(event, { ...props, league_platform: move.league_platform });
  return true;
}

// ── One tap → one attempt (F7, F9, F17) ────────────────────────────────────

export type AttemptOutcome =
  /** Offline at the tap: nothing sent, no attempt_id, no event (F17). */
  | { sent: false }
  | { sent: true; attemptId: string; response: MoveResponse }
  | { sent: true; attemptId: string; failure: MoveFailure };

/** One attempt_id: a v4-UUID-shaped string, 8-4-4-4-12 lowercase hex
 *  (contract §3). Hermes has no Web Crypto, so it uses crypto.getRandomValues
 *  when it exists and Math.random otherwise; the server treats the id as
 *  opaque and scopes it per user, so it needs to be unique, not secret. */
export function newAttemptId(): string {
  const bytes = new Uint8Array(16);
  const c = (globalThis as { crypto?: { getRandomValues?: (a: Uint8Array) => Uint8Array } }).crypto;
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const h = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

async function isOffline(): Promise<boolean> {
  try {
    const state = await NetInfo.fetch();
    return state.isConnected === false;
  } catch {
    // Can't tell: the request goes out, and a drop after it is outcome unknown.
    return false;
  }
}

/** One named-CTA tap. Reads NetInfo first: offline sends nothing and mints
 *  nothing. Otherwise mints ONE attempt_id for this tap, sends, and records
 *  `write_attempted` / `write_failed` (C1–C6). */
export async function attemptMove(input: {
  move: FaMoveCapability;
  surface: FaMoveSurface;
  request: Omit<MoveRequest, 'attempt_id'>;
}): Promise<AttemptOutcome> {
  if (await isOffline()) return { sent: false };
  const attemptId = newAttemptId();
  const body: MoveRequest = { ...input.request, surface: input.surface, attempt_id: attemptId };
  trackFaMove(input.move, 'fa_move_write_attempted', {
    surface: input.surface,
    has_drop: body.drop_player_id != null,
    has_bid: body.faab_bid != null,
    consent_ticked: body.consent != null,
    attempt_id: attemptId,
  });
  let failure: MoveFailure;
  try {
    const response = await submitMove(body);
    if (response && (response.status === 'complete' || response.status === 'pending')) {
      return { sent: true, attemptId, response };
    }
    // A 2xx the client can't read: it may have landed.
    failure = { state: 'unknown', errorCode: 'unknown', status: 200 };
  } catch (err) {
    failure = classifyMoveError(err);
  }
  trackFaMove(input.move, 'fa_move_write_failed', {
    surface: input.surface,
    error_code: failure.errorCode,
    status: failure.status,
    attempt_id: attemptId,
    ...(failure.kind ? { kind: failure.kind } : {}),
  });
  return { sent: true, attemptId, failure };
}

// ── Copy slots (contract §7) ───────────────────────────────────────────────

const PLACEHOLDERS = ['add', 'drop', 'bid', 'league', 'date', 'name', 'cta'] as const;
export type CopyVars = Partial<Record<(typeof PLACEHOLDERS)[number], string | null>>;

/** Fills the contract's placeholders. An unknown placeholder is left as is;
 *  a known one with no value makes the whole template unusable (null), so
 *  the caller falls back instead of showing "{drop}". */
export function fillTemplate(template: string, vars: CopyVars): string | null {
  let missing = false;
  const out = template.replace(/\{([a-z_]+)\}/g, (whole, key: string) => {
    if (!(PLACEHOLDERS as readonly string[]).includes(key)) return whole;
    const v = vars[key as keyof CopyVars];
    if (v == null || v === '') {
      missing = true;
      return whole;
    }
    return v;
  });
  return missing ? null : out;
}

const PLATFORM_NAME: Record<LeaguePlatform, string> = { sleeper: 'Sleeper', mfl: 'MFL', espn: 'ESPN' };

// The neutral fallbacks (G21), ONE constant (F4). Platform-free: `{platform}`
// is filled with the league platform's name, here only, never in a server
// template. Never consent text, never "Sleeper doesn't allow apps to submit
// claims". Final copy: marketing-lead addendum 17 §A (A2, A3.1–A3.10); the
// finality, waiver and bid lines are legal's (D10(b), R15.1) with the
// platform filled in. Pinned verbatim by tests/check-fa-move.js (Z1).
export const FA_MOVE_FALLBACK_COPY = {
  header_add: 'Add {name}',
  header_claim: 'Claim {name}',
  cta_add: 'Add {add}',
  cta_add_drop: 'Add {add}, drop {drop}',
  cta_claim: 'Claim {add} for {bid}',
  cta_claim_drop: 'Claim {add} for {bid}, drop {drop}',
  cta_claim_no_bid: 'Claim {add}',
  cta_claim_drop_no_bid: 'Claim {add}, drop {drop}',
  league_line: 'In {league}',
  finality: "Final on {platform}. Fleeced can't undo it.",
  waiver_line: 'This places a waiver claim for {add} (dropping {drop} if it clears). {platform} processes it on its waiver schedule.',
  waiver_line_no_drop: 'This places a waiver claim for {add}. {platform} processes it on its waiver schedule.',
  bid_line: 'Bid: {bid}',
  window_line: 'Roster moves: on until {date}',
  turn_off: 'Turn off',
  do_in_platform: 'Do it in {platform} instead',
  open_platform: 'Open in {platform} to claim',
  open_in_platform: 'Open in {platform}',
  handoff_footer: "You'll finish this move in {platform}.",
  connect_line: 'Connect your {platform} sign-in to make moves from here.',
  verify_line: 'Verify your {platform} sign-in to make moves from here.',
  other_account_line: "That {platform} account isn't in {league}. Connect the one that owns your team.",
  not_sent_line: "Couldn't reach {platform} right now, so nothing was sent.",
  // State 11 when Fleeced's own server didn't answer (offline at the tap, a
  // consent GET with no answer): not the platform's fault, so no platform
  // named. not_sent_line stays for the server's {p}_write_failed + network.
  // PENDING MARKETING (platforms-eng is telling them).
  offline_line: "Couldn't connect right now, so nothing was sent.",
  unknown_title: 'Check before resending',
  unknown_body: "Couldn't confirm whether this move reached {platform}. Check your roster and claims in {platform} before you make it again.",
  unavailable_line: "Moves from Fleeced aren't available right now. You can still make this move in {platform}.",
  still_sending: 'Still sending…',
  not_connected: "{platform} isn't connected",
  terms_changed: 'The terms changed. Read them again before you tick the box.',
  result_added: 'Done',
  result_pending: 'Claim submitted',
  refusal_title: "This move wasn't made",
  drop_to_make_room: 'Drop a player to make room',
  not_now: 'Not now',
  tick_hint: 'Tick the box to make the move',
  // The consent step's links when the block carries none (R15.8: "Terms · Privacy").
  terms_link: 'Terms',
  privacy_link: 'Privacy',
  link_hint: 'Opens in your browser',
  // The host's list row after a claim was submitted (scope §C state 9).
  claim_pending: 'Claim pending',
  // A non-Sleeper row held in hand-off with no server line (this binary has
  // no other platform's opener).
  held_line: "This move can't be made from Fleeced right now. Check {platform}.",
  // Settings, when DELETE fails (contract §2): the grant stays in force.
  stop_failed: "Couldn't turn off roster moves. Try again.",
} satisfies Record<MoveCopyKey, string> & Record<string, string>;
export type FallbackKey = keyof typeof FA_MOVE_FALLBACK_COPY;

/** The fallback for `key`, with `{platform}` named and the rest filled. */
export function fallbackCopy(key: FallbackKey, vars: CopyVars, platform: LeaguePlatform | null): string | null {
  const named = FA_MOVE_FALLBACK_COPY[key].replace(/\{platform\}/g, platform ? PLATFORM_NAME[platform] : 'your league app');
  return fillTemplate(named, vars);
}

/** A pre-tap slot: the server's template filled, else the neutral fallback. */
export function moveCopy(
  copy: MoveCopy | null | undefined,
  key: MoveCopyKey,
  vars: CopyVars,
  platform: LeaguePlatform | null,
): string | null {
  const server = copy?.[key];
  if (typeof server === 'string' && server.trim() !== '') {
    const filled = fillTemplate(server, vars);
    if (filled != null) return filled;
  }
  return fallbackCopy(key, vars, platform);
}

/** The named CTA (D10(a)) for the row's move_kind, from `move.copy` or the
 *  fallback. The consent step's "This move" line uses this same string. */
export function moveCtaLabel(
  copy: MoveCopy | null | undefined,
  kind: MoveKind,
  vars: { add: string; drop?: string | null; bid?: string | null },
  platform: LeaguePlatform | null,
): string {
  const hasDrop = !!vars.drop;
  const hasBid = !!vars.bid;
  // Contract §7: a claim with no bid (a priority-waiver league) has its own
  // slots; the bid forms carry {bid}.
  const key: MoveCopyKey =
    kind === 'claim'
      ? hasBid
        ? hasDrop ? 'cta_claim_drop' : 'cta_claim'
        : hasDrop ? 'cta_claim_drop_no_bid' : 'cta_claim_no_bid'
      : hasDrop ? 'cta_add_drop' : 'cta_add';
  return moveCopy(copy, key, vars, platform) ?? vars.add;
}

/** A claim's lines under the CTA (contract §7): `waiver_line` with a drop,
 *  `waiver_line_no_drop` without, then `bid_line` only when there's a bid. */
export function waiverLines(
  copy: MoveCopy | null | undefined,
  vars: { add: string; drop?: string | null; bid?: string | null },
  platform: LeaguePlatform | null,
): string[] {
  const lines = [moveCopy(copy, vars.drop ? 'waiver_line' : 'waiver_line_no_drop', vars, platform)];
  if (vars.bid) lines.push(moveCopy(copy, 'bid_line', vars, platform));
  return lines.filter((l): l is string => !!l);
}

/** `{bid}`: the dollar amount, as the CTA names it ("Claim A for $7"). */
export function bidText(bid: number): string {
  return `$${bid.toLocaleString('en-US')}`;
}

/** `{date}`: the window's end, short ("Nov 8"). */
export function windowDateText(until: string | null | undefined): string | null {
  if (!until) return null;
  const t = Date.parse(until);
  if (!Number.isFinite(t)) return null;
  return new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
