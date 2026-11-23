#!/usr/bin/env node
// Matches › Dismiss › Undo: the Undo toast lives exactly as long as the undo
// window, and an Undo offered on screen always works.
//
// WHY THIS EXISTS. A Release simulator pass (2026-11-22): Dismiss on a mutual
// match, tap Undo on the "Dismissed" toast — the match stayed gone and the
// server had it dismissed. The undo path itself was wired (undoDismiss
// restores the cache and drops the held POST). The defect was the toast's
// clock: Toast's hold effect listed `onDismiss` in its deps, and every host
// passes an inline `() => setToast(null)`, so EVERY re-render of the host
// restarted the 5 s hold. MatchesScreen re-renders constantly around a
// dismiss (the held POST firing at 5 s, the mutation's state, the reconcile
// refetch), so the toast stayed up seconds after the hold had committed the
// dismiss; an Undo tapped then found no pending dismiss and did nothing.
//
// Pinned:
//   (t1-t4, EXECUTED) Toast.tsx is transpiled and rendered twice under a
//        stub React with a NEW inline onDismiss each time, as every host
//        does. The hold effect's deps are identical across the two renders
//        (React would not restart it); a new message does restart it; when
//        the hold fires, the LATEST onDismiss is called; a hidden (fading)
//        toast takes no touches.
//   (m1-m2, structural, G-035) MatchesScreen's flushPendingDismiss — the
//        one place the held dismiss is sent — clears an "Undo" toast before
//        it mutates, and both dismiss paths (mutual + awaiting) still hand
//        the toast `undoDismiss`.
//
// Run: node tests/check-toast-undo-window.js   (or: npm run test:toast-undo-window)

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
let failures = 0;
const assert = (cond, name, detail) => {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
};

// ── Stub React: hooks keyed by call order, effects recorded per render ────
let hookIdx = 0;
const hookState = [];
let effects = [];
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }),
  Fragment: 'Fragment',
};
const useRef = (init) => {
  const i = hookIdx++;
  if (!hookState[i]) hookState[i] = { current: init };
  return hookState[i];
};
const useEffect = (fn, deps) => {
  hookIdx++;
  effects.push({ fn, deps, src: fn.toString() });
};
const timers = [];
const stubs = {
  react: { __esModule: true, default: React, useEffect, useRef },
  'react-native': {
    AccessibilityInfo: { announceForAccessibility: () => {} },
    StyleSheet: { create: (s) => s },
    Text: 'Text', Pressable: 'Pressable', View: 'View',
  },
  'react-native-reanimated': {
    __esModule: true,
    default: { View: 'Animated.View' },
    useSharedValue: (v) => { const r = useRef({ value: v }); return r.current; },
    useAnimatedStyle: (f) => f(),
    withTiming: (to, _cfg, cb) => { if (cb) cb(true); return to; },
    runOnJS: (fn) => fn,
  },
  '../theme/chalkline': new Proxy({}, { get: () => new Proxy({}, { get: () => 0 }) }),
  '../state/useFeatureFlags': { useFlag: () => true },
  '../hooks/useReducedMotionSafe': { useReducedMotionSafe: () => false },
};

const toastSrc = fs.readFileSync(path.join(MOBILE, 'src/components/Toast.tsx'), 'utf8');
const js = ts.transpileModule(toastSrc, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019, jsx: ts.JsxEmit.React,
    esModuleInterop: true,
  },
}).outputText;
const mod = { exports: {} };
// eslint-disable-next-line no-new-func
new Function('module', 'exports', 'require', 'setTimeout', 'clearTimeout', js)(
  mod, mod.exports,
  (id) => { if (!(id in stubs)) throw new Error(`unstubbed import ${id}`); return stubs[id]; },
  (fn, ms) => { timers.push({ fn, ms, live: true }); return timers.length - 1; },
  (t) => { if (timers[t]) timers[t].live = false; },
);
const Toast = mod.exports.default;

function render(props) {
  hookIdx = 0;
  effects = [];
  const tree = Toast(props);
  const hold = effects.filter((e) => /setTimeout/.test(e.src));
  return { tree, hold: hold.length === 1 ? hold[0] : null };
}
const sameDeps = (a, b) => !!a && !!b && a.length === b.length && a.every((x, i) => Object.is(x, b[i]));

const action = { label: 'Undo', onPress: () => {} };
const calls = [];
const r1 = render({ visible: true, message: 'Dismissed', tone: 'success', holdMs: 5000, action,
  onDismiss: () => calls.push('first') });
const r2 = render({ visible: true, message: 'Dismissed', tone: 'success', holdMs: 5000, action,
  onDismiss: () => calls.push('second') });
assert(!!r1.hold && !!r2.hold, 't0. Toast has exactly one hold effect (the one with setTimeout)');
assert(
  r1.hold && r2.hold && sameDeps(r1.hold.deps, r2.hold.deps),
  't1. a host re-render with a new inline onDismiss does NOT restart the hold (deps unchanged)',
  r1.hold && r2.hold ? `deps differ at ${r1.hold.deps.findIndex((x, i) => !Object.is(x, r2.hold.deps[i]))}` : '',
);
const r3 = render({ visible: true, message: 'Standing offer revoked', tone: 'success', holdMs: 5000,
  onDismiss: () => calls.push('third') });
assert(r2.hold && r3.hold && !sameDeps(r2.hold.deps, r3.hold.deps),
  't2. a new message (a new toast) does restart the hold');

// Fire the hold as React would have armed it on the first show, after the
// host re-rendered with a different inline callback.
calls.length = 0;
render({ visible: true, message: 'Dismissed', tone: 'success', holdMs: 5000, action,
  onDismiss: () => calls.push('first') });
const armed = render({ visible: true, message: 'Dismissed', tone: 'success', holdMs: 5000, action,
  onDismiss: () => calls.push('latest') });
const firstEffect = r1.hold.fn; // armed on show, never re-run since deps are equal
timers.length = 0;
firstEffect();
const t = timers[0];
assert(!!t && t.ms === 5000, 't3a. the hold is armed for holdMs (5000)', JSON.stringify(timers.map((x) => x.ms)));
if (t) t.fn();
assert(calls.length === 1 && calls[0] === 'latest',
  't3b. when the hold fires it calls the LATEST onDismiss', JSON.stringify(calls));
void armed;

{
  // Mid-fade: the host has set visible=false but opacity is not 0 yet, so the
  // element is still rendered. It must ignore touches.
  for (const h of hookState) if (h && h.current && typeof h.current.value === 'number') h.current.value = 0.5;
  const hidden = render({ visible: false, message: 'Dismissed', tone: 'success', holdMs: 5000, action,
    onDismiss: () => {} });
  const pe = hidden.tree && hidden.tree.props ? hidden.tree.props.pointerEvents : undefined;
  assert(!!hidden.tree && pe === 'none', 't4. a fading (hidden) toast still on screen takes no touches',
    `rendered=${!!hidden.tree} pointerEvents=${pe}`);
}

// ── MatchesScreen wiring ──────────────────────────────────────────────────
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');
const SCREEN = strip(fs.readFileSync(path.join(MOBILE, 'src/screens/MatchesScreen.tsx'), 'utf8'));
{
  const i = SCREEN.indexOf('function flushPendingDismiss()');
  const body = i === -1 ? '' : SCREEN.slice(i, SCREEN.indexOf('\n  }\n', i));
  const clear = body.search(/setToast\(\(t\) => \(t\?\.action\?\.label === 'Undo' \? null : t\)\)/);
  const mutate = body.search(/dismissMutation\.mutate\(p\.id\)/);
  assert(clear !== -1 && mutate !== -1 && clear < mutate,
    'm1. flushPendingDismiss clears the Undo toast before it sends the held dismiss');
}
assert((SCREEN.match(/action: \{ label: 'Undo', onPress: undoDismiss \}/g) || []).length === 2,
  'm2. both dismiss paths (mutual, awaiting) still offer Undo → undoDismiss');

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll toast-undo-window checks passed.');
