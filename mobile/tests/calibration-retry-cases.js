// Exercise the actual screen's hooks and Retry buttons without device/network I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const screen = fs.readFileSync(path.join(__dirname, '../src/screens/CalibrationScreen.tsx'), 'utf8');
const js = ts.transpileModule(screen, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const element = (type, props) => ({type, props});
class ApiError extends Error { constructor(status, code) { super(); this.status = status; this.body = {error: code}; } }
function run({active, status = 503, code, stale = false, pending = false, replacement,
              refetchError = false, deferred, building = false, slow = false}) {
  const reads = [], writes = [], stateWrites = [], refs = [], cleanups = [], effects = [];
  let state = 0;
  const stubs = {
    'react/jsx-runtime': {jsx: element, jsxs: element},
    react: {
      useState: value => {
        const index = state++;
        return [index === 0 && active ? 'session-1' : index === 5 && slow ? true : value,
          next => stateWrites.push([index, next])];
      },
      useRef: value => {const ref = {current: value}; refs.push(ref); return ref;},
      useEffect: (fn, deps) => {if (deps.length === 0) {effects.push(fn); cleanups.push(fn());}},
    },
    'react-native': {StyleSheet: {create: x => x}}, 'react-native-safe-area-context': {},
    '@react-navigation/native': {useNavigation: () => ({})},
    '@tanstack/react-query': {
      useQueryClient: () => ({}), useMutation: () => ({mutate: () => writes.push(1)}),
      useQuery: ({queryKey}) => {
        const key = queryKey[1], failed = key === (active ? 'next' : 'current') && !pending && !building;
        return {error: failed ? new ApiError(status, code) : null, isError: failed, isPending: pending,
          data: building && key === 'current' ? {session: {status:'building', session_id:'queued'}}
            : stale && key === 'next' ? {card: {card_id:'previous'}, progress:{total:2}} : undefined,
          refetch: () => {reads.push(key); return deferred || Promise.resolve({
            isError: refetchError, data: {session: replacement}});}};
      },
    },
    '../theme/chalkline': {chalk:{}, ice:{}, ink:{}, radii:{}, space:{}, type:{}},
    '../components/chalkline': {}, '../components/GradingCard': {}, '../components/GradingResults': {},
    '../components/Toast': {}, '../api/client': {ApiError}, '../api/grading': {},
    '../state/useSession': {useSession: fn => fn({user:{user_id:'account-1'}, league: {league_id:'league-1'}})},
  };
  const out = {};
  vm.runInNewContext(js, {exports: out, require: id => {assert.ok(id in stubs, id); return stubs[id];}});
  const byId = {};
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(visit); return; }
    if (node.props.testID) byId[node.props.testID] = node.props;
    visit(node.props.children);
  }
  visit(out.default());
  return {byId, reads, writes, stateWrites, refs, cleanups, effects};
}
for (const args of [{active:false}, {active:true}, {active:true, stale:true}]) {
  const {byId, reads, writes} = run(args);
  assert.ok(byId['calibration.retry'], 'a failed read must offer retry');
  assert.ok(!byId['calibration.card'] && !byId['calibration.loading']);
  byId['calibration.retry'].onPress();
  assert.deepEqual(reads, [args.active ? 'next' : 'current']);
  assert.deepEqual(writes, []);
}
assert.ok(run({active:true,status:404}).byId['calibration.unavailable']);
assert.ok(run({active:true,pending:true}).byId['calibration.loading']);
console.log('PASS  failed current/card reads recover without resubmission; disabled and loading states preserved');

async function recoveryCases() {
  for (const state of ['open', 'building', 'failed', 'completed', null]) {
    const view = run({active:true, status:409, code:'comparison_not_ready',
      replacement: state && {status:state, session_id:'replacement'}});
    await view.byId['calibration.retry'].onPress();
    assert.deepEqual(view.reads, ['current']);
    assert.deepEqual(view.writes, []);
    assert.deepEqual(view.stateWrites.slice(0, 2), [
      [0, state === 'open' ? 'replacement' : null],
      [1, state === 'completed' ? 'replacement' : null],
    ]);
  }
  const failed = run({active:true, status:409, code:'comparison_not_ready', refetchError:true});
  await failed.byId['calibration.retry'].onPress();
  assert.deepEqual(failed.stateWrites, []);
  for (const code of ['round_paused', 'answer_conflict', undefined]) {
    const view=run({active:true, status:409, code});
    await view.byId['calibration.retry'].onPress();
    assert.deepEqual(view.reads, ['next']);
    assert.deepEqual(view.stateWrites, []);
  }
  for (const change of ['account', 'league', 'unmount']) {
    let resolve;
    const deferred=new Promise(r=>{resolve=r;});
    const view=run({active:true,status:409,code:'comparison_not_ready',deferred});
    const action=view.byId['calibration.retry'].onPress();
    if(change==='unmount') view.cleanups[0]();
    else view.refs[0].current={userId:change==='account'?'other':'account-1',leagueId:change==='league'?'other':'league-1'};
    resolve({data:{session:{status:'open',session_id:'replacement'}},isError:false});
    await action;
    assert.deepEqual(view.stateWrites, []);
  }
  const obsolete=run({active:true,status:409,code:'comparison_not_ready'});
  obsolete.refs[0].current={userId:'another-account',leagueId:'league-1'};
  await obsolete.byId['calibration.retry'].onPress();
  assert.deepEqual(obsolete.reads, []);
  assert.deepEqual(obsolete.stateWrites, []);
  const replay=run({active:true,status:409,code:'comparison_not_ready',
    replacement:{status:'open',session_id:'replacement'}});
  replay.cleanups[0]();
  replay.effects[0]();
  await replay.byId['calibration.retry'].onPress();
  assert.deepEqual(replay.reads, ['current']);
  assert.deepEqual(replay.stateWrites[0], [0, 'replacement']);
  const slow=run({building:true,slow:true});
  assert.equal(slow.byId['calibration.retry'].label, 'Check again');
  slow.byId['calibration.retry'].onPress();
  assert.deepEqual(slow.reads, ['current']);
  assert.deepEqual(slow.writes, []);
  console.log('PASS  replacement discovery, typed conflict, failed read, context race and queued-build recovery');
}
recoveryCases().catch(error=>{console.error(error); process.exitCode=1;});

// Retained independent peer boundary controls.

async function independentCases() {
  const retryable=run({active:true,status:503,code:'comparison_not_ready'});
  await retryable.byId['calibration.retry'].onPress();
  assert.deepEqual(retryable.reads,['next']);
  assert.deepEqual(retryable.stateWrites,[]);
  for(const terminal of ['failed','completed']) {
    const view=run({active:true,status:409,code:'comparison_not_ready',replacement:{status:terminal,session_id:'new-id'}});
    await view.byId['calibration.retry'].onPress();
    assert.deepEqual(view.writes,[]);
    assert.deepEqual(view.stateWrites[0],[0,null]);
    assert.deepEqual(view.stateWrites[1],[1,terminal==='completed'?'new-id':null]);
  }
  const unmounted=run({active:true,status:409,code:'comparison_not_ready'});
  unmounted.cleanups[0]();
  await unmounted.byId['calibration.retry'].onPress();
  assert.deepEqual(unmounted.reads,[]);
  let resolve;
  const d=new Promise(r=>{resolve=r;});
  const aba=run({active:true,status:409,code:'comparison_not_ready',deferred:d});
  const action=aba.byId['calibration.retry'].onPress();
  aba.refs[0].current={userId:'other',leagueId:'league-1'};
  aba.refs[0].current={userId:'account-1',leagueId:'league-1'};
  resolve({isError:false,data:{session:{status:'open',session_id:'obsolete'}}});
  await action;
  assert.deepEqual(aba.stateWrites,[]);
  assert.ok(screen.includes("['grading', 'current', leagueId, userId]"));
  console.log('PASS independent 6 boundary controls');
}
independentCases().catch(error=>{console.error(error);process.exitCode=1;});
