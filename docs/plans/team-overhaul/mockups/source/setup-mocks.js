(function () {
  'use strict';
  const roster = [
    { id: 'allen', name: 'Josh Allen', position: 'QB', rebuild: 'A possible long-term anchor', allin: 'Keep your starting production' },
    { id: 'maye', name: 'Drake Maye', position: 'QB', rebuild: 'A possible foundation piece', allin: 'Explore moving depth for immediate help' },
    { id: 'henry', name: 'Derrick Henry', position: 'RB', rebuild: 'Turn current production into future assets', allin: 'Keep your starting production' },
    { id: 'cook', name: 'James Cook', position: 'RB', rebuild: 'Explore a productive-player return', allin: 'Keep your starting production' },
    { id: 'benson', name: 'Trey Benson', position: 'RB', rebuild: 'A possible development piece', allin: 'Explore moving future upside for help now' },
    { id: 'jefferson', name: 'Justin Jefferson', position: 'WR', rebuild: 'A possible long-term anchor', allin: 'Keep your starting production' },
    { id: 'evans', name: 'Mike Evans', position: 'WR', rebuild: 'Turn current production into future assets', allin: 'Keep your starting production' },
    { id: 'odunze', name: 'Rome Odunze', position: 'WR', rebuild: 'A possible foundation piece', allin: 'Explore moving future upside for help now' },
    { id: 'kittle', name: 'George Kittle', position: 'TE', rebuild: 'Turn current production into future assets', allin: 'Keep your starting production' },
    { id: 'kraft', name: 'Tucker Kraft', position: 'TE', rebuild: 'A possible development piece', allin: 'Explore moving depth for immediate help' },
    { id: 'own-2027-1', name: '2027 1st', position: 'PICK', origin: 'Your original pick' },
    { id: 'acquired-2027-1', name: '2027 1st', position: 'PICK', origin: 'Acquired · East End' },
    { id: '2027-2', name: '2027 2nd', position: 'PICK', origin: 'Your original pick' },
    { id: '2028-1', name: '2028 1st', position: 'PICK', origin: 'Your original pick' },
    { id: '2028-3', name: '2028 3rd', position: 'PICK', origin: 'Your original pick' }
  ];
  const rebuildIds = ['henry', 'cook', 'evans', 'kittle'];
  const allinIds = ['maye', 'benson', 'odunze', 'kraft', 'own-2027-1', 'acquired-2027-1', '2027-2', '2028-1', '2028-3'];
  const styles = `<style>
    #mock-screen [data-use-targets]{min-height:44px}
    #mock-screen .setup-choice{display:block;width:100%;text-align:left;background:#13161B;border:1px solid #59647A;border-radius:8px;color:#ECEFF4;padding:20px 16px;min-height:116px;cursor:pointer}
    #mock-screen .setup-choice+.setup-choice{margin-top:12px}
    #mock-screen .setup-choice[aria-pressed="true"]{border-color:#56D9EC;background:#1A1E25}
    #mock-screen .setup-choice-head{display:flex;justify-content:space-between;gap:12px;align-items:center;font:600 24px/28px 'Barlow Condensed',sans-serif;letter-spacing:.03em;text-transform:uppercase}
    #mock-screen .setup-choice p{font:400 13px/19px 'Archivo',sans-serif;color:#97A1AE;margin:10px 0 0}
    #mock-screen .setup-choice small{display:block;margin-top:12px;color:#97A1AE;font:500 11px/16px 'IBM Plex Mono',monospace}
    #mock-screen .setup-tick{display:inline-grid;flex-shrink:0;width:22px;height:22px;place-items:center;border:1px solid #59647A;border-radius:2px}
    #mock-screen [aria-pressed="true"] .setup-tick{background:#56D9EC;border-color:#56D9EC;color:#071013}
    #mock-screen .setup-tick svg{display:block;width:16px;height:16px}
    #mock-screen .setup-section{margin:24px 0 12px;display:flex;align-items:center;gap:8px;font:600 11px/16px 'Archivo',sans-serif;letter-spacing:.08em;text-transform:uppercase}
    #mock-screen .setup-section::before{content:'';width:3px;height:14px;background:#56D9EC}
    #mock-screen .setup-section .mono{margin-left:auto;color:#97A1AE}
    #mock-screen .setup-roster-row{width:100%;min-height:72px;display:flex;align-items:center;text-align:left;gap:12px;padding:12px;background:#13161B;border:1px solid #59647A;border-radius:4px;color:#ECEFF4;margin-bottom:8px;cursor:pointer}
    #mock-screen .setup-roster-row[aria-pressed="true"]{border-color:#56D9EC;background:#1A1E25}
    #mock-screen .setup-asset-copy{min-width:0;flex:1}
    #mock-screen .setup-asset-name{display:block;font:600 14px/20px 'Archivo',sans-serif}
    #mock-screen .setup-asset-reason{display:block;font:400 12px/18px 'Archivo',sans-serif;color:#97A1AE;margin-top:3px}
    #mock-screen .setup-recommended{display:block;color:#F0508C;font:600 11px/16px 'Archivo',sans-serif;letter-spacing:.04em;margin-top:3px}
    #mock-screen .setup-position{padding:3px 5px;border:1px solid currentColor;border-radius:2px;font:600 11px/14px 'Archivo',sans-serif;min-width:30px;text-align:center;flex-shrink:0}
    #mock-screen .setup-position-QB{color:#F97316}#mock-screen .setup-position-RB{color:#22C55E}#mock-screen .setup-position-WR{color:#3B82F6}#mock-screen .setup-position-TE{color:#A855F7}#mock-screen .setup-position-PICK{color:#97A1AE}
    #mock-screen .setup-footer{display:grid;gap:8px;margin-top:24px;padding-top:16px;border-top:1px solid #262C35}
    #mock-screen .setup-footer button{width:100%;min-height:44px}
    #mock-screen .setup-pool-receipt{border:1px solid #262C35;border-radius:8px;background:#1A1E25;padding:16px;margin-top:16px}
    #mock-screen .setup-pool-receipt strong{font:600 22px/26px 'IBM Plex Mono',monospace}
    #mock-screen .setup-pool-receipt p{margin:8px 0 0;color:#97A1AE;font-size:13px;line-height:19px}
    #mock-screen .setup-warning{border:1px solid #F59E0B;border-left-width:3px;border-radius:4px;background:#1A1E25;padding:12px;margin:16px 0}
    #mock-screen .setup-warning strong{font-size:14px;line-height:20px;color:#ECEFF4}
    #mock-screen .setup-warning p{font-size:13px;line-height:19px;color:#97A1AE;margin:8px 0 0}
    #mock-screen .setup-warning .setup-warning-label{font:600 11px/16px 'Archivo',sans-serif;color:#F59E0B;letter-spacing:.06em;display:block;margin-bottom:6px}
    #mock-screen .setup-honesty{font:400 12px/18px 'Archivo',sans-serif;color:#97A1AE;margin:12px 0}
    #mock-screen .setup-inline-actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
    #mock-screen .setup-inline-actions button{min-height:44px;flex:1;font-size:12px}
    #mock-screen .setup-target-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
    #mock-screen .setup-target{padding:12px;border:1px solid #59647A;border-radius:4px;background:#13161B;color:#ECEFF4;min-height:84px;text-align:left;cursor:pointer}
    #mock-screen .setup-target[aria-pressed="true"]{border-color:#56D9EC;background:#1A1E25}
    #mock-screen .setup-target-head{display:flex;align-items:center;justify-content:space-between;gap:8px;font:600 16px/20px 'Archivo',sans-serif}
    #mock-screen .setup-target small{display:block;margin-top:10px;font:400 12px/18px 'Archivo',sans-serif;color:#97A1AE}
    #mock-screen .setup-target .setup-tick{width:18px;height:18px}
    #mock-screen .setup-priority-note{border-top:1px solid #262C35;margin-top:16px;padding-top:16px;font:400 13px/19px 'Archivo',sans-serif;color:#97A1AE}
    #mock-screen .setup-step-list{list-style:none;margin:16px 0 0;padding:0;display:grid;gap:12px}
    #mock-screen .setup-step-list li{display:flex;gap:12px;align-items:baseline;font-size:13px;color:#97A1AE;line-height:19px}
    #mock-screen .setup-step-list .mono{color:#ECEFF4;min-width:24px}
    #mock-screen .setup-own-note{font-size:13px;line-height:19px;border-left:3px solid #59647A;padding-left:12px;margin:16px 0;color:#97A1AE}
    #mock-screen .setup-zero{font-size:13px;color:#F59E0B;line-height:19px}
    #mock-screen .setup-choice:focus-visible,#mock-screen .setup-roster-row:focus-visible,#mock-screen .setup-target:focus-visible{outline:2px solid #56D9EC;outline-offset:2px}
  </style>`;
  const check = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10l4 4 8-8" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="square"/></svg>';
  function tick(selected) { return '<span class="setup-tick" aria-hidden="true">' + (selected ? check : '') + '</span>'; }
  function defaults(state) {
    if (!['rebuild', 'allin'].includes(state.outlook)) state.outlook = 'rebuild';
    if (typeof state.ownsFirst !== 'boolean') state.ownsFirst = false;
    if (!Array.isArray(state.selectedAssets)) state.selectedAssets = recommended(state);
    if (!Array.isArray(state.positions)) state.positions = [];
  }
  function recommended(state) {
    return (state.outlook === 'rebuild' ? rebuildIds : allinIds).filter(id => id !== 'own-2027-1' || state.ownsFirst);
  }
  function isAllIn(state) { return state.outlook === 'allin'; }
  function ownershipNotice(state) {
    if (isAllIn(state)) return '';
    if (state.ownsFirst) return '<div class="setup-own-note"><strong>You own your 2027 1st.</strong><br>Moving productive players can improve your own draft position if your league’s draft-order rules reward lower roster production or results. Your league rules still apply; a pick position is not guaranteed.</div>';
    return '<div class="setup-warning"><span class="setup-warning-label">YOUR 2027 1ST IS ELSEWHERE</span><strong>A reset could improve someone else’s pick.</strong><p>Northside holds your original 2027 1st. Reducing production would not improve a pick you currently own.</p><p><strong>Priority 1: Recover your first.</strong> Your roadmap will highlight an offer for that exact pick. You choose when to send it and can send other offers first.</p></div>';
  }
  function outlook(state) {
    return `<div class="eyebrow">TEAM OVERHAUL · 01</div><h2 class="mock-title">WHAT ARE YOU TRYING TO DO?</h2><p class="mock-subtitle">Choose a direction for a major roster reset.</p>
      <button type="button" class="setup-choice" data-outlook="allin" aria-pressed="${isAllIn(state)}"><span class="setup-choice-head">Push all in ${tick(isAllIn(state))}</span><p>Turn picks and future upside into a stronger team for this season.</p><small>Shop future assets · Add current production</small></button>
      <button type="button" class="setup-choice" data-outlook="rebuild" aria-pressed="${!isAllIn(state)}"><span class="setup-choice-head">Blow it up ${tick(!isAllIn(state))}</span><p>Move production for younger building blocks and draft capital.</p><small>Shop productive players · Build future value</small></button>
      <div class="panel" style="margin-top:24px"><div class="eyebrow">HOW YOUR PLAN COMES TOGETHER</div><ol class="setup-step-list"><li><span class="mono">01</span>Choose the assets you’re open to moving.</li><li><span class="mono">02</span>Like or pass on trade ideas.</li><li><span class="mono">03</span>Choose a plan with 4–5 independent trades.</li><li><span class="mono">04</span>Rank alternatives and track your offers.</li></ol></div>
      <div class="setup-footer"><button type="button" class="primary" data-navigate="assets">Choose my trade pool</button></div>`;
  }
  function assetRow(asset, state) {
    const selected = state.selectedAssets.includes(asset.id);
    const suggested = recommended(state).includes(asset.id);
    const reason = asset.position === 'PICK' ? asset.origin : asset[state.outlook];
    return `<button type="button" class="setup-roster-row" data-asset="${asset.id}" aria-pressed="${selected}" aria-label="${selected ? 'Remove' : 'Add'} ${asset.name}${asset.origin ? ', ' + asset.origin : ''} ${selected ? 'from' : 'to'} trade pool"><span class="setup-position setup-position-${asset.position}">${asset.position}</span><span class="setup-asset-copy"><span class="setup-asset-name">${asset.name}</span><span class="setup-asset-reason">${reason}</span>${suggested ? '<span class="setup-recommended">Suggested to shop</span>' : ''}</span>${tick(selected)}</button>`;
  }
  function assets(state) {
    const visible = roster.filter(asset => asset.id !== 'own-2027-1' || state.ownsFirst);
    return `<div class="eyebrow">TEAM OVERHAUL · 02</div><h2 class="mock-title">BUILD YOUR TRADE POOL</h2><p class="mock-subtitle">${isAllIn(state) ? 'We’ve suggested future assets to shop for production now.' : 'We’ve suggested productive players to turn into future assets.'} Add or remove any asset.</p>
      <div class="setup-pool-receipt"><strong>${state.selectedAssets.length}</strong> <span>assets available to trade</span><p>Selected assets are available to use. Your final plan may use only part of this pool.</p></div>
      ${ownershipNotice(state)}
      <div class="setup-inline-actions"><button type="button" class="secondary" data-restore-pool>Restore suggestions</button><button type="button" class="ghost" data-clear-pool>Clear selection</button></div>
      ${['QB', 'RB', 'WR', 'TE', 'PICK'].map(position => { const rows = visible.filter(a => a.position === position); return `<div class="setup-section">${position === 'PICK' ? 'Draft picks' : position}<span class="mono">${rows.length}</span></div>${rows.map(a => assetRow(a, state)).join('')}`; }).join('')}
      ${isAllIn(state) ? '<p class="setup-honesty">A trade can send picks only. Every pick is tracked by original owner, year and round so it cannot be spent twice.</p>' : '<p class="setup-honesty">A trade can return picks only. Picks in your pool are available as optional sweeteners.</p>'}
      ${!state.selectedAssets.length ? '<p class="setup-zero" role="status">Choose at least one asset to continue. A small pool may support fewer than 4–5 independent trades.</p>' : ''}
      <div class="setup-footer"><button type="button" class="primary" data-navigate="positions"${!state.selectedAssets.length ? ' disabled' : ''}>Continue</button><button type="button" class="ghost" data-navigate="outlook">Back to outlook</button></div>`;
  }
  function positions(state) {
    const allin = isAllIn(state);
    const options = [{ id: 'QB', label: 'Quarterback', hint: allin ? 'Starting production' : 'Future building blocks' }, { id: 'RB', label: 'Running back', hint: allin ? 'Suggested · example need' : 'Future building blocks' }, { id: 'WR', label: 'Wide receiver', hint: allin ? 'Suggested · example need' : 'Suggested · youth' }, { id: 'TE', label: 'Tight end', hint: allin ? 'Starting production' : 'Future building blocks' }];
    if (!allin) options.push({ id: 'PICKS', label: 'Draft picks', hint: 'Suggested · future capital' });
    return `<div class="eyebrow">TEAM OVERHAUL · 03</div><h2 class="mock-title">WHAT DO YOU WANT BACK?</h2><p class="mock-subtitle">Optional. Choose where to focus your returns, or leave it open.</p>
      <div class="panel"><div class="eyebrow">SUGGESTED DIRECTION</div><p style="margin:12px 0 0">${allin ? 'Look for production at RB and WR.' : 'Look for young building blocks and draft capital.'}</p><p class="setup-honesty">${allin ? 'These example needs illustrate how roster analysis could guide the plan.' : 'Rebuilding applies a future-value preference across positions. Draft picks are a return type, alongside the position choices.'}</p><button type="button" class="secondary" data-use-targets>Use suggestions</button></div>
      <div class="setup-target-grid">${options.map(option => `<button type="button" class="setup-target" data-position="${option.id}" aria-pressed="${state.positions.includes(option.id)}"><span class="setup-target-head">${option.id}${tick(state.positions.includes(option.id))}</span><small>${option.label}<br>${option.hint}</small></button>`).join('')}</div>
      <div class="setup-priority-note">${state.positions.length ? '<strong>Focus: ' + state.positions.map(p => p === 'PICKS' ? 'draft picks' : p).join(', ') + '.</strong> These preferences guide the overall roadmap. Strong offers at other positions can still appear.' : '<strong>No position preference.</strong> We’ll use your outlook and team needs to suggest returns.'}</div>
      ${!allin && !state.ownsFirst ? '<div class="setup-own-note"><strong>First priority: your 2027 1st.</strong><br>We’ll look for a recovery offer with Northside, even if you leave draft picks unselected here.</div>' : ''}
      <div class="setup-footer"><button type="button" class="primary" data-navigate="review">Continue</button><button type="button" class="ghost" data-clear-targets>Clear preferences</button><button type="button" class="ghost" data-navigate="assets">Back to trade pool</button></div>`;
  }
  function render(page, state) {
    defaults(state);
    return styles + (page === 'outlook' ? outlook(state) : page === 'assets' ? assets(state) : positions(state));
  }
  function bind(root, state, update) {
    defaults(state);
    root.querySelectorAll('[data-outlook]').forEach(el => el.addEventListener('click', () => {
      if (state.outlook === el.dataset.outlook) return;
      state.outlook = el.dataset.outlook;
      state.selectedAssets = recommended(state);
      state.positions = [];
      update();
    }));
    root.querySelectorAll('[data-asset]').forEach(el => el.addEventListener('click', () => {
      const id = el.dataset.asset;
      state.selectedAssets = state.selectedAssets.includes(id) ? state.selectedAssets.filter(asset => asset !== id) : state.selectedAssets.concat(id);
      update();
    }));
    root.querySelector('[data-restore-pool]')?.addEventListener('click', () => { state.selectedAssets = recommended(state); update(); });
    root.querySelector('[data-clear-pool]')?.addEventListener('click', () => { state.selectedAssets = []; update(); });
    root.querySelectorAll('[data-position]').forEach(el => el.addEventListener('click', () => {
      const id = el.dataset.position;
      state.positions = state.positions.includes(id) ? state.positions.filter(position => position !== id) : state.positions.concat(id);
      update();
    }));
    root.querySelector('[data-use-targets]')?.addEventListener('click', () => { state.positions = isAllIn(state) ? ['RB', 'WR'] : ['WR', 'PICKS']; update(); });
    root.querySelector('[data-clear-targets]')?.addEventListener('click', () => { state.positions = []; update(); });
  }
  window.OverhaulSetup = { render, bind };
})();
