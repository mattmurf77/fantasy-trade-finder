const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tagName=tag;this.children=[];this.textContent='';this.hidden=false;this.open=false;this.attrs={}; }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(k,v){this.attrs[k]=v;}
  get allText(){return this.textContent+' '+this.children.map(c=>c.allText||String(c)).join(' ');}
  get visibleText(){return this.hidden?'':this.textContent+' '+(this.tagName==='details'&&!this.open?this.children.slice(0,1):this.children).map(c=>c.visibleText).join(' ');}
}
const host=new Element('section');
let league='123',user='account',fail=false;
const team={roster_id:1,name:'Synthetic team',playoff_probability:.95,nonplayoff_probability:.05,bye_probability:.75,
  expected_record:[12.5,1.3,.2],modal_record:[13,1,0],current_record:[8,0,0],current_points_for:1200,current_ppg:150,maxpf_mean:2400,
  pick_owner_roster_id:1,conditional_expected_pick:3.1,maxpf_quantiles:{'0.1':2150,'0.9':2650},pick_probabilities:[.05],weeks:[]};
const result={iterations:1000,captured_at:'2026-11-01T00:00:00+00:00',model_version:'synthetic-v1',config:{draft_season:2027,draft_round:1,historical_weight:.6,ir_maxpf:'exclude'},playoff_byes:2,coverage:{estimated:true},teams:[team],warnings:['Synthetic retained evidence']};
const context={leagueId:()=>league,userId:()=>user,apiFetch:async(path,options)=>{if(options?.method==='POST') return {ok:true,json:async()=>({run_id:'b'.repeat(32),status:'queued'})};if(fail)throw Error('network down');return {ok:true,json:async()=>({state:'current',next_attempt_not_before:'2026-11-10T14:30:00+00:00',run:{run_id:'a'.repeat(32),result}})};}};
const window={FTF_FLAG:()=>true,FTFWinNowContext:context};
vm.runInNewContext(fs.readFileSync(require('node:path').resolve(__dirname, '../../web/js/league-projections.js'),'utf8'),{window,document:{createElement:t=>new Element(t),getElementById:()=>host},URL:{},console});
(async()=>{
  await window.loadLeagueProjectionBatch();
  const find=(node,text)=>node.textContent===text?node:node.children.map(c=>find(c,text)).find(Boolean);
  assert.match(host.visibleText,/Partial Sleeper data.*Playoff odds.*Synthetic team.*95\.0%/);
  assert.doesNotMatch(host.visibleText,/synthetic-v1|Synthetic retained evidence|Next eligible attempt/);
  find(host,'Synthetic team').onclick();
  assert.match(host.visibleText,/Most likely finish.*Bye odds: 75\.0%/);
  find(host,'Non-playoff picks').onclick();
  assert.match(host.visibleText,/Assumes|Estimates assume regular-season Max PF draft order/);
  assert.match(host.visibleText,/Miss playoffs.*5\.0%/);
  find(host,'Synthetic team').onclick();
  assert.match(host.visibleText,/Expected pick if this team misses: 3\.1/);
  assert.match(host.allText,/Synthetic retained evidence/);
  fail=true;await window.loadLeagueProjectionBatch();
  assert.match(host.allText,/Synthetic retained evidence/,'same-context GET failure must preserve last valid rendered projection');
  await find(host,'40%').onclick();
  assert.match(host.allText,/Comparison queued for background processing/,'restored result controls must acknowledge successfully queued comparisons');
  league='456';await window.loadLeagueProjectionBatch();
  assert.doesNotMatch(host.allText,/Synthetic retained evidence/,'league switch must not retain previous league result');
  console.log('Web projection hierarchy, team and draft disclosure, comparison and context checks passed');
})().catch(err=>{console.error(err.message);process.exitCode=1;});
