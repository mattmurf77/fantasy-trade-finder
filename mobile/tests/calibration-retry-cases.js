// Run the real screen through status changes and check which requests it sends.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/screens/CalibrationScreen.tsx'),'utf8');
const js = ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
class ApiError extends Error {
  constructor(status, code, detail={}) {
    super(code); this.status=status; this.body={error:code,...detail};
  }
}
const deferred = () => {let resolve, reject; const promise = new Promise((rs,rj)=>{resolve=rs;reject=rj;}); return {promise,resolve,reject};};
const session = (status, id='s', league='l') => ({status,session_id:id,league_id:league,progress:{answered:0,total:3}});
const card = id => ({session_id:id,done:false,card:{card_id:'c-'+id,position:1,trade:{give:[],receive:[]}},progress:{answered:0,total:3}});
const element = (type,props) => ({type,props});
const keyOf = key => JSON.stringify(key);
const same = (a,b) => a && b && a.length===b.length && a.every((value,i)=>Object.is(value,b[i]));

function makeHarness(initial=null) {
  let userId='u', leagueId='l', revision=1, mounted=true, cursor=0, dirty=true, output={}, disclosure, current=initial;
  const hooks=[], pendingEffects=[], scheduledQueries=[], queries=new Map(), calls=[], timers=new Map();
  let timerId=0;
  const responses={current:[],next:[],start:[],answer:[],results:[]}, beforeWire={};
  function hook(init) {const i=cursor++; return hooks[i] || (hooks[i]=init());}
  function invoke(kind,args,fallback) {
    calls.push([kind,...args]);
    const queue=responses[kind];
    if(!queue?.length)return Promise.resolve(fallback());
    const value=queue.shift();
    return value instanceof Error ? Promise.reject(value) : Promise.resolve(value);
  }
  async function wire(kind, id, options, fallback) {
    if (beforeWire[kind]) await beforeWire[kind];
    if (options?.signal?.aborted) throw Object.assign(new Error('Aborted'),{name:'AbortError'});
    options?.beforeDispatch?.();
    return invoke(kind,[id],fallback);
  }
  const useSession = fn => fn(useSession.getState());
  useSession.getState = () => ({user:{user_id:userId},league:{league_id:leagueId},hasToken:true});
  const cache={
    setQueryData(key, value) {
      const entry=entryFor(key);
      entry.data=typeof value==='function'?value(entry.data):value;
      entry.error=null; dirty=true;
    },
    invalidateQueries({queryKey}) {
      const entry=entryFor(queryKey);
      return entry.run ? entry.run() : Promise.resolve();
    },
  };
  function entryFor(key) {
    const serialized=keyOf(key);
    if(!queries.has(serialized))queries.set(serialized,{key,data:undefined,error:null,isFetching:false});
    return queries.get(serialized);
  }
  function useQuery(opts) {
    const slot=hook(()=>({key:null,enabled:false}));
    const key=keyOf(opts.queryKey);
    const entry=entryFor(opts.queryKey);
    const enabled=opts.enabled!==false;
    const activated=enabled&&(!slot.enabled||slot.key!==key);
    slot.key=key; slot.enabled=enabled;
    entry.opts=opts;
    async function run() {
      if(entry.inflight)return entry.inflight;
      entry.isFetching=true; dirty=true;
      const abort=new AbortController();
      const promise=Promise.resolve().then(()=>opts.queryFn({queryKey:opts.queryKey,signal:abort.signal}))
        .then(data=>{entry.data=data;entry.error=null;return {data,isError:false,isSuccess:true};},
          error=>{entry.error=error;return {data:entry.data,error,isError:true,isSuccess:false};})
        .finally(()=>{entry.isFetching=false;entry.inflight=null;dirty=true;});
      entry.inflight=promise;
      return promise;
    }
    entry.run=run;
    if(activated && (entry.data===undefined||opts.refetchOnMount==='always')) scheduledQueries.push(run);
    return {data:entry.data,error:entry.error,isError:!!entry.error,isSuccess:entry.data!==undefined&&!entry.error,
      isPending:entry.data===undefined&&!entry.error,isFetching:entry.isFetching,refetch:run};
  }
  const react={
    useState(value) {
      const slot=hook(()=>({value:typeof value==='function'?value():value}));
      return [slot.value,next=>{const v=typeof next==='function'?next(slot.value):next;if(!Object.is(v,slot.value)){slot.value=v;dirty=true;}}];
    },
    useRef(current) {return hook(()=>({current}));},
    useEffect(fn,deps) {
      const slot=hook(()=>({}));
      if(!same(slot.deps,deps)){slot.deps=deps;slot.fn=fn;pendingEffects.push(()=>{slot.cleanup?.();slot.cleanup=fn();});}
    },
  };
  const stubs={
    'react/jsx-runtime':{jsx:element,jsxs:element},react,
    'react-native':{StyleSheet:{create:x=>x}},'react-native-safe-area-context':{},
    '@react-navigation/native':{useNavigation:()=>({})},
    '@tanstack/react-query':{useQueryClient:()=>cache,useQuery,useMutation(opts){
      const slot=hook(()=>({error:null,isPending:false}));
      slot.reset ||= () => {if(slot.error||slot.isPending){slot.error=null;slot.isPending=false;dirty=true;}};
      slot.opts=opts;
      function mutate(variables) {
        slot.isPending=true;slot.error=null;dirty=true;
        return Promise.resolve().then(()=>opts.mutationFn(variables)).then(data=>{
          slot.isPending=false;dirty=true;slot.opts.onSuccess?.(data,variables);return data;
        },error=>{
          slot.isPending=false;slot.error=error;dirty=true;slot.opts.onError?.(error,variables);
        });
      }
      return {isPending:slot.isPending,error:slot.error,mutate,reset:slot.reset};
    }},
    '../theme/chalkline':{chalk:{},ice:{},ink:{},radii:{},space:{},type:{}},
    '../components/chalkline':{},'../components/GradingCard':{},'../components/GradingResults':{},'../components/Toast':{},
    '../api/client':{ApiError,getSessionRevision:()=>revision,requestAborted:()=>Object.assign(new Error('Aborted'),{name:'AbortError'})},
    '../api/grading':{
      GRADING_TAG_LABELS:{},
      getCurrentGradingSession:(id,options)=>wire('current',id,options,()=>({session:current})),
      startGradingSession:(id,options)=>wire('start',id,options,()=>({session:session('building','started',id)})),
      getNextGradingCard:(id,options)=>wire('next',id,options,()=>card(id)),
      getGradingResults:(id,options)=>wire('results',id,options,()=>({session_id:id})),
      answerGradingCard:async(id,answer,options)=>{
        if(beforeWire.answer)await beforeWire.answer;
        options?.beforeDispatch?.();
        return invoke('answer',[id,JSON.parse(JSON.stringify(answer))],()=>({session_status:'open'}));
      },
    },
    '../state/useSession':{useSession},
    // Founders' review (docs/plans/founder-review/): a non-founder session — the
    // capability probe answers false, so the screen is the grading page only.
    '../api/founder':{getFounderCapability:async()=>false},
    '../components/founder/FounderReview':{},
    // Trade rules' leave guard: no unsaved notes on the grading page.
    '../components/founder/RuleWaterfallReview':{confirmLeaveNotes:(go)=>go()},
  };
  const out={};
  vm.runInNewContext(js,{exports:out,require:id=>{assert.ok(id in stubs,id);return stubs[id];},AbortController,
    setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),console});
  function render(){
    cursor=0;dirty=false;output={};disclosure=undefined;
    function visit(node){if(Array.isArray(node))return node.forEach(visit);if(node&&typeof node==='object'&&node.props){
      if(node.props.testID)output[node.props.testID]=node.props;
      if(typeof node.props['aria-expanded']==='boolean') disclosure=node.props;
      visit(node.props.children);
    }}
    visit(out.default());
    while(pendingEffects.length)pendingEffects.shift()();
    while(scheduledQueries.length)void scheduledQueries.shift()();
  }
  async function flush(){for(let i=0;i<5;i++){
    let renders=0;while(mounted&&dirty){assert.ok(++renders<15,'render loop');render();}
    await new Promise(setImmediate);
  }}
  function select({user=userId,league=leagueId,token=revision,rerender=true}={}){userId=user;leagueId=league;revision=token;if(rerender)dirty=true;}
  const byId=id=>output['calibration.'+id];
  return {calls,responses,beforeWire,flush,select,byId,disclosure:()=>disclosure,
    expireTimers(){for(const [id, fn] of [...timers]){timers.delete(id);fn();}},
    replayMount(){const mountedEffect=hooks.find(slot=>slot.fn && slot.deps.length===0);mountedEffect.cleanup();mountedEffect.cleanup=mountedEffect.fn();},
    unmount(){mounted=false;for(const slot of hooks)slot.cleanup?.();},
    publishCurrent(value){current=value;const scope=[...queries.values()].findLast(entry=>entry.key[1]==='current');assert.ok(scope);cache.setQueryData(scope.key,{session:value});},
    forceCurrent(value){current=value;}, status(){return Object.keys(output);},counts(kind){return calls.filter(call=>call[0]===kind);}};
}

async function main(){
  const failures=[];
  async function check(name, fn) {
    try {await fn(); console.log('PASS',name);}
    catch(e){failures.push(name);console.error('FAIL',name,e.message);}
  }
  await check('ready deck does no exposure until Resume and one next after it',async()=>{
    const h=makeHarness(session('open'));await h.flush();
    assert.ok(h.byId('resume'));assert.deepEqual(h.calls,[['current','l']]);
    await h.byId('resume').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['next','s']]);assert.ok(h.byId('card'));
  });
  await check('passive building deck becomes Resume without exposure',async()=>{
    const h=makeHarness(session('building'));await h.flush();
    assert.deepEqual(h.calls,[['current','l']]);
    h.publishCurrent(session('open'));await h.flush();
    assert.deepEqual(h.calls,[['current','l']]);assert.ok(h.byId('resume'),h.status().join(','));
  });
  await check('a passive build timeout checks status again without exposing or starting',async()=>{
    const h=makeHarness(session('building'));await h.flush();h.expireTimers();await h.flush();
    assert.equal(h.byId('retry').label,'Check again');h.byId('retry').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['current','l']]);
    h.publishCurrent(session('open'));await h.flush();assert.ok(h.byId('resume'));
  });
  await check('mount effect replay preserves a valid Resume action',async()=>{
    const h=makeHarness(session('open'));await h.flush();h.replayMount();
    h.byId('resume').onPress();await h.flush();assert.deepEqual(h.counts('next'),[['next','s']]);
  });
  await check('explicit Start building deck transitions directly to one first card',async()=>{
    const h=makeHarness();await h.flush();assert.ok(h.byId('start'));
    await h.byId('start').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['start','l']]);assert.ok(h.byId('loading'));
    h.publishCurrent(session('open','started'));await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['start','l'],['next','started']]);assert.ok(h.byId('card'));
  });
  for(const change of ['account','league','token','unmount']){
    await check('stale Resume handler after '+change+' does not request next',async()=>{
      const h=makeHarness(session('open'));await h.flush();const click=h.byId('resume').onPress;
      if(change==='unmount')h.unmount();else h.select(change==='account'?{user:'u2'}:change==='league'?{league:'l2'}:{token:2,rerender:false});
      await h.flush();await click();await h.flush();
      assert.deepEqual(h.counts('next'),[]);
    });
    await check('obsolete Start response after '+change+' does not request next',async()=>{
      const h=makeHarness();const d=deferred();h.responses.start.push(d.promise);await h.flush();
      void h.byId('start').onPress();await h.flush();
      if(change==='unmount')h.unmount();else h.select(change==='account'?{user:'u2'}:change==='league'?{league:'l2'}:{token:2,rerender:false});
      await h.flush();d.resolve({session:session('open','obsolete')});await h.flush();
      assert.deepEqual(h.counts('next'),[]);
      if(change!=='unmount')assert.equal(h.byId('card'),undefined);
    });
  }
  for (const error of [new ApiError(503, 'transient'), new ApiError(503, 'comparison_not_ready'),
      new ApiError(409, 'round_paused'), new ApiError(409, 'answer_conflict')]) {
    await check('next error retries the same request: '+error.status+' '+error.message,async()=>{
      const h=makeHarness(session('open'));h.responses.next.push(error);
      await h.flush();h.byId('resume').onPress();await h.flush();
      assert.ok(h.byId('retry'));assert.ok(!h.byId('card') && !h.byId('loading'));
      await h.byId('retry').onPress();await h.flush();
      assert.deepEqual(h.calls,[['current','l'],['next','s'],['next','s']]);assert.ok(h.byId('card'));
    });
  }
  await check('status read failure retries status, while disabled Calibration stays unavailable',async()=>{
    const h=makeHarness(session('open'));h.responses.current.push(new ApiError(503, 'transient'));
    await h.flush();assert.ok(h.byId('retry'));assert.ok(!h.byId('card') && !h.byId('loading'));
    h.byId('retry').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['current','l']]);assert.ok(h.byId('resume'));
    const disabled=makeHarness();disabled.responses.current.push(new ApiError(404, 'not_found'));
    await disabled.flush();assert.ok(disabled.byId('unavailable'));assert.ok(!disabled.byId('retry'));
  });
  await check('stale successor recovers to ready card without another Start',async()=>{
    const h=makeHarness(session('open'));h.responses.next.push(new ApiError(409,'comparison_not_ready'));
    await h.flush();h.forceCurrent(session('open','replacement'));void h.byId('resume').onPress();await h.flush();
    if(h.byId('retry'))await h.byId('retry').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['next','s'],['current','l'],['next','replacement']]);assert.ok(h.byId('card'));
  });
  for(const change of ['account','league','token','unmount','account round trip']){
    await check('stale successor is not adopted after '+change,async()=>{
      const h=makeHarness(session('open'));const d=deferred();h.responses.next.push(new ApiError(409,'comparison_not_ready'));
      await h.flush();h.responses.current.push(d.promise);void h.byId('resume').onPress();await h.flush();
      if(h.byId('retry'))void h.byId('retry').onPress();await h.flush();
      assert.equal(h.counts('current').length,2);
      if(change==='unmount')h.unmount();
      else if(change==='account round trip'){h.select({user:'u2'});await h.flush();h.select({user:'u'});}
      else h.select(change==='account'?{user:'u2'}:change==='league'?{league:'l2'}:{token:2,rerender:false});
      await h.flush();d.resolve({session:session('open','obsolete')});await h.flush();
      assert.deepEqual(h.counts('next'),[['next','s']]);
    });
  }
  await check('stale successor building preserves explicit consent to eventual replacement',async()=>{
    const h=makeHarness(session('open'));h.responses.next.push(new ApiError(409,'comparison_not_ready'));
    await h.flush();h.forceCurrent(session('building','replacement'));void h.byId('resume').onPress();await h.flush();
    if(h.byId('retry'))await h.byId('retry').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['next','s'],['current','l']]);assert.ok(h.byId('loading'));
    h.publishCurrent(session('open','replacement'));await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['next','s'],['current','l'],['next','replacement']]);assert.ok(h.byId('card'));
  });
  await check('a failed successor lookup stays on read retry and does not Start',async()=>{
    const h=makeHarness(session('open'));h.responses.next.push(new ApiError(409,'comparison_not_ready'));
    await h.flush();h.byId('resume').onPress();await h.flush();
    h.responses.current.push(new ApiError(503,'transient'));
    await h.byId('retry').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['next','s'],['current','l']]);assert.ok(h.byId('retry'));
    h.forceCurrent(session('open','replacement'));
    await h.byId('retry').onPress();await h.flush();
    assert.deepEqual(h.calls.slice(-2),[['current','l'],['next','replacement']]);assert.ok(h.byId('card'));
  });
  for(const route of ['start','next'])await check(route+' awaiting async header/token lookup cannot dispatch after same-scope revision change',async()=>{
    const h=makeHarness(route==='next'?session('open'):null);const d=deferred();h.beforeWire[route]=d.promise;
    await h.flush();void h.byId(route==='next'?'resume':'start').onPress();await h.flush();
    h.select({token:2,rerender:false});d.resolve();await h.flush();
    assert.deepEqual(h.counts(route),[]);
  });
  await check('Start response for completed round fetches results without exposing any card',async()=>{
    const h=makeHarness();h.responses.start.push({session:session('completed')});
    await h.flush();await h.byId('start').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['start','l'],['results','s']]);
    assert.equal(h.byId('card'),undefined);
  });
  await check('answer invalidates its scoped next query and final answer fetches results',async()=>{
    const h=makeHarness(session('open'));await h.flush();
    void h.byId('resume').onPress();await h.flush();
    void h.byId('skip').onPress();await h.flush();
    h.responses.answer.push({session_status:'completed',session_id:'s'});
    void h.byId('skip').onPress();await h.flush();
    assert.deepEqual(h.calls,[['current','l'],['next','s'],['answer','c-s',{skip:true}],['next','s'],
      ['answer','c-s',{skip:true}],['results','s']]);
  });
  await check('optional feedback starts collapsed, survives closing, and resets for the next trade',async()=>{
    const h=makeHarness(session('open'));await h.flush();h.byId('resume').onPress();await h.flush();
    assert.equal(h.disclosure()['aria-expanded'],false);
    assert.equal(h.byId('tag.overpay'),undefined);
    h.disclosure().onPress();await h.flush();
    h.byId('tag.overpay').onPress();h.byId('no').onPress();await h.flush();
    h.disclosure().onPress();await h.flush();
    assert.equal(h.byId('tag.overpay'),undefined);
    const next=card('s');next.card.card_id='c-next';next.card.position=2;
    h.responses.next.push(next);h.byId('submit').onPress();await h.flush();
    assert.deepEqual(h.counts('answer'),[['answer','c-s',{grade:1,tags:['overpay']}]]);
    assert.equal(h.disclosure()['aria-expanded'],false);
    h.disclosure().onPress();await h.flush();
    assert.equal(h.byId('tag.overpay').accessibilityState.selected,false);
  });
  await check('obsolete final answer cannot fetch results after account switch',async()=>{
    const h=makeHarness(session('open'));const d=deferred();h.responses.answer.push(d.promise);await h.flush();
    void h.byId('resume').onPress();await h.flush();
    void h.byId('skip').onPress();await h.flush();
    h.select({user:'u2'});await h.flush();d.resolve({session_status:'completed',session_id:'s'});await h.flush();
    assert.deepEqual(h.counts('results'),[]);
  });
  if(failures.length)process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1;});
