import { ApiError, getSessionRevision, getSessionToken, isCurrentSessionExpiry, requestAborted, runWithDeadline, TIMEOUT_MESSAGE } from '../api/client';
import type { LeagueLite, SessionInitControl, SessionInitSeed } from '../api/auth';
import type { SavedUser } from './useSession';

export const LEAGUE_ATTEMPT_MS = 90_000;
export type InitCause = 'automatic' | 'refresh' | 'selection';
export interface LeagueContext {
  user: SavedUser;
  league: LeagueLite;
  token: string;
  generation: number;
  authorization: number;
  deadlineAt: number;
  assertIdentity: (error?: unknown) => void;
  assertCurrent: () => void;
}
interface Lane {
  tail: Promise<void>;
  uncertain: number;
  readyGeneration?: number;
  readyAt: number;
  pending: Map<number, Promise<void>>;
}
const uncertainError = () => new ApiError(409, {error: 'session_init_uncertain'}, 'League setup could not be confirmed. Please refresh or choose your league again.');

/** One in-process owner for every native league-init writer. A timeout is NOT
 * server cancellation: uncertainty survives screen remount/foreground until a
 * later deliberate action. Only acknowledged successful A→B is serialized. */
export function createLeagueSessionLifecycle(deps: {
  currentUser: () => SavedUser | null;
  initialize: (user: SavedUser, league: LeagueLite, control: SessionInitControl) => Promise<SessionInitSeed>;
  onReady: (context: LeagueContext, seed: SessionInitSeed) => void;
}) {
  let generation = 0, sequence = 0, revision = getSessionRevision();
  let intent: {userId: string; leagueId: string} | undefined;
  const lanes = new Map<string, Lane>();
  const cancelObsolete = new Set<() => void>();
  const advance = () => { generation++; for (const cancel of cancelObsolete) cancel(); return generation; };
  const invalidate = () => { advance(); intent = undefined; };
  const currentGeneration = () => generation;
  const assertIdentity = (user: SavedUser, expected: number, tokenRevision: number, error?: unknown) => {
    if (generation !== expected || deps.currentUser()?.user_id !== user.user_id
      || (getSessionRevision() !== tokenRevision && !isCurrentSessionExpiry(error, tokenRevision))) throw requestAborted();
  };
  async function capture(user: SavedUser, league: LeagueLite, cause: InitCause, deadlineAt: number, signal?: AbortSignal, selectionAuthorization?: number): Promise<LeagueContext> {
    if (deps.currentUser()?.user_id !== user.user_id) throw requestAborted();
    if (revision !== getSessionRevision()) { revision = getSessionRevision(); invalidate(); }
    if (!league.league_id || league.league_id === 'no_league') throw requestAborted();
    const matches = intent?.userId === user.user_id && intent?.leagueId === league.league_id;
    const obsoleteIntent = !!intent && !matches && cause === 'automatic';
    if (!intent || cause === 'selection' || (cause === 'refresh' && !matches)) {
      advance(); intent = {userId: user.user_id, leagueId: league.league_id};
    }
    let expected = generation;
    const tokenRevision = getSessionRevision();
    const authorization = cause === 'automatic' ? 0 : selectionAuthorization ?? ++sequence;
    const token = await runWithDeadline(() => getSessionToken(), deadlineAt, signal);
    assertIdentity(user, expected, tokenRevision);
    if (!token) throw requestAborted();
    let lane = lanes.get(token);
    if (!lane) { lane = {tail: Promise.resolve(), uncertain: 0, readyAt: 0, pending: new Map()}; lanes.set(token, lane); }
    if (lane.uncertain && cause === 'automatic') throw uncertainError();
    if (obsoleteIntent) throw requestAborted();
    if (lane.uncertain && authorization > lane.uncertain) expected = advance();
    return {user, league, token, generation: expected, authorization, deadlineAt,
      assertIdentity: error => assertIdentity(user, expected, tokenRevision, error),
      assertCurrent: () => {
        assertIdentity(user, expected, tokenRevision);
        if (Date.now() >= deadlineAt) throw new ApiError(0, null, TIMEOUT_MESSAGE, true);
      }};
  }
  async function ensure(context: LeagueContext, options: {force?: boolean; maxAgeMs?: number; deadlineAt: number; signal?: AbortSignal}): Promise<void> {
    context.assertCurrent();
    const lane = lanes.get(context.token)!;
    if (lane.uncertain) {
      if (context.authorization <= lane.uncertain) throw uncertainError();
      lane.uncertain = 0; // explicit authorization means uninitialized, never ready
      lane.readyGeneration = undefined;
    }
    let work = lane.pending.get(context.generation);
    if (!work && !options.force && lane.readyGeneration === context.generation && Date.now() - lane.readyAt < (options.maxAgeMs ?? Infinity)) return;
    if (!work) {
      const predecessor = lane.tail;
      const ownDeadline = Math.min(context.deadlineAt, options.deadlineAt, Date.now() + LEAGUE_ATTEMPT_MS);
      let dispatched = false;
      const superseded = new AbortController();
      // Discard obsolete preparation immediately, but never pretend aborting
      // an accepted POST canceled the server's writer. B waits for its ACK.
      const cancel = () => { if (context.generation !== generation && !dispatched) superseded.abort(); };
      cancelObsolete.add(cancel);
      const markUncertain = () => { lane.uncertain = ++sequence; lane.readyGeneration = undefined; };
      work = runWithDeadline(async signal => {
        const assertCurrent = () => {
          context.assertCurrent();
          if (signal.aborted || Date.now() >= ownDeadline) throw new ApiError(0, null, TIMEOUT_MESSAGE, true);
        };
        await predecessor;
        assertCurrent();
        // An intent queued BEFORE its predecessor became uncertain is not a
        // fresh manual authorization, even if the original call was a tap.
        if (lane.uncertain) throw uncertainError();
        const control: SessionInitControl = {
          token: context.token, signal, deadlineAt: ownDeadline, assertCurrent,
          onDispatch: () => { dispatched = true; },
          submit: async send => {
            try { const result = await send(); dispatched = false; return result; }
            catch (error) {
              // Gateway/server failures are not proof that a mutation stopped.
              const denied = error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408;
              if (dispatched && !denied) markUncertain();
              dispatched = false; throw error;
            }
          },
        };
        const seed = await deps.initialize(context.user, context.league, control);
        assertCurrent();
        if (lane.uncertain) throw uncertainError();
        deps.onReady(context, seed);
        lane.readyGeneration = context.generation; lane.readyAt = Date.now();
      }, ownDeadline, superseded.signal).catch(error => {
        if (dispatched) markUncertain();
        throw error;
      }).finally(() => cancelObsolete.delete(cancel));
      lane.pending.set(context.generation, work);
      lane.tail = work.then(() => {}, () => {});
      const pending = work;
      void lane.tail.then(() => { if (lane.pending.get(context.generation) === pending) lane.pending.delete(context.generation); });
    }
    // Only this caller detaches; never abort somebody else's shared init.
    await runWithDeadline(() => work!, options.deadlineAt, options.signal);
    context.assertCurrent();
  }
  // Connect learns its target after a URL read. Its existing gesture must be
  // dated now, not upgraded into fresh permission when that read completes.
  const reserveSelectionAuthorization = () => ++sequence;
  const onSuperseded = (context: LeagueContext, cancel: () => void) => {
    const check = () => { try { context.assertIdentity(); } catch { cancel(); } };
    cancelObsolete.add(check);
    check();
    return () => { cancelObsolete.delete(check); };
  };
  return {capture, ensure, invalidate, currentGeneration, reserveSelectionAuthorization, onSuperseded};
}
