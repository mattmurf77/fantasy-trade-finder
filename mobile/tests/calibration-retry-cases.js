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
class ApiError extends Error { constructor(status) { super(); this.status = status; } }
function run({active, status = 503, stale = false, pending = false}) {
  const reads = [], writes = [];
  let state = 0;
  const stubs = {
    'react/jsx-runtime': {jsx: element, jsxs: element},
    react: {useState: value => [state++ === 0 && active ? 'session-1' : value, () => {}], useEffect() {}},
    'react-native': {StyleSheet: {create: x => x}}, 'react-native-safe-area-context': {},
    '@react-navigation/native': {useNavigation: () => ({})},
    '@tanstack/react-query': {
      useQueryClient: () => ({}), useMutation: () => ({mutate: () => writes.push(1)}),
      useQuery: ({queryKey}) => {
        const key = queryKey[1], failed = key === (active ? 'next' : 'current') && !pending;
        return {error: failed ? new ApiError(status) : null, isError: failed, isPending: pending,
          data: stale && key === 'next' ? {card: {card_id:'previous'}, progress:{total:2}} : undefined,
          refetch: () => reads.push(key)};
      },
    },
    '../theme/chalkline': {chalk:{}, ice:{}, ink:{}, radii:{}, space:{}, type:{}},
    '../components/chalkline': {}, '../components/GradingCard': {}, '../components/GradingResults': {},
    '../components/Toast': {}, '../api/client': {ApiError}, '../api/grading': {},
    '../state/useSession': {useSession: fn => fn({league: {league_id:'league-1'}})},
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
  return {byId, reads, writes};
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
