#!/usr/bin/env node
// R2 (action-banner ux-states §7, 11-06 bug fix) — arriving on Matches with
// a match_id scrolls to that card and marks it.
//
// WHY THIS EXISTS
//   A push tap on "@Alex accepted your trade" landed on the Matches list,
//   not on that trade. RootNav → utils/deepLinks.routeNotificationTap
//   already passed `{ match_id, src: 'push', ts }` into Matches, but
//   MatchesScreen read route.params only for `guidedArrival`, `segment` and
//   `leagueId`; nothing read `match_id`. And every card reads "New match
//   with @…" whatever its state (R9), so after the push the mark is the only
//   thing that says which card it meant. This guard pins the one arrival
//   effect, its edge states (§7 "When the match isn't there"), the scroll
//   mechanics release-lead's QA (#568) tightened, and design-lead's mark.
//
// Two halves:
//   U-*  EXECUTED: transpile the real pure module (src/utils/matchesDerive.ts,
//        zero runtime imports by design) and run indexForMatch,
//        notFoundToast, the shipped MATCH_NOT_FOUND_LINE, clampOffset,
//        scrollFailureJump and endClamp under plain node (the
//        check-matches-counts.js idiom; mobile has no jest).
//   P-*  STRUCTURAL pins on MatchesScreen.tsx (comments stripped) plus the
//        producer contract in utils/deepLinks.ts and navigation/RootNav.tsx.
//
// HONEST LABEL (G-035): the P-* pins prove the presence of exact wirings,
// not runtime behavior. Whether the list visibly lands on the card, the
// outline shows for ~2 s with all four sides, and VoiceOver focus moves is
// on the manual TestFlight checklist in docs/plans/matches-push-scroll/.
//
// Named sabotages (each run RED once during authoring, then restored) — see
// the list in docs/plans/matches-push-scroll/scope.md §3.
//
// Run: node tests/check-matches-push-scroll.js

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');
const flatten = (src) => stripComments(src).replace(/\s+/g, ' ');

let failures = 0;
let passes = 0;
const ok = (name) => {
  passes += 1;
  console.log(`PASS  ${name}`);
};
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));
const eq = (name, actual, expected) =>
  assert(
    JSON.stringify(actual) === JSON.stringify(expected),
    name,
    `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );
// Slice [start, end) between two literal anchors in a flattened source.
const slice = (src, startAnchor, endAnchor) => {
  const s = src.indexOf(startAnchor);
  if (s < 0) return '';
  const e = src.indexOf(endAnchor, s + startAnchor.length);
  return e < 0 ? '' : src.slice(s, e);
};
const count = (src, needle) => src.split(needle).length - 1;

// ── U: execute the pure helpers ────────────────────────────────────────────
const js = ts.transpileModule(read('src/utils/matchesDerive.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `matchesDerive.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const {
  indexForMatch,
  notFoundToast,
  MATCH_NOT_FOUND_LINE,
  NOT_FOUND_HOLD_MS,
  clampOffset,
  scrollFailureJump,
  endClamp,
} = moduleShim.exports;

{
  const rows = [{ match_id: '11' }, { match_id: '12' }, { match_id: '13' }];
  eq('U-1a indexForMatch finds the row the arrival names', indexForMatch(rows, '12'), 1);
  eq('U-1b not in the list → -1 (the not-found path)', indexForMatch(rows, '99'), -1);
  eq('U-1c empty list → -1', indexForMatch([], '12'), -1);
  eq('U-1d ids compare as strings (route param is String()-coerced)', indexForMatch(rows, '011'), -1);
}
eq('U-2a notFoundToast(null) → null: no line renders', notFoundToast(null), null);
eq('U-2b notFoundToast(string) → exactly that string, held ~4 s, neutral tone',
  notFoundToast('Some words.'), { msg: 'Some words.', holdMs: 4000 });
eq('U-2c MATCH_NOT_FOUND_LINE SHIPS AS null (marketing owns the words, ~11-03)',
  MATCH_NOT_FOUND_LINE, null);
eq('U-2d NOT_FOUND_HOLD_MS is the §7 ~4 s', NOT_FOUND_HOLD_MS, 4000);
eq('U-3a clampOffset floors at 0', clampOffset(-12, 500), 0);
eq('U-3b clampOffset passes an in-range offset', clampOffset(240, 500), 240);
eq('U-3c clampOffset caps at the content end (no blank band)', clampOffset(900, 500), 500);
eq('U-3d unknown end → floor only', clampOffset(900, null), 900);
eq('U-3e content shorter than the viewport → 0', clampOffset(40, -100), 0);
eq('U-4a measured average → the estimate, minus the view offset',
  scrollFailureJump({ index: 10, averageItemLength: 300, highestMeasuredFrameIndex: 4 }, 12, null),
  { offset: 2988 });
eq('U-4b the estimate is clamped to the content end',
  scrollFailureJump({ index: 10, averageItemLength: 300, highestMeasuredFrameIndex: 4 }, 12, 2500),
  { offset: 2500 });
eq('U-4c fresh mount (average 0) → step to the furthest measured row',
  scrollFailureJump({ index: 20, averageItemLength: 0, highestMeasuredFrameIndex: 3 }, 12, null),
  { index: 3 });
eq('U-4d nothing measured → no jump',
  scrollFailureJump({ index: 20, averageItemLength: 0, highestMeasuredFrameIndex: -1 }, 12, null),
  null);
eq('U-5a a settle past the end → pull back to the end', endClamp(900, 1500, 700), 800);
eq('U-5b a settle within 1pt of the end → no pull', endClamp(800.5, 1500, 700), null);
eq('U-5c an in-range settle → no pull', endClamp(300, 1500, 700), null);

// ── P: MatchesScreen structure ─────────────────────────────────────────────
const RAW = read('src/screens/MatchesScreen.tsx');
const F = flatten(RAW);

// The arrival block (params → handlers) and its one arrival effect.
const BLOCK = slice(F, 'const arrivalMatchId =', 'const matchCounts = useMemo(');
const EFFECT = slice(
  BLOCK,
  'useEffect(() => { const pending = arrivalRef.current; if (!isFocused) {',
  'const onArrivalScrollFailed',
);
const FAILED = slice(BLOCK, 'const onArrivalScrollFailed = useCallback(', 'const onArrivalSettle');
const SETTLE = slice(BLOCK, 'const onArrivalSettle = useCallback(', 'const onArrivalDrag');
const LIST = slice(F, 'ref={matchesListRef}', 'ItemSeparatorComponent');
const ROW = LIST.includes('renderItem={({ item }) => (') ? LIST.slice(LIST.indexOf('renderItem={({ item }) => (')) : '';
const MARK = slice(F, 'export const ARRIVAL_MARK = {', '} as const;');
const FOUND = slice(EFFECT, "if (segment !== 'mutual') return;", '}, [isFocused');
assert(BLOCK.length > 0 && EFFECT.length > 0, 'P-0a the arrival block and its effect exist');
assert(FAILED.length > 0 && SETTLE.length > 0 && LIST.length > 0 && ROW.length > 0 && MARK.length > 0
  && FOUND.length > 0,
  'P-0b the failure and settle handlers, the Mutual FlatList, its row, ARRIVAL_MARK and the found path exist');

// P-1 — reads match_id and ts (ts arrives as a string via the v2 path route),
// through typed params.
assert(/const arrivalMatchId = route\.params\?\.match_id != null \? String\(route\.params\.match_id\) : null;/.test(BLOCK),
  'P-1a reads route.params?.match_id (String-coerced)');
assert(/const arrivalTs = route\.params\?\.ts != null \? String\(route\.params\.ts\) : null;/.test(BLOCK),
  'P-1b reads route.params?.ts (String-coerced: the v2 router parses it from the query)');
assert(/const route = useRoute<RouteProp<\{ Matches: MatchesRouteParams \}, 'Matches'>>\(\);/.test(F)
  && !/useRoute<any>/.test(F)
  && /type MatchesRouteParams = \{[^}]*match_id\?: string \| number;[^}]*ts\?: string \| number;[^}]*\} \| undefined;/.test(F),
  'P-1c the route params are typed (match_id and ts as string | number), not useRoute<any>');

// P-2 — one arrival per ts.
assert(EFFECT.includes('if (arrivalDoneTsRef.current === arrivalTs) return;'),
  'P-2a dedupe: an already-finished ts returns before anything else');
assert(/const finishArrival = useCallback\(\(\) => \{ const a = arrivalRef\.current; if \(a\) arrivalDoneTsRef\.current = a\.ts; arrivalRef\.current = null; \}, \[\]\);/.test(BLOCK),
  'P-2b finishArrival() records the ts (re-focus / re-render / tab press never replay)');
{
  const deps = (EFFECT.match(/\}, \[([^\]]*)\]\);\s*$/) || [])[1] || '';
  assert(/\barrivalTs\b/.test(deps) && /\barrivalMatchId\b/.test(deps) && /\bisFocused\b/.test(deps),
    'P-2c the effect re-runs on a new ts / match_id and on focus', `deps: [${deps}]`);
  assert(/matchesQuery\.isFetching/.test(deps) && /matchesQuery\.isPaused/.test(deps)
    && /matchesQuery\.isError/.test(deps) && /hiddenAwareMatches/.test(deps)
    && /visibleMatches/.test(deps) && /\bsegment\b/.test(deps),
  'P-2d deps cover the wait, the refetch outcome, the lists and the segment', `deps: [${deps}]`);
}

// P-3 — §7 step 1: land on Mutual at once, before the wait; and an
// unfinished arrival never stays armed.
{
  const land = EFFECT.indexOf("setSegment('mutual');");
  const wait = EFFECT.indexOf('if (matchesQuery.isFetching) return;');
  assert(land > -1 && wait > -1 && land < wait,
    'P-3a a new arrival sets the segment to Mutual at once, before waiting for the list');
}
assert(/if \(!isFocused\) \{ if \(pending\?\.mutualShown\) finishArrival\(\); if \(markRef\.current\) endMark\(\); return; \}/.test(EFFECT),
  'P-3b leaving the tab after Mutual rendered cancels the arrival and clears the mark');
assert(/\} else if \(a\.mutualShown && segment !== 'mutual'\) \{ finishArrival\(\); endMark\(\); return; \} if \(segment === 'mutual'\) a\.mutualShown = true;/.test(EFFECT),
  'P-3c picking Awaiting/Standing after Mutual rendered cancels it (no later scroll, mark or re-chip)');
assert(/mutualShown: false, \};/.test(EFFECT), 'P-3d a new arrival starts with mutualShown false');

// P-4 — wait for the list before any lookup.
{
  const wait = EFFECT.indexOf('if (matchesQuery.isFetching) return;');
  const look = EFFECT.indexOf('indexForMatch(');
  assert(wait > -1 && look > wait, 'P-4 waits while the list loads or a refetch runs, before any lookup');
}

// P-5 — find in the whole hidden-aware list; refetch ONCE when missing.
assert(/const loadedIndex = hiddenAwareMatches === null \? -1 : indexForMatch\(hiddenAwareMatches, arrivalMatchId\);/.test(EFFECT),
  'P-5a looks the id up in the whole list (every league, minus pending dismisses)');
assert(/if \(!a\.refetched && !matchesQuery\.isPaused\) \{ a\.refetched = true; a\.trustView = false; void matchesQuery\.refetch\(\); return; \}/.test(EFFECT),
  'P-5b not in the cached list → refetch once (never while paused offline), then look again');
eq('P-5c exactly one refetch call in the arrival block', count(BLOCK, '.refetch('), 1);

// P-6 — not found: no line on failure/offline; otherwise only via the constant.
{
  const nf = slice(EFFECT, 'if (loadedIndex < 0) {', 'const index = indexForMatch(visibleMatches');
  assert(/finishArrival\(\); if \(hiddenAwareMatches === null \|\| matchesQuery\.isError \|\| matchesQuery\.isPaused\) return; endMark\(\); if \(!a\.dragged\) matchesListRef\.current\?\.scrollToOffset\(\{ offset: 0, animated: true \}\); const line = notFoundToast\(MATCH_NOT_FOUND_LINE\); if \(line\) setToast\(line\); return;/.test(nf),
    'P-6a fetch failed / offline → the arrival ends with NO line and no scroll; else nothing marked, the list at its top (never under a finger), and the line only via notFoundToast(MATCH_NOT_FOUND_LINE)');
  assert(nf.length > 0 && !/scrollToIndex|setMark|setFilterLeagueId|showMark|track\(/.test(nf)
    && count(nf, 'scrollTo') === 1,
    'P-6b the not-found branch never scrolls to a row, marks, re-chips or tracks');
  eq('P-6c setToast appears once in the arrival block (the not-found line)', count(BLOCK, 'setToast('), 1);
}

// P-7 — §7 step 3: All only when the chip hides the row.
assert(/const index = indexForMatch\(visibleMatches, arrivalMatchId\); if \(index < 0\) \{ a\.trustView = false; setFilterLeagueId\('all'\); return; \}/.test(EFFECT),
  'P-7a the chip goes to All only when the visible list hides a row the whole list has');
eq("P-7b setFilterLeagueId('all') appears once in the arrival block", count(BLOCK, 'setFilterLeagueId('), 1);
assert(EFFECT.indexOf("if (segment !== 'mutual') return;") > EFFECT.indexOf('const index = indexForMatch(visibleMatches'),
  'P-7c no scroll until the Mutual list has rendered');

// P-8 — §7 step 4: scrollToIndex on matchesListRef, the row 8pt+ below the
// list's top so the outline's −6pt top stroke isn't clipped (QA P2-1).
assert(/matchesListRef\.current\?\.scrollToIndex\(\{ index, animated: true, viewPosition: 0, viewOffset: ARRIVAL_VIEW_OFFSET, \}\);/.test(EFFECT),
  'P-8a scrollToIndex on matchesListRef with viewPosition 0 and viewOffset ARRIVAL_VIEW_OFFSET');
{
  const vo = (F.match(/const ARRIVAL_VIEW_OFFSET = space\.(\w+);/) || [])[1];
  const sp = flatten(read('src/theme/chalkline.ts')).match(/export const space = \{([^}]*)\}/);
  const val = vo && sp ? Number((sp[1].match(new RegExp(`\\b${vo}: (\\d+)`)) || [])[1]) : NaN;
  assert(val >= 8, 'P-8b ARRIVAL_VIEW_OFFSET is a space token ≥ 8pt (clears the outline\'s 6pt outset)',
    `space.${vo} = ${val}`);
}
assert(/if \(dragged \|\| \(trustView && fullyVisibleRef\.current\.has\(arrivalMatchId\)\)\) \{ showMark\(arrivalTs\); return; \}/.test(EFFECT)
  && EFFECT.indexOf('if (dragged ||') < EFFECT.indexOf('scrollToIndex('),
  'P-8c a drag first, or a row already fully in view, skips the scroll and marks straight away');
assert(/viewabilityConfig = useRef\(\{ itemVisiblePercentThreshold: 100 \}\)\.current/.test(BLOCK)
  && LIST.includes('viewabilityConfig={viewabilityConfig}')
  && LIST.includes('onViewableItemsChanged={onViewableItemsChanged}'),
  'P-8d "fully in view" comes from a stable 100% viewability config on the Mutual list');

// P-9 — onScrollToIndexFailed: jump, then retry after layout, BOUNDED.
assert(LIST.includes('onScrollToIndexFailed={onArrivalScrollFailed}'),
  'P-9a onScrollToIndexFailed is wired on the Mutual FlatList (the one holding matchesListRef)');
assert(/const jump = scrollFailureJump\(info, ARRIVAL_VIEW_OFFSET, maxOffset\);/.test(FAILED)
  && /if \(jump && 'offset' in jump\) \{ list\.scrollToOffset\(\{ offset: jump\.offset, animated: false \}\); \} else if \(jump\) \{ list\.scrollToIndex\(\{ index: jump\.index, animated: false, viewPosition: 0, viewOffset: ARRIVAL_VIEW_OFFSET, \}\); \}/.test(FAILED),
  'P-9b it jumps to the clamped estimate, or (average 0) steps to the furthest measured row');
assert(/const maxOffset = contentH > 0 && viewportH > 0 \? contentH - viewportH : null;/.test(FAILED)
  && /onContentSizeChange=\{\(_w, h\) => \{ listContentHRef\.current = h; \}\}/.test(LIST)
  && /onLayout=\{\(e\) => \{ listViewportHRef\.current = e\.nativeEvent\.layout\.height; \}\}/.test(LIST),
  'P-9c the estimate is clamped to the Mutual list\'s tracked content end');
assert(/scrollTriesRef\.current \+= 1; const willRetry = scrollTriesRef\.current <= ARRIVAL_MAX_TRIES;/.test(FAILED)
  && /if \(!willRetry\) return;/.test(FAILED)
  && FAILED.indexOf('if (!willRetry) return;') < FAILED.indexOf('retryTimerRef.current = setTimeout(')
  && /const ARRIVAL_MAX_TRIES = 4;/.test(F),
  'P-9d retries are bounded (ARRIVAL_MAX_TRIES = 4); past it the last jump stands');
assert(/retryTimerRef\.current = setTimeout\(\(\) => \{[\s\S]*try \{ matchesListRef\.current\?\.scrollToIndex\(\{ index: info\.index, animated: true, viewPosition: 0, viewOffset: ARRIVAL_VIEW_OFFSET, \}\); \} catch[\s\S]*\}, ARRIVAL_RETRY_MS\);/.test(FAILED),
  'P-9e the retry is scrollToIndex after layout, with the same viewOffset, guarded (a list change never throws)');
assert(/scrollTriesRef\.current = 0;/.test(FOUND), 'P-9f each arrival gets its own retry budget');

// P-10 — the list never moves under a finger.
assert(LIST.includes('onScrollBeginDrag={onArrivalDrag}')
  && /const onArrivalDrag = useCallback\(\(\) => \{ if \(arrivalRef\.current\) arrivalRef\.current\.dragged = true; clearTimeout\(retryTimerRef\.current\);/.test(BLOCK),
  'P-10 a drag marks the arrival dragged and cancels a pending retry');

// P-11 — the mark appears once the scroll settles (or a fallback); a tail
// target that ran past the end is pulled back first (no blank band).
assert(LIST.includes('onMomentumScrollEnd={onArrivalSettle}')
  && /if \(!m \|\| m\.shown \|\| ignoreSettleRef\.current\) return;/.test(SETTLE)
  && /showMark\(m\.ts\);/.test(SETTLE),
  'P-11a onMomentumScrollEnd shows a pending mark (not a stepping jump\'s own event)');
assert(/const armSettleFallback = useCallback\(\(ts: string\) => \{ clearTimeout\(settleTimerRef\.current\); settleTimerRef\.current = setTimeout\(\(\) => showMark\(ts\), ARRIVAL_SETTLE_FALLBACK_MS\); \}, \[showMark\]\);/.test(BLOCK)
  && /armSettleFallback\(arrivalTs\);/.test(FOUND),
  'P-11b a fallback shows it when a scroll that moves nothing emits no momentum end');
assert(/const end = endClamp\(contentOffset\.y, contentSize\.height, layoutMeasurement\.height\); if \(end != null && !endClampedRef\.current\) \{ endClampedRef\.current = true; armSettleFallback\(m\.ts\); matchesListRef\.current\?\.scrollToOffset\(\{ offset: end, animated: true \}\); return; \}/.test(SETTLE)
  && SETTLE.indexOf('endClamp(') < SETTLE.indexOf('showMark(m.ts)')
  && /endClampedRef\.current = false;/.test(FOUND),
  'P-11c a settle past the content end pulls back to the end (once per arrival) before marking');

// P-12 — design-lead's overlay: absolute, inert, the whole row, last child.
assert(/\{mark\?\.shown && mark\.matchId === item\.match_id \? \( <Animated\.View key=\{mark\.ts\} pointerEvents="none" accessible=\{false\} importantForAccessibility="no-hide-descendants" style=\{\[ARRIVAL_MARK\.style, \{ opacity: markOpacity \}\]\} \/> \) : null\} <\/View> \)\}\s*$/.test(ROW),
  'P-12a the overlay is the row wrapper\'s LAST child, keyed on ts, pointerEvents none, hidden from a11y');
assert(LIST.includes('extraData={mark}'), 'P-12b extraData={mark}: rows re-render when the mark changes');
assert(/ref=\{mark\?\.matchId === item\.match_id \? markHeaderRef : undefined\}/.test(ROW),
  'P-12c the marked row\'s header carries the focus ref');

// P-13 — ARRIVAL_MARK values (one constant, so a revision is one change).
assert(/style: \{ position: 'absolute', top: -6, left: -6, right: -6, bottom: -6, borderWidth: 2, borderColor: flare\.base, borderRadius: radii\.md, \}/.test(MARK),
  'P-13a outline: absolute -6 insets, 2pt flare.base border, radii.md');
assert(!/backgroundColor|shadow|elevation|opacity/.test(MARK),
  'P-13b no fill, tint, shadow or glow');
assert(/holdMs: 2000, fadeMs: duration\.fast,/.test(MARK), 'P-13c holds 2000 ms; fades over duration.fast');
assert(/export const duration = \{ fast: 120,/.test(flatten(read('src/theme/chalkline.ts'))),
  'P-13d duration.fast is 120 ms (--t-fast)');

// P-14 — timing: full opacity at once, 2000 ms, then 120 ms ease-out native.
assert(/markOpacity\.setValue\(1\);/.test(BLOCK), 'P-14a it appears at full opacity (no fade-in)');
assert(/markTimerRef\.current = setTimeout\(\(\) => \{[\s\S]*\}, ARRIVAL_MARK\.holdMs\);/.test(BLOCK)
  && /Animated\.timing\(markOpacity, \{ toValue: 0, duration: ARRIVAL_MARK\.fadeMs, easing: Easing\.out\(Easing\.quad\), useNativeDriver: true, \}\)/.test(BLOCK),
  'P-14b hold ARRIVAL_MARK.holdMs, then Animated.timing 1 → 0 over fadeMs, ease-out, native driver');

// P-15 — Reduce Motion: same hold, then gone with no fade.
assert(/AccessibilityInfo\.isReduceMotionEnabled\(\) \.catch\(\(\) => false\) \.then\(\(reduceMotion\) => \{ if \(markRef\.current\?\.ts !== ts\) return; if \(reduceMotion\) \{ endMark\(\); return; \} Animated\.timing/.test(BLOCK),
  'P-15 Reduce Motion removes it instantly after the hold, before any Animated.timing');

// P-16 — once per arrival, keyed on ts.
assert(/if \(!m \|\| m\.ts !== ts \|\| m\.shown\) return;/.test(BLOCK)
  && /markRef\.current = \{ ts: arrivalTs, shown: false \};/.test(FOUND),
  'P-16 the mark is keyed on the arrival ts and shows at most once per ts');

// P-17 — timers cleared on unmount and when the row goes.
assert(/const clearMarkTimers = useCallback\(\(\) => \{ clearTimeout\(markTimerRef\.current\); clearTimeout\(settleTimerRef\.current\); clearTimeout\(retryTimerRef\.current\); markOpacity\.stopAnimation\(\); \}/.test(BLOCK),
  'P-17a clearMarkTimers clears every timer and stops the fade');
assert(/useEffect\(\(\) => \(\) => \{ clearMarkTimers\(\); markRef\.current = null; \}, \[clearMarkTimers\]\);/.test(BLOCK),
  'P-17b unmount clears the timers (no setState after unmount)');
assert(/if \(mark && \(segment !== 'mutual' \|\| indexForMatch\(visibleMatches, mark\.matchId\) < 0\)\) \{ endMark\(\); \}/.test(BLOCK),
  'P-17c the row going (Dismiss, chip, segment) ends the mark and its timer');
assert(/const endMark = useCallback\(\(\) => \{ clearMarkTimers\(\); markRef\.current = null; setMark\(null\); \}, \[clearMarkTimers\]\);/.test(BLOCK),
  'P-17d endMark clears the timers, then drops the mark');

// P-18 — §7 step 6: VoiceOver focus to the header; the mark isn't announced.
assert(/useEffect\(\(\) => \{ if \(!mark\?\.shown\) return; const node = markHeaderRef\.current \? findNodeHandle\(markHeaderRef\.current\) : null; if \(node != null\) AccessibilityInfo\.setAccessibilityFocus\(node\); \}, \[mark\?\.shown, mark\?\.ts\]\);/.test(BLOCK),
  'P-18a focus moves to the marked row\'s header once it shows (deps: mark.shown, mark.ts)');
assert(!/announceForAccessibility/.test(BLOCK), 'P-18b no extra announcement');

// P-19 — no analytics event, no new API surface.
assert(!/\btrack\(/.test(BLOCK), 'P-19a the arrival block emits no analytics event');
assert(!/\bapi\.|\bfetch\(|from '\.\.\/api/.test(BLOCK), 'P-19b no new API call (only the existing query\'s refetch)');

// P-20 — the found path's order, and the knobs.
{
  const fin = FOUND.indexOf('finishArrival();');
  const show = FOUND.indexOf('showMark(arrivalTs)');
  const scroll = FOUND.indexOf('scrollToIndex(');
  assert(fin > -1 && show > fin && scroll > fin
    && fin < FOUND.indexOf('markRef.current = { ts: arrivalTs'),
    'P-20a found path: finishArrival() runs before the mark is armed, shown or scrolled to');
  eq('P-20b showMark( is called from exactly three places (fallback, skip, settle)', count(BLOCK, 'showMark('), 3);
  assert(/const ARRIVAL_SETTLE_FALLBACK_MS = 600;/.test(F) && /const ARRIVAL_RETRY_MS = 250;/.test(F),
    'P-20c the settle fallback is 600 ms and the retry delay 250 ms');
  assert(/trustView: segment === 'mutual',/.test(EFFECT) && count(EFFECT, 'a.trustView = false;') === 2,
    'P-20d the in-view skip trusts viewability only if Mutual was already up, and never after a refetch or a re-chip');
}

// ── Segment finding + producer contract ────────────────────────────────────
// Every match_id lives in Mutual: the Mutual list renders visibleMatches,
// derived from ['matches','all'] (GET /api/trades/matches/all, every status);
// Awaiting is keyed league:trade_id and carries no match_id.
assert(/queryKey: \['matches', 'all'\], queryFn: getAllMatches,/.test(F)
  && /data=\{visibleMatches\} keyExtractor=\{\(m\) => m\.match_id\}/.test(LIST),
  'S-1 the Mutual FlatList renders visibleMatches from [\'matches\',\'all\'], keyed by match_id');
assert(/keyExtractor=\{\(a\) => `\$\{a\.league_id\}:\$\{a\.trade_id\}`\}/.test(F),
  'S-2 Awaiting rows are keyed league:trade_id (no match_id), so an arrival never targets it');
{
  const DL = flatten(read('src/utils/deepLinks.ts'));
  assert(/const V2_MATCH_KINDS = new Set\(\[[^\]]*'match_accepted'/.test(DL),
    "S-3 a match_accepted push resolves to Matches with its match_id");
  assert(/Matches: 'matches\/:match_id\?'/.test(DL)
    && /`app\/matches\/\$\{encodeURIComponent\(String\(matchId\)\)\}\?src=push&ts=\$\{Date\.now\(\)\}`/.test(DL)
    && /params: \{ match_id: String\(matchId\), src: 'push', ts: Date\.now\(\) \}/.test(DL),
    'S-4 routeNotificationTap passes { match_id, src: push, ts } on both routing paths');
  assert(/routeNotificationTap\(tab, matchId\);/.test(flatten(read('src/navigation/RootNav.tsx'))),
    'S-5 RootNav routes match push taps through routeNotificationTap');
}

console.log(failures ? `\n${failures} FAILURE(S), ${passes} passed` : `\nALL CHECKS PASSED (${passes})`);
process.exit(failures ? 1 : 0);
