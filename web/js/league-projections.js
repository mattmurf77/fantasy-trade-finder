/* Stored scheduled projections only. Viewing never starts provider work. */
(() => {
  'use strict';
  let epoch = 0, displayedContext = null;
  const el = (tag, text) => {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n;};
  const pct = n => `${(n * 100).toFixed(1)}%`;
  const num = n => n == null ? 'Unavailable' : n.toFixed(1);
  const states = {no_run: 'Waiting for the first weekly forecast.', queued: 'Weekly update queued.',
    running: 'Weekly update in progress.', current: '', stale: 'Weekly update due.',
    refresh_failed: 'Latest update failed.', incomplete_projections: 'Missing player or scoring data.',
    unsupported_policy: 'This league’s rules aren’t supported yet.', failed: 'Weekly update failed.'};
  const date = iso => new Date(iso).toLocaleDateString(undefined,{month:'short',day:'numeric'});
  const disclosure = label => {const d=el('details');d.append(el('summary',label));return d;};
  const button = (label,action) => {const b=el('button',label);b.type='button';b.onclick=action;return b;};

  function renderTeams(host, result) {
    const names = new Map(result.teams.map(t => [t.roster_id,t.name]));
    const controls = el('div'); controls.className='league-projection-controls';
    const table = el('table'); table.className='league-projection-table';
    const draftNote = el('p','Estimates assume regular-season Max PF draft order.');
    const empty = el('p','No team projections in this forecast.'); empty.hidden = result.teams.length > 0;
    const sortPanel = disclosure('Sort teams');
    const sort = el('select'); sort.setAttribute('aria-label','Sort projected standings');
    for (const [value,label] of [['odds','Playoff odds'],['name','Team name'],['record','Current record']]) {
      const option=el('option',label);option.value=value;sort.append(option);
    }
    sortPanel.append(sort,el('p','Average records come from simulations. Odds don’t confirm a playoff spot.'));
    let pickView=false;
    const playoff = button('Playoffs', () => {pickView=false;draw();});
    const draft = button('Non-playoff picks', () => {pickView=true;draw();});
    controls.append(playoff,draft);
    host.append(controls,draftNote,table,empty,sortPanel);

    function draw() {
      playoff.setAttribute('aria-pressed',String(!pickView));
      draft.setAttribute('aria-pressed',String(pickView));
      draftNote.hidden=!pickView;sortPanel.hidden=pickView;
      const head=el('thead'), headers=el('tr'), body=el('tbody');
      ['Team',pickView?'Miss playoffs':'Playoff odds',pickView?'Proj. Max PF':'Avg. record'].forEach(label => {
        const th=el('th',label); th.scope='col'; headers.append(th);
      });
      head.append(headers);table.replaceChildren(head,body);
      const teams=[...result.teams].sort((a,b) => pickView ? a.maxpf_mean-b.maxpf_mean : sort.value==='name'
        ? a.name.localeCompare(b.name) : sort.value==='record'
          ? (b.current_record[0]+.5*b.current_record[2])-(a.current_record[0]+.5*a.current_record[2])
          : b.playoff_probability-a.playoff_probability);
      for (const team of teams) {
        const row=el('tr'), name=el('td'), detailRow=el('tr'), detail=el('td');
        detail.colSpan=3;detailRow.hidden=true;detailRow.append(detail);
        const expand=button(team.name, () => {
          if (detailRow.hidden && !detail.children.length) teamDetail(detail,team,pickView,names,result);
          detailRow.hidden=!detailRow.hidden;
          expand.setAttribute('aria-expanded',String(!detailRow.hidden));
        });
        expand.className='league-projection-team';expand.setAttribute('aria-expanded','false');
        name.append(expand);
        row.append(name,el('td',pct(pickView?team.nonplayoff_probability:team.playoff_probability)),
          el('td',pickView?num(team.maxpf_mean):team.expected_record.map(num).join('–')));
        body.append(row,detailRow);
      }
    }
    sort.onchange=draw; draw();
  }

  function teamDetail(detail,team,pickView,names,result) {
    if (pickView) {
      detail.append(el('p',`Pick owner: ${names.get(team.pick_owner_roster_id) || `Team ${team.pick_owner_roster_id}`} · ${result.config.draft_season} round ${result.config.draft_round}`),
        el('p',`Expected pick if this team misses: ${num(team.conditional_expected_pick)}`));
      const picks=disclosure('Pick odds and range');
      picks.append(el('p',`Current Max PF: ${num(team.current_maxpf)} · ${num(team.maxpf_per_completed_week)} per week`),
        el('p',`Projected Max PF, middle 80%: ${num(team.maxpf_quantiles['0.1'])}–${num(team.maxpf_quantiles['0.9'])}`),
        el('p','Pick odds include the chance of making playoffs.'),
        el('p',team.pick_probabilities.map((p,i)=>`Pick ${i+1}: ${pct(p)}`).join(' · ')),
        el('p',`Missed-playoff simulations: ${team.nonplayoff_samples}. This franchise is projected to own ${num(team.owner_expected_nonplayoff_picks)} non-playoff picks, with a ${pct(team.owner_probability_at_least_one)} chance of at least one.`));
      detail.append(picks);
    } else {
      const records=disclosure('Final record odds');
      records.append(el('p',(team.final_record_distribution||[]).map(r=>`${r.record.join('–')}: ${pct(r.probability)}`).join(' · ')));
      detail.append(el('p',`Current: ${team.current_record.join('–')} · ${num(team.current_points_for)} PF · ${num(team.current_ppg)} PPG`),
        el('p',`Most likely finish: ${team.modal_record.join('–')}${result.playoff_byes>0?` · Bye odds: ${pct(team.bye_probability)}`:''}`),records);
    }
    const weeks=disclosure('Weekly projections');detail.append(weeks);
    team.weeks.forEach(w => {
      const detail = disclosure(`Week ${w.week} · ${pct(w.win_probability)} win`);
      weeks.append(detail);
      detail.append(el('p', `vs ${names.get(w.opponent_roster_id) || `Team ${w.opponent_roster_id}`}: win ${pct(w.win_probability)}, tie ${pct(w.tie_probability)}, loss ${pct(w.loss_probability)}. ${w.actual_score_observed ? `Recorded completed lineup score ${num(w.modeled_score_mean)}; no historical blend or score simulation.` : `Score mean ${num(w.modeled_score_mean)}, standard deviation ${num(w.modeled_score_sd)}.`}`));
      if (w.maxpf_floor) {
        const m = w.maxpf_floor;
        detail.append(el('p', m.policy ? `Max PF target ${num(m.target_mean)}; simulated mean ${num(m.simulated_mean)}. Simulation averages vary; predictive uncertainty is not calibrated.` : `Historical model: input Max PF ${num(m.input_mean)}; simulated mean ${num(m.simulated_mean)}.`));
        if (m.policy) {
          const diagnostics=el('details'); diagnostics.append(el('summary','Model diagnostics'));
          diagnostics.append(el('p', `Latent mean ${m.latent_maxpf_mean == null ? "not used for a zero target gap" : num(m.latent_maxpf_mean)}. Configured latent variance ${num(m.configured_latent_maxpf_variance)}; realized model variance ${num(m.analytic_realized_variance)}. Latent residual correlation ${num(m.configured_residual_correlation)}; sampled total correlation ${num(m.simulated_correlation)}. Simulation mean standard error ${m.simulated_mean_standard_error?.toPrecision(3)}. Rounding mean bound ±${m.rounding_mean_error_bound} points. Floor adjustment relative to latent draws ${num(m.mean_uplift)}; floor activation ${pct(m.frequency)}.`));
          detail.append(diagnostics);
        }
      }
      if (w.observed_mean_conditioning?.known_maxpf_floor != null) detail.append(el('p', `An already completed eligible lineup establishes at least ${num(w.observed_mean_conditioning.known_maxpf_floor)} Max PF. ${w.maxpf_score_observed ? 'Max PF is fully observed for this roster.' : `Target adjustment from that known result: ${num(w.observed_mean_conditioning.target_adjustment)} points.`}`));
      if (w.actual_score_observed) detail.append(el('p', `Recorded team total ${w.modeled_actual_projection} supplies the actual score; individual missing scores remain unavailable.`));
      if (w.projection_coverage?.estimated) {
        const c=w.projection_coverage;
        detail.append(el('p', `Available projections: ${c.priced_actual_pool} actual-lineup players, ${c.priced_maxpf_pool} Max PF players. ${c.fallback ? `Completed team history supplies ${c.fallback_lanes.join(' and ')} projection: ${w.modeled_actual_projection} / ${w.modeled_maxpf_projection}.` : 'Unknown players and rules are not confirmed zeros.'}`));
        c.unpriced_players.forEach(p => detail.append(el('p', `${p.name || p.player_id}: no usable estimate (${p.reason.replace(/_/g,' ')}).`)));
        c.partial_players.forEach(p => detail.append(el('p', `${p.name || p.player_id}: partial contributions; missing ${p.missing_keys.map(k=>k.replace(/_/g,' ')).join(', ')}.`)));
        if(c.idp_replacement_unavailable) detail.append(el('p','No hypothetical IDP bye replacement was added because its historical scoring average is unavailable.'));
      }
      w.actual.lineup.forEach(r => detail.append(el('p', `${r.slot}: ${r.player ? `${r.player.hypothetical ? 'Hypothetical bye replacement' : r.player.name || r.player.player_id} · ${r.player.points}` : r.unpriced_locked_player ? `Locked starter ${r.unpriced_locked_player.name || r.unpriced_locked_player.player_id}: actual score unavailable` : 'Empty slot'}`)));
      detail.append(el('p', `Historical component ${num(w.historical_component)} plus projection component ${num(w.projection_component)}. Exclusions: ${w.exclusions.map(p => `${p.player_id} (${p.reason})`).join(', ') || 'None'}.`));
    });
  }

  window.loadLeagueProjectionBatch = async () => {
    const host = document.getElementById('league-projection-batch');
    const context = window.FTFWinNowContext;
    const generation = ++epoch;
    if (!host) return;
    host.hidden = !window.FTF_FLAG('league.projections');
    if (host.hidden || !context?.leagueId()) { host.replaceChildren(); displayedContext = null; return; }
    const league = context.leagueId(), user = context.userId();
    const identity = `${user}:${league}`;
    const previous = displayedContext === identity ? Array.from(host.childNodes || host.children) : [];
    host.replaceChildren();
    const title = el('h2', 'Projected standings'); host.append(title, el('p', 'Loading projections…'));
    const isCurrent = () => context.leagueId() === league && context.userId() === user;
    const check = button('Check for update', window.loadLeagueProjectionBatch);
    try {
      const response = await context.apiFetch(`/api/leagues/${encodeURIComponent(league)}/projection-runs/latest`);
      if (!response?.ok) throw new Error('Saved projections could not be loaded.');
      const data = await response.json();
      if (generation !== epoch || !isCurrent()) return;
      displayedContext = identity;
      host.replaceChildren(title);
      const status=states[data.state] ?? 'Projection unavailable.';
      if (status) host.append(el('p',status));
      const result=data.run?.result;
      if (!result) {host.append(el('p','Current standings are still available.'),check);return;}
      host.append(el('p',[data.state==='current'?'Weekly estimate':`Last saved: ${date(result.captured_at)}`,
        result.coverage?.estimated?'Partial Sleeper data':null,result.provisional?'Provisional':null].filter(Boolean).join(' · ')));
      renderTeams(host,result);

      const forecast=disclosure('Forecast details');
      forecast.append(el('p',`Forecasts update weekly. ${data.next_attempt_not_before?`Next eligible attempt: ${new Date(data.next_attempt_not_before).toLocaleString()}.`:''}`),
        el('p',`${result.iterations.toLocaleString()} simulations · Inputs: ${new Date(result.captured_at).toLocaleString()} · Model ${result.model_version}`),check);
      if (result.coverage?.estimated) forecast.append(el('p',`Partial player-weeks: ${result.coverage.partial_player_weeks || 0}. Without a usable projection: ${result.coverage.unpriced_player_weeks || 0}. Missing scoring can move estimates up or down.`));
      const assumptions=disclosure('Assumptions and scoring');
      assumptions.append(el('p',`Historical weight ${result.config.historical_weight * 100}%. IR Max PF scenario: ${result.config.ir_maxpf}. Current reserves excluded from actual lineups. Draft exact ties randomized. Variance and correlation are uncalibrated scenario inputs.`));
      result.warnings.forEach(w => assumptions.append(el('p',w)));
      const scoring=disclosure('Scoring settings');
      Object.entries(result.scoring || {}).filter(([,v])=>v!==0).forEach(([k,v])=>scoring.append(el('p',`${k.replace(/_/g,' ')}: ${v}`)));
      assumptions.append(scoring);forecast.append(assumptions);
      const comparisons = disclosure('Compare history weights');
      comparisons.append(el('p','Try a different weight for past scores. The weekly forecast stays the same.'));
      host.append(comparisons,forecast);
      for (const weight of [.4,.6,.8]) {
        const compare = el('button', `${weight * 100}%`); compare.type = 'button'; comparisons.append(compare);
        compare.onclick = async () => {
          if (!isCurrent()) return;
          const label = el('p', 'Queueing comparison…'); comparisons.append(label);
          try {
            const response = await context.apiFetch(`/api/leagues/${encodeURIComponent(league)}/projection-runs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({baseline_run_id:data.run.run_id, config:{...result.config,historical_weight:weight}})});
            if (!response?.ok) throw new Error('comparison unavailable');
            const queued = await response.json();
            if (context.leagueId() !== league || context.userId() !== user) return;
            label.textContent = 'Comparison queued for background processing. The weekly baseline stays unchanged.';
            const checkComparison = el('button', 'Check comparison'); checkComparison.type = 'button'; comparisons.append(checkComparison);
            checkComparison.onclick = async () => {
              const r = await context.apiFetch(`/api/projection-runs/${queued.run_id}`);
              if (!r?.ok || context.leagueId() !== league || context.userId() !== user) return;
              const run = await r.json();
              label.textContent = run.result ? `${weight * 100}% scenario: ${run.result.teams.map(t => `${t.name} ${pct(t.playoff_probability)} playoffs, conditional pick ${num(t.conditional_expected_pick)}`).join('; ')}` : `Comparison ${run.status.replace(/_/g,' ')}.`;
            };
          } catch (_) { label.textContent='Could not queue the comparison. The weekly baseline stays unchanged.'; }
        };
      }
      for (const kind of ['csv','manifest']) {
        const button = el('button', `Export ${kind.toUpperCase()}`); button.type='button';
        button.onclick = async () => {
          if (!isCurrent()) return;
          const r = await context.apiFetch(`/api/projection-runs/${data.run.run_id}/export/${kind}`);
          if (!r?.ok || context.leagueId() !== league || context.userId() !== user) return;
          const url = URL.createObjectURL(await r.blob()); const a=el('a');a.href=url;a.download=`league-projections.${kind==='csv'?'csv':'json'}`;a.click();URL.revokeObjectURL(url);
        }; forecast.append(button);
      }
    } catch (_) {
      if (generation === epoch && context.leagueId() === league && context.userId() === user) {
        const note=el('p',previous.length?'Couldn’t check for an update. Showing last saved results.':'Couldn’t load projections. Current standings are still available.');
        note.className='league-projection-error';
        if (previous.length) host.replaceChildren(previous[0],note,...previous.slice(1).filter(n=>n.className!=='league-projection-error'));
        else host.replaceChildren(title,note,check);
      }
    }
  };
})();
