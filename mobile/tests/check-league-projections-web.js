const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tagName=tag;this.children=[];this.textContent='';this.hidden=false; }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  get allText(){return this.textContent+' '+this.children.map(c=>c.allText||String(c)).join(' ');}
}
const host=new Element('section');
let league='123',user='account',fail=false;
const result={iterations:1000,captured_at:'2026-11-01T00:00:00+00:00',model_version:'synthetic-v1',config:{draft_season:2027,draft_round:1,historical_weight:.6,ir_maxpf:'exclude'},teams:[],warnings:['Synthetic retained evidence']};
const context={leagueId:()=>league,userId:()=>user,apiFetch:async(path,options)=>{if(options?.method==='POST') return {ok:true,json:async()=>({run_id:'b'.repeat(32),status:'queued'})};if(fail)throw Error('network down');return {ok:true,json:async()=>({state:'current',next_attempt_not_before:'2026-11-10T14:30:00+00:00',run:{run_id:'a'.repeat(32),result}})};}};
const window={FTF_FLAG:()=>true,FTFWinNowContext:context};
vm.runInNewContext(fs.readFileSync(require('node:path').resolve(__dirname, '../../web/js/league-projections.js'),'utf8'),{window,document:{createElement:t=>new Element(t),getElementById:()=>host},URL:{},console});
(async()=>{
  await window.loadLeagueProjectionBatch();
  assert.match(host.allText,/Synthetic retained evidence/);
  fail=true;await window.loadLeagueProjectionBatch();
  assert.match(host.allText,/Synthetic retained evidence/,'same-context GET failure must preserve last valid rendered projection');
  const find=(node,text)=>node.textContent===text?node:node.children.map(c=>find(c,text)).find(Boolean);
  await find(host,'40%').onclick();
  assert.match(host.allText,/Comparison queued for background processing/,'restored result controls must acknowledge successfully queued comparisons');
  league='456';await window.loadLeagueProjectionBatch();
  assert.doesNotMatch(host.allText,/Synthetic retained evidence/,'league switch must not retain previous league result');
  console.log('3 web state assertions passed');
})().catch(err=>{console.error(err.message);process.exitCode=1;});
