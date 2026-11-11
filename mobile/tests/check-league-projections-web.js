/*
 * Web "Projected standings" (web/js/league-projections.js) run under plain node
 * with a fake DOM, plus the outlook-overlay slice of web/js/app.js that the
 * "Review outlook" button opens.
 *
 * What it proves: the section reads the saved run and never writes (no
 * comparison control, no forecast-details/export controls, no POST); an
 * old-model run reads "Last saved" and carries no outlook prompt; the prompt
 * appears only for an available recommendation that differs; "Review outlook"
 * only tags the recommended option "Suggested" in the existing overlay, never
 * selecting or saving it; and an incomplete estimate says so.
 *
 * HONEST LABEL: the DOM is a fake. Layout, styling and the real overlay markup
 * in web/index.html are not exercised here.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const read = file => fs.readFileSync(path.resolve(__dirname, '../../web/js', file), 'utf8');
const source = read('league-projections.js');
const appSource = read('app.js');

class Element {
  constructor(tag) { this.tagName=tag;this.children=[];this.textContent='';this.hidden=false;this.open=false;this.attrs={}; }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(k,v){this.attrs[k]=v;}
  get allText(){return this.textContent+' '+this.children.map(c=>c.allText||String(c)).join(' ');}
  get visibleText(){return this.hidden?'':this.textContent+' '+(this.tagName==='details'&&!this.open?this.children.slice(0,1):this.children).map(c=>c.visibleText).join(' ');}
}
const find=(node,text)=>node.textContent===text?node:node.children.map(c=>find(c,text)).find(Boolean);
const count=(node,text)=>(node.textContent===text?1:0)+node.children.reduce((n,c)=>n+count(c,text),0);

/* ── The outlook overlay slice of app.js, executed against a fake overlay ── */
const slice=(from,to)=>{const a=appSource.indexOf(from),b=appSource.indexOf(to,a);assert.ok(a>=0&&b>a,`app.js slice ${from} … ${to} not found`);return appSource.slice(a,b);};
const overlay={hidden:true,saved:'rebuilder',writes:0};
const optionButtons=['championship','contender','rebuilder','jets','not_sure'].map(value=>{
  const name={tags:[],appendChild(tag){tag.remove=()=>{name.tags=name.tags.filter(t=>t!==tag);};name.tags.push(tag);}};
  return {dataset:{value},selected:false,name,classList:{toggle:(_,on)=>{optionButtons.find(b=>b.dataset.value===value).selected=on;}},
    querySelector:sel=>sel==='.outlook-option-name'?name:name.tags.find(t=>t.className.split(' ').includes(sel.slice(1)))};
});
const overlayDocument={
  createElement:()=>({className:'',textContent:'',title:''}),
  getElementById:id=>id==='outlook-overlay'?{classList:{add:()=>{overlay.hidden=true;},remove:()=>{overlay.hidden=false;}}}:{style:{},textContent:''},
  querySelectorAll:sel=>sel==='.outlook-option-btn'?optionButtons:optionButtons.flatMap(b=>b.name.tags.filter(t=>t.className.split(' ').includes(sel.slice(1)))),
};
const appWindow={};
vm.runInNewContext(`
  let _cachedLeagues=[], currentLeagueId='123', currentOutlook=overlay.saved, _inferredOutlook='jets', _inferredSignals=[], _pendingOutlookValue=null;
  function _outlookModalStep(){}
  ${slice('const OUTLOOK_META = {','// Positional preferences state')}
  ${slice('function showOutlookModal(','function selectOutlookStep1(')}
  window.dismiss = dismissOutlookModal; window.pending = () => _pendingOutlookValue;
`,{window:appWindow,document:overlayDocument,overlay,apiFetch:()=>{overlay.writes++;throw Error('overlay hook must not fetch');}});
const tagged=()=>optionButtons.filter(b=>b.name.tags.length).map(b=>`${b.dataset.value}:${b.name.tags.map(t=>t.textContent).join()}`);
const selected=()=>optionButtons.filter(b=>b.selected).map(b=>b.dataset.value);

/* ── league-projections.js under a fake DOM ── */
const host=new Element('section');
let league='123',user='account',fail=false;
const flags={'league.projections':true,'league.projection_outlook':true};
const projectedWeek={week:9,opponent_roster_id:1,win_probability:.6,tie_probability:0,loss_probability:.4,actual_score_observed:false,
  modeled_score_mean:120.5,modeled_score_sd:24,actual:{lineup:[]},exclusions:[],
  // fallback / *_component are what an old-model result still carries: they must not be rendered.
  historical_component:99.9,projection_component:88.8,modeled_actual_projection:77.7,modeled_maxpf_projection:66.6,
  projection_coverage:{estimated:true,complete:false,missing_actual_slots:['FLEX','TE'],priced_actual_pool:8,priced_maxpf_pool:20,
    unpriced_players:[],partial_players:[],fallback:true,fallback_lanes:['actual']}};
const observedWeek={week:8,opponent_roster_id:1,win_probability:1,tie_probability:0,loss_probability:0,actual_score_observed:true,
  modeled_score_mean:141.2,modeled_score_sd:0,modeled_actual_projection:141.2,actual:{lineup:[]},exclusions:[],
  // complete:true wins over a stray slot list: the flag, not the list, decides whether the sentence shows.
  projection_coverage:{complete:true,missing_actual_slots:['K']}};
const team={roster_id:1,name:'Synthetic team',playoff_probability:.95,nonplayoff_probability:.05,bye_probability:.75,
  expected_record:[12.5,1.3,.2],modal_record:[13,1,0],current_record:[8,0,0],current_points_for:1200,current_ppg:150,maxpf_mean:2400,
  pick_owner_roster_id:1,conditional_expected_pick:3.1,maxpf_quantiles:{'0.1':2150,'0.9':2650},pick_probabilities:[.05],weeks:[observedWeek,projectedWeek]};
const result={iterations:1000,captured_at:'2026-11-01T12:00:00+00:00',model_version:'synthetic-v1',score_sd:24,
  config:{draft_season:2027,draft_round:1,ir_maxpf:'exclude'},playoff_byes:2,
  coverage:{estimated:true,estimate_status:'complete',missing_lineup_slots:0},teams:[team],warnings:['Synthetic retained evidence'],scoring:{rec:1}};
const recommendation={status:'available',reason:null,playoff_probability:.7449,recommended_outlook:'contender',current_outlook:'rebuilder',
  differs:true,suggestion:'Server-written suggestion sentence.',explanation:'Server-written explanation sentence.',captured_at:result.captured_at};
let payload={state:'current',next_attempt_not_before:'2026-11-10T14:30:00+00:00',run:{run_id:'a'.repeat(32),result}};
const calls=[];
const context={leagueId:()=>league,userId:()=>user,apiFetch:async(url,options)=>{
  calls.push({url,method:options?.method||'GET'});
  if(fail)throw Error('network down');
  return {ok:true,json:async()=>payload};
}};
const window={FTF_FLAG:key=>!!flags[key],FTFWinNowContext:context,FTFOutlookLabel:appWindow.FTFOutlookLabel,
  FTFReviewOutlook:key=>{reviewed.push(key);return appWindow.FTFReviewOutlook(key);}};
const reviewed=[];
vm.runInNewContext(source,{window,document:{createElement:t=>new Element(t),getElementById:()=>host},console});
const load=async next=>{if(next)payload=next;await window.loadLeagueProjectionBatch();};
const withResult=(coverage,extra)=>({...payload,...extra,run:{run_id:'a'.repeat(32),result:{...result,coverage:{...result.coverage,...coverage}}}});
const noPrompt=label=>{
  assert.equal(find(host,'Review outlook'),undefined,`${label}: no Review outlook button`);
  assert.doesNotMatch(host.allText,/playoff chance|Consider |Server-written suggestion/,`${label}: no outlook prompt copy`);
};

(async()=>{
  /* Current run, current model, complete estimate, no recommendation block. */
  await load();
  assert.match(host.visibleText,/Weekly estimate · Partial Sleeper data.*Playoff odds.*Synthetic team.*95\.0%/);
  assert.doesNotMatch(host.allText,/Last saved|Incomplete|incomplete/,'a complete current-model run is the weekly estimate');
  noPrompt('no recommendation block');
  find(host,'Synthetic team').onclick();
  assert.match(host.visibleText,/Most likely finish.*Bye odds: 75\.0%/);
  assert.match(host.allText,/Recorded completed lineup score 141\.2\. /,'observed week copy');
  assert.match(host.allText,/Projected lineup score 120\.5, standard deviation 24\.0\./,'projected week copy');
  assert.match(host.allText,/No projection for an eligible player at: FLEX, TE\./,'missing-slot week copy');
  assert.equal(count(host,'No projection for an eligible player at: FLEX, TE.'),1,'only the incomplete week names missing slots');
  assert.doesNotMatch(host.allText,/eligible player at: K/,'a complete week shows no missing-slot sentence');
  assert.match(host.allText,/Max PF players\. Unknown players and rules are not confirmed zeros\./);
  assert.equal(count(host,'Exclusions: None.'),2,'exclusions stay as their own line on every week');
  assert.doesNotMatch(host.allText,/historical blend|Historical component|projection component|Completed team history|99\.9|88\.8|66\.6/i,'no history-blend or history-fallback wording');
  find(host,'Non-playoff picks').onclick();
  assert.match(host.visibleText,/Estimates assume regular-season Max PF draft order/);
  assert.match(host.visibleText,/Miss playoffs.*5\.0%/);
  find(host,'Synthetic team').onclick();
  assert.match(host.visibleText,/Expected pick if this team misses: 3\.1/);

  /* Removed controls: comparison, forecast details, exports. */
  assert.doesNotMatch(host.allText,/Compare history weights|Check comparison|Comparison queued|history weight|Historical weight/i,'no comparison control');
  for (const label of ['40%','60%','80%','Export CSV','Export MANIFEST','Check comparison']) assert.equal(find(host,label),undefined,`no "${label}" control`);
  assert.doesNotMatch(host.allText,/Forecast details|Assumptions and scoring|Scoring settings|Forecasts update weekly|Next eligible attempt|synthetic-v1|Synthetic retained evidence|simulations ·/,'no Forecast details disclosure');
  assert.doesNotMatch(source,/POST|method\s*:|\/export\//,'the web section issues no write or export request');

  /* Same-context failure keeps the last rendered forecast and one retry button. */
  fail=true;await load();await load();
  assert.match(host.allText,/Couldn’t check for an update\. Showing last saved results\..*Synthetic team/,'same-context GET failure must preserve last valid rendered projection');
  assert.equal(count(host,'Couldn’t check for an update. Showing last saved results.'),1,'repeated failures show one notice');
  assert.equal(count(host,'Check for update'),1,'failure branch keeps exactly one Check for update button');
  league='456';await load();
  assert.doesNotMatch(host.allText,/Synthetic team/,'league switch must not retain previous league result');
  assert.match(host.allText,/Couldn’t load projections\. Current standings are still available\./);
  assert.equal(count(host,'Check for update'),1,'load failure keeps one Check for update button');
  fail=false;
  await load({state:'no_run',run:null});
  assert.match(host.visibleText,/Waiting for the first weekly forecast\..*Current standings are still available\./);
  assert.equal(count(host,'Check for update'),1,'no-result branch keeps one Check for update button');

  /* Old-model run: last saved, never the weekly estimate, never a prompt (even if a block claims one). */
  await load({state:'current',model_current:false,outlook_recommendation:recommendation,run:{run_id:'a'.repeat(32),result}});
  assert.match(host.visibleText,/Last saved: /,'old-model run reads Last saved');
  assert.doesNotMatch(host.allText,/Weekly estimate/,'old-model run is never the weekly estimate');
  noPrompt('old-model run');
  await load({state:'stale',model_current:false,outlook_recommendation:{...recommendation,status:'unavailable',reason:'model_outdated',recommended_outlook:null,differs:false,suggestion:null},run:{run_id:'a'.repeat(32),result}});
  assert.match(host.visibleText,/Weekly update due\..*Last saved: /);
  noPrompt('old-model run, server-marked unavailable');

  /* Available and different: the prompt, in the server's words, opening the existing overlay. */
  await load({state:'current',model_current:true,outlook_recommendation:recommendation,run:{run_id:'a'.repeat(32),result}});
  assert.match(host.visibleText,/Weekly estimate · Partial Sleeper data\s+74% playoff chance · Consider Contender\s+Server-written suggestion sentence\.\s+Review outlook/,'prompt sits directly under the header line');
  assert.doesNotMatch(host.allText,/Why no outlook suggestion|Server-written explanation/);
  const before=calls.length;
  await find(host,'Review outlook').onclick();
  assert.deepEqual(reviewed,['contender'],'Review outlook hands the recommended key to the app.js hook');
  assert.equal(calls.length,before,'Review outlook makes no network request');
  assert.equal(overlay.writes,0,'opening the overlay for review fetches nothing');
  assert.equal(overlay.hidden,false,'the existing outlook overlay opens');
  assert.deepEqual(tagged(),['contender:Suggested'],'only the recommended option is marked Suggested');
  assert.match(optionButtons[1].name.tags[0].className,/\boutlook-review-tag\b/,'review mark carries the flare class');
  assert.deepEqual(selected(),['rebuilder'],'the saved outlook stays selected; the suggestion is not selected');
  assert.equal(appWindow.pending(),null,'nothing is staged for saving');
  appWindow.dismiss();
  assert.deepEqual(tagged(),[],'dismissing the overlay clears the Suggested mark');
  assert.equal(overlay.hidden,true);

  /* Matching, unavailable, flag-off: no prompt. */
  await load({...payload,outlook_recommendation:{...recommendation,differs:false,suggestion:null,current_outlook:'contender'}});
  noPrompt('matching recommendation');
  assert.doesNotMatch(host.allText,/Why no outlook suggestion|Server-written explanation/,'matching recommendation shows nothing');
  await load({...payload,outlook_recommendation:{...recommendation,status:'unavailable',reason:'incomplete',playoff_probability:null,recommended_outlook:null,differs:false,suggestion:null}});
  noPrompt('unavailable recommendation');
  assert.match(host.visibleText,/Why no outlook suggestion/);
  assert.doesNotMatch(host.visibleText,/Server-written explanation/,'the explanation stays behind a tap');
  assert.match(host.allText,/Server-written explanation sentence\./);
  flags['league.projection_outlook']=false;
  await load({...payload,outlook_recommendation:recommendation});
  noPrompt('flag off');
  assert.doesNotMatch(host.allText,/Why no outlook suggestion/,'flag off renders no outlook copy at all');
  flags['league.projection_outlook']=true;

  /* Incomplete estimate. */
  await load(withResult({estimate_status:'incomplete',missing_lineup_slots:3},{outlook_recommendation:undefined}));
  assert.match(host.visibleText,/Weekly estimate · Partial Sleeper data · Incomplete\s+3 lineup slots had no projection for an eligible player, so these odds are incomplete\./,'incomplete estimate is labelled and explained');

  /* Every request this section made was a read of the saved run. */
  assert.ok(calls.length>8);
  for (const call of calls) {
    assert.equal(call.method,'GET',`unexpected ${call.method} ${call.url}`);
    assert.match(call.url,/^\/api\/leagues\/(123|456)\/projection-runs\/latest$/,`unexpected request ${call.url}`);
  }
  console.log('Web projection hierarchy, week copy, removed controls, model/incomplete labels, outlook prompt + review hook, and context checks passed');
})().catch(err=>{console.error(err.message);process.exitCode=1;});
