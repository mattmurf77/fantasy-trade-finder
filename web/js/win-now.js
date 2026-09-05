/* Win Now is a separate viewer-scoped flow. It never consumes, sorts, or
 * submits decisions to the legacy dynasty deck. All untrusted text uses DOM textContent. */
(() => {
  'use strict';
  const context = window.FTFWinNowContext;
  if (!context) return;
  const controls = document.getElementById('win-now-controls');
  const results = document.getElementById('win-now-results');
  const status = document.getElementById('win-now-status');
  let active = false, epoch = 0, controller = null, timer = null, expiryTimer = null;
  let baseline = null, resultMeta = null, trades = null, editor = null, evaluation = null;
  let busy = false, loading = false, message = '', objective = 'wins', budget = '3', fairness = '90';
  let protectedIds = [], giveIds = [], receiveIds = [], decisions = {};
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  const num = n => finite(n) ? n.toFixed(2) : '—';
  const pct = n => finite(n) && n >= 0 && n <= 1 ? `${(100 * n).toFixed(1)}%` : '—';
  const delta = (before, after, points = false) => {
    if (!finite(before) || !finite(after)) return '—';
    const d = (after - before) * (points ? 100 : 1);
    return `${d > 0 ? '+' : ''}${d.toFixed(points ? 1 : 2)}${points ? ' pp' : ''}`;
  };
  const flag = key => window.FTF_FLAG(key);
  const stale = meta => !!meta?.stale || (!!meta?.expires_at && Date.parse(meta.expires_at) <= Date.now());
  const titleAvailable = meta => flag('outlook.championship_probabilities') && meta?.championship_available === true;
  const receipt = meta => {
    const date = meta?.as_of && Number.isFinite(Date.parse(meta.as_of)) ? new Date(meta.as_of).toLocaleString() : 'timestamp unavailable';
    const source = meta?.source === 'sleeper_weekly_experimental' ? 'Sleeper weekly projections' : meta?.source || 'Source unavailable';
    const warning = meta?.scoring_warning ? `\n${meta.scoring_warning}` : '';
    return `${meta?.calibrated === true ? 'Calibrated model' : 'Uncalibrated beta'} · Intervals describe Monte Carlo sampling only; projection/model uncertainty is excluded.\n${source} · ${date} · Coverage ${finite(meta?.coverage) ? pct(meta.coverage) : 'unavailable'}${warning}`;
  };
  const enabled = () => active && !!context.leagueId() && flag('outlook.season_projections');
  const validNumber = (value, min, max) => value.trim() !== '' && Number.isFinite(Number(value)) && Number(value) >= min && Number(value) <= max;
  const canSearch = () => enabled() && flag('trades.win_now') && baseline?.status === 'available' && !stale(baseline.meta) && !stale(resultMeta) && validNumber(budget, 0, 10) && validNumber(fairness, 75, 100) && (objective !== 'championship' || titleAvailable(baseline.meta));
  const params = () => ({league_id: context.leagueId(), objective, max_dynasty_spend_pct: Number(budget), min_fairness: Number(fairness) / 100, protected_ids: [...protectedIds]});
  const el = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
  const paragraph = (parent, text, cls) => parent.appendChild(el('p', text, cls));
  const button = (parent, text, fn, {disabled = false, selected, id} = {}) => {
    const node = el('button', text); node.type = 'button'; node.disabled = disabled;
    if (id) node.id = id;
    if (selected !== undefined) node.setAttribute('aria-pressed', String(selected));
    node.addEventListener('click', fn); parent.appendChild(node); return node;
  };
  function cancel() {
    epoch += 1; controller?.abort(); controller = null;
    if (timer) clearTimeout(timer); timer = null; busy = false;
  }
  function clearResults() { cancel(); trades = null; resultMeta = null; editor = null; evaluation = null; message = ''; }
  function reset() {
    if (expiryTimer) clearTimeout(expiryTimer); expiryTimer = null;
    clearResults(); baseline = null; loading = false; protectedIds = []; decisions = {}; giveIds = []; receiveIds = [];
    if (active) render();
  }
  function begin() {
    cancel(); controller = new AbortController(); busy = true; message = '';
    return {epoch, signal: controller.signal, league: context.leagueId(), user: context.userId()};
  }
  const isCurrent = request => active && request.epoch === epoch && request.league === context.leagueId() && request.user === context.userId();
  async function api(path, request, body) {
    const timeout = setTimeout(() => { if (isCurrent(request)) controller?.abort(); }, 20000);
    try {
      const response = await context.apiFetch(path, {signal: request.signal, ...(body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})});
      if (!response) throw new Error('Session changed. Refresh season projections.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.reason?.replace(/_/g, ' ') || data.error || `Request failed (${response.status}). Please retry.`);
      return data;
    } finally { clearTimeout(timeout); }
  }
  function fail(error, request) {
    if (!isCurrent(request)) return;
    busy = false; loading = false;
    message = error.name === 'AbortError' ? 'Request timed out. Please retry.' : error.message || 'Could not load Win Now. Please retry.';
    render();
  }
  async function load() {
    reset();
    if (!enabled()) return render();
    const request = begin(); loading = true; render();
    try {
      const data = await api(`/api/league/season-projections?league_id=${encodeURIComponent(request.league)}`, request);
      if (!isCurrent(request)) return;
      baseline = data; busy = false; loading = false;
      if (!titleAvailable(data.meta) && objective === 'championship') objective = 'wins';
      render();
    } catch (error) { fail(error, request); }
  }
  async function search() {
    if (!canSearch() || busy) return;
    clearResults(); const request = begin(); const started = Date.now(); render();
    const apply = async job => {
      if (!isCurrent(request)) return;
      if (job.status === 'complete' && job.result) {
        busy = false; resultMeta = job.result.meta;
        if (stale(resultMeta)) message = 'These projections are stale. Refresh before searching.';
        else trades = job.result.trades; // Server ordering is authoritative.
        return render();
      }
      if (job.status === 'failed' || job.status === 'unavailable') {
        busy = false; message = job.message || job.reason?.replace(/_/g, ' ') || 'Search unavailable. Please retry.'; return render();
      }
      if (!job.job_id || Date.now() - started >= 90000) {
        busy = false; message = 'Search has not finished. Try again when you are ready.'; return render();
      }
      timer = setTimeout(async () => {
        if (!isCurrent(request)) return;
        try { await apply(await api(`/api/win-now/jobs/${encodeURIComponent(job.job_id)}`, request)); }
        catch (error) { fail(error, request); }
      }, 1500);
    };
    try { await apply(await api('/api/win-now/search', request, params())); }
    catch (error) { fail(error, request); }
  }
  function edit(trade) {
    cancel(); editor = trade; evaluation = null; message = '';
    giveIds = trade.give.map(asset => asset.id); receiveIds = trade.receive.map(asset => asset.id); renderResults();
    document.getElementById('win-now-editor')?.scrollIntoView({block: 'start'});
  }
  async function evaluate() {
    if (!canSearch() || busy || !editor || !giveIds.length || !receiveIds.length) return;
    const request = begin(); evaluation = null; render();
    try {
      const data = await api('/api/win-now/evaluate', request, {...params(), partner_roster_id: editor.partner_roster_id, give_ids: giveIds, receive_ids: receiveIds});
      if (isCurrent(request)) { evaluation = data; busy = false; render(); }
    } catch (error) { fail(error, request); }
  }
  async function decide(trade, decision) {
    if (!canSearch() || busy) return;
    const request = begin(); render();
    try {
      const response = await api(`/api/win-now/scenarios/${encodeURIComponent(trade.scenario_id)}/decision`, request, {decision});
      if (isCurrent(request)) { busy = false; if (response.ok) decisions[trade.scenario_id] = decision; else message = response.message || response.reason?.replace(/_/g, ' ') || 'Decision was not saved. Please retry.'; render(); }
    } catch (error) { fail(error, request); }
  }
  function metrics(parent, before, after, title) {
    const rows = [
      ['Next matchup', 'next_matchup_win_probability', true],
      ['Next 3 weeks', 'next_three_week_expected_wins', false], ['Remaining wins', 'expected_remaining_wins', false], ['Final wins', 'expected_wins', false],
      ['Make playoffs', 'playoff_probability', true], ['Bye', 'bye_probability', true],
      ...(title ? [['Championship', 'championship_probability', true]] : []),
    ];
    for (const [label, key, points] of rows) {
      const format = points ? pct : num;
      paragraph(parent, `${label}: ${format(before?.[key])} → ${format(after?.[key])} (${delta(before?.[key], after?.[key], points)})`);
    }
  }
  function evidence(parent, trade, meta) {
    if (objective !== 'championship' || titleAvailable(meta)) {
      const metric = {wins: 'next_three_week_expected_wins', playoffs: 'playoff_probability', championship: 'championship_probability'}[objective];
      const label = {wins: 'Next 3 weeks', playoffs: 'Make playoffs', championship: 'Championship'}[objective];
      const uncertainty = trade.buyer.uncertainty?.[metric];
      const format = value => finite(value) ? `${delta(0, value, objective !== 'wins')}${objective === 'wins' ? ' wins' : ''}` : 'unavailable';
      paragraph(parent, `${label} · Sampling range ${format(uncertainty?.lower_bound)} to ${format(uncertainty?.upper_bound)}. Independent-run change ${format(uncertainty?.confirmation_delta)}; conservative search gain ${format(trade.conservative_season_gain)}. Sampling error only, not a forecast confidence interval.`);
    }
    parent.appendChild(el('h3', 'Your team · before → after')); metrics(parent, trade.buyer.before, trade.buyer.after, titleAvailable(meta));
    parent.appendChild(el('h3', `${trade.partner_username || 'Partner'} · before → after`)); metrics(parent, trade.partner.before, trade.partner.after, titleAvailable(meta));
    const v = trade.valuation || {};
    paragraph(parent, `Dynasty cost ${num(v.buyer_dynasty_cost)} / budget ${num(v.buyer_budget)}. Give-package loss ${pct(v.buyer_package_loss_fraction)}.`);
    paragraph(parent, `Market balance ${pct(v.market_ratio)} · Partner dynasty gain ${pct(v.partner_gain_fraction)}`);
    paragraph(parent, `Partner evidence: ${v.partner_basis?.replace(/_/g, ' ') || 'Market-based estimate'} · Confidence ${pct(v.partner_confidence)} · Board coverage ${pct(v.partner_coverage)}`);
    paragraph(parent, `Partner intent: ${trade.partner_intent || v.partner_intent || 'Unknown; no rebuild intent assumed'}`);
    for (const reason of trade.reasons || []) paragraph(parent, reason);
    paragraph(parent, receipt(meta), 'win-now-receipt');
  }
  const assetLabel = asset => `${asset.name} · ${asset.is_pick ? 'PICK' : asset.position || 'Player'}`;
  function renderEditor() {
    if (!editor || !canSearch()) return;
    const card = el('article', undefined, 'win-now-card'); card.id = 'win-now-editor';
    card.appendChild(el('h2', `Evaluate with ${editor.partner_username || 'partner'}`));
    paragraph(card, 'Choose up to 3 assets on each side from the snapshot. Every edit requires a fresh evaluation.');
    for (const side of ['give', 'receive']) {
      card.appendChild(el('h3', `You ${side}`)); const row = el('div', undefined, 'win-now-row');
      const owner = side === 'give' ? baseline.buyer_roster_id : editor.partner_roster_id;
      const assets = baseline.assets?.length ? baseline.assets.filter(asset => asset.owner_roster_id === owner) : editor[side];
      for (const asset of assets) button(row, assetLabel(asset), () => {
        cancel(); evaluation = null; message = '';
        const ids = side === 'give' ? giveIds : receiveIds;
        const next = ids.includes(asset.id) ? ids.filter(id => id !== asset.id) : [...ids, asset.id];
        if (side === 'give') giveIds = next; else receiveIds = next;
        renderResults(); syncStatus();
      }, {selected: (side === 'give' ? giveIds : receiveIds).includes(asset.id), disabled: asset.tradable === false || (side === 'give' && protectedIds.includes(asset.id)) || ((side === 'give' ? giveIds : receiveIds).length >= 3 && !(side === 'give' ? giveIds : receiveIds).includes(asset.id))});
      card.appendChild(row);
    }
    button(card, 'Evaluate edited trade', evaluate, {disabled: busy || !giveIds.length || !receiveIds.length, id: 'win-now-evaluate'});
    if (evaluation) {
      paragraph(card, evaluation.status === 'unavailable' || stale(evaluation.meta) ? evaluation.message || 'Evaluation unavailable. Refresh projections.' : evaluation.eligible ? 'Meets Win Now requirements' : 'Does not meet Win Now requirements');
      for (const reason of evaluation.rejection_reasons || []) paragraph(card, reason.replace(/_/g, ' '));
      if (evaluation.status === 'available' && !stale(evaluation.meta) && evaluation.scenario) evidence(card, evaluation.scenario, evaluation.meta);
    }
    results.appendChild(card);
  }
  function renderResults() {
    results.replaceChildren();
    if (!enabled() || !baseline || baseline.status !== 'available' || stale(baseline.meta) || stale(resultMeta) || !flag('trades.win_now')) return;
    if (trades?.length === 0) paragraph(results, 'No trades met your season gain, dynasty budget, fairness and partner-fit requirements. Change your limits or retry after projections update.');
    (trades || []).forEach((trade, i) => {
      const card = el('article', undefined, 'win-now-card');
      card.appendChild(el('h2', `${i + 1}. Trade with ${trade.partner_username || `Team ${trade.partner_roster_id}`}`));
      paragraph(card, `You give: ${trade.give.map(asset => asset.name).join(' + ')}`);
      paragraph(card, `You receive: ${trade.receive.map(asset => asset.name).join(' + ')}`);
      evidence(card, trade, resultMeta);
      const row = el('div', undefined, 'win-now-row');
      button(row, 'Edit & evaluate', () => edit(trade), {disabled: busy});
      button(row, decisions[trade.scenario_id] === 'like' ? 'Liked' : 'Like', () => decide(trade, 'like'), {disabled: busy || !!decisions[trade.scenario_id]});
      button(row, decisions[trade.scenario_id] === 'pass' ? 'Passed' : 'Pass', () => decide(trade, 'pass'), {disabled: busy || !!decisions[trade.scenario_id]});
      card.appendChild(row); results.appendChild(card);
    });
    renderEditor();
  }
  function input(parent, label, value, update, id, min, max) {
    const wrapper = el('label', label); const node = el('input'); node.type = 'number'; node.min = String(min); node.max = String(max); node.step = '0.1'; node.value = value; node.id = id;
    node.addEventListener('input', () => {
      update(node.value); clearResults(); renderResults(); syncStatus();
      const searchButton = document.getElementById('win-now-search'); if (searchButton) searchButton.disabled = !canSearch();
    });
    wrapper.appendChild(node); parent.appendChild(wrapper);
  }
  function syncStatus() {
    status.textContent = message || (busy ? loading ? 'Loading season projections…' : 'Working…' : !validNumber(budget, 0, 10) || !validNumber(fairness, 75, 100) ? 'Enter a dynasty sacrifice from 0 to 10% and market balance from 75 to 100%.' : '');
  }
  function render() {
    if (expiryTimer) clearTimeout(expiryTimer); expiryTimer = null;
    const now = Date.now();
    const future = [baseline?.meta?.expires_at, resultMeta?.expires_at, evaluation?.meta?.expires_at]
      .map(value => value ? Date.parse(value) : NaN).filter(value => Number.isFinite(value) && value > now);
    if (active && future.length) expiryTimer = setTimeout(() => {
      cancel(); message = 'These projections are stale. Refresh season projections before continuing.'; render();
    }, Math.min(Math.min(...future) - now + 10, 2147483647));
    controls.replaceChildren(); syncStatus();
    if (!enabled()) { paragraph(controls, 'Season projections are not available for this league yet.'); return results.replaceChildren(); }
    button(controls, loading ? 'Loading season projections…' : 'Refresh season projections', load, {disabled: loading});
    if (baseline) paragraph(controls, receipt(baseline.meta), 'win-now-receipt');
    if (baseline?.status === 'unavailable') paragraph(controls, baseline.message || baseline.reason?.replace(/_/g, ' ') || 'This league format or forecast source is not supported yet.');
    if (stale(baseline?.meta) || stale(resultMeta)) paragraph(controls, 'These projections are stale. Refresh to get a supported snapshot before searching or evaluating.');
    if (baseline?.status === 'available' && !stale(baseline.meta)) {
      const card = el('section', undefined, 'win-now-card'); card.appendChild(el('h2', 'Projected standings'));
      const tableWrap = el('div', undefined, 'win-now-table-wrap'); const table = el('table', undefined, 'win-now-table');
      const header = el('tr');
      for (const label of ['Avg finish / team', 'W–L–T', 'Playoffs', 'Bye', ...(titleAvailable(baseline.meta) ? ['Championship'] : [])]) { const th = el('th', label); th.scope = 'col'; header.appendChild(th); }
      const head = el('thead'); head.appendChild(header); table.appendChild(head); const body = el('tbody');
      const standings = [...(baseline.teams || [])].sort((a, b) => (finite(a.projected_seed) ? a.projected_seed : Infinity) - (finite(b.projected_seed) ? b.projected_seed : Infinity) || a.roster_id - b.roster_id);
      for (const team of standings) {
        const row = el('tr');
        const cells = [`${num(team.projected_seed)} ${team.username || `Team ${team.roster_id}`}${team.roster_id === baseline.buyer_roster_id ? ' · You' : ''}`, `${num(team.expected_wins)}–${num(team.expected_losses)}–${num(team.expected_ties)}`, pct(team.playoff_probability), pct(team.bye_probability), ...(titleAvailable(baseline.meta) ? [pct(team.championship_probability)] : [])];
        for (const value of cells) row.appendChild(el('td', value)); body.appendChild(row);
        if (team.finish_distribution) { const dist = el('tr'); const cell = el('td', `Finish: ${Object.entries(team.finish_distribution).map(([seed, chance]) => `#${seed} ${pct(chance)}`).join(' · ')}`); cell.colSpan = cells.length; dist.appendChild(cell); body.appendChild(dist); }
      }
      table.appendChild(body); tableWrap.appendChild(table); card.appendChild(tableWrap); controls.appendChild(card);
      if (flag('trades.win_now')) {
        controls.appendChild(el('h2', 'Choose your priority')); const row = el('div', undefined, 'win-now-row');
        for (const [key, label] of [['wins', 'Next 3 weeks'], ['playoffs', 'Make playoffs'], ...(titleAvailable(baseline.meta) ? [['championship', 'Championship']] : [])]) button(row, label, () => { clearResults(); objective = key; render(); }, {selected: objective === key});
        controls.appendChild(row);
        if (!titleAvailable(baseline.meta)) paragraph(controls, 'Championship priority is unavailable until the title model is validated.');
        input(controls, 'Maximum dynasty sacrifice (0–10%)', budget, value => { budget = value; }, 'win-now-budget', 0, 10);
        paragraph(controls, 'Percent of your fixed baseline roster value. The denominator stays the same for every offer; this is not percent of the outgoing package.');
        input(controls, 'Minimum market balance (75–100%)', fairness, value => { fairness = value; }, 'win-now-fairness', 75, 100);
        paragraph(controls, "The server's policy floor also applies. Search never relaxes either limit.");
        const owned = (baseline.assets || []).filter(asset => asset.owner_roster_id === baseline.buyer_roster_id);
        if (owned.length) {
          controls.appendChild(el('h3', 'Protect assets · never offer these')); const choices = el('div', undefined, 'win-now-row');
          for (const asset of owned) button(choices, assetLabel(asset), () => { clearResults(); protectedIds = protectedIds.includes(asset.id) ? protectedIds.filter(id => id !== asset.id) : [...protectedIds, asset.id]; render(); }, {selected: protectedIds.includes(asset.id)});
          controls.appendChild(choices);
        }
        button(controls, 'Find Win Now trades', search, {disabled: busy || !canSearch(), id: 'win-now-search'});
      } else paragraph(controls, 'Win Now trade search is not available yet.');
    }
    if (busy && !loading) button(controls, 'Cancel', () => { cancel(); message = 'Search cancelled. Change your limits or try again.'; render(); });
    renderResults();
  }
  function applyFlags() {
    document.getElementById('trades-win-now')?.classList.toggle('hidden', !flag('trades.win_now') || !flag('outlook.season_projections'));
    document.getElementById('league-win-now')?.classList.toggle('hidden', !flag('outlook.season_projections'));
    if (active) load();
  }
  window.FTFWinNow = {reset, onView(view) { active = view === 'win-now'; if (active) load(); else reset(); }};
  document.addEventListener('ftf:flags-ready', applyFlags);
  applyFlags();
})();
