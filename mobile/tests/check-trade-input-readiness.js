#!/usr/bin/env node
// Executes production admission, mutation callbacks, fair sweep, handoff, DNA
// coalescing and deadline code. Synthetic controls, not physical-device timing.
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict'),ts=require('typescript');
const src=path.join(__dirname,'../src');
const read=f=>fs.readFileSync(path.join(src,f),'utf8');
function compile(code,context={}) {const module={exports:{}};vm.runInNewContext(ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,{module,exports:module.exports,setTimeout,clearTimeout,AbortController,Date,Promise,performance,...context});return module.exports;}
function tree(f){const ast=ts.createSourceFile(f,read(f),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),nodes=[];(function walk(n){nodes.push(n);ts.forEachChild(n,walk);})(ast);return {ast,nodes};}
const screen=tree('screens/TradesScreen.tsx');
const fn=name=>screen.nodes.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name).getText(screen.ast);
function bind(code,c){return compile('module.exports=function(c){with(c){return ('+code+');}}')(c);}
const mutation=screen.nodes.find(n=>ts.isVariableDeclaration(n)&&n.name.getText(screen.ast)==='generateMutation').initializer.arguments[0];
const props=Object.fromEntries(mutation.properties.map(n=>[n.name?.getText(screen.ast),n.initializer?.getText(screen.ast)]));
const api=tree('api/client.ts');
const deadlineSource=api.nodes.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='runWithDeadline').getText(api.ast);
class ApiError extends Error {constructor(status,body,message,isTimeout=false){super(message);this.status=status;this.body=body;this.isTimeout=isTimeout;}}
const deadline=compile(deadlineSource,{ApiError,TIMEOUT_MESSAGE:'Timed out',requestAborted:()=>new Error('aborted')}).runWithDeadline;
const tick=()=>new Promise(r=>setImmediate(r));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const json=v=>JSON.parse(JSON.stringify(v));
let passed=0;
async function check(name,run){await run();passed++;console.log('PASS '+name);}
function world(){
 const e={revision:1,session:{hasToken:true,switching:false,user:{user_id:'synthetic'},league:{league_id:'L'},activeFormat:'sf'},calls:[],effects:[]};
 const handoff=compile(read('state/tradeSearchHandoff.ts'),{require:n=>n.includes('client')?{getSessionRevision:()=>e.revision}:{useSession:{getState:()=>e.session}}});
 const rules=compile(read('utils/tradePages.ts'));
 const device=compile(read('utils/devicePage.ts'),{require:()=>rules});
 const storage={getAllKeys:async()=>[],multiRemove:async()=>{},removeItem:async()=>{}};
 const store=compile(read('state/devicePageStore.ts')+'\nexport function reviewListenerCount(){return settledListeners.size;}',{require:n=>{
  if(n.includes('async-storage'))return {default:storage};
  if(n==='react-native')return {AppState:{currentState:'active'}};
  if(n.includes('react-query'))return {onlineManager:{isOnline:()=>true}};
  if(n==='../api/client')return {getSessionRevision:()=>e.revision,runWithDeadline:deadline,setOnWriteRequest:f=>{e.write=f;}};
  if(n==='../api/trades')return {};
  if(n==='./tradeSearchHandoff')return handoff;
  if(n==='../utils/devicePage')return device;
  throw Error(n);
 }});
 const begin=store.beginTradePageInputTransition;
 store.beginTradePageInputTransition=(context=handoff.tradeSearchContextIdentity())=>begin(context);
 const c={...handoff,...store,ApiError,traceFor:()=>null,monotonicNow:()=>performance.now(),gateFailureReason:()=> 'gate',TRADE_INPUTS_CHANGED:'Your trade inputs changed while searching. Try again.',TRADE_CONTEXT_NOT_READY:'Your league is still getting ready. Try again.',DECK_FAIL_GENERIC:'Could not load',
  mountedRef:{current:true},deckEpochRef:{current:1},modelAttemptRef:{current:1},lastModelRequestRef:{current:null},canvasSelectionRef:{current:null},
  generateTrades:(request,paging,options)=>{e.calls.push({request,paging,options});return Promise.resolve({job_id:'j',search_id:'tap',status:'complete',cards:[{trade_id:'card'}]});},
  setJob:x=>e.effects.push(['job',x]),setDeckFailure:x=>e.effects.push(['failure',x]),setToast:x=>e.effects.push(['toast',x]),
  autoResearchRef:{current:'idle'},autoResearchAfterAnswer:()=> 'idle',deckScopeRef:{current:null},deckKeyRef:{current:null},validatedAtRef:{current:0},
  devicePageScope:device.devicePageScope,deckSearchRef:{current:null},readErrorCopy:compile(read('utils/verification.ts'),{require:()=>({ApiError})}).readErrorCopy,gateSignalFor:()=>null,
  useFinderTargets:{getState:()=>({pinnedGive:[],pinnedReceive:[],packageMode:false})},canvasResultsLive:true,
  autoGenRef:{current:'none'},setAutoGenFailed:()=>{},setGateEnd:()=>{},isResultsPushed:false,deckRef:{current:[]},popToLanding:()=>{},
  failDeckSearch:()=>{},noteFirstResponse:()=>{},noteSearchCards:()=>{},failFirstCard:()=>{},
 };
 c.modelAttemptCurrent=bind(fn('modelAttemptCurrent'),c);
 const handlers=Object.fromEntries(Object.entries(props).map(([k,v])=>[k,bind(v,c)]));
 function vars(){return {searchId:'tap',request:{league_id:'L',pinned_give_players:['g'],pinned_receive_players:['r'],opponent_user_id:'O'},deadlineAt:Date.now()+1000,tapAt:performance.now(),context:{epoch:1,deviceKey:'key',contextIdentity:handoff.tradeSearchContextIdentity(),attempt:1}};}
 async function execute(v=vars()){let context;try{context=await handlers.onMutate(v);const response=await handlers.mutationFn(v);handlers.onSuccess(response,v,context);return {response,context};}catch(error){handlers.onError(error,v,context);return {error,context};}}
 return {...e,e,c,handoff,store,handlers,vars,execute};
}
(async()=>{
 await check('token lookup or server readiness backoff cannot send under a replacement context',async()=>{
  const w=world(),send=deferred();let fetches=0;
  w.c.generateTrades=async (_request,_paging,options)=>{
   await send.promise;
   options.beforeDispatch();
   fetches++;
   return {job_id:'wrong-context'};
  };
  const pending=w.execute();await tick();
  w.e.revision++;
  send.resolve();
  const result=await pending;
  assert.match(result.error.message,/trade_search_context_changed/);
  assert.equal(fetches,0);assert.deepEqual(w.e.effects,[]);
 });
 await check('pending preference write settles before POST and its valid card is applied',async()=>{
  const w=world();w.e.write('/api/league/preferences','start');const v=w.vars(),p=w.execute(v);await tick();assert.equal(w.e.calls.length,0);
  w.e.write('/api/league/preferences','settled');const result=await p;
  assert(result.response);assert.equal(w.e.calls.length,1);assert.equal(w.e.calls[0].paging.searchId,'tap');assert.equal(w.e.calls[0].options.deadlineAt,v.deadlineAt);
  assert(w.e.effects.some(x=>x[0]==='job'&&x[1]?.job_id==='j'));assert.equal(v.context.identity,w.handoff.tradeSearchIdentity());
 });
 await check('logical coalesced transition spans API settlement gaps',async()=>{
  const w=world(),finish=w.store.beginTradePageInputTransition();w.e.write('/api/league/preferences','start');const p=w.execute();
  w.e.write('/api/league/preferences','settled');await tick();assert.equal(w.e.calls.length,0);
  w.e.write('/api/league/preferences','start');w.e.write('/api/league/preferences','settled');await tick();assert.equal(w.e.calls.length,0);
  finish();await p;assert.equal(w.e.calls.length,1);
 });
 await check('failed logical save releases barrier with actionable error and no generation',async()=>{
  const w=world(),finish=w.store.beginTradePageInputTransition();const p=w.execute();await tick();finish(false);const result=await p;
  assert.match(result.error.message,/could not be saved/);assert.equal(w.e.calls.length,0);assert.equal(w.store.hasPendingTradePageInputs(),false);
  assert(w.e.effects.some(x=>x[0]==='failure'&&/saved/.test(x[1].message)));
 });
 await check('save failure after original tap but before destination admission is not forgotten',async()=>{
  const w=world(),v=w.vars(),finish=w.store.beginTradePageInputTransition();finish(false);const result=await w.execute(v);
  assert.match(result.error.message,/could not be saved/);assert.equal(w.e.calls.length,0);
  // An explicit later attempt may use the actual persisted preferences.
  const next=w.vars();await w.execute(next);assert.equal(w.e.calls.length,1);
 });
 await check('a failed save from the former league cannot fail the replacement league search',async()=>{
  const w=world(),finish=w.store.beginTradePageInputTransition();
  w.e.session.league={league_id:'new'};
  const v=w.vars();v.request.league_id='new';
  const p=w.execute(v);await tick();finish(false);
  assert((await p).response);
  assert.equal(w.e.calls[0].request.league_id,'new');
 });
 await check('same-context billing refusal retains gate handling despite changed input revision',async()=>{
  const w=world(),v=w.vars();await w.handlers.onMutate(v);w.store.beginTradePageInputTransition()();const error=new ApiError(402,{},'Pro');error.isProRequired=true;
  let gates=0;w.c.failDeckSearch=()=>gates++;w.handlers.onError(error,v,v.context);assert.equal(gates,1);assert(!w.e.effects.some(x=>x[0]==='failure'));
 });
 await check('deadline bounds pending readiness and leaves explicit same-context retry',async()=>{
  const w=world(),finish=w.store.beginTradePageInputTransition(),v=w.vars();v.deadlineAt=Date.now()+25;
  const result=await w.execute(v);assert.equal(result.context,undefined);assert.equal(result.error.isTimeout,true);assert.equal(w.e.calls.length,0);
  assert(w.e.effects.some(x=>x[0]==='failure'));finish();await tick();assert.equal(w.e.calls.length,0);
 });
 for(const [name,change]of Object.entries({account:w=>w.e.session.user={user_id:'B'},league:w=>w.e.session.league={league_id:'B'},format:w=>w.e.session.activeFormat='1qb',token:w=>w.e.revision++,logout:w=>w.e.session.hasToken=false,switching:w=>w.e.session.switching=true,unmount:w=>w.c.mountedRef.current=false,epoch:w=>w.c.deckEpochRef.current++,newerAttempt:w=>w.c.modelAttemptRef.current++})){
  await check(name+' replacement while waiting cannot send or apply undefined-context error',async()=>{const w=world(),finish=w.store.beginTradePageInputTransition(),p=w.execute();await tick();change(w);finish();const result=await p;assert(result.error);assert.equal(result.context,undefined);assert.equal(w.e.calls.length,0);assert.deepEqual(w.e.effects,[]);});
 }
 await check('write beginning in readiness continuation gap is awaited before identity binding',async()=>{
  const w=world();let waits=0,finish;const original=w.c.waitForTradePageInputs;
  w.c.waitForTradePageInputs=async(...args)=>{await original(...args);if(++waits===1)finish=w.store.beginTradePageInputTransition();};
  const p=w.execute();await tick();assert.equal(waits,1);assert.equal(w.e.calls.length,0);finish();await p;assert.equal(waits,2);assert.equal(w.e.calls.length,1);
 });
 await check('failed write in the final admission microtask gap cannot silently use old preferences',async()=>{
  const w=world(),original=w.c.waitForTradePageInputs;
  w.c.waitForTradePageInputs=async(...args)=>{await original(...args);w.store.beginTradePageInputTransition()(false);};
  const result=await w.execute();assert.match(result.error.message,/could not be saved/);assert.equal(w.e.calls.length,0);assert(w.e.effects.some(x=>x[0]==='failure'));
 });
 await check('write after admission refuses network rather than accepting an incomplete generation',async()=>{
  const w=world(),v=w.vars();await w.handlers.onMutate(v);const finish=w.store.beginTradePageInputTransition();
  assert.throws(()=>w.handlers.mutationFn(v),/trade_search_context_changed/);assert.equal(w.e.calls.length,0);finish();
 });
 for(const outcome of ['success','error'])await check('post-admission input invalidation surfaces retry on '+outcome,async()=>{
  const w=world(),v=w.vars(),d=deferred();w.c.generateTrades=()=>d.promise;const p=w.execute(v);await tick();const finish=w.store.beginTradePageInputTransition();finish();
  outcome==='success'?d.resolve({job_id:'old',status:'complete',cards:[{}]}):d.reject(Error('network'));
  await p;assert(!w.e.effects.some(x=>x[0]==='job'&&x[1]));assert(w.e.effects.some(x=>x[0]==='failure'&&/inputs changed/.test(x[1].message)));
 });
 await check('captured model terms detach selected arrays before waiting',()=>{
  const w=world(),pins=[{id:'g'}],receive=[{id:'r'}];Object.assign(w.c,{leagueId:'L',effectiveFairness:.5,scopedOpponent:'O',tradeIntent:'tier_up',targetingEnabled:true,
   useFinderTargets:{getState:()=>({pinnedGive:pins,pinnedReceive:receive,packageMode:true})},modelSelectionParams:compile(read('utils/tradeSearchRequest.ts')).modelSelectionParams});
  const request=bind(fn('modelRequest'),w.c)({});pins[0].id='changed';receive.push({id:'new'});assert.deepEqual(json(request.pinned_give_players),['g']);assert.deepEqual(json(request.pinned_receive_players),['r']);assert.equal(request.opponent_user_id,'O');
 });
 for(const mode of ['model','fair'])await check(mode+' builder pushes without eager POST or stale page while writes pending',()=>{
  const w=world(),finish=w.store.beginTradePageInputTransition(),pushes=[];
  const c={...w.handoff,switching:false,leagueId:'L',fairnessReady:true,hasPendingTradePageInputs:w.store.hasPendingTradePageInputs,
   resultsPushPendingRef:{current:false},dropPendingSearch:()=>{},generateTrades:()=>{throw Error('eager POST');},getFairPackages:()=>{throw Error('eager POST');},readDevicePage:()=>{throw Error('stale page');}};
  bind(fn('pushWithFirstPage'),c)({searchId:'tap',anchor:mode==='fair'?{}:null},x=>pushes.push(x));assert.equal(pushes.length,1);finish();
 });
 await check('actual dispatch retains accepted selection for retry before admission or network',async()=>{
  const w=world(),selected={giveIds:['g'],receiveIds:['r']};w.c.canvasSelectionRef.current=selected;
  Object.assign(w.c,{canvasResultsLive:false,claimPendingSearch:()=> 'tap',claimSearch:()=>{},handoffSearchRef:{current:null},lastFairRequestRef:{current:null},deviceKey:'key',uuidv4:()=> 'new',
   modelRequest:()=>({league_id:'L',pinned_give_players:[...selected.giveIds],pinned_receive_players:[...selected.receiveIds]}),tradeRequestDeadline:()=>Date.now()+1000,generateMutation:{mutate:vars=>{w.dispatched=vars;}}});
  bind(fn('dispatchGenerate'),w.c)({});assert.equal(w.c.lastModelRequestRef.current,w.dispatched.request);assert.equal(w.c.canvasSelectionRef.current,null);
  selected.giveIds.push('later');assert.deepEqual(json(w.c.lastModelRequestRef.current.pinned_give_players),['g']);
 });
 await check('original tap age reduces rather than resets API deadline',()=>{
  const w={traceFor:()=>({tapAt:100}),monotonicNow:()=>4100,timeoutForRequest:()=>30000};const before=Date.now(),due=bind(fn('tradeRequestDeadline'),w)('tap','/api/trades/generate');assert(due>=before+26000&&due<=Date.now()+26000);
 });
 // Execute the actual fair loader with its real admission and catch/finally.
 function fairWorld(){const w=world(),c=w.c;Object.assign(c,{leagueId:'L',scopedOpponent:'O',effectiveFairness:.5,deckMode:'organic',
  fairPendingRef:{current:false},lastFairRequestRef:{current:null},handoffSearchRef:{current:'tap'},lastDispositionedRef:{current:null},flushPendingPassRef:{current:()=>{}},
  claimPendingSearch:()=>null,claimSearch:()=>{},beginTradeSearch:()=>{throw Error('must retain tap');},tradeRequestDeadline:()=>Date.now()+1000,
  fairPackagesRequest:compile(read('utils/tradeSearchRequest.ts')).fairPackagesRequest,ideaToCard:x=>x,
  getFairPackages:(request,options)=>{w.e.calls.push({request,options});return Promise.resolve({ideas:[{trade_id:'fair'}]});},
  setFairPending:x=>w.e.effects.push(['pending',x]),setFairDeck:x=>w.e.effects.push(['fair',x]),setDeck:x=>w.e.effects.push(['deck',x]),setDeckIdx:()=>{},setScopedEmpty:()=>{},setSummaryDismissed:()=>{}});
  return {...w,run:bind(fn('runFairPackages'),c)};
 }
 await check('fair pending-write handoff preserves exact terms, original search and one request',async()=>{
  const w=fairWorld(),finish=w.store.beginTradePageInputTransition(),anchor={giveIds:['g'],receiveIds:['r']};const p=w.run(anchor,'O');anchor.giveIds.push('late');await tick();assert.equal(w.e.calls.length,0);finish();await p;
  assert.equal(w.e.calls.length,1);assert.deepEqual(json(w.e.calls[0].request.give_player_ids),['g']);assert.equal(w.c.deckSearchRef.current.id,'tap');assert(w.e.effects.some(x=>x[0]==='deck'&&x[1][0]?.trade_id==='fair'));assert.equal(w.c.fairPendingRef.current,false);
 });
 await check('fair write in admission microtask gap also waits',async()=>{const w=fairWorld(),original=w.c.waitForTradePageInputs;let count=0,finish;
  w.c.waitForTradePageInputs=async(...args)=>{await original(...args);if(++count===1)finish=w.store.beginTradePageInputTransition();};const p=w.run({giveIds:['g'],receiveIds:[]});await tick();assert.equal(w.e.calls.length,0);finish();await p;assert.equal(count,2);assert.equal(w.e.calls.length,1);
 });
 await check('fair accepted attempt without ready authority surfaces a bounded readiness error',async()=>{
  const w=fairWorld();w.e.session.hasToken=false;await w.run({giveIds:['g'],receiveIds:[]});assert.equal(w.e.calls.length,0);assert(w.e.effects.some(x=>x[0]==='failure'&&/getting ready/.test(x[1]?.message)));
 });
 await check('model dispatch without ready authority surfaces readiness and never binds later account',()=>{
  const w=world();w.e.session.hasToken=false;Object.assign(w.c,{canvasResultsLive:false,claimPendingSearch:()=> 'tap',claimSearch:()=>{},handoffSearchRef:{current:null},lastFairRequestRef:{current:null},deviceKey:'key',uuidv4:()=> 'new',generateMutation:{mutate:()=>{throw Error('unready mutation');}}});
  bind(fn('dispatchGenerate'),w.c)({});assert(w.e.effects.some(x=>x[0]==='failure'&&/getting ready/.test(x[1]?.message)));assert.equal(w.e.calls.length,0);
 });
 await check('fair save failure surfaces retry without a request',async()=>{const w=fairWorld(),finish=w.store.beginTradePageInputTransition(),p=w.run({giveIds:['g'],receiveIds:[]});await tick();finish(false);await p;assert.equal(w.e.calls.length,0);assert(w.e.effects.some(x=>x[0]==='failure'&&/saved/.test(x[1]?.message)));});
 await check('fair post-admission change refuses old cards and surfaces retry',async()=>{const w=fairWorld(),d=deferred();w.c.getFairPackages=()=>d.promise;const p=w.run({giveIds:['g'],receiveIds:[]});await tick();w.store.beginTradePageInputTransition()();d.resolve({ideas:[{trade_id:'old'}]});await p;assert(!w.e.effects.some(x=>x[0]==='deck'&&x[1][0]?.trade_id==='old'));assert(w.e.effects.some(x=>x[0]==='failure'&&/inputs changed/.test(x[1]?.message)));});
 await check('fair old-account wait failure cannot affect replacement context',async()=>{const w=fairWorld(),finish=w.store.beginTradePageInputTransition(),p=w.run({giveIds:['g'],receiveIds:[]});await tick();w.e.effects.length=0;w.e.session.user={user_id:'B'};w.c.deckEpochRef.current++;finish();await p;assert.deepEqual(w.e.effects,[]);assert.equal(w.e.calls.length,0);});
 // Actual autosave loop: A has B queued before its API settlement.
 const dna=tree('components/TradeDnaSheet.tsx');const flush=dna.nodes.find(n=>ts.isVariableDeclaration(n)&&n.name.getText(dna.ast)==='flushDnaSave').initializer.getText(dna.ast);
 for(const failure of [false,true])await check('actual DNA A→B coalescing '+(failure?'failed':'successful')+' tail retains barrier',async()=>{
  const w=world(),a=deferred(),b=deferred();let saves=0;const ctx={dnaInFlight:{current:false},dnaDesired:{current:{value:'A'}},dnaTransition:{current:null},beginTradePageInputTransition:w.store.beginTradePageInputTransition,tradeSearchContextIdentity:w.handoff.tradeSearchContextIdentity,
   saveOutlook:{mutateAsync:()=>++saves===1?a.promise:b.promise},dnaError:null,setDnaError:()=>{},queryClient:{getQueryData:()=>({})},leagueId:'L',dnaTouched:{current:true},prefs:{},setDraftMode:()=>{},setDraftOutlook:()=>{},setDraftValue:()=>{},setDraftFairness:()=>{},setDraftShapes:()=>{},setDraftAvoid:()=>{},setDraftNeeds:()=>{}};
  // Catch restores draft fields through several setters; expose only test stubs.
  const unknown=new Proxy(ctx,{has:(_,k)=>k!=='Promise',get:(t,k)=>k in t?t[k]:(()=>{})});
  ctx.flushDnaSave=bind(flush,unknown);const first=ctx.flushDnaSave();ctx.dnaDesired.current={value:'B'};const searching=w.execute();await tick();a.resolve();await first;await tick();assert.equal(saves,2);assert.equal(w.e.calls.length,0);assert(w.store.hasPendingTradePageInputs());
  failure?b.reject(Error('save failed')):b.resolve();await tick();await searching;assert.equal(w.store.hasPendingTradePageInputs(),false);assert.equal(w.e.calls.length,failure?0:1);
 });
 await check('readiness timeout removes listener and later settlement does not POST',async()=>{
  const w=world(),finish=w.store.beginTradePageInputTransition(),v=w.vars();v.deadlineAt=Date.now()+50;
  const pending=w.execute(v);await tick();assert.equal(w.store.reviewListenerCount(),1);await pending;assert.equal(w.store.reviewListenerCount(),0);finish();await tick();assert.equal(w.e.calls.length,0);
 });
 await check('normal readiness removes listener before response',async()=>{
  const w=world();await w.execute();assert.equal(w.store.reviewListenerCount(),0);assert.equal(w.e.calls.length,1);
 });
 await check('input edit cannot hide a402 behind generic error',async()=>{
  const w=world(),v=w.vars(),d=deferred();let gates=0;w.c.generateTrades=()=>d.promise;w.c.failDeckSearch=()=>gates++;w.c.gateFailureReason=()=> 'paywall';
  const p=w.execute(v);await tick();w.store.beginTradePageInputTransition()();const e=new ApiError(402,null,'paywall');e.isProRequired=true;d.reject(e);await p;
  assert.equal(gates,1);assert(!w.e.effects.some(e=>e[0]==='failure'));
 });
 await check('older same-context attempt is not revived by later write settlement',async()=>{
  const w=world(),finish=w.store.beginTradePageInputTransition(),old=w.execute();await tick();w.c.modelAttemptRef.current++;
  const v=w.vars();v.context.attempt=2;const fresh=w.execute(v);finish();await Promise.all([old,fresh]);
  assert.equal(w.e.calls.length,1);assert.equal(w.e.effects.filter(e=>e[0]==='job'&&e[1]).length,1);
 });
 await check('error after token replacement is ignored even with data-generation change',async()=>{
  const w=world(),d=deferred();w.c.generateTrades=()=>d.promise;const p=w.execute();await tick();w.e.revision++;w.store.beginTradePageInputTransition()();d.reject(Error('old response'));await p;assert.deepEqual(w.e.effects,[]);
 });
 await check('changed saved-request ref after dispatch never replaces the captured request',async()=>{
  const w=world(),v=w.vars(),finish=w.store.beginTradePageInputTransition();const original=v.request;
  const p=w.execute(v);await tick();w.c.lastModelRequestRef.current={league_id:'other'};finish();await p;
  assert.equal(w.e.calls[0].request,original);assert.equal(w.e.calls[0].paging.searchId,'tap');
 });
 console.log(`${passed} trade input readiness controls passed.`);
})().catch(e=>{console.error(e);process.exitCode=1;});
