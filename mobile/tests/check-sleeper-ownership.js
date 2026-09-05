#!/usr/bin/env node
// Ownership hardening: execute the real capture/form with native boundaries
// stubbed; verify wrong-origin messages, proof retention, merge and cancellation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const source = (p) => fs.readFileSync(path.join(root, p), 'utf8');
function load(file, imports) {
  const exports = {};
  const code = ts.transpileModule(source(file), { compilerOptions: {
    jsx: ts.JsxEmit.React, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
    esModuleInterop: true,
  }}).outputText;
  vm.runInNewContext(code, { exports, require: (name) => {
    assert(name in imports, `Unexpected import ${name}`); return imports[name];
  }, setTimeout, clearTimeout, console });
  return exports;
}
function harness() {
  let cursor = 0; const slots = []; const cleanups = [];
  const react = {
    useEffect: (effect) => { const i = cursor++; if (!(i in slots)) {
      slots[i] = true; const cleanup = effect(); if (cleanup) cleanups.push(cleanup);
    } },
    useCallback: (callback) => callback,
    createElement: (type, props, ...children) => ({type, props: props || {}, children}),
    useRef: (initial) => { const i = cursor++; return slots[i] ??= {current: initial}; },
    useState: (initial) => { const i = cursor++; if (!(i in slots)) slots[i] = initial;
      return [slots[i], (next) => { slots[i] = typeof next === 'function' ? next(slots[i]) : next; }]; },
  };
  return {react, unmount: () => cleanups.forEach(cleanup => cleanup()),
    render: (Component, props = {}) => { cursor = 0; return Component(props); }};
}
function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return null;
  if (predicate(tree)) return tree;
  for (const child of tree.children || []) {
    const hit = Array.isArray(child) ? child.map(c => find(c, predicate)).find(Boolean) : find(child, predicate);
    if (hit) return hit;
  }
  return null;
}
function captureTest() {
  const h = harness(); const seen = [];
  const Capture = load('src/components/SleeperLoginCapture.tsx', {
    react: h.react, 'react-native-webview': {WebView: 'WebView'},
  }).default;
  const tree = h.render(Capture, {onToken: (token) => seen.push(token)});
  assert.equal(tree.props.incognito, true);
  assert.equal(tree.props.sharedCookiesEnabled, undefined);
  const message = (url, token = 'a.b.c') => tree.props.onMessage({nativeEvent: {
    url, data: JSON.stringify({type: 'token', token}),
  }});
  for (const url of ['http://sleeper.com/login', 'https://sleeper.com.evil/login', 'https://evil/login']) message(url);
  message('https://sleeper.com/login', {});
  assert.equal(seen.length, 0);
  message('https://sleeper.com/login'); message('https://sleeper.com/login');
  assert.deepEqual(seen, ['a.b.c']);
}
const flush = () => new Promise(resolve => setImmediate(resolve));
async function staleAuthResponseTest(method) {
  let currentToken = 'original-session'; let resolveResponse;
  const changes=[];
  class ApiError extends Error { constructor(status,body,message) {super(message);this.status=status;this.body=body;} }
  const auth=load('src/api/auth.ts', {
    './client': {ApiError, getSessionToken:async()=>currentToken,
      setSessionToken:async token=>{changes.push(token);currentToken=token;},
      api:{post:()=>new Promise(resolve=>{resolveResponse=resolve;})}},
    './events':{}, './sendInSleeper':{maybeReplaySleeperVerification:async()=> 'none'},
    './sleeper':{}, './espn':{}, './platformLink':{},
  });
  const pending=method==='init' ? auth.sessionInit({user_id:'original'}) :
    auth.linkSleeperUsername('manager',undefined,'proof.jwt.sig');
  await flush();
  currentToken='new-session';
  resolveResponse({token:'original-session',session_token:'linked-original-session'});
  await assert.rejects(pending, /session changed/i);
  assert.deepEqual(changes,[], 'late response must not replace the new session token');
}
async function connectAccountSwitchTest(unmount) {
  const h = harness(); const calls = []; let resolveLink;
  let state = {user: {user_id: 'original'}, verification: {},
    setVerification: () => calls.push('verification')};
  const Connect = load('src/screens/SleeperConnectScreen.tsx', {
    react: h.react,
    'react-native': {View:'View', Text:'Text', ActivityIndicator:'Spinner',
      StyleSheet:{create:x=>x}, Linking:{}},
    '../components/SleeperLoginCapture': {__esModule:true, default:'Capture'},
    '../components/chalkline': {Button:'Button'},
    '@react-navigation/native': {useNavigation: () => ({goBack:()=>calls.push('back')})},
    '../theme/chalkline': {ink:{},chalk:{},ice:{},space:{},type:{}},
    '../state/useSession': {useSession:{getState:()=>state}},
    '../api/sendInSleeper': {
      linkSleeperToken: () => new Promise(resolve=>{resolveLink=resolve;}),
      persistSleeperToken: async uid=>calls.push(['persist',uid]),
    },
  }).default;
  const tree=h.render(Connect);
  const pending=find(tree,n=>n.type==='Capture').props.onToken('proof.jwt.sig');
  if (unmount) h.unmount();
  else state={...state,user:{user_id:'different'}};
  resolveLink({verified:true}); await pending;
  assert.deepEqual(calls,[], 'late proof must not persist or verify a different/closed session');
}
async function formTest(mode) {
  const h = harness(); const calls = []; let alertButtons; let resolveBind;
  let currentUser = 'original';
  class ApiError extends Error { constructor(body) { super(body.error); this.body = body; } }
  const native = {StyleSheet: {create: x => x}, Platform: {OS: 'ios'}, Keyboard: {dismiss() {}},
    useWindowDimensions: () => ({height: 800}), Alert: {alert: (_title, _body, buttons) => {alertButtons = buttons;}},
    ...Object.fromEntries(['View','Text','Pressable','Modal','TextInput','KeyboardAvoidingView'].map(x => [x,x]))};
  const Form = load('src/components/LinkSleeperSheet.tsx', {
    react: h.react, 'react-native': native,
    '../theme/chalkline': {ink:{},chalk:{},semantic:{},space:{},radii:{},type:{},shadowSheet:{},scrim:''},
    './chalkline': {Button:'Button'}, './SleeperLoginCapture': {__esModule:true,default:'Capture'},
    '../api/client': {ApiError},
    '../state/useSession': {useSession:{getState:()=>({user:{user_id:currentUser}})}},
    '../api/auth': {linkSleeperUsername: async (name, strategy, proof) => {
      calls.push(['bind',name,strategy,proof]);
      if (mode === 'closed' || mode === 'switched') return new Promise(resolve=>{resolveBind=resolve;});
      if (!strategy) throw new ApiError({error:'merge_choice_required'});
      return {ok:true,sleeper_user_id:'u'};
    }},
    '../api/sendInSleeper': {linkSleeperToken: async proof => {calls.push(['verify',proof]); return {verified:mode !== 'unverified'};},
      persistSleeperToken: async (uid,proof) => calls.push(['persist',uid,proof])},
  }).LinkSleeperForm;
  const props = {onLinked: () => calls.push(['done'])};
  let tree = h.render(Form, props);
  find(tree, n => n.type === 'TextInput').props.onChangeText('manager');
  tree = h.render(Form, props);
  find(tree, n => n.type === 'Button').props.onPress();
  tree = h.render(Form, props);
  assert.equal(find(tree, n => n.type === 'Modal'), null, 'capture adds no modal');
  find(tree, n => n.type === 'Capture').props.onToken('proof.jwt.sig');
  await flush();
  assert.deepEqual(calls, [['bind','manager',undefined,'proof.jwt.sig']]);
  if (mode === 'closed' || mode === 'switched') {
    if (mode === 'closed') h.unmount(); else currentUser = 'different';
    resolveBind({ok:true,sleeper_user_id:'u'}); await flush();
    assert.equal(calls.length,1,'late source binding must not persist proof or update another/closed screen');
    return;
  }
  assert.equal(alertButtons.length,3);
  if (mode === 'cancel') {
    alertButtons[0].onPress(); alertButtons[1].onPress(); await flush();
    assert.equal(calls.length,1,'cancel discards proof');
    return;
  }
  alertButtons[1].onPress(); await flush();
  assert.deepEqual(calls[1],['bind','manager','keep_account','proof.jwt.sig']);
  assert.deepEqual(calls[2],['verify','proof.jwt.sig']);
  assert.equal(calls.filter(c => c[0] === 'persist').length, mode === 'unverified' ? 0 : 1);
  assert.equal(calls.at(-1)[0], 'done');
}
(async () => {
  captureTest();
  await staleAuthResponseTest('init');
  await staleAuthResponseTest('link');
  await connectAccountSwitchTest(false);
  await connectAccountSwitchTest(true);
  for (const mode of ['verified','unverified','cancel','closed','switched']) await formTest(mode);
  const picker = source('src/screens/LeaguePickerScreen.tsx');
  const pick = picker.slice(picker.indexOf('async function pickLeague'));
  assert(pick.indexOf('await submitSessionInit(body)') < pick.indexOf('await setLeague('));
  assert(picker.includes('leagues.verify-sleeper') && picker.includes("navigation.navigate('SleeperConnect')"));
  const auth = source('src/api/auth.ts').split('export async function sessionInit')[1];
  assert(auth.indexOf('await maybeReplaySleeperVerification') < auth.indexOf('api.post'));
  assert(source('src/navigation/RootNav.tsx').includes('sleeperconnect.close'));
  console.log('PASS Sleeper ownership capture, origin, merge, persistence, cancellation and init ordering');
})().catch(error => { console.error(error); process.exitCode = 1; });
