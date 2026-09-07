(function () {
  'use strict';
  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const assetNames = {evans:'Mike Evans',henry:'Derrick Henry',kittle:'George Kittle',cook:'James Cook',maye:'Drake Maye',benson:'Trey Benson',odunze:'Rome Odunze',kraft:'Tucker Kraft','own-2027-1':'Your 2027 1st','acquired-2027-1':'Acquired 2027 1st','2027-2':'Your 2027 2nd','2028-1':'Your 2028 1st','2028-3':'Your 2028 3rd'};
  const style = `<style>
  #mock-screen .ex-trade{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}
  #mock-screen .ex-trade>div+div{border-left:1px solid #262C35;padding-left:12px}
  #mock-screen .ex-trade strong{display:block;font-size:14px;line-height:1.5;margin:8px 0;overflow-wrap:anywhere}
  #mock-screen .ex-small{font-size:12px;color:#97A1AE;line-height:1.5}
  #mock-screen .ex-count{font-family:'IBM Plex Mono',monospace;font-variant-numeric:tabular-nums}
  #mock-screen .ex-statline{display:flex;gap:16px;flex-wrap:wrap;border-top:1px solid #262C35;padding-top:12px;margin-top:12px;font-size:12px;color:#97A1AE}
  #mock-screen .ex-group{border:1px solid #262C35;border-radius:8px;padding:16px;background:#13161B;margin-bottom:12px}
  #mock-screen .ex-group.active{border-color:#56D9EC}
  #mock-screen .ex-group h4{font-family:'Archivo',sans-serif;font-size:14px;margin:6px 0 10px}
  #mock-screen .ex-alt{padding:12px 0;border-top:1px solid #262C35;display:flex;gap:12px;align-items:center}
  #mock-screen .ex-alt .ex-altbody{flex:1;min-width:0}
  #mock-screen .ex-priority-progress{display:flex;justify-content:space-between;gap:12px;align-items:center;margin:16px 0 8px}
  #mock-screen .ex-priority-progress strong{font-size:12px;font-weight:600}
  #mock-screen .ex-package-assets{padding:12px 0 16px;border-bottom:1px solid #262C35;margin-bottom:16px}
  #mock-screen .ex-package-assets h3{font:600 22px/26px 'Barlow Condensed',sans-serif;letter-spacing:.03em;text-transform:uppercase;margin:6px 0 0}
  #mock-screen .ex-tier{border:1px dashed #59647A;border-radius:8px;background:#0C0E11;margin-bottom:12px;overflow:hidden}
  #mock-screen .ex-tier.ex-drop-active{border-color:#56D9EC;border-style:solid;background:#1A1E25}
  #mock-screen .ex-tier-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 12px 8px}
  #mock-screen .ex-tier-label{display:flex;align-items:center;gap:8px;font:600 11px/14px 'Archivo',sans-serif;letter-spacing:.08em;text-transform:uppercase;margin:0}
  #mock-screen .ex-tier-label:before{content:'';width:3px;height:12px;background:#97A1AE;flex:none}
  #mock-screen .ex-tier:first-child .ex-tier-label:before{background:#F0508C}
  #mock-screen .ex-tier-body{padding:0 8px 8px;min-height:52px;display:grid;gap:8px}
  #mock-screen .ex-tier-empty{padding:12px 4px;font-size:12px;line-height:18px;color:#97A1AE;margin:0}
  #mock-screen .ex-priority-card{background:#13161B;border:1px solid #262C35;border-radius:4px;padding:8px}
  #mock-screen .ex-priority-card.ex-dragging{border-color:#56D9EC;opacity:.45}
  #mock-screen .ex-priority-main{display:flex;gap:8px;align-items:center}
  #mock-screen .ex-priority-body{flex:1;min-width:0}
  #mock-screen .ex-priority-body strong{display:block;font-size:13px;line-height:18px;margin:0 0 4px}
  #mock-screen .ex-priority-body .ex-recovery{margin-top:8px;line-height:16px}
  #mock-screen .ex-drag-handle{width:44px;min-width:44px;min-height:44px;padding:0;display:grid;place-items:center;align-self:stretch;background:transparent;border:1px solid #59647A;border-radius:4px;color:#97A1AE;cursor:grab;touch-action:none;user-select:none;-webkit-user-select:none}
  #mock-screen .ex-drag-handle:active{cursor:grabbing;color:#56D9EC;border-color:#56D9EC}
  #mock-screen .ex-drag-handle svg{width:20px;height:20px;pointer-events:none}
  #mock-screen .ex-move-toggle{min-height:44px;min-width:44px;padding:8px;color:#56D9EC;font-size:12px;background:transparent;border:0}
  #mock-screen .ex-move-options{display:flex;flex-wrap:wrap;gap:8px;padding-top:12px;border-top:1px solid #262C35;margin-top:8px}
  #mock-screen .ex-move-options p{width:100%;margin:0}
  #mock-screen .ex-move-options button{flex:1;min-width:52px;min-height:44px;padding:8px;font-size:12px}
  #mock-screen .ex-move-options button[aria-pressed=true]{border-color:#56D9EC;color:#56D9EC}
  #mock-screen .ex-priority-footer{border-top:1px solid #262C35;padding-top:16px;margin-top:20px;display:flex;gap:8px}
  #mock-screen .ex-priority-footer button{flex:1;min-height:44px}
  #mock-screen .ex-drag-preview{position:fixed;z-index:50;pointer-events:none;background:#1A1E25;border:1px solid #56D9EC;border-radius:4px;padding:12px;width:240px;max-width:calc(100vw - 32px);font:600 13px/18px 'Archivo',sans-serif;color:#ECEFF4}
  #mock-screen .ex-drag-preview small{display:block;font-size:12px;font-weight:400;color:#97A1AE;margin-top:4px}
  #mock-screen .ex-priority-help{font-size:11px;color:#97A1AE;line-height:17px;margin:8px 0 16px}
  #mock-screen .ex-priority-live{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
  #mock-screen .ex-drag-handle:focus-visible,#mock-screen .ex-move-toggle:focus-visible,#mock-screen .ex-move-options button:focus-visible{outline:2px solid #56D9EC;outline-offset:2px}
  #mock-screen .ex-label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#97A1AE;font-weight:600}
  #mock-screen .ex-plans{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
  #mock-screen .ex-plans button{min-width:44px;min-height:44px}
  #mock-screen .ex-plans button[aria-pressed=true]{border-color:#56D9EC;color:#56D9EC;background:#1A1E25}
  #mock-screen .ex-meter{height:4px;background:#232833;margin:12px 0 20px}
  #mock-screen .ex-meter span{display:block;height:4px;background:#56D9EC}
  #mock-screen .ex-status{font-size:11px;text-transform:uppercase;letter-spacing:.05em;border:1px solid #59647A;padding:4px 6px;border-radius:2px;display:inline-block}
  #mock-screen .ex-status.accepted{border-color:#22C55E;color:#22C55E}
  #mock-screen .ex-status.declined{border-color:#EF4444;color:#EF4444}
  #mock-screen .ex-status.pending{border-color:#F59E0B;color:#F59E0B}
  #mock-screen .ex-buttons{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
  #mock-screen .ex-buttons>*{flex:1;min-height:44px}
  #mock-screen .ex-like{border-color:#22C55E;color:#22C55E}
  #mock-screen .ex-pass{border-color:#EF4444;color:#EF4444}
  #mock-screen .ex-log{padding-left:20px;color:#97A1AE;font-size:12px;line-height:1.6}
  #mock-screen .ex-intro{margin-bottom:16px}
  #mock-screen .ex-alert{border-left:3px solid #F59E0B;padding:12px;background:#1A1E25;font-size:12px;line-height:1.6;margin:12px 0;color:#ECEFF4}
  #mock-screen .ex-note{border-left:3px solid #59647A;padding:12px;background:#1A1E25;font-size:12px;line-height:1.6;margin:12px 0;color:#97A1AE}
  #mock-screen .ex-recovery{color:#F0508C;font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:600}
  #mock-screen .ex-message{color:#56D9EC;font-size:12px;line-height:1.5;margin:8px 0}
  </style>`;

  function allIn(state) { return ['allin','all-in','push','contend','win-now','all_in'].includes(state.outlook); }
  function selected(state) { return (state.selectedAssets || []).map(a => typeof a === 'string' ? a : a.id); }
  function context(state) {
    const key = allIn(state) ? 'allin' : 'rebuild';
    state.execution = state.execution || {};
    if (!state.execution[key]) state.execution[key] = {decisions:{},cursor:0,plan:0,priorityGroupIndex:0,choices:{},ranks:{},sent:{},events:[],message:''};
    return state.execution[key];
  }
  function dataset(state) {
    const outgoing = selected(state);
    const picks = outgoing.filter(id => id.includes('2027') || id.includes('2028'));
    const specs = allIn(state) ? [
      {id:'picks',name:'Draft capital',pos:'PICKS',ids:picks,teams:['Northside','Harbor','Summit','Metro'],returns:[['Saquon Barkley'],['Christian McCaffrey'],['Josh Jacobs'],['Kyren Williams']]},
      {id:'youth',name:'Quarterback package',pos:'QB / RB',ids:['maye','benson'],teams:['Capital','Parkside','Lakeside','Eastview'],returns:[['Dak Prescott'],['Baker Mayfield'],['Jared Goff'],['Matthew Stafford']]},
      {id:'odunze',name:'Receiver upgrade',pos:'WR',ids:['odunze'],teams:['Northside','Harbor','Summit','Metro'],returns:[['A.J. Brown'],['Davante Adams'],['Tyreek Hill'],['Terry McLaurin']]},
      {id:'kraft',name:'Tight end upgrade',pos:'TE',ids:['kraft'],teams:['Capital','Parkside','Lakeside','Eastview'],returns:[['Travis Kelce'],['Mark Andrews'],['T.J. Hockenson'],['Dallas Goedert']]}
    ] : [
      {id:'evans',name:'Evans sell group',pos:'WR',ids:['evans'],teams:['Northside','Harbor','Summit','Metro'],returns:[[state.ownsFirst ? 'Northside 2027 1st' : 'Your 2027 1st'],['Harbor 2027 1st'],['Summit 2027 1st'],['Metro 2027 1st']]},
      {id:'henry',name:'Henry sell group',pos:'RB',ids:['henry'],teams:['Capital','Parkside','Lakeside','Eastview'],returns:[['Capital 2027 2nd','Capital 2028 2nd'],['Parkside 2027 2nd','Parkside 2028 2nd'],['Lakeside 2027 2nd','Lakeside 2028 2nd'],['Eastview 2027 2nd','Eastview 2028 2nd']]},
      {id:'kittle',name:'Kittle sell group',pos:'TE',ids:['kittle'],teams:['Northside','Harbor','Summit','Metro'],returns:[['Northside 2028 1st'],['Harbor 2028 1st'],['Summit 2028 1st'],['Metro 2028 1st']]},
      {id:'cook',name:'Cook sell group',pos:'RB',ids:['cook'],teams:['Capital','Parkside','Lakeside','Eastview'],returns:[['Luther Burden III','Capital 2029 1st'],['Emeka Egbuka','Parkside 2029 1st'],['Xavier Worthy','Lakeside 2029 1st'],['Jayden Higgins','Eastview 2029 1st']]}
    ];
    return specs.map(s => {
      const ids = s.ids.filter(id => outgoing.includes(id));
      return {...s,ids,give:ids.map(id => assetNames[id] || id),offers:s.returns.map((get,i)=>({id:`${s.id}-${i}`,group:s.id,get,team:s.teams[i],index:i,recovery:!allIn(state)&&!state.ownsFirst&&s.id==='evans'&&i===0}))};
    }).filter(g => g.ids.length);
  }
  const flat = groups => groups.flatMap(g => g.offers.map(o => ({...o,give:g.give,groupName:g.name})));
  const likes = (g,c) => g.offers.filter(o => c.decisions[o.id] === 'like');
  function ready(groups,c) { return groups.length >= 4 && flat(groups).every(o=>c.decisions[o.id]) && groups.every(g=>likes(g,c).length); }
  function plans(groups,c,state) {
    if (!ready(groups,c)) return [];
    const plans = [];
    for (let i=0;i<4;i++) {
      const p={};
      groups.forEach((g,j) => {
        const opts=likes(g,c),recover=opts.find(o=>o.recovery);
        p[g.id]=(recover || opts[(i+j)%opts.length]).id;
      });
      if (!plans.some(q=>JSON.stringify(q)===JSON.stringify(p))) plans.push(p);
    }
    return plans;
  }
  function applyPlan(groups,c,plan) {
    c.choices={...plan}; c.ranks={}; c.priorityGroupIndex=0; c.priorityMoveOffer='';
    groups.forEach(g=>{
      const ordered=likes(g,c).slice().sort((a,b)=>(a.id===plan[g.id]?-1:b.id===plan[g.id]?1:a.index-b.index));
      ordered.forEach((o,i)=>c.ranks[o.id]=i+1);
    });
  }
  function ensurePlan(groups,c,state) {
    const list=plans(groups,c,state);
    if (list.length && groups.some(g=>!likes(g,c).some(o=>o.id===c.choices[g.id]))) { c.plan=Math.min(c.plan||0,list.length-1);applyPlan(groups,c,list[c.plan]); }
    return list;
  }
  function rank(o,c) { return Number(c.ranks[o.id] || o.index+1); }
  function wave(g,c) {
    const options=likes(g,c);
    if(options.some(o=>c.sent[o.id]==='accepted'||c.sent[o.id]==='pending')) return [];
    const available=options.filter(o=>!c.sent[o.id]);
    if(!available.length) return [];
    const n=Math.min(...available.map(o=>rank(o,c)));
    return available.filter(o=>rank(o,c)===n);
  }
  function firstWave(groups,c) { return groups.flatMap(g=>wave(g,c).map(o=>({...o,give:g.give,groupName:g.name}))); }
  function heading(title,sub) { return `<div class="ex-intro"><div class="eyebrow">OVERHAUL LAB · FICTIONAL LEAGUE</div><h2 class="mock-title">${title}</h2><p class="mock-subtitle">${sub}</p></div>`; }
  function exchange(give,get) { return `<div class="ex-trade"><div><span class="ex-label">You send</span>${give.map(n=>`<strong>${esc(n)}</strong>`).join('')}</div><div><span class="ex-label">You receive</span>${get.map(n=>`<strong>${esc(n)}</strong>`).join('')}</div></div>`; }
  function demoNote() { return '<p class="ex-small">Illustrative offers only. League rosters, pick ownership, trade values and outcomes are fictional.</p>'; }
  function missing(groups,c) {
    const total=flat(groups).length,reviewed=flat(groups).filter(o=>c.decisions[o.id]).length;
    const absent=groups.filter(g=>!likes(g,c).length);
    return `<div class="panel"><div class="eyebrow">YOUR LIKES BUILD THE ROADMAP</div><h3 class="mock-title">${groups.length<4?'More sell groups needed':reviewed<total?'Finish your trade chips':'More liked offers needed'}</h3><p class="mock-subtitle">${groups.length<4?`This sample pool supports ${groups.length} of 4 separate sell groups. Return to the pool and use the recommended assets to explore the complete demo.`:reviewed<total?`${reviewed} of ${total} chips reviewed. Like or pass on every chip before we combine the liked trades.`:`You need a liked offer for ${absent.map(g=>g.give.join(' + ')).join(', ')}. We won’t fill the gap with passed offers.`}</p><div class="ex-buttons"><button class="secondary" data-navigate="assets">Edit asset pool</button><button class="primary" data-navigate="review">Review chips</button></div></div>${groups.length>=4?'<div class="ex-note"><div class="eyebrow">REVIEW DOCUMENT SHORTCUT</div><p class="ex-small">Marks all sample chips liked so you can inspect the later-page mocks directly.</p><button class="secondary" data-ex-sample="true">Preview with sample likes</button></div>':''}`;
  }
  function recoveryNote(state,groups,c) {
    if(allIn(state)||state.ownsFirst) return '';
    const own=flat(groups).find(o=>o.recovery);
    if(own && c.sent[own.id]==='accepted') return '<div class="ex-note">Your 2027 1st was recovered in this simulation.</div>';
    const liked=own && c.decisions[own.id]==='like';
    return `<div class="ex-alert"><div class="ex-recovery">Overall execution priority 1</div><strong>Recover your own 2027 1st.</strong><br>Your pick is with Northside. ${liked?'The Northside trade returns that exact pick. We recommend executing it first; you can still send other offers first.':'Review the Northside recovery offer. Moving production will not improve a pick you own until you recover it. You can still choose to send other offers first.'}</div>`;
  }
  function renderReview(state,groups,c) {
    const offers=flat(groups),count=offers.filter(o=>c.decisions[o.id]).length;
    if(!offers.length) return heading('Review the possibilities','Start with a sell pool to see trade ideas.')+missing(groups,c);
    const cursor=Math.min(c.cursor||0,offers.length-1),o=offers[cursor],decision=c.decisions[o.id];
    return heading('Find the moves you like','Each chip is one offer. Only your likes can become part of a roadmap.')+`<div class="row"><span class="ex-small">${count} of ${offers.length} reviewed</span><span class="ex-small"><span class="ex-count">${offers.filter(x=>c.decisions[x.id]==='like').length}</span> liked</span></div><div class="ex-meter"><span style="width:${count/offers.length*100}%"></span></div>
      <article class="panel"><div class="row"><span class="eyebrow">${esc(o.groupName)}</span><span class="ex-count">${cursor+1} / ${offers.length}</span></div><h3>${esc(o.team)}</h3>${o.recovery?'<div class="ex-recovery">Overall execution priority 1 · recover your own 2027 1st</div>':''}${exchange(o.give,o.get)}<div class="ex-note">${allIn(state)?'Illustrates turning future value into a starting-lineup upgrade.':'Illustrates moving production into draft capital and younger assets.'} No trade valuation is calculated in this mock.</div><div class="ex-buttons"><button class="secondary ex-pass" data-ex-decision="pass" data-offer="${o.id}">${decision==='pass'?'Passed':'Pass'}</button><button class="secondary ex-like" data-ex-decision="like" data-offer="${o.id}">${decision==='like'?'Liked':'Like'}</button></div></article>
      <div class="ex-buttons"><button class="ghost" data-ex-cursor="${Math.max(0,cursor-1)}" ${cursor===0?'disabled':''}>Previous chip</button><button class="ghost" data-ex-cursor="${Math.min(offers.length-1,cursor+1)}" ${cursor===offers.length-1?'disabled':''}>Next chip</button></div>
      ${count===offers.length?(ready(groups,c)?'<div class="ex-note">Review complete. Your liked offers cover all 4 sell groups.</div><button class="primary" data-navigate="roadmaps">Build my roadmaps</button>':missing(groups,c)):''}
      <div class="divider"></div><button class="secondary" data-ex-sample="true">Use sample likes for all ${offers.length} chips</button><p class="ex-small">Demo shortcut: marks every sample chip liked so you can explore four roadmaps and fallback priorities.</p>${demoNote()}`;
  }
  function renderRoadmaps(state,groups,c) {
    const list=ensurePlan(groups,c,state);
    let out=heading('Your overhaul roadmaps','A roadmap combines 4 sell groups. Each group has its own outgoing assets and liked alternatives.');
    if(!list.length) return out+missing(groups,c);
    const locked=Object.keys(c.sent).length>0;
    out+=recoveryNote(state,groups,c)+`<div class="ex-plans" aria-label="Alternative roadmaps">${list.map((p,i)=>`<button class="secondary" data-ex-plan="${i}" aria-pressed="${c.plan===i}" ${locked?'disabled':''}>${i+1}</button>`).join('')}</div><div class="row"><span class="eyebrow">ROADMAP ${Number(c.plan||0)+1} OF ${list.length}</span><span class="pill">4 distinct sell groups</span></div><p class="ex-small">${list.length<4?'Your likes currently support fewer than four distinct combinations.':'Choose a numbered roadmap to compare alternatives.'} ${locked?'Simulation started: this roadmap is locked until you reset.':''}</p>`;
    groups.forEach((g,i)=>{
      const chosen=g.offers.find(o=>o.id===c.choices[g.id])||likes(g,c)[0];
      out+=`<article class="ex-group"><div class="row"><span class="eyebrow">SELL GROUP ${i+1} · ${g.pos}</span><button class="ghost" data-ex-swap="${g.id}" ${locked||likes(g,c).length<2?'disabled':''}>Swap offer</button></div><h4>${esc(g.give.join(' + '))}</h4><p class="ex-small">To ${esc(chosen.team)} · receive</p><strong>${esc(chosen.get.join(' + '))}</strong>${chosen.recovery?'<p class="ex-recovery">Overall execution priority 1 · recover your own first</p>':''}<div class="ex-statline"><span>${likes(g,c).length} liked alternatives</span><span>No outgoing overlap with other groups</span></div></article>`;
    });
    return out+`<div class="ex-note">All 4 selected offers use separate outgoing and incoming assets. Equal-priority alternatives within one group can intentionally compete for that group’s assets.</div><button class="primary" data-ex-priority-start="true">Set offer priorities</button>${demoNote()}`;
  }
  function renderPriorities(state,groups,c) {
    const list=ensurePlan(groups,c,state);
    let out=heading('Set offer priorities','One package at a time. Drag its liked offers into priority tiers, just like your tiers board.');
    if(!list.length) return out+missing(groups,c);
    const locked=Object.keys(c.sent).length>0;
    const i=Math.max(0,Math.min(Number(c.priorityGroupIndex)||0,groups.length-1)),g=groups[i];
    c.priorityGroupIndex=i;
    const opts=likes(g,c).slice().sort((a,b)=>rank(a,c)-rank(b,c)||a.index-b.index),minimum=Math.min(...opts.map(o=>rank(o,c))),tied=opts.filter(o=>rank(o,c)===minimum).length;
    out+=`<div class="ex-priority-progress" data-ex-package-progress><strong>Package <span class="ex-count">${i+1}</span> of <span class="ex-count">${groups.length}</span></strong><span class="ex-small">${opts.length} liked offers</span></div><div class="ex-meter"><span style="width:${(i+1)/groups.length*100}%"></span></div><div class="ex-package-assets"><span class="ex-label">This package sends</span><h3 tabindex="-1" data-ex-priority-heading>${esc(g.give.join(' + '))}</h3></div>`;
    if(g.offers.some(o=>o.recovery)) out+=recoveryNote(state,groups,c);
    out+=`<p class="ex-small">Same tier = send together. Later tiers are backups you can send after responses, with time to negotiate.</p><p class="ex-priority-help" id="ex-priority-help">${locked?'Priorities are locked while this simulation is in progress. Reset the simulation to edit.':'Drag using the handle, or tap Move to choose a tier. Keyboard: focus a handle and use the up/down arrow keys.'}</p><div class="ex-priority-live" aria-live="polite" aria-atomic="true" data-ex-drag-status></div><div data-ex-priority-board="${g.id}">`;
    [1,2,3,4].forEach(n=>{
      const tierOffers=opts.filter(o=>rank(o,c)===n);
      out+=`<section class="ex-tier" data-ex-priority-tier="${n}" role="group" aria-label="Priority ${n}"><div class="ex-tier-head"><h4 class="ex-tier-label">Priority <span class="ex-count">${n}</span></h4><span class="ex-small">${n===minimum?'Send first':'Backup'} · <span class="ex-count">${tierOffers.length}</span></span></div><div class="ex-tier-body">`;
      out+=tierOffers.map(o=>`<article class="ex-priority-card" data-ex-priority-offer="${o.id}"><div class="ex-priority-main"><button type="button" class="ex-drag-handle" data-ex-drag-offer="${o.id}" aria-label="Move ${esc(o.team)} offer, priority ${n}" aria-describedby="ex-priority-help" ${locked?'disabled':''}><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M6 4h2m4 0h2M6 10h2m4 0h2M6 16h2m4 0h2"/></svg></button><div class="ex-priority-body"><strong>${esc(o.team)}</strong><div class="ex-small">Get ${esc(o.get.join(' + '))}</div>${o.recovery?'<div class="ex-recovery">Overall priority 1 · recover your first</div>':''}</div><button type="button" class="ex-move-toggle" data-ex-move-picker="${o.id}" aria-label="Choose a priority for ${esc(o.team)} offer" aria-expanded="${c.priorityMoveOffer===o.id}" ${locked?'disabled':''}>Move</button></div>${c.priorityMoveOffer===o.id?`<div class="ex-move-options"><p class="ex-small">Move ${esc(o.team)} to:</p>${[1,2,3,4].map(to=>`<button type="button" class="secondary" data-ex-move-rank="${to}" data-offer="${o.id}" aria-label="Move ${esc(o.team)} to priority ${to}" aria-pressed="${n===to}" ${locked?'disabled':''}>P<span class="ex-count">${to}</span></button>`).join('')}</div>`:''}</article>`).join('');
      if(!tierOffers.length)out+=`<p class="ex-tier-empty">${locked?'No offers at this priority.':'Drop an offer here'}</p>`;
      out+='</div></section>';
    });
    out+='</div>';
    if(tied>1) out+=`<div class="ex-alert"><strong>${tied} offers will send together.</strong> First come, first served: these offers use the same assets, so only one can be accepted.</div>`;
    return out+`<div class="ex-priority-footer"><button type="button" class="secondary" data-ex-package-back="true">Back</button><button type="button" class="primary" data-ex-package-next="true">${i===groups.length-1?'Review send summary':'Continue'}</button></div><p class="ex-small">${i===groups.length-1?'Next: review the first offers across all packages.':`Next: ${esc(groups[i+1].give.join(' + '))}`}</p>${demoNote()}`;
  }
  function renderSummary(state,groups,c) {
    const list=ensurePlan(groups,c,state);
    let out=heading('Ready to put it in motion','Review exactly which offers would go out now. This is a local simulation.');
    if(!list.length) return out+missing(groups,c);
    const offers=firstWave(groups,c),activeGroups=new Set(offers.map(o=>o.group)).size,ties=groups.filter(g=>wave(g,c).length>1),started=Object.keys(c.sent).length>0;
    out+=`<div class="panel"><div class="eyebrow">CURRENT SEND BATCH</div><h3 class="mock-title"><span class="ex-count">${offers.length}</span> ${offers.length===1?'offer':'offers'} · <span class="ex-count">${activeGroups}</span> ${activeGroups===1?'sell group':'sell groups'}</h3><p class="mock-subtitle">At most one accepted trade per sell group. ${activeGroups} ${activeGroups===1?'trade in this batch can succeed':'trades in this batch can all succeed'} without reusing assets.</p></div>`+recoveryNote(state,groups,c);
    if(ties.length) out+=`<div class="ex-alert"><strong>First come, first served.</strong> ${ties.map(g=>`${wave(g,c).length} offers for ${esc(g.give.join(' + '))}`).join('; ')} are being sent at the same time. Those offers reuse the same outgoing assets. Only the first accepted offer can complete; its alternatives must become unavailable.</div>`;
    offers.forEach(o=>{out+=`<article class="ex-group"><div class="row"><span class="eyebrow">${esc(o.groupName)}</span><span class="ex-count">PRIORITY ${rank(o,c)}</span></div><h4>Offer to ${esc(o.team)}</h4>${o.recovery?'<div class="ex-recovery">Overall execution priority 1 · recover your own 2027 1st</div>':''}${exchange(o.give,o.get)}</article>`;});
    if(!offers.length) out+=`<div class="ex-note">${started?'Your current offers are pending or complete. Open the tracker to simulate responses and review the next available offers.':'No eligible offers in this batch.'}</div>`;
    out+=`<div class="ex-note">After a decline, return to this roadmap to review the next priority. This mock requires a manual send for the next batch. Provider cancellation and response syncing remain design decisions.</div><div class="ex-buttons">${offers.length?'<button class="primary" data-ex-send="all">Simulate send all</button>':''}<button class="secondary" data-navigate="tracking">Open saved roadmap</button></div>${demoNote()}`;
    return out;
  }
  function renderTracking(state,groups,c) {
    const list=ensurePlan(groups,c,state);
    let out=heading('Your roadmap, in progress','Come back as offers receive responses. Review alternatives for any sell group that is still open.');
    if(!list.length) return out+missing(groups,c);
    const accepted=groups.filter(g=>g.offers.some(o=>c.sent[o.id]==='accepted')).length,pending=Object.values(c.sent).filter(s=>s==='pending').length;
    out+=`<div class="panel"><div class="row"><span class="eyebrow">LOCAL SIMULATION</span><span class="ex-count">${accepted} / 4 complete</span></div><div class="ex-meter"><span style="width:${accepted/4*100}%"></span></div><p class="ex-small">${pending} offers awaiting a simulated response. Changes stay in this review document on this browser.</p></div>`+recoveryNote(state,groups,c);
    groups.forEach((g,i)=>{
      const acceptedOffer=g.offers.find(o=>c.sent[o.id]==='accepted'),pendingOffers=g.offers.filter(o=>c.sent[o.id]==='pending'),next=wave(g,c),history=likes(g,c).filter(o=>c.sent[o.id] && c.sent[o.id]!=='unavailable');
      out+=`<article class="ex-group"><div class="row"><span class="eyebrow">SELL GROUP ${i+1}</span><span class="ex-status ${acceptedOffer?'accepted':pendingOffers.length?'pending':''}">${acceptedOffer?'Complete':pendingOffers.length?'Awaiting responses':'Ready'}</span></div><h4>${esc(g.give.join(' + '))}</h4>`;
      if(acceptedOffer) out+=`<div class="ex-note">Accepted by ${esc(acceptedOffer.team)}. Received ${esc(acceptedOffer.get.join(' + '))}. These outgoing assets are locked; every overlapping alternative is unavailable in this simulation.</div>`;
      history.forEach(o=>{
        out+=`<div class="ex-alt"><div class="ex-altbody"><strong>${esc(o.team)}</strong><div class="ex-small">${esc(o.get.join(' + '))}</div><span class="ex-status ${c.sent[o.id]}">${esc(c.sent[o.id])}</span>${c.sent[o.id]==='pending'?`<div class="ex-buttons"><button class="secondary" data-ex-response="accepted" data-offer="${o.id}">Accept</button><button class="secondary" data-ex-response="declined" data-offer="${o.id}">Decline</button></div>`:''}</div></div>`;
      });
      if(next.length) out+=`<div class="ex-note"><strong>Next: priority ${rank(next[0],c)}</strong><br>${next.map(o=>`${esc(o.team)} → ${esc(o.get.join(' + '))}`).join('<br>')}${next.length>1?'<br>Equal priority: first come, first served.':''}</div><button class="secondary" data-ex-send="${g.id}">Simulate ${history.length?'next':'first'} ${next.length===1?'offer':`${next.length} offers`}</button>`;
      if(!next.length&&!pendingOffers.length&&!acceptedOffer) out+='<div class="ex-note">All liked alternatives were declined. More ideas are needed for these assets.</div>';
      if(pendingOffers.length) out+=`<p class="ex-small">${likes(g,c).filter(o=>!c.sent[o.id]).length} alternatives waiting. Resolve the active offers before sending the next rank.</p>`;
      out+='</article>';
    });
    if(c.events.length) out+=`<details><summary>Simulation activity (${c.events.length})</summary><ol class="ex-log">${c.events.slice().reverse().map(e=>`<li>${esc(e)}</li>`).join('')}</ol></details>`;
    return out+`<div class="ex-buttons"><button class="secondary" data-navigate="summary">Review next batch</button><button class="ghost" data-ex-reset="true">Reset simulation</button></div>${demoNote()}`;
  }
  function render(page,state) {
    const c=context(state),groups=dataset(state);
    const fn={review:renderReview,roadmaps:renderRoadmaps,priorities:renderPriorities,summary:renderSummary,tracking:renderTracking}[page];
    return fn?style+(c.message?`<div class="ex-message" role="status">${esc(c.message)}</div>`:'')+fn(state,groups,c):'';
  }
  function movePriority(offerId,nextRank,c,groups) {
    if(Object.keys(c.sent).length)return false;
    const g=groups.find(g=>likes(g,c).some(o=>o.id===offerId));
    if(!g||!Number.isInteger(nextRank)||nextRank<1||nextRank>4)return false;
    const o=g.offers.find(o=>o.id===offerId);
    c.ranks[o.id]=nextRank;c.priorityMoveOffer='';
    const sorted=likes(g,c).slice().sort((a,b)=>rank(a,c)-rank(b,c)||a.index-b.index);
    c.choices[g.id]=sorted[0].id;
    c.message=`${o.team} moved to priority ${nextRank}. Offers in the same tier send together.`;
    return true;
  }
  function bindPriorityBoard(root,state,update) {
    const doc=root.ownerDocument,view=doc.defaultView;
    const focusOffer=id=>root.querySelector(`[data-ex-drag-offer="${id}"]`)?.focus({preventScroll:true});
    root.querySelectorAll('[data-ex-move-picker]').forEach(el=>el.addEventListener('click',()=>{
      const c=context(state);if(Object.keys(c.sent).length)return;
      c.priorityMoveOffer=c.priorityMoveOffer===el.dataset.exMovePicker?'':el.dataset.exMovePicker;c.message='';
      update();
      if(c.priorityMoveOffer)root.querySelector(`[data-offer="${c.priorityMoveOffer}"][data-ex-move-rank]`)?.focus({preventScroll:true});
      else focusOffer(el.dataset.exMovePicker);
    }));
    root.querySelectorAll('[data-ex-move-rank]').forEach(el=>el.addEventListener('click',()=>{
      const id=el.dataset.offer;
      if(movePriority(id,Number(el.dataset.exMoveRank),context(state),dataset(state))){update();focusOffer(id);}
    }));
    root.querySelectorAll('[data-ex-drag-offer]').forEach(handle=>{
      handle.addEventListener('keydown',event=>{
        if(event.key!=='ArrowUp'&&event.key!=='ArrowDown')return;
        event.preventDefault();
        const c=context(state),groups=dataset(state),id=handle.dataset.exDragOffer;
        const offer=flat(groups).find(o=>o.id===id);if(!offer)return;
        const nextRank=Math.max(1,Math.min(4,rank(offer,c)+(event.key==='ArrowUp'?-1:1)));
        if(movePriority(id,nextRank,c,groups)){update();focusOffer(id);}
      });
      handle.addEventListener('pointerdown',event=>{
        if(handle.disabled||event.isPrimary===false||(event.pointerType==='mouse'&&event.button!==0)||Object.keys(context(state).sent).length)return;
        event.preventDefault();
        const id=handle.dataset.exDragOffer,offer=flat(dataset(state)).find(o=>o.id===id);
        if(!offer)return;
        const card=handle.closest('[data-ex-priority-offer]'),ghost=doc.createElement('div'),live=root.querySelector('[data-ex-drag-status]');
        const pointerId=event.pointerId;
        let x=event.clientX,y=event.clientY,target=null,frame=0,finished=false;
        ghost.className='ex-drag-preview';ghost.setAttribute('aria-hidden','true');
        ghost.innerHTML=`${esc(offer.team)}<small>Get ${esc(offer.get.join(' + '))}</small>`;
        root.appendChild(ghost);card.classList.add('ex-dragging');
        const position=()=>{
          ghost.style.left=`${Math.max(8,Math.min(x+16,view.innerWidth-ghost.offsetWidth-8))}px`;
          ghost.style.top=`${Math.max(8,Math.min(y+16,view.innerHeight-ghost.offsetHeight-8))}px`;
          const hit=doc.elementFromPoint(x,y)?.closest('[data-ex-priority-tier]');
          const next=hit&&root.contains(hit)?hit:null;
          if(next!==target){
            target?.classList.remove('ex-drop-active');target=next;target?.classList.add('ex-drop-active');
            if(live)live.textContent=target?`Drop ${offer.team} into priority ${target.dataset.exPriorityTier}.`:'Move over a priority tier to drop.';
          }
        };
        const cleanup=()=>{
          if(finished)return;finished=true;
          view.cancelAnimationFrame(frame);ghost.remove();card.classList.remove('ex-dragging');target?.classList.remove('ex-drop-active');
          doc.removeEventListener('pointermove',onMove);doc.removeEventListener('pointerup',onUp);doc.removeEventListener('pointercancel',onCancel);doc.removeEventListener('keydown',onKey);
          handle.removeEventListener('lostpointercapture',onCancel);
          if(handle.hasPointerCapture?.(pointerId))handle.releasePointerCapture(pointerId);
        };
        const onMove=e=>{if(e.pointerId!==pointerId)return;e.preventDefault();x=e.clientX;y=e.clientY;position();};
        const onUp=e=>{
          if(e.pointerId!==pointerId)return;
          x=e.clientX;y=e.clientY;position();const nextRank=target?Number(target.dataset.exPriorityTier):null;cleanup();
          if(nextRank&&movePriority(id,nextRank,context(state),dataset(state))){update();focusOffer(id);}
          else if(live)live.textContent='Move cancelled. Offer priority is unchanged.';
        };
        const onCancel=e=>{if(e.pointerId!=null&&e.pointerId!==pointerId)return;cleanup();if(live)live.textContent='Move cancelled. Offer priority is unchanged.';};
        const onKey=e=>{if(e.key==='Escape'){e.preventDefault();onCancel(e);}};
        const scroll=()=>{
          if(finished)return;
          if(!handle.isConnected){cleanup();return;}
          const step=y<64?-12:y>view.innerHeight-64?12:0;
          if(step){view.scrollBy(0,step);position();}
          frame=view.requestAnimationFrame(scroll);
        };
        doc.addEventListener('pointermove',onMove,{passive:false});doc.addEventListener('pointerup',onUp);doc.addEventListener('pointercancel',onCancel);doc.addEventListener('keydown',onKey);
        handle.addEventListener('lostpointercapture',onCancel);
        handle.setPointerCapture?.(pointerId);position();frame=view.requestAnimationFrame(scroll);
        if(live)live.textContent=`Moving ${offer.team}. Drop into a priority tier, or press Escape to cancel.`;
      });
    });
  }
  function bind(root,state,update) {
    const listen=(selector,event,fn)=>root.querySelectorAll(selector).forEach(el=>el.addEventListener(event,()=>{fn(el,context(state),dataset(state));update();}));
    listen('[data-ex-decision]','click',(el,c,groups)=>{
      if(Object.keys(c.sent).length) {c.message='Reset the simulation before changing the reviewed offer pool.';return;}
      c.decisions[el.dataset.offer]=el.dataset.exDecision;c.choices={};c.ranks={};c.message='';
      const offers=flat(groups),next=offers.findIndex((o,i)=>i>c.cursor&&!c.decisions[o.id]);
      if(next>=0)c.cursor=next;
      else { const unresolved=offers.findIndex(o=>!c.decisions[o.id]);if(unresolved>=0)c.cursor=unresolved; }
    });
    listen('[data-ex-cursor]','click',(el,c)=>{c.cursor=Number(el.dataset.exCursor);c.message='';});
    listen('[data-ex-sample]','click',(el,c,groups)=>{
      if(Object.keys(c.sent).length){c.message='Reset the simulation before changing the reviewed offer pool.';return;}
      flat(groups).forEach(o=>c.decisions[o.id]='like');c.choices={};c.ranks={};c.message='Demo shortcut applied: every sample chip is now liked. You can still pass on any chip.';
    });
    listen('[data-ex-plan]','click',(el,c,groups)=>{if(Object.keys(c.sent).length)return;const list=plans(groups,c,state);c.plan=Number(el.dataset.exPlan);if(list[c.plan])applyPlan(groups,c,list[c.plan]);c.message='';});
    listen('[data-ex-swap]','click',(el,c,groups)=>{
      if(Object.keys(c.sent).length)return;
      const g=groups.find(g=>g.id===el.dataset.exSwap),opts=likes(g,c),i=opts.findIndex(o=>o.id===c.choices[g.id]),next=opts[(i+1)%opts.length];
      c.choices[g.id]=next.id;const ordered=[next,...opts.filter(o=>o.id!==next.id)];ordered.forEach((o,j)=>c.ranks[o.id]=j+1);c.message=`Swapped the ${g.give.join(' + ')} group to ${next.team}. Its alternatives remain liked.`;
    });
    listen('[data-ex-priority-start]','click',(el,c)=>{c.priorityGroupIndex=0;c.priorityMoveOffer='';c.message='';state.page='priorities';});
    root.querySelectorAll('[data-ex-package-next],[data-ex-package-back]').forEach(el=>el.addEventListener('click',()=>{
      const c=context(state),groups=dataset(state),i=Number(c.priorityGroupIndex)||0;
      c.message='';c.priorityMoveOffer='';
      if(el.hasAttribute('data-ex-package-back')){
        if(i>0)c.priorityGroupIndex=i-1;else state.page='roadmaps';
      }else if(i<groups.length-1)c.priorityGroupIndex=i+1;
      else state.page='summary';
      update();
      const title=root.querySelector('[data-ex-priority-heading]');
      if(title){title.focus({preventScroll:true});root.scrollIntoView({block:'start',behavior:'auto'});}
    }));
    bindPriorityBoard(root,state,update);
    listen('[data-ex-send]','click',(el,c,groups)=>{
      ensurePlan(groups,c,state);if(!ready(groups,c))return;
      const scope=el.dataset.exSend==='all'?groups:groups.filter(g=>g.id===el.dataset.exSend),offers=firstWave(scope,c);
      offers.forEach(o=>{c.sent[o.id]='pending';c.events.push(`Simulated offer to ${o.team}: ${o.give.join(' + ')} for ${o.get.join(' + ')}.`);});
      c.message=offers.length?`${offers.length} offers marked pending locally. No real offers were sent.`:'No new offers are available to send.';
      if(offers.length)state.page='tracking';
    });
    listen('[data-ex-response]','click',(el,c,groups)=>{
      const g=groups.find(g=>g.offers.some(o=>o.id===el.dataset.offer)),o=g.offers.find(o=>o.id===el.dataset.offer);
      if(c.sent[o.id]!=='pending')return;
      c.sent[o.id]=el.dataset.exResponse;
      c.events.push(`${o.team} ${el.dataset.exResponse} the simulated offer for ${g.give.join(' + ')}.`);
      if(el.dataset.exResponse==='accepted') {
        g.offers.filter(x=>x.id!==o.id).forEach(x=>{c.sent[x.id]='unavailable';});
        c.message='Accepted in the simulation. Overlapping alternatives are unavailable and this sell group is complete.';
      } else c.message='Declined in the simulation. Review the next priority once all active offers in this group are resolved.';
    });
    listen('[data-ex-reset]','click',(el,c)=>{c.sent={};c.events=[];c.message='Simulation reset. Your likes and priorities are preserved.';});
  }
  window.OverhaulExecution={render,bind,reset(state){delete state.execution;},inspect(state){const c=context(state),groups=dataset(state);return {groups,plans:plans(groups,c,state),wave:firstWave(groups,c),ready:ready(groups,c),context:c};}};
})();
