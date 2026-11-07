/* Stored scheduled projections only. Viewing never starts provider work. */
(() => {
  'use strict';
  let epoch = 0, displayedContext = null;
  const el = (tag, text) => {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n;};
  const pct = n => `${(n * 100).toFixed(1)}%`;
  const num = n => n == null ? 'Unavailable' : n.toFixed(1);
  const states = {no_run: 'Projections are being prepared for a scheduled batch. Current standings remain available.',
    queued: 'Queued for a scheduled update.', running: 'A scheduled update is running.', current: 'Latest completed projection.',
    stale: 'The next weekly update is due. This is the last completed forecast.', refresh_failed: 'The latest update failed. The last completed projection remains below.',
    incomplete_projections: 'Some player or scoring inputs are missing. A complete projection is not available.',
    unsupported_policy: 'Projection data or league-rule coverage is not available yet.', failed: 'The scheduled update failed.'};
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
    const title = el('h2', 'Standings projections'); host.append(title, el('p', 'Loading saved projections…'));
    try {
      const response = await context.apiFetch(`/api/leagues/${encodeURIComponent(league)}/projection-runs/latest`);
      if (!response?.ok) throw new Error('Saved projections could not be loaded.');
      const data = await response.json();
      if (generation !== epoch || context.leagueId() !== league || context.userId() !== user) return;
      displayedContext = identity;
      host.replaceChildren(title, el('p', states[data.state] || 'Projection unavailable.'));
      host.append(el('p', `Forecasts update weekly. ${data.next_attempt_not_before ? `Next eligible attempt: ${new Date(data.next_attempt_not_before).toLocaleString()}.` : 'An attempt time has not been assigned yet.'} Completion time depends on available inputs.`));
      const check = el('button', 'Check saved update'); check.type = 'button'; check.onclick = window.loadLeagueProjectionBatch; host.append(check);
      const result = data.run?.result;
      if (!result) {host.append(el('p', 'Official current standings remain available while projections are being prepared.')); return;}
      host.append(el('p', `Model estimate · ${result.iterations.toLocaleString()} simulations · Inputs ${new Date(result.captured_at).toLocaleString()} · ${result.model_version}`));
      const scroll = el('div'); scroll.className = 'league-projection-scroll';
      const table = el('table'); table.append(el('caption', 'Playoff likelihood, sorted by probability. Expected records are averages; modal records are the most frequent exact result.'));
      const head = el('tr'); ['Team', 'Current W–L–T', 'PF / PPG', 'Expected W–L–T', 'Modal W–L–T', 'Playoffs', 'Bye'].forEach(t => head.append(el('th', t))); table.append(head);
      const sort = el('select'); sort.setAttribute?.('aria-label', 'Sort projected standings');
      for (const [value,label] of [['odds','Playoff probability'],['name','Team name'],['record','Current record']]) {
        const option=el('option',label);option.value=value;sort.append(option);
      }
      const drawPlayoffs = () => {
        while (table.children.length > 2) table.removeChild(table.lastChild);
        [...result.teams].sort((a,b) => sort.value==='name' ? a.name.localeCompare(b.name) : sort.value==='record' ? (b.current_record[0]+.5*b.current_record[2])-(a.current_record[0]+.5*a.current_record[2]) : b.playoff_probability-a.playoff_probability).forEach(team => {
          const row=el('tr');[team.name,team.current_record.join('–'),`${num(team.current_points_for)} / ${num(team.current_ppg)}`,team.expected_record.map(num).join('–'),team.modal_record.join('–'),pct(team.playoff_probability),pct(team.bye_probability)].forEach(v=>row.append(el('td',v)));table.append(row);
        });
      };
      sort.onchange=drawPlayoffs;host.append(sort);drawPlayoffs();
      scroll.append(table); host.append(scroll);
      const draftScroll = el('div'); draftScroll.className = 'league-projection-scroll'; const draft = el('table');
      draft.append(el('caption', `Non-playoff picks, ${result.config.draft_season} round ${result.config.draft_round}. Sorted by projected Max PF, not final draft order. Pick odds include playoff risk.`));
      const dh = el('tr'); ['Original team', 'Current owner', 'Current Max PF / week', 'Projected Max PF [10–90%]', 'Miss playoffs', 'Unconditional pick odds', 'Expected pick if missed'].forEach(t => dh.append(el('th', t))); draft.append(dh);
      [...result.teams].sort((a,b) => a.maxpf_mean-b.maxpf_mean).forEach(team => {
        const row = el('tr'); [team.name, `Team ${team.pick_owner_roster_id}`, `${num(team.current_maxpf)} / ${num(team.maxpf_per_completed_week)}`, `${num(team.maxpf_mean)} [${num(team.maxpf_quantiles['0.1'])}–${num(team.maxpf_quantiles['0.9'])}]`, pct(team.nonplayoff_probability), team.pick_probabilities.map((p,i) => `${i+1}: ${pct(p)}`).join(' / '), num(team.conditional_expected_pick)].forEach(v => row.append(el('td',v))); draft.append(row);
        const detail = el('details'); detail.append(el('summary', `${team.name}: weekly lineups and matchup odds`));
        detail.append(el('p', `Final record distribution: ${(team.final_record_distribution || []).map(r => `${r.record.join('–')}: ${pct(r.probability)}`).join('; ')}. Missed-playoff samples: ${team.nonplayoff_samples}. ${team.name} franchise portfolio expected picks: ${num(team.owner_expected_nonplayoff_picks)}; chance of at least one: ${pct(team.owner_probability_at_least_one)}.`));
        team.weeks.forEach(w => {
          detail.append(el('p', `Week ${w.week} vs Team ${w.opponent_roster_id}: win ${pct(w.win_probability)}, tie ${pct(w.tie_probability)}, loss ${pct(w.loss_probability)}. Score mean ${num(w.modeled_score_mean)}, standard deviation ${num(w.modeled_score_sd)}.`));
          if (w.maxpf_floor) detail.append(el('p', `Max PF before floor ${num(w.maxpf_floor.input_mean)}; simulated mean ${num(w.maxpf_floor.simulated_mean)}. Floor adds ${num(w.maxpf_floor.mean_uplift)} points on average (${pct(w.maxpf_floor.frequency)} of scenarios).`));
          w.actual.lineup.forEach(r => detail.append(el('p', `${r.slot}: ${r.player ? `${r.player.hypothetical ? 'Hypothetical bye replacement' : r.player.name || r.player.player_id} · ${r.player.points}` : 'Empty slot'}`)));
          detail.append(el('p', `Historical component ${num(w.historical_component)} plus projection component ${num(w.projection_component)}. Exclusions: ${w.exclusions.map(p => `${p.player_id} (${p.reason})`).join(', ') || 'None'}.`));
        }); host.append(detail);
      });
      draftScroll.append(draft); host.append(draftScroll, el('h3','Assumptions and coverage'));
      host.append(el('p', `Historical weight ${result.config.historical_weight * 100}%. IR Max PF scenario: ${result.config.ir_maxpf}. Current reserves excluded from actual lineups. Draft exact ties randomized. Variance and correlation are uncalibrated scenario inputs.`));
      result.warnings.forEach(w => host.append(el('p',w)));
      const comparisons = el('div'); host.append(el('h3', 'Compare historical weighting'), comparisons);
      for (const weight of [.4,.6,.8]) {
        const compare = el('button', `${weight * 100}%`); compare.type = 'button'; comparisons.append(compare);
        compare.onclick = async () => {
          const label = el('p', 'Queueing a comparison of the same saved inputs…'); comparisons.append(label);
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
          const r = await context.apiFetch(`/api/projection-runs/${data.run.run_id}/export/${kind}`);
          if (!r?.ok || context.leagueId() !== league || context.userId() !== user) return;
          const url = URL.createObjectURL(await r.blob()); const a=el('a');a.href=url;a.download=`league-projections.${kind==='csv'?'csv':'json'}`;a.click();URL.revokeObjectURL(url);
        }; host.append(button);
      }
    } catch (_) {
      if (generation === epoch && context.leagueId() === league && context.userId() === user) {
        if (previous.length) host.replaceChildren(...previous);
        host.append(el('p', 'Saved projections could not be loaded. Previous results and current standings remain available.'));
      }
    }
  };
})();
