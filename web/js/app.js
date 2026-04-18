    // ═══════════════════════════════════════════════════════════════
    //  DEBUG LOG DRAWER
    //  logDrawer.action / .req / .res / .err / .info — call anywhere
    // ═══════════════════════════════════════════════════════════════

    const logDrawer = (() => {
      const MAX   = 500;
      const buf   = [];     // { ts, kind, raw } — raw is plain text for copy
      let open    = false;

      function ts() {
        const d = new Date();
        return d.toTimeString().slice(0,8) + '.' + String(d.getMilliseconds()).padStart(3,'0');
      }

      function kindClass(k) {
        return { action:'action', req:'req', res:'res', reserr:'res-err',
                 info:'info', error:'error', server:'server' }[k] || 'info';
      }

      function push(kind, html, raw) {
        if (buf.length >= MAX) buf.shift();
        const t = ts();
        buf.push({ ts: t, kind, html, raw: `[${t}] [${kind.toUpperCase()}] ${raw}` });
        _render();
      }

      function _render() {
        const body  = document.getElementById('log-body');
        const count = document.getElementById('log-count');
        if (!body) return;
        const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;

        // Only re-render the last entry if body already has children (fast path)
        if (buf.length && body.children.length === buf.length - 1) {
          const e = buf[buf.length - 1];
          const div = document.createElement('div');
          div.className = 'log-entry';
          div.innerHTML = `<span class="log-ts">${e.ts}</span>`
            + `<span class="log-dot ${kindClass(e.kind)}"></span>`
            + `<span class="log-msg">${e.html}</span>`;
          body.appendChild(div);
        } else {
          body.innerHTML = buf.map(e =>
            `<div class="log-entry">`
            + `<span class="log-ts">${e.ts}</span>`
            + `<span class="log-dot ${kindClass(e.kind)}"></span>`
            + `<span class="log-msg">${e.html}</span>`
            + `</div>`
          ).join('');
        }

        count.textContent = `${buf.length} entr${buf.length === 1 ? 'y' : 'ies'}`;
        if (atBottom || open) body.scrollTop = body.scrollHeight;
      }

      function h(s) {
        return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      }

      return {
        toggle() {
          open = !open;
          document.getElementById('log-handle').classList.toggle('open', open);
          document.getElementById('log-body').classList.toggle('open', open);
          if (open) document.getElementById('log-body').scrollTop = 9999;
        },

        // ── Public log methods ──────────────────────────────────────
        action(msg) {
          push('action', `<span class="hi">▶ ${h(msg)}</span>`, msg);
        },

        req(method, url, body) {
          const extra = body ? ` <span style="color:#4a4f66">${h(JSON.stringify(body)).slice(0,120)}</span>` : '';
          push('req', `<span style="color:#f59e0b">${h(method)}</span> <span class="url">${h(url)}</span>${extra}`,
               `${method} ${url}${body ? ' ' + JSON.stringify(body).slice(0,120) : ''}`);
        },

        res(status, url, summary) {
          const ok   = status >= 200 && status < 300;
          const cls  = ok ? 'ok' : 'err';
          const kind = ok ? 'res' : 'reserr';
          push(kind,
            `<span class="${cls}">${h(status)}</span> <span class="url">${h(url)}</span>`
            + (summary ? ` → <span class="hi">${h(summary)}</span>` : ''),
            `${status} ${url}${summary ? ' → ' + summary : ''}`);
        },

        info(msg) {
          push('info', h(msg), msg);
        },

        error(msg) {
          push('error', `<span class="err">✖ ${h(msg)}</span>`, msg);
        },

        server(entry) {
          // entry from /api/debug/log: { ts, level, msg }
          const cls = entry.level === 'ERROR' ? 'err'
                    : entry.level === 'WARNING' ? 'warn' : '';
          push('server',
            `<span style="color:#a855f7">[server]</span> `
            + `<span class="${cls}">${h(entry.msg)}</span>`,
            `[server] ${entry.msg}`);
        },

        async fetchBackend() {
          this.info('Fetching server log…');
          try {
            const res  = await fetch('/api/debug/log?n=80');
            const data = await res.json();
            if (data.entries) {
              data.entries.forEach(e => this.server(e));
              this.info(`← Loaded ${data.entries.length} server entries (${data.total_buffered} total buffered)`);
            }
          } catch(e) {
            this.error('Could not fetch /api/debug/log: ' + e.message);
          }
          if (!open) this.toggle();
        },

        copy() {
          const text = buf.map(e => e.raw).join('\n');
          navigator.clipboard.writeText(text).then(
            () => showToast('📋 Log copied to clipboard'),
            () => {
              // Fallback: open in new tab as text
              const w = window.open('','_blank');
              w.document.write('<pre>' + text.replace(/</g,'&lt;') + '</pre>');
            }
          );
        },

        clear() {
          buf.length = 0;
          document.getElementById('log-body').innerHTML = '';
          document.getElementById('log-count').textContent = '0 entries';
        },
      };
    })();

    // ── Instrumented fetch wrapper ──────────────────────────────────
    async function apiFetch(url, opts = {}) {
      // Inject session token on every request
      opts.headers = opts.headers || {};
      if (sessionToken) opts.headers['X-Session-Token'] = sessionToken;

      const method = (opts.method || 'GET').toUpperCase();
      let bodyPreview;
      if (opts.body) {
        try { bodyPreview = JSON.parse(opts.body); } catch { bodyPreview = opts.body; }
      }
      logDrawer.req(method, url, bodyPreview);
      let res;
      try {
        res = await fetch(url, opts);
      } catch (e) {
        logDrawer.error(`Network error on ${method} ${url}: ${e.message}`);
        throw e;
      }
      // Clone so we can read body for logging without consuming it
      const clone = res.clone();
      let _parsedBody = null;
      let summary = '';
      try {
        const raw = await clone.text();
        _parsedBody = raw ? JSON.parse(raw) : null;
        const parsed = _parsedBody;
        if (parsed === null) {
          summary = 'null';
        } else if (Array.isArray(parsed)) {
          summary = `array[${parsed.length}]`;
        } else if (parsed && typeof parsed === 'object') {
          // Show the most useful key fields
          const keys = ['user_id','display_name','username','error','ok',
                        'league_id','name','player_count','opponents'];
          const parts = keys.filter(k => parsed[k] !== undefined)
                            .map(k => `${k}=${JSON.stringify(parsed[k])}`);
          summary = parts.length ? parts.join(' ') : `{${Object.keys(parsed).slice(0,4).join(',')}}`;
        }
      } catch { /* non-JSON – ignore */ }
      logDrawer.res(res.status, url, summary || (res.ok ? 'ok' : 'error'));

      // ── Session expiry handling ─────────────────────────────────────
      if (res.status === 401 && _parsedBody && _parsedBody.error === 'session_expired') {
        logDrawer.info('Session expired — clearing token and reconnecting…');
        localStorage.removeItem(LS_TOKEN);
        sessionToken = null;
        showToast('Session expired — reconnecting…');
        const savedUser   = getSavedUser();
        const savedLeague = getSavedLeague();
        if (savedUser && savedLeague) {
          showInitOverlay('Reconnecting…');
          await initSession(savedUser, savedLeague);
          hideInitOverlay();
        } else {
          boot();
        }
        return;  // caller receives undefined; their try/catch handles it
      }

      return res;
    }

    // ═══════════════════════════════════════════════════════════════
    //  AUTH + SLEEPER INTEGRATION
    // ═══════════════════════════════════════════════════════════════

    const LS_USER    = 'sleeper_user';     // { user_id, display_name, avatar_id }
    const LS_LEAGUE  = 'sleeper_league';   // { league_id, league_name }
    const LS_TOKEN   = 'fumble_session_token';

    let sessionToken = localStorage.getItem(LS_TOKEN) || null;

    let currentLeagueId = null;
    let currentUserId   = null;   // set after login / session restore
    let _cachedLeagues  = [];   // populated by showLeagueScreen; used by selectLeague
    let currentOutlook  = null; // team outlook for the active league (loaded from DB)
    let _myRoster       = [];   // player objects from session/init user_roster
    let _pinnedGivePlayers = new Set();  // player IDs the user wants to trade away
    let _pickerPosFilter   = 'ALL';      // current position filter for the picker

    // ── Boot: check stored session ──────────────────────────────────
    async function boot() {
      logDrawer.info('Page loaded — checking localStorage…');
      const user   = getSavedUser();
      const league = getSavedLeague();

      if (!user) {
        logDrawer.info('No saved user → showing login screen');
        showAuthScreen();
        return;
      }
      logDrawer.info(`Saved user found: ${user.display_name} (${user.user_id})`);
      // Hide the auth-screen immediately so restored sessions don't flash
      // the login page underneath the init overlay or main app.
      hideAuthScreen();
      renderAccountChip(user);

      if (!league) {
        logDrawer.info('No saved league → showing league picker');
        showLeagueScreen(user);
        return;
      }
      logDrawer.info(`Saved league: ${league.league_name} (${league.league_id})`);

      // If we have a stored session token, ping the server to check liveness.
      // A 401 means the session expired (e.g. server restarted); clear the
      // token so initSession() will create a fresh one below.
      if (sessionToken) {
        try {
          const pingRes = await fetch('/api/session/ping', {
            headers: { 'X-Session-Token': sessionToken },
          });
          if (pingRes.status === 401) {
            logDrawer.info('Session token expired — will re-init');
            localStorage.removeItem(LS_TOKEN);
            sessionToken = null;
          } else {
            logDrawer.info('Session token still valid ✓');
          }
        } catch (e) {
          logDrawer.info(`Session ping failed (${e.message}) — continuing with re-init`);
        }
      }

      currentLeagueId = league.league_id;
      currentUserId   = user.user_id || null;
      showInitOverlay('Importing your roster…');
      logDrawer.info('Re-initialising session from saved league…');
      const ok = await initSession(user, league);
      hideInitOverlay();

      if (!ok) {
        logDrawer.error('initSession failed on reload — clearing league, re-showing picker');
        clearSavedLeague();
        showLeagueScreen(user);
      } else {
        logDrawer.info('Session restored ✓');
        initFairnessSlider();   // load per-league fairness preference on restore
        _startNotifPolling();
        // Populate the league switcher — _cachedLeagues is empty on a fresh page load
        // so we fetch leagues in the background without blocking the UI
        apiFetch(`/api/sleeper/leagues/${user.user_id}`)
          .then(r => r.json())
          .then(leagues => {
            if (leagues && leagues.length) {
              _cachedLeagues = leagues;
              renderLeagueSwitcher();
              logDrawer.info(`League switcher populated (${leagues.length} leagues)`);
            }
          })
          .catch(e => logDrawer.error(`Could not populate league switcher on reload: ${e.message}`));
      }
    }

    // ── Saved user helpers ──────────────────────────────────────────
    function getSavedUser()   { try { return JSON.parse(localStorage.getItem(LS_USER)); }   catch { return null; } }
    function getSavedLeague() { try { return JSON.parse(localStorage.getItem(LS_LEAGUE)); } catch { return null; } }
    function saveUser(u)   { localStorage.setItem(LS_USER,   JSON.stringify(u)); }
    function saveLeague(l) { localStorage.setItem(LS_LEAGUE, JSON.stringify(l)); }
    function clearSavedLeague() { localStorage.removeItem(LS_LEAGUE); }

    function logout() {
      logDrawer.action('Logout clicked — clearing localStorage');
      localStorage.removeItem(LS_USER);
      localStorage.removeItem(LS_LEAGUE);
      localStorage.removeItem(LS_TOKEN);
      sessionToken              = null;
      currentLeagueId           = null;
      currentUserId             = null;
      currentOutlook            = null;
      currentAcquirePositions   = [];
      currentTradeAwayPositions = [];
      invalidateRankingProgressCache();
      if (_notifPollTimer) { clearInterval(_notifPollTimer); _notifPollTimer = null; }
      _notifState = [];
      _updateNotifBadge(0);
      document.getElementById('account-chip-container').innerHTML = '';
      showAuthScreen();
    }

    // ── Auth Screen ─────────────────────────────────────────────────
    function showAuthScreen() {
      document.getElementById('auth-screen').classList.remove('hidden');
      document.getElementById('auth-error').textContent = '';
      document.getElementById('username-input').value = '';
      document.getElementById('auth-btn').disabled = false;
      document.getElementById('auth-btn').textContent = 'Connect with Sleeper →';
      setTimeout(() => document.getElementById('username-input').focus(), 100);
    }

    function hideAuthScreen() {
      document.getElementById('auth-screen').classList.add('hidden');
    }

    async function handleLogin() {
      const input  = document.getElementById('username-input');
      const btn    = document.getElementById('auth-btn');
      const errEl  = document.getElementById('auth-error');
      // Sleeper usernames are always lowercase — normalise so users
      // Sleeper usernames are always lowercase — normalise so users
      // don't have to worry about capitalisation
      const rawInput = input.value;
      const username = rawInput.trim().toLowerCase();

      logDrawer.action(`Login button clicked — raw="${rawInput}" normalised="${username}"`);

      if (!username) {
        logDrawer.error('Empty username — aborting');
        errEl.textContent = 'Please enter your Sleeper username.';
        input.classList.add('error');
        return;
      }

      // Reflect the normalised value back so the user can see what was sent
      input.value = username;
      input.classList.remove('error');
      errEl.textContent = '';
      btn.disabled = true;
      btn.textContent = 'Looking up…';

      const url = `/api/sleeper/user/${encodeURIComponent(username)}`;
      logDrawer.info(`Encoded URL: ${url}`);

      try {
        const res  = await apiFetch(url);
        logDrawer.info(`Response status: ${res.status}  ok=${res.ok}`);

        let data;
        try {
          data = await res.json();
          logDrawer.info(`Response body: ${JSON.stringify(data).slice(0, 300)}`);
        } catch (jsonErr) {
          logDrawer.error(`Failed to parse JSON: ${jsonErr.message}`);
          errEl.textContent = 'Server returned invalid response. Check the debug log.';
          btn.disabled = false;
          btn.textContent = 'Connect with Sleeper →';
          return;
        }

        // Diagnose every failure branch individually
        if (!res.ok) {
          logDrawer.error(`res.ok=false (HTTP ${res.status}) — server rejected the request`);
          errEl.textContent = data.error || `Server error ${res.status}. Check the debug log.`;
          input.classList.add('error');
          btn.disabled = false;
          btn.textContent = 'Connect with Sleeper →';
          return;
        }

        if (data === null) {
          logDrawer.error('Sleeper returned null — username does not exist on Sleeper');
          errEl.textContent = 'Username not found on Sleeper. Check spelling (usernames are lowercase).';
          input.classList.add('error');
          btn.disabled = false;
          btn.textContent = 'Connect with Sleeper →';
          return;
        }

        if (data.error) {
          logDrawer.error(`data.error present: "${data.error}"`);
          errEl.textContent = data.error;
          input.classList.add('error');
          btn.disabled = false;
          btn.textContent = 'Connect with Sleeper →';
          return;
        }

        if (!data.user_id) {
          logDrawer.error(`No user_id in response. Keys present: ${Object.keys(data).join(', ')}`);
          errEl.textContent = 'Unexpected response from Sleeper — no user_id. Check debug log.';
          input.classList.add('error');
          btn.disabled = false;
          btn.textContent = 'Connect with Sleeper →';
          return;
        }

        logDrawer.info(`✓ Login success — user_id=${data.user_id}  display_name=${data.display_name}`);

        const user = {
          user_id:      data.user_id,
          display_name: data.display_name || data.username || username,
          avatar_id:    data.avatar || null,
        };
        saveUser(user);
        renderAccountChip(user);
        hideAuthScreen();
        logDrawer.info('Moving to league selection…');
        showLeagueScreen(user);

      } catch (e) {
        logDrawer.error(`Fetch exception: ${e.message}`);
        errEl.textContent = 'Could not reach server — is server.py running?';
        btn.disabled = false;
        btn.textContent = 'Connect with Sleeper →';
      }
    }

    // Enter key triggers login
    document.getElementById('username-input').addEventListener('keydown', e => {
      if (e.key === 'Enter') handleLogin();
    });

    // ── League Screen ───────────────────────────────────────────────
    async function showLeagueScreen(user) {
      logDrawer.info(`Showing league picker for user_id=${user.user_id}`);
      const screen = document.getElementById('league-screen');
      const list   = document.getElementById('league-list');
      const sub    = document.getElementById('league-subtitle');

      sub.textContent = `Leagues for ${user.display_name}`;
      list.innerHTML  = '<div class="league-loading">⏳ Loading your leagues…</div>';
      screen.classList.remove('hidden');

      try {
        const res     = await apiFetch(`/api/sleeper/leagues/${user.user_id}`);
        const leagues = await res.json();
        logDrawer.info(`Leagues response: ${JSON.stringify(leagues).slice(0, 200)}`);

        if (!leagues || !leagues.length) {
          logDrawer.error('No 2024 leagues found for this user');
          list.innerHTML = `<div class="league-empty">No 2024 NFL leagues found for this account.<br>Make sure you're using your Sleeper username (not email).</div>`;
          return;
        }

        logDrawer.info(`Found ${leagues.length} league(s): ${leagues.map(l => l.name).join(', ')}`);
        _cachedLeagues = leagues;

        // Auto-select the invited league if the user was referred and the
        // league is in their list — saves a click for referred users.
        const invitedLeagueId = localStorage.getItem('ftf_invited_league');
        if (invitedLeagueId) {
          const idx = leagues.findIndex(lg => lg.league_id === invitedLeagueId);
          if (idx >= 0) {
            logDrawer.info(`Auto-selecting invited league: ${leagues[idx].name}`);
            localStorage.removeItem('ftf_invited_league');  // consume the intent
            // Defer slightly so the screen transition is perceptible
            setTimeout(() => selectLeague(idx, null), 200);
            return;
          }
        }

        // Pass only the numeric index — avoids any quoting/escaping issues with league names
        list.innerHTML = leagues.map((lg, i) => `
          <div class="league-item" id="li-${lg.league_id}" onclick="selectLeague(${i}, this)">
            <div class="league-item-icon">🏈</div>
            <div class="league-item-info">
              <div class="league-item-name">${escapeHtml(lg.name || 'Unnamed League')}</div>
              <div class="league-item-meta">${lg.total_rosters || '?'} teams · ${lg.scoring_settings?.rec ? 'PPR' : 'Standard'}</div>
            </div>
            <div class="league-item-arrow">›</div>
          </div>
        `).join('');

      } catch (e) {
        logDrawer.error(`showLeagueScreen fetch error: ${e.message}`);
        list.innerHTML = `<div class="league-empty">Failed to load leagues. Check your connection.</div>`;
      }
    }

    function hideLeagueScreen() {
      document.getElementById('league-screen').classList.add('hidden');
    }

    // ── Ranking Method Selection Screen ──────────────────────────────
    function hideMethodScreen() {
      document.getElementById('ranking-method-screen').classList.add('hidden');
    }

    function _enterMainApp() {
      // Honor ?view=<id> URL param (e.g., navigating back from the tiers page)
      const qsView = new URLSearchParams(window.location.search).get('view');
      const targetView = (qsView && VIEW_TO_NAV[qsView]) ? qsView : 'rank';
      if (qsView) {
        const clean = window.location.pathname + window.location.hash;
        window.history.replaceState({}, document.title, clean);
      }
      loadTrio();
      // Restore auto-confirm toggle state from localStorage
      {
        const acBtn = document.getElementById('auto-confirm-toggle');
        if (acBtn) {
          acBtn.classList.toggle('active', autoConfirmEnabled);
          acBtn.textContent = autoConfirmEnabled ? '\u26A1 I AM SPEED \u2014 ON' : '\u26A1 I AM SPEED \u2014 OFF';
        }
        const submitRow = document.querySelector('.submit-row');
        if (submitRow) submitRow.style.display = autoConfirmEnabled ? 'none' : '';
      }
      renderLeagueSwitcher();
      refreshCoverage();
      initFairnessSlider();
      _startNotifPolling();
      // Agent 6 — show Portfolio subtab only for users with ≥2 synced leagues
      { const _ps = document.getElementById('portfolio-subtab'); if (_ps) _ps.classList.toggle('hidden', (_cachedLeagues || []).length < 2); }
      // Render the scoring toggles now that the main views exist in the DOM
      if (typeof renderScoringToggles === 'function') renderScoringToggles();

      // Route to the requested view (default: Trios under Rank Players)
      if (targetView && targetView !== 'rank') switchView(targetView);
      else _syncNavActive('rank');
    }

    async function selectRankingMethod(method) {
      // Save the chosen method to the backend
      let methodSaved = true;
      try {
        const res = await apiFetch('/api/ranking-method', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ method }),
        });
        if (!res.ok) methodSaved = false;
      } catch (e) {
        methodSaved = false;
        logDrawer.warn(`Failed to save ranking method: ${e.message}`);
      }

      if (!methodSaved) {
        showToast('\u26A0\uFE0F Could not save your choice — you may see this screen again');
      }

      hideMethodScreen();

      if (method === 'trio') {
        // Go to Rank Players → Trios sub-view
        _enterMainApp();
      } else if (method === 'manual') {
        // Go to Rank Players → Manual sub-view
        _enterMainApp();
        switchView('rankings');
      } else if (method === 'tiers') {
        // Navigate to the positional tiers page
        window.location.href = '/positional-tiers.html';
      }
    }

    async function selectLeague(idx, el) {
      const lg         = _cachedLeagues[idx];
      const leagueId   = lg.league_id;
      const leagueName = lg.name || 'Unnamed League';
      logDrawer.action(`League selected: "${leagueName}" (${leagueId})`);
      if (el) {
        el.classList.add('loading');
        const arrow = el.querySelector('.league-item-arrow');
        if (arrow) arrow.textContent = '⏳';
      }

      const user = getSavedUser();
      if (!user) { logout(); return; }

      hideLeagueScreen();
      showInitOverlay('Fetching player database…');

      // 1. Warm the Sleeper player cache (first call downloads ~5MB)
      logDrawer.info('Warming player cache (/api/sleeper/players)…');
      try {
        const pr = await apiFetch('/api/sleeper/players');
        if (!pr.ok) throw new Error(`HTTP ${pr.status}`);
        logDrawer.info('Player cache ready ✓');
      } catch (e) {
        logDrawer.error(`Player cache failed: ${e.message}`);
        hideInitOverlay();
        showToast('⚠️ Failed to load player database');
        el.classList.remove('loading');
        el.querySelector('.league-item-arrow').textContent = '›';
        showLeagueScreen(user);
        return;
      }

      setInitLabel('Fetching rosters…');
      logDrawer.info('Fetching rosters + league users in parallel…');

      // 2. Fetch all rosters + league users in parallel
      let rosters, leagueUsers;
      try {
        const [rRes, uRes] = await Promise.all([
          apiFetch(`/api/sleeper/rosters/${leagueId}`),
          apiFetch(`/api/sleeper/league_users/${leagueId}`),
        ]);
        rosters     = await rRes.json();
        leagueUsers = await uRes.json();
        logDrawer.info(`Rosters: ${rosters?.length ?? 'null'}  League users: ${leagueUsers?.length ?? 'null'}`);
      } catch (e) {
        logDrawer.error(`Roster/user fetch failed: ${e.message}`);
        hideInitOverlay();
        showToast('⚠️ Failed to fetch roster data');
        el.classList.remove('loading');
        el.querySelector('.league-item-arrow').textContent = '›';
        showLeagueScreen(user);
        return;
      }

      // Build username map: owner_id → display_name
      const usernameMap = {};
      for (const u of (leagueUsers || [])) {
        usernameMap[u.user_id] = u.display_name || u.username || u.user_id;
      }

      // 3. Find user's roster
      logDrawer.info(`Looking for roster with owner_id=${user.user_id} among ${rosters?.length} rosters…`);
      const allOwnerIds = (rosters || []).map(r => r.owner_id).join(', ');
      logDrawer.info(`All owner_ids in league: ${allOwnerIds}`);

      const userRoster = (rosters || []).find(r => r.owner_id === user.user_id);
      if (!userRoster) {
        logDrawer.error(`No roster found for owner_id=${user.user_id} — owner_ids present: ${allOwnerIds}`);
        hideInitOverlay();
        showToast('⚠️ Could not find your roster in this league');
        el.classList.remove('loading');
        el.querySelector('.league-item-arrow').textContent = '›';
        showLeagueScreen(user);
        return;
      }

      const userPlayerIds = (userRoster.players || []).filter(Boolean);
      logDrawer.info(`User roster: ${userPlayerIds.length} players — ${userPlayerIds.slice(0,5).join(', ')}…`);

      const opponentRosters = (rosters || [])
        .filter(r => r.owner_id && r.owner_id !== user.user_id)
        .map(r => ({
          user_id:    r.owner_id,
          username:   usernameMap[r.owner_id] || `Team ${r.roster_id}`,
          player_ids: (r.players || []).filter(Boolean),
        }))
        .filter(r => r.player_ids.length > 0);
      logDrawer.info(`Opponent rosters: ${opponentRosters.length}`);

      setInitLabel('Building your rankings…');

      // 4. Call session/init on the backend
      const ok = await initSession(user, { league_id: leagueId, league_name: leagueName }, {
        userPlayerIds,
        opponentRosters,
      });

      hideInitOverlay();

      if (!ok) {
        logDrawer.error('initSession returned false — see log above for details');
        showToast('⚠️ Failed to initialise session');
        el.classList.remove('loading');
        el.querySelector('.league-item-arrow').textContent = '›';
        showLeagueScreen(user);
        return;
      }

      // 5. Persist and show app
      saveLeague({ league_id: leagueId, league_name: leagueName });
      currentLeagueId = leagueId;
      currentUserId   = user.user_id || null;
      renderAccountChip(user);
      logDrawer.info(`✅ League initialised — ${userPlayerIds.length} players imported`);
      showToast(`✅ Roster loaded — ${userPlayerIds.length} players imported`);

      // Check if user has unlocked the trade finder — if not, show ranking method selection
      let showMethodScreen = false;
      try {
        const progRes = await apiFetch('/api/rankings/progress');
        if (progRes.ok) {
          const prog = await progRes.json();
          // Only show the method screen for truly fresh users:
          // - Not yet unlocked (no pending method-based unlock)
          // - Has never chosen a method
          // - Has never ranked a single player (pre-existing users skip this)
          const hasExistingRankings = (prog.total_completed || 0) > 0;
          if (!prog.unlocked && !prog.ranking_method && !hasExistingRankings) {
            showMethodScreen = true;
          }
        }
      } catch (_) { /* proceed to main app on error */ }

      if (showMethodScreen) {
        document.getElementById('ranking-method-screen').classList.remove('hidden');
        // Don't load the main app yet — wait for method selection
      } else {
        _enterMainApp();
      }
    }

    // ── Init Session ────────────────────────────────────────────────
    async function initSession(user, league, rosterData) {
      logDrawer.info(`initSession — league=${league.league_id}  haveRosterData=${!!rosterData}`);

      if (!rosterData) {
        // Page-reload path: need to re-fetch roster data
        logDrawer.info('No rosterData provided — fetching from Sleeper…');
        try {
          const pr = await apiFetch('/api/sleeper/players');
          if (!pr.ok) { logDrawer.error(`Player cache HTTP ${pr.status}`); return false; }
        } catch (e) { logDrawer.error(`Player cache error: ${e.message}`); return false; }

        setInitLabel('Fetching rosters…');
        try {
          const [rRes, uRes] = await Promise.all([
            apiFetch(`/api/sleeper/rosters/${league.league_id}`),
            apiFetch(`/api/sleeper/league_users/${league.league_id}`),
          ]);
          const rosters     = await rRes.json();
          const leagueUsers = await uRes.json();
          const usernameMap = {};
          for (const u of (leagueUsers || [])) {
            usernameMap[u.user_id] = u.display_name || u.username || u.user_id;
          }
          logDrawer.info(`Reload fetch: ${rosters?.length} rosters, owner_ids: ${(rosters||[]).map(r=>r.owner_id).join(', ')}`);

          const userRoster = (rosters || []).find(r => r.owner_id === user.user_id);
          if (!userRoster) {
            logDrawer.error(`No roster for owner_id=${user.user_id} on reload`);
            return false;
          }

          rosterData = {
            userPlayerIds:   (userRoster.players || []).filter(Boolean),
            opponentRosters: (rosters || [])
              .filter(r => r.owner_id && r.owner_id !== user.user_id)
              .map(r => ({
                user_id:    r.owner_id,
                username:   usernameMap[r.owner_id] || `Team ${r.roster_id}`,
                player_ids: (r.players || []).filter(Boolean),
              }))
              .filter(r => r.player_ids.length > 0),
          };
          logDrawer.info(`rosterData built: ${rosterData.userPlayerIds.length} user players, ${rosterData.opponentRosters.length} opponents`);
        } catch (e) { logDrawer.error(`Roster reload error: ${e.message}`); return false; }
      }

      setInitLabel('Initialising rankings engine…');
      const body = {
        user_id:          user.user_id,
        display_name:     user.display_name || '',
        username:         user.display_name || '',
        avatar:           user.avatar_id    || null,
        league_id:        league.league_id,
        league_name:      league.league_name,
        user_player_ids:  rosterData.userPlayerIds,
        opponent_rosters: rosterData.opponentRosters,
        // Referral attribution — captured from the invite URL. Only set on
        // first session_init for a given user (backend upsert_user ignores
        // it on UPDATE).
        invited_by:       localStorage.getItem('ftf_invited_by') || undefined,
      };
      // Track current user globally so invite URLs can carry ?ref={username}
      window._currentUser = user;
      logDrawer.info(`POSTing /api/session/init — ${rosterData.userPlayerIds.length} user_player_ids, ${rosterData.opponentRosters.length} opponents`);

      try {
        const res  = await apiFetch('/api/session/init', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify(body),
        });
        if (!res) return false;  // session expired mid-flight (handled by apiFetch)
        const data = await res.json();
        logDrawer.info(`session/init response: ${JSON.stringify(data).slice(0, 200)}`);
        if (data && data.ok) {
          // Persist session token for future requests
          if (data.token) {
            sessionToken = data.token;
            localStorage.setItem(LS_TOKEN, sessionToken);
            logDrawer.info(`Session token stored (${sessionToken.slice(0, 8)}…)`);
          }
          logDrawer.info(`✅ session/init OK — ${data.player_count} players, ${data.opponents} opponents`);
          // Store the user's roster for the player picker
          if (data.user_roster && Array.isArray(data.user_roster)) {
            _myRoster = data.user_roster;
            logDrawer.info(`Cached ${_myRoster.length} roster players for trade picker`);
            renderPlayerPicker();
          }
          return true;
        }
        logDrawer.error(`session/init returned ok=false: ${JSON.stringify(data)}`);
        return false;
      } catch (e) {
        logDrawer.error(`session/init exception: ${e.message}`);
        return false;
      }
    }

    // ── Init overlay helpers ────────────────────────────────────────
    function showInitOverlay(label) {
      setInitLabel(label);
      document.getElementById('init-overlay').classList.remove('hidden');
    }
    function hideInitOverlay() {
      document.getElementById('init-overlay').classList.add('hidden');
    }
    function setInitLabel(text) {
      document.getElementById('init-label').textContent = text;
    }

    // ── Account chip ────────────────────────────────────────────────
    function renderAccountChip(user) {
      const league = getSavedLeague();
      const initials = (user.display_name || '?').slice(0, 2).toUpperCase();
      const avatarUrl = user.avatar_id
        ? `https://sleepercdn.com/avatars/thumbs/${user.avatar_id}`
        : null;

      const avatarHtml = avatarUrl
        ? `<img src="${avatarUrl}" alt="" onerror="this.style.display='none'">`
        : initials;

      const leagueSection = league
        ? `<div class="account-menu-league">League</div>
           <div class="account-menu-item" style="cursor:default;color:var(--muted)">
             🏈 ${escapeHtml(league.league_name || 'My League')}
           </div>
           <div class="account-menu-item" onclick="switchLeague()">↔ Switch league</div>
           <div class="account-menu-divider"></div>`
        : '';

      document.getElementById('account-chip-container').innerHTML = `
        <div class="account-chip">
          <div class="account-avatar">${avatarHtml}</div>
          <div class="account-name">${escapeHtml(user.display_name || 'Unknown')}</div>
          <div class="account-menu">
            ${leagueSection}
            <div class="account-menu-item danger" onclick="logout()">⎋ Log out</div>
          </div>
        </div>
      `;
    }

    async function switchLeague() {
      clearSavedLeague();
      currentLeagueId = null;
      const user = getSavedUser();
      if (user) showLeagueScreen(user);
    }

    // ── Utilities ───────────────────────────────────────────────────
    function escapeHtml(s) {
      return String(s)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }


    // ═══════════════════════════════════════════════════════════════
    //  RANKING APP
    // ═══════════════════════════════════════════════════════════════

    const SIDES = ['a', 'b', 'c'];

    let currentPosition = 'QB';
    let currentTrio     = null;
    let selectionOrder  = [];
    let locked          = false;
    let autoConfirmEnabled = localStorage.getItem('autoConfirm') === 'true';

    function toggleAutoConfirm() {
      autoConfirmEnabled = !autoConfirmEnabled;
      localStorage.setItem('autoConfirm', autoConfirmEnabled);
      const btn = document.getElementById('auto-confirm-toggle');
      if (btn) {
        btn.classList.toggle('active', autoConfirmEnabled);
        btn.textContent = autoConfirmEnabled ? '⚡ I AM SPEED — ON' : '⚡ I AM SPEED — OFF';
      }
      // When turning on auto-confirm, hide the submit button row
      const submitRow = document.querySelector('.submit-row');
      if (submitRow) {
        submitRow.style.display = autoConfirmEnabled ? 'none' : '';
      }
    }

    function switchPosition(pos, btn) {
      currentPosition = pos;
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      selectionOrder = [];
      locked = false;
      loadTrio();
    }

    // ── Load next trio ──────────────────────────────────────────────
    async function loadTrio() {
      if (locked) return;
      resetCards();
      setCardsLoading();

      try {
        const res  = await apiFetch(`/api/trio?position=${currentPosition || ''}`);
        const data = await res.json();
        if (data.error) { showToast('⚠️ ' + data.error); return; }
        currentTrio = data;
        renderCard('a', data.player_a);
        renderCard('b', data.player_b);
        renderCard('c', data.player_c);
        await loadProgress();
      } catch {
        showToast('Could not reach server — is server.py running?');
      }
    }

    // ── Card click ──────────────────────────────────────────────────
    function selectCard(side) {
      if (locked || !currentTrio) return;

      // ── Undo: clicking an already-ranked card removes it + later picks ──
      const existingIdx = selectionOrder.indexOf(side);
      if (existingIdx !== -1) {
        const removed = selectionOrder.splice(existingIdx);
        removed.forEach(s => {
          const c = document.getElementById('card-' + s);
          c.classList.remove('ranked-1', 'ranked-2', 'ranked-3');
          document.getElementById('badge-' + s).textContent = '';
        });
        document.getElementById('submit-btn').classList.remove('ready');
        _updateTrioInstruction();
        return;
      }

      // ── Add: assign this card the next rank ──
      selectionOrder.push(side);
      const rank = selectionOrder.length;
      const card = document.getElementById('card-' + side);
      card.classList.remove('ranked-1', 'ranked-2', 'ranked-3');
      card.classList.add('ranked-' + rank);
      document.getElementById('badge-' + side).textContent = String(rank);
      _updateTrioInstruction();

      // ── Speed mode (I AM SPEED): auto-rank the 3rd & auto-submit after the 2nd pick ──
      if (autoConfirmEnabled && selectionOrder.length === 2) {
        const last = SIDES.find(s => !selectionOrder.includes(s));
        selectionOrder.push(last);
        const lastCard = document.getElementById('card-' + last);
        lastCard.classList.add('ranked-3');
        document.getElementById('badge-' + last).textContent = '3';
        document.getElementById('submit-btn').classList.add('ready');
        submitRanking();
        return;
      }

      // ── Manual mode: enable submit once all three have been explicitly ranked ──
      if (selectionOrder.length === 3) {
        document.getElementById('submit-btn').classList.add('ready');
      }
    }

    function _updateTrioInstruction() {
      const instr = document.getElementById('instruction');
      if (!instr) return;
      const remaining = 3 - selectionOrder.length;
      if      (remaining === 3) instr.innerHTML = 'Tap players in order of preference — <strong>best first</strong>';
      else if (remaining === 2) instr.innerHTML = 'Good — now tap your <strong>2nd choice</strong>';
      else if (remaining === 1) instr.innerHTML = 'Last one — tap your <strong>3rd choice</strong>';
      else                      instr.innerHTML = '✓ All ranked — confirm when ready';
    }

    // ── Submit ranking ──────────────────────────────────────────────
    async function submitRanking() {
      if (locked || selectionOrder.length < 3 || !currentTrio) return;
      locked = true;
      document.getElementById('submit-btn').classList.remove('ready');

      const players = { a: currentTrio.player_a, b: currentTrio.player_b, c: currentTrio.player_c };
      const ranked  = selectionOrder.map(s => players[s].id);

      try {
        const res  = await apiFetch('/api/rank3', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ ranked }),
        });
        const data = await res.json();

        // Stale trio: service was rebuilt between display and submit.
        // Reload a fresh trio so the user can rank again.
        if (data.error === 'stale_trio') {
          showToast('↻ Player data refreshed — please rank these players again');
          locked = false;
          loadTrio();
          return;
        }

        if (data.error) { showToast('⚠️ ' + data.error); locked = false; return; }

        updateProgress(data);

        if (data.threshold_met && data.interaction_count === data.threshold) {
          _celebrationActive = true;
          showRankingCelebration(currentPosition);
        }
        // Re-check the Find a Trade ranking gate (updates live if that tab is open)
        _onRankingSwipeComplete();
      } catch {
        showToast('Submit failed — check server connection');
      }

      setTimeout(() => {
        selectionOrder = [];
        locked = false;
        if (!_celebrationActive) loadTrio();
      }, 350);
    }

    // ── Ranking celebration modal ─────────────────────────────────────
    const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE'];
    let _celebrationActive = false;

    async function showRankingCelebration(completedPosition) {
      // Fetch latest progress to determine which positions are done
      let progress;
      try {
        const res = await apiFetch('/api/rankings/progress');
        if (!res.ok) return;
        progress = await res.json();
      } catch (_) { return; }

      const threshold = progress.threshold || 10;
      const completedPositions = POSITION_ORDER.filter(p => (progress[p] || 0) >= threshold);
      const allDone = completedPositions.length === 4;

      const overlay = document.getElementById('celebration-overlay');
      const emoji   = document.getElementById('celebration-emoji');
      const title   = document.getElementById('celebration-title');
      const sub     = document.getElementById('celebration-sub');
      const actions = document.getElementById('celebration-actions');

      // Build actions safely via DOM API — no string interpolation into onclick
      actions.innerHTML = '';
      const makeBtn = (label, cls, handler) => {
        const b = document.createElement('button');
        b.className = 'celebration-btn ' + cls;
        b.textContent = label;
        b.addEventListener('click', handler);
        return b;
      };

      if (allDone) {
        emoji.textContent = '\uD83C\uDFC6';  // trophy
        title.textContent = 'All positions ranked!';
        sub.textContent   = 'Your dynasty rankings are fully established. Time to find some trades!';
        actions.appendChild(makeBtn(`Continue ranking ${completedPosition}`, 'secondary', closeCelebration));
        actions.appendChild(makeBtn('Give me some offers \u2192', 'primary', () => {
          closeCelebration();
          switchView('trades');
        }));
      } else {
        const nextPos = POSITION_ORDER.find(p => !completedPositions.includes(p));
        emoji.textContent = '\uD83C\uDF89';  // party popper
        title.textContent = `${completedPosition} rankings complete!`;
        sub.textContent   = `${completedPositions.length}/4 positions done.${nextPos ? ` ${nextPos} is next.` : ''}`;
        actions.appendChild(makeBtn(`Keep ranking ${completedPosition}`, 'secondary', closeCelebration));
        if (nextPos) {
          actions.appendChild(makeBtn(`Proceed to ${nextPos} \u2192`, 'primary', () => {
            closeCelebration();
            switchToPosition(nextPos);
          }));
        }
      }

      overlay.classList.remove('hidden');
    }

    function closeCelebration() {
      document.getElementById('celebration-overlay').classList.add('hidden');
      _celebrationActive = false;
      loadTrio();
    }

    function switchToPosition(pos) {
      currentPosition = pos;
      document.querySelectorAll('.tabs .tab').forEach(t => {
        t.classList.toggle('active', t.textContent.trim() === pos);
      });
      loadTrio();
    }

    // ── Render helpers ──────────────────────────────────────────────
    function renderCard(side, p) {
      const pos  = p.position.toLowerCase();
      const card = document.getElementById('card-' + side);
      // Picks now carry a real position (RB/WR/TE) so they're mixed into
      // position pools — use pick_value as the discriminator for rendering.
      const isPickCard = p.pick_value != null;
      const cardPos    = isPickCard ? 'pick' : pos;
      const badgeLabel = isPickCard ? 'PICK' : p.position;

      card.className = 'card ' + cardPos;

      document.getElementById('posbadge-' + side).className = 'pos-badge ' + cardPos;
      document.getElementById('posbadge-' + side).textContent = badgeLabel;

      const extraEl = document.getElementById('extra-' + side);

      if (isPickCard) {
        // Pick card layout
        document.getElementById('name-' + side).textContent = p.name;
        document.getElementById('team-' + side).textContent = p.team || '';  // original team
        const pickVal = p.pick_value != null ? p.pick_value.toFixed(1) : '—';
        document.getElementById('meta-' + side).textContent = `Dynasty value: ${pickVal}`;
        if (extraEl) {
          const tier = buildTierBadge(p);
          extraEl.innerHTML = tier;
        }
        return;
      }

      // Regular player card
      document.getElementById('name-' + side).textContent  = p.name;
      document.getElementById('team-' + side).textContent  = p.team || 'FA';
      document.getElementById('meta-' + side).textContent  =
        `Age ${p.age} · ${p.years_experience} yr${p.years_experience !== 1 ? 's' : ''} exp`;

      // Extra row: dynasty context + depth chart + rookie badge + injury
      if (extraEl) {
        const parts = [];
        parts.push(buildDcBadge(p));
        parts.push(buildRookieBadge(p));
        parts.push(buildInjuryBadge(p.injury_status));
        const tier  = buildTierBadge(p);
        const stage = buildCareerBadge(p);
        if (tier)  parts.push(tier);
        if (stage) parts.push(stage);
        if (p.college) parts.push(`<span style="color:var(--muted)">${escapeHtml(p.college)}</span>`);
        extraEl.innerHTML = parts.filter(Boolean).join('');
      }
    }

    function setCardsLoading() {
      SIDES.forEach(s => {
        document.getElementById('name-' + s).textContent = 'Loading…';
        document.getElementById('team-' + s).textContent = '';
        document.getElementById('meta-' + s).textContent = '';
        document.getElementById('posbadge-' + s).textContent = '';
        const extraEl = document.getElementById('extra-' + s);
        if (extraEl) extraEl.innerHTML = '';
      });
    }

    function resetCards() {
      selectionOrder = [];
      SIDES.forEach(s => {
        const card = document.getElementById('card-' + s);
        card.classList.remove('ranked-1', 'ranked-2', 'ranked-3');
        document.getElementById('badge-' + s).textContent = '';
      });
      document.getElementById('submit-btn').classList.remove('ready');
      document.getElementById('instruction').innerHTML =
        'Tap players in order of preference — <strong>best first</strong>';
    }

    // ── Progress ────────────────────────────────────────────────────
    async function loadProgress() {
      const res  = await apiFetch(`/api/progress?position=${currentPosition || ''}`);
      const data = await res.json();
      updateProgress(data);
      // Also refresh the overall unlock bar
      updateUnlockBar();
    }

    function updateProgress(data) {
      const count     = data.interaction_count;
      const threshold = data.threshold;
      const pct       = Math.min(100, Math.round(count / threshold * 100));

      document.getElementById('progress-label').textContent =
        `${count} / ${threshold} rankings`;
      document.getElementById('progress-fill').style.width = pct + '%';

      const status = document.getElementById('progress-status');
      const fill   = document.getElementById('progress-fill');

      if (data.threshold_met) {
        status.className   = 'met';
        status.textContent = '✓ Rankings established';
        fill.classList.add('complete');
      } else {
        status.className   = '';
        status.textContent = `${threshold - count} to go`;
        fill.classList.remove('complete');
      }
    }

    // ── Unlock progress bar (segmented) ──────────────────────────────
    async function updateUnlockBar() {
      const progress = await fetchRankingProgress(true);
      if (!progress) return;
      renderUnlockBar(progress);
    }

    function renderUnlockBar(progress) {
      const wrap = document.getElementById('unlock-bar-wrap');
      if (!wrap) return;

      const threshold = progress.threshold || 10;
      const positions = ['QB', 'RB', 'WR', 'TE'];

      // Show/hide the "Overall" ranking tab based on unlock status
      const overallTab = document.getElementById('overall-rank-tab');
      if (overallTab) {
        overallTab.classList.toggle('hidden', !progress.unlocked);
      }

      // Hide once fully unlocked
      if (progress.unlocked) {
        wrap.classList.add('unlocked');
        return;
      }
      wrap.classList.remove('unlocked');

      let totalDone = 0;
      const totalRequired = threshold * positions.length;

      positions.forEach(pos => {
        const count  = Math.min(progress[pos] || 0, threshold);
        totalDone   += count;
        const pct    = Math.round(count / threshold * 100);
        const done   = count >= threshold;

        const fill  = document.getElementById(`unlock-fill-${pos}`);
        const label = document.getElementById(`unlock-label-${pos}`);
        if (fill) fill.style.width = pct + '%';
        if (label) {
          label.innerHTML = `${pos} <span class="unlock-label-count">${count}/${threshold}</span>`;
          label.classList.toggle('done', done);
        }
      });

      const overallPct = Math.round(totalDone / totalRequired * 100);
      const pctEl = document.getElementById('unlock-bar-pct');
      if (pctEl) pctEl.textContent = overallPct + '%';

      // Update title based on progress
      const titleEl = wrap.querySelector('.unlock-bar-title');
      if (titleEl) {
        titleEl.textContent = progress.unlocked
          ? '✅ Find a Trade unlocked!'
          : `🔓 Find a Trade`;
      }
    }

    // ── Rankings panel ──────────────────────────────────────────────
    /** Fetch all-position rankings to populate the ELO map for player picker sort order. */
    async function refreshPlayerEloMap() {
      try {
        const res = await apiFetch('/api/rankings?position=');
        if (!res.ok) return;
        const data = await res.json();
        if (data.rankings) {
          for (const r of data.rankings) {
            _playerEloMap[r.id] = r.elo;
          }
        }
      } catch (_) { /* non-critical — picker falls back to search_rank */ }
    }

    async function openRankings() {
      const res  = await apiFetch(`/api/rankings?position=${currentPosition}`);
      const data = await res.json();

      document.getElementById('panel-title').textContent =
        `${currentPosition} Rankings`;

      const list = document.getElementById('rankings-list');
      if (!data.rankings || data.rankings.length === 0) {
        list.innerHTML = `<div class="panel-empty">No rankings yet — start ranking!</div>`;
      } else {
        // Update ELO map while we have the data
        for (const r of data.rankings) _playerEloMap[r.id] = r.elo;
        list.innerHTML = data.rankings.map(r => {
          const dcBadge  = buildDcBadge(r);
          const injBadge = buildInjuryBadge(r.injury_status);
          const rkBadge  = buildRookieBadge(r);
          const extraBits = [dcBadge, rkBadge, injBadge].filter(Boolean).join('');
          return `
          <div class="rank-row">
            <div class="rank-num">${r.rank}</div>
            <div class="pos-badge ${r.position.toLowerCase()}">${r.position}</div>
            <div class="rank-name">${escapeHtml(r.name)}${extraBits ? `<span style="margin-left:5px">${extraBits}</span>` : ''}</div>
            <div class="rank-team">${escapeHtml(r.team || 'FA')}</div>
            <div class="rank-wl">${r.wins}W / ${r.losses}L</div>
            <div class="rank-elo">${r.elo.toFixed(0)}</div>
          </div>`;
        }).join('');
      }
      document.getElementById('overlay').classList.add('open');
    }

    function closeRankings(event) {
      if (!event || event.target === document.getElementById('overlay')) {
        document.getElementById('overlay').classList.remove('open');
      }
    }

    // ── Rankings table (editable tab) ──────────────────────────────
    let _rankingsTablePos = null;   // null = Overall, 'QB'/'RB'/'WR'/'TE' = position
    let _rankingsData     = [];     // current data backing the table
    let _draggedRow       = null;

    function switchRankingsPos(pos, btn) {
      document.querySelectorAll('.rankings-pos-filters .tab').forEach(t => t.classList.remove('active'));
      if (btn) btn.classList.add('active');
      _rankingsTablePos = pos === 'ALL' ? null : pos;
      loadRankingsTable();
    }

    async function loadRankingsTable() {
      const posParam = _rankingsTablePos || '';
      try {
        const res = await apiFetch(`/api/rankings?position=${posParam}`);
        if (!res.ok) return;
        const data = await res.json();
        _rankingsData = data.rankings || [];
        // Update ELO map
        for (const r of _rankingsData) _playerEloMap[r.id] = r.elo;
        renderRankingsTable();
      } catch (_) { /* ignore */ }
    }

    function renderRankingsTable() {
      const tbody  = document.getElementById('rankings-tbody');
      const empty  = document.getElementById('rankings-table-empty');
      if (!tbody) return;

      if (!_rankingsData.length) {
        tbody.innerHTML = '';
        if (empty) empty.classList.remove('hidden');
        return;
      }
      if (empty) empty.classList.add('hidden');

      tbody.innerHTML = _rankingsData.map((r, i) => {
        const pos = (r.position || '?').toLowerCase();
        return `<tr draggable="true" data-player-id="${r.id}" data-index="${i}">
          <td class="rt-rank-col"><span class="rt-editable-cell" contenteditable="true"
                data-player-id="${r.id}">${i + 1}</span></td>
          <td class="rt-drag-col" title="Drag to reorder">\u2807</td>
          <td class="rt-player-name">${escapeHtml(r.name || 'Unknown')}</td>
          <td><span class="pos-badge ${pos}">${(r.position || '?').toUpperCase()}</span></td>
          <td>${r.age || ''}</td>
          <td>${escapeHtml(r.team || 'FA')}</td>
          <td style="color:var(--muted)">${r.elo ? r.elo.toFixed(0) : ''}</td>
        </tr>`;
      }).join('');

      // Attach drag-and-drop handlers
      tbody.querySelectorAll('tr').forEach(row => {
        row.addEventListener('dragstart', _rtDragStart);
        row.addEventListener('dragover',  _rtDragOver);
        row.addEventListener('drop',      _rtDrop);
        row.addEventListener('dragend',   _rtDragEnd);
      });

      // Attach editable cell handlers
      tbody.querySelectorAll('.rt-editable-cell').forEach(cell => {
        cell.addEventListener('blur',    _rtOnRankEdit);
        cell.addEventListener('keydown', e => {
          if (e.key === 'Enter') { e.preventDefault(); cell.blur(); }
        });
      });
    }

    // ── Drag and drop ───────────────────────────────────────────────
    function _rtDragStart(e) {
      _draggedRow = e.target.closest('tr');
      if (_draggedRow) _draggedRow.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    }

    function _rtDragOver(e) {
      e.preventDefault();
      const row = e.target.closest('tr');
      if (!row || row === _draggedRow) return;
      const tbody = row.parentNode;
      // Clear other indicators
      tbody.querySelectorAll('.drag-over-top,.drag-over-bottom').forEach(r => {
        r.classList.remove('drag-over-top', 'drag-over-bottom');
      });
      const rect = row.getBoundingClientRect();
      const mid  = rect.top + rect.height / 2;
      if (e.clientY < mid) {
        row.classList.add('drag-over-top');
        tbody.insertBefore(_draggedRow, row);
      } else {
        row.classList.add('drag-over-bottom');
        tbody.insertBefore(_draggedRow, row.nextSibling);
      }
    }

    function _rtDrop(e) { e.preventDefault(); }

    function _rtDragEnd() {
      if (_draggedRow) _draggedRow.classList.remove('dragging');
      _draggedRow = null;
      // Clear all drag indicators
      document.querySelectorAll('.drag-over-top,.drag-over-bottom').forEach(r => {
        r.classList.remove('drag-over-top', 'drag-over-bottom');
      });
      _rtRenumberAndSubmit();
    }

    // ── Rank editing ────────────────────────────────────────────────
    function _rtOnRankEdit(e) {
      const cell     = e.target;
      const newRank  = parseInt(cell.textContent.trim(), 10);
      const playerId = cell.dataset.playerId;
      if (isNaN(newRank) || newRank < 1) {
        renderRankingsTable();  // revert
        return;
      }
      const tbody = document.getElementById('rankings-tbody');
      const rows  = Array.from(tbody.querySelectorAll('tr'));
      const currentRow = rows.find(r => r.dataset.playerId === playerId);
      if (!currentRow) return;

      // Remove and insert at new position
      tbody.removeChild(currentRow);
      const targetIndex = Math.min(newRank - 1, tbody.children.length);
      const targetRow   = tbody.children[targetIndex];
      if (targetRow) {
        tbody.insertBefore(currentRow, targetRow);
      } else {
        tbody.appendChild(currentRow);
      }
      _rtRenumberAndSubmit();
    }

    // ── Renumber visible ranks and submit reorder to backend ────────
    // Debounce guard — if a save is already in flight, queue exactly one more
    // attempt to capture the final state after rapid reorders.
    let _rtInFlight = false;
    let _rtQueued   = false;

    function _rtRenumberAndSubmit() {
      const tbody = document.getElementById('rankings-tbody');
      const rows  = Array.from(tbody.querySelectorAll('tr'));

      // Always update visible rank numbers immediately for responsive UI
      rows.forEach((r, i) => {
        const editCell = r.querySelector('.rt-editable-cell');
        if (editCell) editCell.textContent = i + 1;
      });

      // If a save is in flight, just mark that another one is needed
      if (_rtInFlight) { _rtQueued = true; return; }

      _rtSubmitNow();
    }

    function _rtSubmitNow() {
      const tbody = document.getElementById('rankings-tbody');
      const rows  = Array.from(tbody.querySelectorAll('tr'));
      const orderedIds = rows.map(r => r.dataset.playerId);

      _rtInFlight = true;
      apiFetch('/api/rankings/reorder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          position: _rankingsTablePos || null,
          ordered_ids: orderedIds,
        }),
      })
        .then(() => {
          if (_rtQueued) {
            // A reorder happened while we were saving — send the latest state
            _rtQueued = false;
            _rtInFlight = false;
            _rtSubmitNow();
          } else {
            _rtInFlight = false;
            loadRankingsTable();
          }
        })
        .catch(() => {
          _rtInFlight = false;
          _rtQueued   = false;
          showToast('Failed to save reorder');
        });
    }

    // ── Rookie board ────────────────────────────────────────────────
    let rookieData = null;   // cached { grouped: {QB:[],RB:[],WR:[],TE:[]}, total: N }
    let rookieFilter = 'ALL';

    async function openRookieBoard() {
      document.getElementById('rookie-overlay').classList.add('open');
      if (!rookieData) {
        document.getElementById('rookie-list').innerHTML =
          '<div class="panel-empty">Loading rookies…</div>';
        try {
          const res  = await apiFetch('/api/rookies');
          rookieData = await res.json();
        } catch {
          document.getElementById('rookie-list').innerHTML =
            '<div class="panel-empty">Failed to load rookie data.</div>';
          return;
        }
      }
      renderRookieList();
    }

    function closeRookieBoard(event) {
      if (!event || event.target === document.getElementById('rookie-overlay')) {
        document.getElementById('rookie-overlay').classList.remove('open');
      }
    }

    function filterRookies(pos, btn) {
      rookieFilter = pos;
      document.querySelectorAll('.rookie-filter-tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      renderRookieList();
    }

    function renderRookieList() {
      if (!rookieData) return;
      const listEl = document.getElementById('rookie-list');
      const grouped = rookieData.grouped || {};
      const positions = ['QB', 'RB', 'WR', 'TE'];
      let html = '';
      let globalRank = 0;

      // Flatten + sort all for "ALL" view
      if (rookieFilter === 'ALL') {
        const all = positions.flatMap(pos => (grouped[pos] || []).map(r => ({...r, _pos: pos})));
        // sort by search_rank (nulls last)
        all.sort((a, b) => {
          if (a.search_rank == null && b.search_rank == null) return 0;
          if (a.search_rank == null) return 1;
          if (b.search_rank == null) return -1;
          return a.search_rank - b.search_rank;
        });
        if (all.length === 0) {
          listEl.innerHTML = '<div class="panel-empty">No rookie data available yet.</div>';
          return;
        }
        html = all.map((r, i) => rookieRowHTML(r, i + 1)).join('');
      } else {
        const players = grouped[rookieFilter] || [];
        if (players.length === 0) {
          listEl.innerHTML = `<div class="panel-empty">No ${rookieFilter} rookies found.</div>`;
          return;
        }
        html = `<div class="rookie-section-title">${rookieFilter}</div>`;
        html += players.map((r, i) => rookieRowHTML(r, i + 1)).join('');
      }
      listEl.innerHTML = html;
    }

    function rookieRowHTML(r, rank) {
      const pos      = (r.position || '').toLowerCase();
      const team     = escapeHtml(r.team || 'Undrafted');
      const age      = r.age ? `Age ${r.age}` : '';
      const college  = r.college ? escapeHtml(r.college) : '';
      const tier     = buildTierBadge(r);
      const metaBits = [team, age, college].filter(Boolean).join(' · ');
      return `<div class="rookie-row">
        <div class="rookie-rank">${rank}</div>
        <div class="rookie-info">
          <div class="rookie-name">${escapeHtml(r.name || '?')}</div>
          <div class="rookie-meta">
            <span class="pos-badge ${pos}">${r.position || '?'}</span>
            ${tier}
            <span>${metaBits}</span>
          </div>
        </div>
      </div>`;
    }

    // ── Toast ───────────────────────────────────────────────────────
    let toastTimer;
    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => t.classList.remove('show'), 3000);
    }

    // ── Top-level view switch ────────────────────────────────────────
    // ── League Switcher ─────────────────────────────────────────────

    function renderLeagueSwitcher() {
      const row    = document.getElementById('league-switcher-row');
      const select = document.getElementById('league-select');
      // Agent 6 — mirror league count to Portfolio subtab visibility
      { const _ps = document.getElementById('portfolio-subtab'); if (_ps) _ps.classList.toggle('hidden', (_cachedLeagues || []).length < 2); }
      if (!row || !select) return;

      // Only show the switcher when there are multiple leagues to choose from
      if (_cachedLeagues.length < 2) { row.style.display = 'none'; return; }

      // Re-build options (idempotent — safe to call multiple times)
      select.innerHTML = _cachedLeagues.map((lg, i) =>
        `<option value="${i}">${escapeHtml(lg.name || 'Unnamed League')}</option>`
      ).join('');

      // Pre-select the active league
      const activeIdx = _cachedLeagues.findIndex(lg => lg.league_id === currentLeagueId);
      if (activeIdx >= 0) select.selectedIndex = activeIdx;

      row.style.display = 'flex';
      document.getElementById('league-switch-status').textContent = '';
    }

    async function switchToLeague(idx) {
      const lg = _cachedLeagues[idx];
      if (!lg || lg.league_id === currentLeagueId) return;

      const select   = document.getElementById('league-select');
      const status   = document.getElementById('league-switch-status');
      const genBtn   = document.getElementById('gen-btn');
      const user     = getSavedUser();
      if (!user) { logout(); return; }

      logDrawer.action(`League switcher → "${lg.name}" (${lg.league_id})`);
      select.disabled = true;
      if (genBtn) genBtn.disabled = true;
      status.textContent = '⏳ Switching…';

      // Warm player cache (no-op if already loaded), then fetch new rosters
      try {
        const pr = await apiFetch('/api/sleeper/players');
        if (!pr.ok) throw new Error(`Player cache HTTP ${pr.status}`);
      } catch (e) {
        logDrawer.error(`League switch — player cache failed: ${e.message}`);
        status.textContent = '⚠️ Failed';
        select.disabled = false;
        if (genBtn) genBtn.disabled = false;
        // Revert visual selection to current league
        const revertIdx = _cachedLeagues.findIndex(l => l.league_id === currentLeagueId);
        if (revertIdx >= 0) select.selectedIndex = revertIdx;
        showToast('⚠️ Could not load player database');
        return;
      }

      let rosters, leagueUsers;
      try {
        const [rRes, uRes] = await Promise.all([
          apiFetch(`/api/sleeper/rosters/${lg.league_id}`),
          apiFetch(`/api/sleeper/league_users/${lg.league_id}`),
        ]);
        rosters     = await rRes.json();
        leagueUsers = await uRes.json();
        logDrawer.info(`Switch roster fetch: ${rosters?.length} rosters, ${leagueUsers?.length} users`);
      } catch (e) {
        logDrawer.error(`League switch — roster fetch failed: ${e.message}`);
        status.textContent = '⚠️ Failed';
        select.disabled = false;
        if (genBtn) genBtn.disabled = false;
        const revertIdx = _cachedLeagues.findIndex(l => l.league_id === currentLeagueId);
        if (revertIdx >= 0) select.selectedIndex = revertIdx;
        showToast('⚠️ Failed to fetch roster data');
        return;
      }

      const usernameMap = {};
      for (const u of (leagueUsers || [])) {
        usernameMap[u.user_id] = u.display_name || u.username || u.user_id;
      }

      const userRoster = (rosters || []).find(r => r.owner_id === user.user_id);
      if (!userRoster) {
        logDrawer.error(`League switch — no roster found for owner_id=${user.user_id}`);
        status.textContent = '⚠️ No roster';
        select.disabled = false;
        if (genBtn) genBtn.disabled = false;
        const revertIdx = _cachedLeagues.findIndex(l => l.league_id === currentLeagueId);
        if (revertIdx >= 0) select.selectedIndex = revertIdx;
        showToast('⚠️ Could not find your roster in this league');
        return;
      }

      const userPlayerIds = (userRoster.players || []).filter(Boolean);
      const opponentRosters = (rosters || [])
        .filter(r => r.owner_id && r.owner_id !== user.user_id)
        .map(r => ({
          user_id:    r.owner_id,
          username:   usernameMap[r.owner_id] || `Team ${r.roster_id}`,
          player_ids: (r.players || []).filter(Boolean),
        }))
        .filter(r => r.player_ids.length > 0);

      status.textContent = '⏳ Loading…';
      const ok = await initSession(
        user,
        { league_id: lg.league_id, league_name: lg.name },
        { userPlayerIds, opponentRosters }
      );

      select.disabled = false;
      if (genBtn) genBtn.disabled = false;

      if (!ok) {
        logDrawer.error(`League switch — initSession failed for ${lg.league_id}`);
        status.textContent = '⚠️ Failed';
        const revertIdx = _cachedLeagues.findIndex(l => l.league_id === currentLeagueId);
        if (revertIdx >= 0) select.selectedIndex = revertIdx;
        showToast('⚠️ Failed to switch league');
        return;
      }

      // Commit the switch — clear pinned players since roster changed
      currentLeagueId = lg.league_id;
      _pinnedGivePlayers.clear();
      renderPlayerPicker();
      saveLeague({ league_id: lg.league_id, league_name: lg.name });
      renderAccountChip(user);
      status.textContent = '✓ Switched';
      setTimeout(() => { status.textContent = ''; }, 2000);
      logDrawer.info(`✅ League switched to "${lg.name}"`);
      showToast(`✅ Switched to ${lg.name}`);

      // Clear stale trade cards and reset ranking gate for new league
      document.getElementById('trades-list').innerHTML =
        `<div class="trades-empty"><strong>League switched</strong>Hit "Find a Trade" to see trade ideas for ${escapeHtml(lg.name)}.</div>`;
      const _gateEl = document.getElementById('trades-gate');
      const _wrapEl = document.getElementById('trades-wrap');
      if (_gateEl) { _gateEl.classList.remove('active', 'unlocking'); _gateEl.innerHTML = ''; }
      if (_wrapEl) { _wrapEl.classList.remove('gate-active'); }
      refreshCoverage();

      // Load per-league fairness preference and reset outlook
      initFairnessSlider();
      currentOutlook            = null;
      currentAcquirePositions   = [];
      currentTradeAwayPositions = [];
      invalidateRankingProgressCache();
      updateOutlookBadge();
      checkOutlookPrompt();
    }

    // ── Leaguemate ranking coverage ─────────────────────────────────────
    async function refreshCoverage() {
      const leagueId = currentLeagueId;
      if (!leagueId || leagueId === 'league_demo') {
        document.getElementById('coverage-row').style.display = 'none';
        return;
      }

      try {
        const res  = await apiFetch(`/api/league/coverage?league_id=${leagueId}`);
        const data = await res.json();
        if (data.error || data.total === undefined) {
          document.getElementById('coverage-row').style.display = 'none';
          return;
        }

        const { ranked, total } = data;
        const pct = total > 0 ? Math.round(ranked / total * 100) : 0;
        const bar = document.getElementById('coverage-bar');
        const lbl = document.getElementById('coverage-label');
        const row = document.getElementById('coverage-row');

        bar.style.width = pct + '%';

        if (ranked === 0) {
          lbl.innerHTML = `<span class="coverage-none">0 of ${total} leaguemates ranked — trades use estimates</span>`;
        } else if (ranked === total) {
          lbl.innerHTML = `<span class="coverage-real">All ${total} leaguemates ranked ✓</span>`;
        } else {
          lbl.innerHTML = `<span class="coverage-real">${ranked}</span> of ${total} leaguemates ranked`;
        }

        row.style.display = 'flex';
        logDrawer.info(`Coverage: ${ranked}/${total} leaguemates have submitted rankings`);
      } catch (e) {
        logDrawer.error(`Coverage fetch failed: ${e.message}`);
        document.getElementById('coverage-row').style.display = 'none';
      }
    }

    // ── Ranking Gate ─────────────────────────────────────────────────────

    let _rankingProgress      = null;  // cached progress object
    let _rankingProgressLeague = null; // which league the cache belongs to

    /** Fetch /api/rankings/progress; cache per league. force=true busts cache. */
    async function fetchRankingProgress(force = false) {
      if (!force && _rankingProgress && _rankingProgressLeague === currentLeagueId) {
        return _rankingProgress;
      }
      try {
        const res  = await apiFetch('/api/rankings/progress');
        const data = await res.json();
        if (!data.error) {
          _rankingProgress       = data;
          _rankingProgressLeague = currentLeagueId;
        }
      } catch { /* network error — keep old cache */ }
      return _rankingProgress;
    }

    /** Invalidate the progress cache (call on league change or logout). */
    function invalidateRankingProgressCache() {
      _rankingProgress       = null;
      _rankingProgressLeague = null;
    }

    /** Build one position row for the locked state screen. */
    function _gatePositionRow(pos, count, threshold) {
      const capped = Math.min(count, threshold);
      const pct    = Math.round(capped / threshold * 100);
      const done   = count >= threshold;
      return `
        <div class="gate-pos-row">
          <span class="gate-pos-label">${pos}</span>
          <div class="gate-pos-bar-wrap">
            <div class="gate-pos-bar-fill${done ? ' complete' : ''}"
                 style="width:${pct}%"></div>
          </div>
          <span class="gate-pos-count">${capped}&nbsp;/&nbsp;${threshold}</span>
          <span class="gate-pos-check">${done ? '✓' : ''}</span>
        </div>`;
    }

    /** Render (or refresh) the locked gate screen inside #trades-gate. */
    function _showTradesGate(progress) {
      const wrap = document.getElementById('trades-wrap');
      const gate = document.getElementById('trades-gate');
      if (!wrap || !gate) return;

      const { QB = 0, RB = 0, WR = 0, TE = 0, threshold = 10 } = progress || {};

      gate.innerHTML = `
        <div class="trades-gate-icon">🔒</div>
        <div class="trades-gate-title">Complete your rankings to unlock Find a Trade</div>
        <div class="trades-gate-sub">Rank at least 10 players per position so we can find the best trade fits for you</div>
        <div class="trades-gate-positions">
          ${_gatePositionRow('QB', QB, threshold)}
          ${_gatePositionRow('RB', RB, threshold)}
          ${_gatePositionRow('WR', WR, threshold)}
          ${_gatePositionRow('TE', TE, threshold)}
        </div>
        <button class="trades-gate-cta" onclick="switchToRankView()">Go rank players →</button>`;

      gate.classList.add('active');
      wrap.classList.add('gate-active');
    }

    /** Animate the gate away and restore normal trade UI. */
    function _hideTradesGate() {
      const wrap = document.getElementById('trades-wrap');
      const gate = document.getElementById('trades-gate');
      if (!wrap || !gate) return;

      gate.classList.add('unlocking');
      setTimeout(() => {
        gate.classList.remove('active', 'unlocking');
        gate.innerHTML = '';
        wrap.classList.remove('gate-active');
      }, 360);
    }

    /**
     * Returns true (unlocked) or false (locked / gate rendered).
     * Call whenever Find a Trade tab is opened.
     */
    async function checkTradesGate(force = false) {
      const progress = await fetchRankingProgress(force);
      if (!progress) return true; // can't tell — let trades show

      if (!progress.unlocked) {
        _showTradesGate(progress);
        return false;
      }

      // Unlocked — make sure any stale gate overlay is cleared.
      // Without this, if the gate was rendered on a previous visit
      // the gate-active CSS class hides the trade header/button.
      _hideTradesGate();
      return true;
    }

    /**
     * Called from submitRanking() after every successful swipe.
     * If Find a Trade is the active view, refresh the gate live.
     */
    function _onRankingSwipeComplete() {
      // Invalidate cache so the next check fetches fresh data
      fetchRankingProgress(true).then(progress => {
        if (!progress) return;
        // Update the segmented unlock bar on the ranking page
        renderUnlockBar(progress);
        const tradesView = document.getElementById('view-trades');
        if (!tradesView || !tradesView.classList.contains('active')) return;

        const gate = document.getElementById('trades-gate');
        const gateShowing = gate && gate.classList.contains('active');

        if (!progress.unlocked && gateShowing) {
          // Update progress bars in-place
          _showTradesGate(progress);
        } else if (progress.unlocked && gateShowing) {
          // Just crossed the threshold — celebrate and reveal trades
          _hideTradesGate();
          showToast('🎉 Find a Trade unlocked!');
          // Give the animation a beat before loading trades
          setTimeout(() => {
            renderLeagueSwitcher();
            refreshCoverage();
            loadMatches();
            checkOutlookPrompt();
            refreshTrades();
          }, 380);
        }
      });
    }

    /** Navigate to the Rank Players → Trios sub-view. */
    function switchToRankView() {
      switchView('rank');
    }

    // Maps each view id to its tier-1 group + tier-2 data-view so the nav
    // can stay in sync regardless of how we got to the view.
    const VIEW_TO_NAV = {
      rank:      { group: 'rank',   subView: 'rank' },
      rankings:  { group: 'rank',   subView: 'rankings' },
      trends:    { group: 'rank',   subView: 'trends' },
      trades:    { group: 'trades', subView: 'trades' },
      matches:   { group: 'trades', subView: 'matches' },
      portfolio: { group: 'trades', subView: 'portfolio' },
      // 'league' is reachable only via the 🏆 header chip; no tier-2 needed.
      league:    { group: null,     subView: null },
    };

    function _syncNavActive(view) {
      const map = VIEW_TO_NAV[view];
      // Tier 1
      document.querySelectorAll('.nav-tier-1 .nav-tab').forEach(t => t.classList.remove('active'));
      if (map && map.group) {
        document.querySelector(`.nav-tier-1 .nav-tab[data-group="${map.group}"]`)?.classList.add('active');
      }
      // Tier 2 visibility + active sub-tab
      document.querySelectorAll('.nav-subtabs').forEach(s => s.classList.add('hidden'));
      if (map && map.group) {
        const subs = document.getElementById(`subtabs-${map.group}`);
        if (subs) subs.classList.remove('hidden');
      }
      document.querySelectorAll('.nav-subtab').forEach(s => s.classList.remove('active'));
      if (map && map.subView) {
        document.querySelector(`.nav-subtabs:not(.hidden) .nav-subtab[data-view="${map.subView}"]`)?.classList.add('active');
      }
    }

    /** Tier-1 click handler. Shows that group's tier-2 subtabs and, when the
     *  user isn't already inside the group, routes to its default sub-view. */
    function switchTabGroup(group, btn) {
      // Is the user already inside this group's views?
      const activeViewId = document.querySelector('.view.active')?.id || '';
      const currentGroup = Object.entries(VIEW_TO_NAV).find(
        ([vid, m]) => activeViewId === 'view-' + vid
      )?.[1]?.group;

      if (currentGroup === group) {
        // Already in the group — just refresh nav state without navigating.
        _syncNavActive(activeViewId.replace(/^view-/, ''));
        return;
      }

      // Otherwise route to the group's default sub-view.
      if (group === 'rank') {
        goToTiers();  // Default under Rank Players → Tiers page
      } else if (group === 'trades') {
        switchView('trades');
      }
    }

    /** Navigate to the standalone positional-tiers page. */
    function goToTiers() {
      window.location.href = '/positional-tiers.html';
    }

    function switchView(view, btn) {
      _syncNavActive(view);
      document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
      document.getElementById('view-' + view).classList.add('active');

      // Defensively dismiss any open celebration modal — prevents
      // _celebrationActive from stranding a permanent block on loadTrio().
      const celebOverlay = document.getElementById('celebration-overlay');
      if (celebOverlay && !celebOverlay.classList.contains('hidden')) {
        celebOverlay.classList.add('hidden');
        _celebrationActive = false;
      }
      if (view === 'trades') {
        renderLeagueSwitcher();
        refreshCoverage();
        checkOutlookPrompt();   // show onboarding modal if no outlook set for this league
        refreshPlayerEloMap();  // populate ELO sort for player picker
        // Check ranking gate; only refresh trades if already unlocked
        checkTradesGate().then(unlocked => {
          if (unlocked) refreshTrades();
        });
      }
      if (view === 'rankings') {
        loadRankingsTable();
        checkFormatEmptyState('rankings');
      }
      if (view === 'matches') {
        loadMatches();
      }
      if (view === 'portfolio') {
        loadPortfolio();
      }
      if (view === 'league') {
        loadLeagueSummary();
      }
      if (view === 'rank') {
        checkFormatEmptyState('rank');
      }
    }

    // ── Trade finder ─────────────────────────────────────────────────
    // ── Fairness slider helpers ────────────────────────────────────────────

    function _fairnessStorageKey() {
      return `fairness_threshold_${currentLeagueId || 'default'}`;
    }

    function getFairnessThreshold() {
      const chk = document.getElementById('fairness-equal-chk');
      if (chk && chk.checked) return 1.0;
      const slider = document.getElementById('fairness-slider');
      if (!slider) return 0.75;
      return parseInt(slider.value, 10) / 100;
    }

    function _saveFairnessToStorage() {
      const slider = document.getElementById('fairness-slider');
      const chk    = document.getElementById('fairness-equal-chk');
      if (!slider) return;
      try {
        localStorage.setItem(_fairnessStorageKey(), JSON.stringify({
          value: slider.value,
          equal: chk ? chk.checked : false,
        }));
      } catch {}
    }

    function _loadFairnessFromStorage() {
      const slider = document.getElementById('fairness-slider');
      const chk    = document.getElementById('fairness-equal-chk');
      const lbl    = document.getElementById('fairness-value');
      if (!slider) return;
      try {
        const stored = JSON.parse(localStorage.getItem(_fairnessStorageKey()) || 'null');
        if (stored) {
          slider.value   = stored.value || 75;
          if (chk) chk.checked = !!stored.equal;
        }
      } catch {}
      _syncFairnessUI();
    }

    function _syncFairnessUI() {
      const slider = document.getElementById('fairness-slider');
      const chk    = document.getElementById('fairness-equal-chk');
      const lbl    = document.getElementById('fairness-value');
      if (!slider || !lbl) return;
      const isEqual = chk && chk.checked;
      slider.disabled = isEqual;
      lbl.textContent = isEqual ? '100%' : slider.value + '%';
    }

    function onFairnessSlider(val) {
      const lbl = document.getElementById('fairness-value');
      if (lbl) lbl.textContent = val + '%';
      _saveFairnessToStorage();
    }

    function onFairnessEqualChk(checked) {
      _syncFairnessUI();
      _saveFairnessToStorage();
    }

    // Call this whenever the active league changes so the slider reflects
    // the per-league setting.
    function initFairnessSlider() {
      _loadFairnessFromStorage();
    }

    // ── Player Picker (trade-away selector) ──────────────────────────────

    let _pickerCollapsed = true;   // collapsed by default

    function togglePlayerPicker() {
      _pickerCollapsed = !_pickerCollapsed;
      const section = document.getElementById('player-picker-section');
      const body    = document.getElementById('player-picker-body');
      const chevron = document.getElementById('picker-chevron');
      const sub     = document.getElementById('picker-sub');
      if (body)    body.style.display    = _pickerCollapsed ? 'none' : '';
      if (chevron) chevron.textContent   = _pickerCollapsed ? '\u25B6' : '\u25BC';
      if (sub)     sub.style.display     = _pickerCollapsed ? 'none' : '';
      if (section) section.classList.toggle('collapsed', _pickerCollapsed);
    }

    // Map of player_id → ELO for sorting picker chips by value
    let _playerEloMap = {};

    function renderPlayerPicker() {
      const section = document.getElementById('player-picker-section');
      if (!section || !_myRoster.length) return;
      section.style.display = '';

      const chips = document.getElementById('picker-chips');
      if (!chips) return;

      // Sort by ELO value descending (highest value first).
      // Falls back to search_rank if no ELO data available yet.
      const sorted = [..._myRoster].sort((a, b) => {
        const eloA = _playerEloMap[a.id] || 0;
        const eloB = _playerEloMap[b.id] || 0;
        if (eloA || eloB) return eloB - eloA;  // ELO descending
        return (a.search_rank || 999) - (b.search_rank || 999);
      });

      const filtered = _pickerPosFilter === 'ALL'
        ? sorted
        : sorted.filter(p => (p.position || '').toUpperCase() === _pickerPosFilter);

      chips.innerHTML = filtered.map(p => {
        const pos = (p.position || '?').toLowerCase();
        const sel = _pinnedGivePlayers.has(p.id) ? 'selected' : '';
        const team = p.team || 'FA';
        const name = p.name || 'Unknown';
        return `<div class="player-chip ${sel}" onclick="togglePinnedPlayer('${p.id}')">
          <span class="chip-check">${sel ? '✓' : ''}</span>
          <span class="chip-pos ${pos}">${(p.position || '?').toUpperCase()}</span>
          <span class="chip-name">${escapeHtml(name)}</span>
          <span class="chip-team">${escapeHtml(team)}</span>
        </div>`;
      }).join('');

      _updatePickerBadge();
    }

    function togglePinnedPlayer(playerId) {
      if (_pinnedGivePlayers.has(playerId)) {
        _pinnedGivePlayers.delete(playerId);
      } else {
        _pinnedGivePlayers.add(playerId);
      }
      renderPlayerPicker();
    }

    function clearPinnedPlayers() {
      _pinnedGivePlayers.clear();
      renderPlayerPicker();
    }

    function filterPickerPos(pos, btn) {
      _pickerPosFilter = pos;
      // Update active tab
      document.querySelectorAll('#picker-pos-filters .picker-pos-tab').forEach(t => t.classList.remove('active'));
      if (btn) btn.classList.add('active');
      renderPlayerPicker();
    }

    function _updatePickerBadge() {
      const badge = document.getElementById('picker-count-badge');
      const clearBtn = document.getElementById('picker-clear-btn');
      const count = _pinnedGivePlayers.size;
      if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? '' : 'none';
      }
      if (clearBtn) {
        clearBtn.style.display = count > 0 ? '' : 'none';
      }
    }

    // ── Trade generation ───────────────────────────────────────────────────

    async function generateTrades() {
      const btn = document.getElementById('gen-btn');
      btn.disabled = true;
      btn.textContent = '⏳ Generating…';

      const leagueId         = currentLeagueId || 'league_demo';
      const fairnessThreshold = getFairnessThreshold();
      const pinnedGive       = [..._pinnedGivePlayers];

      try {
        const payload = { league_id: leagueId, fairness_threshold: fairnessThreshold };
        if (pinnedGive.length > 0) {
          payload.pinned_give_players = pinnedGive;
          logDrawer.info(`Pinned ${pinnedGive.length} player(s) to trade away`);
        }
        const res  = await apiFetch('/api/trades/generate', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify(payload),
        });
        const cards = await res.json();
        if (cards.error) { showToast('⚠️ ' + cards.error); return; }
        const pinnedLabel = pinnedGive.length > 0 ? ` for ${pinnedGive.length} pinned player(s)` : '';
        showToast(`✅ Found ${cards.length} trade ideas${pinnedLabel}`);
        renderTrades(cards);
        updateLikedBadge();
      } catch {
        showToast('Could not reach server');
      } finally {
        btn.disabled = false;
        btn.textContent = '⚡ Find a Trade';
      }
    }

    async function refreshTrades() {
      const leagueId = currentLeagueId || 'league_demo';
      try {
        const res   = await apiFetch(`/api/trades?league_id=${leagueId}`);
        const cards = await res.json();
        if (!cards.error) renderTrades(cards);
        updateLikedBadge();
      } catch {}
    }

    function renderTrades(cards) {
      const list = document.getElementById('trades-list');
      if (!cards.length) {
        list.innerHTML = `<div class="trades-empty">
          <strong>No trades yet</strong>
          Hit "Find a Trade" to generate personalised trade suggestions<br>
          based on your rankings vs your leaguemates.
        </div>`;
        return;
      }

      const _rankNudgeHTML = `
        <div class="rank-more-nudge">
          <span class="rank-more-nudge-text">Not happy with your offers? Rank more players so Find a Trade can think like you! 📊</span>
          <button class="rank-more-nudge-btn" onclick="switchToRankView()">Rank more →</button>
        </div>`;

      list.innerHTML = cards.map(card => {
        const givePlayers  = card.give.map(p => tradePlayerHTML(p)).join('');
        const recvPlayers  = card.receive.map(p => tradePlayerHTML(p)).join('');
        const decided      = card.decision !== null;
        const cls          = card.decision === 'like' ? 'liked' : card.decision === 'pass' ? 'passed' : '';
        const score        = Math.round(card.mismatch_score);
        const actionBtns   = decided
          ? `<div style="font-size:13px;color:var(--muted);text-align:center;padding:4px 0;">
               ${card.decision === 'like' ? '✅ Interested' : '✗ Passed'}
             </div>`
          : `<div class="trade-actions">
               <button class="trade-pass-btn" onclick="swipeTrade('${card.trade_id}','pass')">✕ Pass</button>
               <button class="trade-like-btn" onclick="swipeTrade('${card.trade_id}','like')">✓ Interested</button>
             </div>`;

        const dataTag = card.real_opponent
          ? `<span title="Based on this leaguemate's actual rankings" style="font-size:10px;color:var(--green);margin-left:4px;font-weight:700;">● real</span>`
          : `<span title="Opponent rankings estimated" style="font-size:10px;color:var(--muted);margin-left:4px;">○ est.</span>`;

        return `<div class="trade-card ${cls}" id="tc-${card.trade_id}">
          <div class="trade-meta">
            <span>vs <span class="trade-league">${escapeHtml(card.target_username)}</span>${dataTag}</span>
            <span class="score-pill">Match score ${score}</span>
          </div>
          <div class="trade-sides">
            <div class="trade-side give">
              <div class="trade-side-label">You give</div>
              ${givePlayers}
            </div>
            <div class="trade-arrow">⇄</div>
            <div class="trade-side recv">
              <div class="trade-side-label">You receive</div>
              ${recvPlayers}
            </div>
          </div>
          ${actionBtns}
        </div>`;
      }).join('') + _rankNudgeHTML;
    }

    function buildInjuryBadge(injuryStatus) {
      if (!injuryStatus) return '';
      const s = injuryStatus.toLowerCase();
      let cls = 'q', label = injuryStatus;
      if (s.includes('injured reserve') || s === 'ir') {
        cls = 'ir'; label = 'IR';
      } else if (s.includes('out')) {
        cls = 'out'; label = 'OUT';
      } else if (s.includes('doubtful')) {
        cls = 'd'; label = 'DOUBT';
      } else if (s.includes('questionable')) {
        cls = 'q'; label = 'Q';
      } else if (s.includes('suspend')) {
        cls = 'out'; label = 'SUSP';
      }
      return `<span class="inj-badge ${cls}">${label}</span>`;
    }

    function buildDcBadge(p) {
      if (p.depth_chart_order == null) return '';
      const order = parseInt(p.depth_chart_order, 10);
      if (isNaN(order) || order > 3) return '';
      return `<span class="dc-badge">${p.position}${order}</span>`;
    }

    function buildRookieBadge(p) {
      return (p.years_experience === 0) ? '<span class="rookie-badge">ROOKIE</span>' : '';
    }

    // ── Dynasty context helpers ─────────────────────────────────────
    function yearsOfControl(p) {
      if (!p.age || p.age <= 0) return null;
      const pos = (p.position || '').toUpperCase();
      let ceiling;
      if (pos === 'RB')       ceiling = 30;
      else if (pos === 'QB')  ceiling = 35;
      else                    ceiling = 32;  // WR, TE, default
      return Math.max(0, ceiling - p.age);
    }

    function valueTier(p) {
      if (!p.search_rank && p.search_rank !== 0) return null;
      const r = p.search_rank;
      if (r <= 50)  return 'elite';
      if (r <= 150) return 'high';
      if (r <= 300) return 'mid';
      return 'depth';
    }

    function careerStage(p) {
      const yrs = p.years_experience;
      if (yrs == null) return null;
      if (yrs <= 2) return 'Rising';
      if (yrs <= 5) return 'Prime';
      return null;
    }

    function buildTierBadge(p) {
      const tier = valueTier(p);
      if (!tier) return '';
      const labels = { elite: 'Elite', high: 'High', mid: 'Mid', depth: 'Depth' };
      return `<span class="tier-badge tier-${tier}">${labels[tier]}</span>`;
    }

    function buildCareerBadge(p) {
      const stage = careerStage(p);
      if (!stage) return '';
      return `<span class="career-badge">${stage}</span>`;
    }

    function buildControlYears(p) {
      const yrs = yearsOfControl(p);
      if (yrs == null || yrs <= 0) return '';
      return `<span class="control-years">${yrs}yr ctrl</span>`;
    }

    function tradePlayerHTML(p) {
      const pos = (p.position || '?').toLowerCase();

      if (p.pick_value != null) {
        const pickVal  = p.pick_value.toFixed(1);
        const origTeam = escapeHtml(p.team || '');
        return `<div class="trade-player">
          <div class="trade-player-name">${escapeHtml(p.name || 'Unknown')}</div>
          <div class="trade-player-meta">
            <span class="pos-badge pick">PICK</span>
            ${buildTierBadge(p)}
            <span style="color:var(--muted)">${origTeam}${origTeam ? ' · ' : ''}val ${pickVal}</span>
          </div>
        </div>`;
      }

      const team      = escapeHtml(p.team || 'FA');
      const age       = p.age ? `Age ${p.age}` : '';
      const yrsLabel  = (p.years_experience != null && p.years_experience > 0)
                          ? `${p.years_experience}yr` : '';
      const dcBadge   = buildDcBadge(p);
      const injBadge  = buildInjuryBadge(p.injury_status);
      const rookieBdg = buildRookieBadge(p);
      const tierBdg   = buildTierBadge(p);
      const metaParts = [team, age, yrsLabel].filter(Boolean).join(' · ');
      return `<div class="trade-player">
        <div class="trade-player-name">${escapeHtml(p.name || 'Unknown')}</div>
        <div class="trade-player-meta">
          <span class="pos-badge ${pos}">${p.position || '?'}</span>
          ${dcBadge}${injBadge}${rookieBdg}${tierBdg}
          <span>${metaParts}</span>
        </div>
      </div>`;
    }

    async function swipeTrade(tradeId, decision) {
      try {
        const res  = await apiFetch('/api/trades/swipe', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ trade_id: tradeId, decision }),
        });
        const card = await res.json();
        if (card.error) { showToast('⚠️ ' + card.error); return; }

        const el = document.getElementById('tc-' + tradeId);
        if (el) {
          el.classList.remove('liked', 'passed');
          if (decision === 'like') {
            el.classList.add('liked');
            el.querySelector('.trade-actions').outerHTML =
              `<div style="font-size:13px;color:var(--green);text-align:center;padding:4px 0;">✅ Interested</div>`;
            const recvNames = card.receive.map(p => p.name.split(' ').pop()).join(' & ');
            const giveNames = card.give.map(p => p.name.split(' ').pop()).join(' & ');
            showToast(`✅ Interested — rankings nudged: ${recvNames} ↑  ${giveNames} ↓`);
          } else {
            el.classList.add('passed');
            el.querySelector('.trade-actions').outerHTML =
              `<div style="font-size:13px;color:var(--muted);text-align:center;padding:4px 0;">✗ Passed</div>`;
            const giveNames = card.give.map(p => p.name.split(' ').pop()).join(' & ');
            const recvNames = card.receive.map(p => p.name.split(' ').pop()).join(' & ');
            showToast(`✗ Passed — rankings nudged: ${giveNames} ↑  ${recvNames} ↓`);
          }
        }
        updateLikedBadge();

        // Mutual match detection
        if (card.matched) {
          showMatchOverlay({
            partnerName: card.partner_name,
            myGive:      card.my_give    || [],
            myReceive:   card.my_receive || [],
          });
          loadMatches();          // refresh matches panel in background
          fetchNotifications();   // pull in the newly-created match notification
        }
      } catch {
        showToast('Failed to record decision');
      }
    }

    // ── Mutual match overlay ────────────────────────────────────────────
    function showMatchOverlay({ partnerName, myGive, myReceive }) {
      document.getElementById('match-partner-name').textContent = partnerName || 'your leaguemate';

      const giveStr = myGive.length    ? myGive.join(', ')    : '—';
      const recvStr = myReceive.length ? myReceive.join(', ') : '—';
      document.getElementById('match-trade-detail').innerHTML =
        `<span class="mdt-label">You give</span>
         <span class="mdt-give">${giveStr}</span>
         <span class="mdt-label" style="margin-top:8px">You receive</span>
         <span class="mdt-recv">${recvStr}</span>`;

      const overlay = document.getElementById('match-overlay');
      overlay.classList.remove('hidden');
      overlay.onclick = (e) => { if (e.target === overlay) dismissMatch(); };
    }

    function dismissMatch() {
      document.getElementById('match-overlay').classList.add('hidden');
    }

    // ── Matches panel ───────────────────────────────────────────────────
    async function loadMatches() {
      try {
        const res     = await apiFetch('/api/trades/matches');
        const matches = await res.json();
        renderMatchesList(matches);
        updateMatchesBadge(matches);
      } catch {}
    }

    // ── Agent 6 — Cross-league portfolio ────────────────────────────────
    async function loadPortfolio() {
      const body = document.getElementById('portfolio-body');
      if (!body) return;

      // Fewer than 2 leagues → show empty/unlock state
      if ((_cachedLeagues || []).length < 2) {
        body.innerHTML = `<div class="portfolio-empty">
          <strong>Connect another Sleeper league to unlock Portfolio</strong>
          <div class="portfolio-empty-sub">Portfolio tracks your exposure across every team you run.</div>
        </div>`;
        return;
      }

      body.innerHTML = `<div class="portfolio-empty">Loading portfolio…</div>`;
      try {
        const res  = await apiFetch('/api/portfolio');
        const data = await res.json();
        const players = (data && data.players) || [];
        if (!players.length) {
          body.innerHTML = `<div class="portfolio-empty">
            <strong>No players found</strong>
            <div class="portfolio-empty-sub">Your rosters may still be syncing — try again in a moment.</div>
          </div>`;
          return;
        }
        const total = players[0].total_leagues || (_cachedLeagues || []).length;
        const rows = players.map(p => `
          <div class="portfolio-row">
            <div class="portfolio-row-main">
              <span class="portfolio-player">${escapeHtml(p.name || p.player_id)}</span>
              <span class="portfolio-pos pos-${(p.pos || '').toLowerCase()}">${escapeHtml(p.pos || '')}</span>
            </div>
            <div class="portfolio-row-exposure">
              <span class="portfolio-count">${p.exposure}/${p.total_leagues}</span>
              <span class="portfolio-count-label">leagues</span>
            </div>
            <div class="portfolio-leagues">${(p.league_names || []).map(escapeHtml).join(' • ')}</div>
          </div>`).join('');
        body.innerHTML = `
          <div class="portfolio-summary">You own <strong>${players.length}</strong> distinct players across <strong>${total}</strong> leagues.</div>
          <div class="portfolio-list">${rows}</div>`;
      } catch (e) {
        body.innerHTML = `<div class="portfolio-empty">Couldn't load portfolio.</div>`;
      }
    }

    function renderMatchesList(matches) {
      const list    = document.getElementById('matches-list');

      if (!matches || matches.length === 0) {
        list.innerHTML = `<div class="trades-empty">
          <strong>No matches yet</strong>
          When you and a leaguemate both like the same trade,<br>
          it will show up here.
        </div>`;
        return;
      }

      // Sort each bucket by matched_at descending (most recent first)
      const byDate = (a, b) => new Date(b.matched_at || 0) - new Date(a.matched_at || 0);
      const pending  = matches.filter(m => m.status === 'pending').sort(byDate);
      const accepted = matches.filter(m => m.status === 'accepted').sort(byDate);
      const declined = matches.filter(m => m.status === 'declined').sort(byDate);

      let html = '';

      if (pending.length > 0) {
        html += `<div class="match-sub-section">
          <div class="match-sub-header pending">⏳ Pending (${pending.length})</div>
          ${pending.map(renderMatchCard).join('')}
        </div>`;
      }
      if (accepted.length > 0) {
        html += `<div class="match-sub-section">
          <div class="match-sub-header accepted">✅ Accepted (${accepted.length})</div>
          ${accepted.map(renderMatchCard).join('')}
        </div>`;
      }
      if (declined.length > 0) {
        html += `<div class="match-sub-section">
          <div class="match-sub-header declined">✗ Declined (${declined.length})</div>
          ${declined.map(renderMatchCard).join('')}
        </div>`;
      }

      list.innerHTML = html;
    }

    function renderMatchCard(m) {
      const giveStr = (m.my_give_names  || m.my_give    || []).join(', ') || '—';
      const recvStr = (m.my_receive_names || m.my_receive || []).join(', ') || '—';
      const date    = m.matched_at ? new Date(m.matched_at).toLocaleDateString() : '';
      const partner = m.partner_name || 'Leaguemate';

      // ── Decision area ──────────────────────────────────────────────────
      let decisionHtml = '';

      if (m.status === 'pending') {
        if (!m.my_decision) {
          // User hasn't decided yet — show Accept / Decline buttons
          decisionHtml = `
            <div class="match-decision-btns">
              <button class="match-decline-btn"
                      id="dec-decline-${m.match_id}"
                      onclick="recordDisposition(${m.match_id},'decline',this)">
                ✕ Decline
              </button>
              <button class="match-accept-btn"
                      id="dec-accept-${m.match_id}"
                      onclick="recordDisposition(${m.match_id},'accept',this)">
                ✓ Accept
              </button>
            </div>`;
        } else {
          // User decided, waiting for partner
          const myLabel = m.my_decision === 'accept'
            ? `<span class="dec-accept">✅ You accepted</span>`
            : `<span class="dec-decline">✗ You declined</span>`;
          decisionHtml = `
            <div class="match-decision-status">
              ${myLabel}
              <span class="dec-waiting">• Waiting for ${partner}…</span>
            </div>`;
        }
      } else {
        // Both decided — reveal both
        const myLabel = m.my_decision === 'accept'
          ? `<span class="dec-accept">✅ You accepted</span>`
          : `<span class="dec-decline">✗ You declined</span>`;
        const theirLabel = m.their_decision === 'accept'
          ? `<span class="dec-accept">✅ ${partner} accepted</span>`
          : `<span class="dec-decline">✗ ${partner} declined</span>`;
        decisionHtml = `
          <div class="match-decision-status">
            ${myLabel} <span style="color:var(--muted)">•</span> ${theirLabel}
          </div>`;
      }

      return `
        <div class="match-row" id="match-card-${m.match_id}">
          <div class="match-row-partner">${partner}</div>
          <div class="match-row-detail">
            Give: <span class="match-row-give">${giveStr}</span><br>
            Receive: <span class="match-row-recv">${recvStr}</span>
            ${date ? `<br><span style="font-size:11px;color:var(--muted)">Matched ${date}</span>` : ''}
          </div>
          ${decisionHtml}
        </div>`;
    }

    async function recordDisposition(matchId, decision, btn) {
      // Disable both buttons immediately to prevent double-submit
      const card = document.getElementById('match-card-' + matchId);
      if (card) {
        card.querySelectorAll('button').forEach(b => {
          b.disabled = true;
          if (b === btn) b.textContent = decision === 'accept' ? '✓ Accepting…' : '✕ Declining…';
        });
      }

      try {
        const res  = await apiFetch(`/api/trades/matches/${matchId}/disposition`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ decision }),
        });
        const data = await res.json();

        if (data.error) {
          showToast('⚠️ ' + data.error);
          // Re-enable buttons on error
          if (card) card.querySelectorAll('button').forEach(b => b.disabled = false);
          return;
        }

        // Toast based on outcome
        if (data.outcome === 'accepted') {
          showToast('🎉 Trade accepted! Rankings updated.');
        } else if (data.outcome === 'declined') {
          showToast('Trade declined. Rankings corrected.');
        } else {
          showToast(decision === 'accept'
            ? '✅ Accepted — waiting for partner'
            : '✗ Declined — waiting for partner');
        }

        // Full re-render from the response payload
        if (data.matches) {
          renderMatchesList(data.matches);
          updateMatchesBadge(data.matches);
        } else {
          loadMatches();
        }
      } catch {
        showToast('Failed to record decision');
        if (card) card.querySelectorAll('button').forEach(b => b.disabled = false);
      }
    }

    function updateMatchesBadge(matches) {
      // Badge shows count of pending matches where the user hasn't decided yet
      const undecided = (matches || []).filter(m => m.status === 'pending' && !m.my_decision);
      const badge = document.getElementById('matches-badge');
      if (undecided.length > 0) {
        badge.textContent = undecided.length;
        badge.classList.add('show');
      } else {
        badge.classList.remove('show');
      }
    }

    // ── Team Outlook ─────────────────────────────────────────────────────

    const OUTLOOK_META = {
      championship: { emoji: '🏆', short: 'Win Now',   label: 'Championship or Bust' },
      contender:    { emoji: '💪', short: 'Contender', label: 'Contender'             },
      rebuilder:    { emoji: '🔨', short: 'Rebuild',   label: 'Rebuilder'             },
      jets:         { emoji: '🟢', short: 'Jets Mode', label: 'NY Jets'               },
      not_sure:     { emoji: '🤷', short: 'No Adj.',   label: 'Not Sure'              },
    };

    // Positional preferences state (parallel to currentOutlook)
    let currentAcquirePositions    = [];  // e.g. ["WR", "TE"]
    let currentTradeAwayPositions  = [];  // e.g. ["QB"]
    let _pendingOutlookValue       = null; // holds step-1 selection until step-2 saved

    async function checkOutlookPrompt() {
      // Skip for demo league or no session
      if (!currentLeagueId || currentLeagueId === 'league_demo') return;
      try {
        const res  = await apiFetch(`/api/league/preferences?league_id=${currentLeagueId}`);
        const data = await res.json();
        currentOutlook             = data.team_outlook || null;
        currentAcquirePositions    = data.acquire_positions    || [];
        currentTradeAwayPositions  = data.trade_away_positions || [];
        updateOutlookBadge();
        if (!currentOutlook) {
          showOutlookModal(true);   // required — no dismiss
        }
      } catch (e) {
        logDrawer.warn('checkOutlookPrompt failed: ' + e.message);
      }
    }

    function _outlookModalStep(n) {
      document.getElementById('outlook-step-1').style.display = (n === 1) ? '' : 'none';
      document.getElementById('outlook-step-2').style.display = (n === 2) ? '' : 'none';
    }

    function _populatePosPrefCheckboxes() {
      // Set checkbox state from currentAcquirePositions / currentTradeAwayPositions
      document.querySelectorAll('#outlook-step-2 input[type="checkbox"]').forEach(chk => {
        const side = chk.dataset.side;
        const pos  = chk.dataset.pos;
        if (side === 'acquire') {
          chk.checked = currentAcquirePositions.includes(pos);
        } else {
          chk.checked = currentTradeAwayPositions.includes(pos);
        }
      });
    }

    function _readPosPrefCheckboxes() {
      const acquire = [], away = [];
      document.querySelectorAll('#outlook-step-2 input[type="checkbox"]').forEach(chk => {
        if (!chk.checked) return;
        if (chk.dataset.side === 'acquire') acquire.push(chk.dataset.pos);
        else away.push(chk.dataset.pos);
      });
      return { acquire, away };
    }

    function showOutlookModal(required) {
      // Update title with current league name
      const leagueObj  = _cachedLeagues.find(l => l.league_id === currentLeagueId);
      const leagueName = leagueObj ? (leagueObj.name || 'this league') : 'this league';
      document.getElementById('outlook-modal-title').textContent =
        `What's your team outlook for ${leagueName}?`;

      // Show/hide dismiss button
      const dismissBtn = document.getElementById('outlook-dismiss-btn');
      if (dismissBtn) dismissBtn.style.display = required ? 'none' : '';

      // Highlight currently selected option (if re-opening)
      document.querySelectorAll('.outlook-option-btn').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.value === currentOutlook);
      });

      // Always start at step 1
      _outlookModalStep(1);
      _pendingOutlookValue = null;

      document.getElementById('outlook-overlay').classList.remove('hidden');
    }

    function dismissOutlookModal() {
      document.getElementById('outlook-overlay').classList.add('hidden');
      _pendingOutlookValue = null;
    }

    // Step 1 selection — advances to step 2
    function selectOutlookStep1(value) {
      if (!currentLeagueId) return;

      // Highlight selection
      document.querySelectorAll('.outlook-option-btn').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.value === value);
      });

      _pendingOutlookValue = value;
      _populatePosPrefCheckboxes(); // pre-populate with existing saved state
      _outlookModalStep(2);
    }

    // Step 2 Save — saves outlook + positional prefs together
    async function saveOutlookWithPositions() {
      if (!currentLeagueId || !_pendingOutlookValue) return;

      const btn = document.getElementById('pos-pref-save-btn');
      if (btn) btn.disabled = true;

      const { acquire, away } = _readPosPrefCheckboxes();

      try {
        const res  = await apiFetch('/api/league/preferences', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            league_id:            currentLeagueId,
            team_outlook:         _pendingOutlookValue,
            acquire_positions:    acquire,
            trade_away_positions: away,
          }),
        });
        const data = await res.json();
        if (data.error) { showToast('⚠️ ' + data.error); if (btn) btn.disabled = false; return; }

        currentOutlook            = _pendingOutlookValue;
        currentAcquirePositions   = acquire;
        currentTradeAwayPositions = away;
        updateOutlookBadge();
        dismissOutlookModal();

        const meta = OUTLOOK_META[_pendingOutlookValue] || { emoji: '', short: _pendingOutlookValue };
        showToast(`${meta.emoji} Preferences saved`);

        // Auto-generate trades so the new prefs take effect immediately
        generateTrades();
      } catch {
        showToast('Failed to save preferences');
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    // "Skip for now" — saves outlook only, no positional prefs
    async function skipPositionalPrefs() {
      if (!currentLeagueId || !_pendingOutlookValue) return;

      try {
        const res  = await apiFetch('/api/league/preferences', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            league_id:            currentLeagueId,
            team_outlook:         _pendingOutlookValue,
            acquire_positions:    [],
            trade_away_positions: [],
          }),
        });
        const data = await res.json();
        if (data.error) { showToast('⚠️ ' + data.error); return; }

        currentOutlook            = _pendingOutlookValue;
        currentAcquirePositions   = [];
        currentTradeAwayPositions = [];
        updateOutlookBadge();
        dismissOutlookModal();

        const meta = OUTLOOK_META[_pendingOutlookValue] || { emoji: '', short: _pendingOutlookValue };
        showToast(`${meta.emoji} Outlook set: ${meta.label}`);

        generateTrades();
      } catch {
        showToast('Failed to save outlook');
      }
    }

    function updateOutlookBadge() {
      const badge = document.getElementById('outlook-badge');
      if (!badge) return;
      if (currentOutlook && OUTLOOK_META[currentOutlook]) {
        const { emoji, short } = OUTLOOK_META[currentOutlook];
        badge.textContent = `${emoji} ${short}`;
        badge.classList.add('show');
      } else {
        badge.textContent = '';
        badge.classList.remove('show');
      }
    }

    async function updateLikedBadge() {
      try {
        const res   = await apiFetch('/api/trades/liked');
        const cards = await res.json();
        const badge = document.getElementById('liked-badge');
        if (cards.length > 0) {
          badge.textContent = cards.length;
          badge.classList.add('show');
        } else {
          badge.classList.remove('show');
        }
      } catch {}
    }

    // ── Notifications ──────────────────────────────────────────────
    let _notifState    = [];   // current cached notifications
    let _notifPollTimer = null;

    function relativeTime(isoStr) {
      if (!isoStr) return '';
      const now   = Date.now();
      const then  = new Date(isoStr).getTime();
      const secs  = Math.max(0, Math.floor((now - then) / 1000));
      if (secs < 60)              return 'just now';
      const mins = Math.floor(secs / 60);
      if (mins < 60)              return `${mins} min ago`;
      const hrs  = Math.floor(mins / 60);
      if (hrs  < 24)              return `${hrs} hr ago`;
      const days = Math.floor(hrs / 24);
      if (days === 1)             return 'yesterday';
      return `${days} days ago`;
    }

    function absoluteTime(isoStr) {
      if (!isoStr) return '';
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleString(undefined, {
        month: 'short', day: 'numeric',
        hour: 'numeric', minute: '2-digit',
      });  // e.g. "Apr 11, 2:34 PM"
    }

    function notifTypeIcon(type) {
      if (type === 'trade_match')    return '🤝';
      if (type === 'trade_accepted') return '✅';
      if (type === 'trade_declined') return '❌';
      return '🔔';
    }

    async function fetchNotifications() {
      if (!currentUserId) return;
      try {
        const res  = await apiFetch(`/api/notifications?user_id=${encodeURIComponent(currentUserId)}`);
        const data = await res.json();
        _notifState = data.notifications || [];
        _updateNotifBadge(data.unread_count || 0);
        // If panel is open, refresh it
        const panel = document.getElementById('notif-panel');
        if (panel && panel.classList.contains('open')) {
          _renderNotifList();
        }
      } catch { /* silent fail */ }
    }

    function _updateNotifBadge(count) {
      const badge = document.getElementById('notif-badge');
      const bell  = document.getElementById('notif-bell-btn');
      if (!badge || !bell) return;
      if (count > 0) {
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.classList.add('show');
        bell.classList.add('has-unread');
      } else {
        badge.classList.remove('show');
        bell.classList.remove('has-unread');
      }
    }

    function _renderNotifList() {
      const listEl = document.getElementById('notif-list');
      if (!listEl) return;
      if (!_notifState || _notifState.length === 0) {
        listEl.innerHTML = '<div class="notif-empty">No notifications yet</div>';
        return;
      }
      listEl.innerHTML = _notifState.map(n => {
        const unreadCls = n.is_read ? '' : ' unread';
        const icon      = notifTypeIcon(n.type);
        const body      = escapeHtml(n.body || n.title || '');
        const rel  = relativeTime(n.created_at);
        const abs  = absoluteTime(n.created_at);
        const time = abs ? `${rel} · ${abs}` : rel;
        return `<div class="notif-row${unreadCls}" onclick="clickNotif(${n.id}, '${n.type}', ${JSON.stringify(n.metadata || {}).replace(/"/g, '&quot;')})">
          <div class="notif-unread-dot"></div>
          <div class="notif-icon">${icon}</div>
          <div class="notif-content">
            <div class="notif-body">${body}</div>
            <div class="notif-time">${time}</div>
          </div>
        </div>`;
      }).join('');
    }

    function toggleNotifPanel(event) {
      event.stopPropagation();
      const panel = document.getElementById('notif-panel');
      if (!panel) return;
      const isOpen = panel.classList.contains('open');
      if (isOpen) {
        panel.classList.remove('open');
      } else {
        _renderNotifList();
        panel.classList.add('open');
      }
    }

    function closeNotifPanel() {
      const panel = document.getElementById('notif-panel');
      if (panel) panel.classList.remove('open');
    }

    async function markAllNotifsRead() {
      if (!currentUserId) return;
      try {
        await apiFetch('/api/notifications/read-all', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ user_id: currentUserId }),
        });
        // Optimistic local update
        _notifState.forEach(n => { n.is_read = 1; });
        _updateNotifBadge(0);
        _renderNotifList();
      } catch { /* silent fail */ }
    }

    async function clickNotif(id, type, metadata) {
      // Mark this notification read
      if (currentUserId) {
        apiFetch('/api/notifications/read', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ user_id: currentUserId, ids: [id] }),
        }).catch(() => {});
      }
      // Optimistic local update
      const notif = _notifState.find(n => n.id === id);
      if (notif) {
        notif.is_read = 1;
        const unread = _notifState.filter(n => !n.is_read).length;
        _updateNotifBadge(unread);
        _renderNotifList();
      }

      // Navigate to the relevant section
      closeNotifPanel();
      const meta = (typeof metadata === 'string') ? JSON.parse(metadata) : (metadata || {});
      const matchId = meta.match_id;

      if (type === 'trade_match' || type === 'trade_accepted' || type === 'trade_declined') {
        // Switch to Find a Trade view (tier 1: Find Trades → Find a Trade)
        {
          switchView('trades');
          // Refresh matches to make sure the target is rendered, then scroll
          if (matchId) {
            loadMatches().then(() => {
              setTimeout(() => {
                // match rows are rendered as match-card-{id}
                const el = document.getElementById('match-card-' + matchId);
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
              }, 200);
            }).catch(() => {});
          }
        }
      }
    }

    // Close panel when clicking outside
    document.addEventListener('click', function(e) {
      const wrap = document.getElementById('notif-bell-wrap');
      if (wrap && !wrap.contains(e.target)) {
        closeNotifPanel();
      }
    });

    function _startNotifPolling() {
      if (_notifPollTimer) clearInterval(_notifPollTimer);
      fetchNotifications();  // immediate fetch on login
      _notifPollTimer = setInterval(fetchNotifications, 30000);
    }

    // ══════════════════════════════════════════════════════════════════
    //  Dual-scoring-format toggle + League Summary + Invite share sheet
    // ══════════════════════════════════════════════════════════════════

    const FORMAT_KEYS = ['1qb_ppr', 'sf_tep'];
    const FORMAT_LABELS = {
      '1qb_ppr': '🏈 1QB PPR',
      'sf_tep':  '🏟 SF TEP',
    };
    const LS_ACTIVE_FORMAT = 'ftf_active_format';

    function getActiveFormat() {
      const stored = localStorage.getItem(LS_ACTIVE_FORMAT);
      return FORMAT_KEYS.includes(stored) ? stored : '1qb_ppr';
    }

    /** Render the scoring-format toggle into every .scoring-toggle-wrap element.
     *  Re-renders on demand (e.g. after format switch) so the active class syncs.
     *
     *  As of the auto-detect rollout, the league's scoring format is sourced
     *  from the Sleeper league metadata — each league plays exactly one format.
     *  We no longer expose a user-level toggle on ranking pages; the League
     *  summary page renders a read-only badge for the detected format. */
    function renderScoringToggles() {
      document.querySelectorAll('.scoring-toggle-wrap').forEach(wrap => {
        const isLeagueDefault = wrap.dataset.view === 'league-default';
        if (!isLeagueDefault) {
          // User-scope toggles are retired — the league dictates scoring.
          wrap.innerHTML = '';
          wrap.style.display = 'none';
          return;
        }
        // Leave league-default wraps alone; renderLeagueSummary paints them
        // with the current detected/overridden format as a read-only badge.
      });
    }

    async function onScoringToggleClick(btn) {
      const fmt   = btn.dataset.format;
      const scope = btn.dataset.scope;
      if (!FORMAT_KEYS.includes(fmt)) return;

      if (scope === 'league') {
        // League default scoring — saves to /api/league/scoring for this league
        if (!currentLeagueId) return;
        btn.classList.add('switching');
        try {
          const res = await apiFetch('/api/league/scoring', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ league_id: currentLeagueId, format: fmt }),
          });
          if (res.ok) {
            // Re-render league default toggle to reflect the saved state
            await loadLeagueSummary();
          }
        } catch (e) {
          showToast('Failed to save league scoring');
        } finally {
          btn.classList.remove('switching');
        }
        return;
      }

      // User-level active format switch
      if (fmt === getActiveFormat()) return;  // already active
      btn.classList.add('switching');
      try {
        const res = await apiFetch('/api/scoring/switch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ format: fmt }),
        });
        if (!res.ok) {
          showToast('Failed to switch scoring format');
          return;
        }
        localStorage.setItem(LS_ACTIVE_FORMAT, fmt);
        renderScoringToggles();
        refreshActiveView();
      } catch (e) {
        showToast('Switch failed: ' + e.message);
      } finally {
        btn.classList.remove('switching');
      }
    }

    /** After a format switch, refresh whatever view is currently visible. */
    function refreshActiveView() {
      const active = document.querySelector('.view.active');
      if (!active) return;
      const id = active.id;
      if (id === 'view-rank') {
        loadTrio();
        loadProgress();
        if (typeof checkFormatEmptyState === 'function') checkFormatEmptyState('rank');
      } else if (id === 'view-rankings') {
        if (typeof loadRankingsTable === 'function') loadRankingsTable();
        if (typeof checkFormatEmptyState === 'function') checkFormatEmptyState('rankings');
      } else if (id === 'view-trades') {
        if (typeof refreshTrades === 'function') refreshTrades();
      } else if (id === 'view-matches') {
        if (typeof loadMatches === 'function') loadMatches();
      } else if (id === 'view-league') {
        loadLeagueSummary();
      }
      if (view === 'trends') {
        loadTrends();
      }
    }

    // ── League Summary ────────────────────────────────────────────────
    async function loadLeagueSummary() {
      if (!currentLeagueId) return;
      try {
        const res = await apiFetch('/api/league/summary?league_id=' + encodeURIComponent(currentLeagueId));
        if (!res.ok) return;
        const data = await res.json();
        renderLeagueSummary(data);
      } catch (e) {
        logDrawer.warn('loadLeagueSummary failed: ' + e.message);
      }
      // Fire the contrarian leaderboard fetch in parallel — independent of
      // the summary response, rendered into its own section below the grid.
      loadLeagueContrarianLeaderboard();
    }

    // Pick the unlocked-count that matches the league's scoring format.
    // Each league plays exactly one format, so we only show one number —
    // backend still returns both counts for back-compat.
    function _leagueUnlockedCount(data) {
      const fmt = data.default_scoring || '1qb_ppr';
      if (fmt === 'sf_tep') return data.leaguemates_unlocked_sf || 0;
      return data.leaguemates_unlocked_1qb || 0;
    }

    function renderLeagueSummary(data) {
      const titleEl = document.getElementById('league-summary-title');
      if (titleEl) titleEl.textContent = data.league_name || 'League';

      const grid = document.getElementById('league-summary-grid');
      if (grid) {
        grid.innerHTML = `
          <div class="summary-card">
            <div class="summary-card-value pending">${data.matches_pending || 0}</div>
            <div class="summary-card-label">Matches Pending</div>
            <div class="summary-card-sub">Waiting on a decision</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-value accepted">${data.matches_accepted || 0}</div>
            <div class="summary-card-label">Matches Accepted</div>
            <div class="summary-card-sub">Both sides agreed</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-value">${data.leaguemates_joined || 0} / ${data.leaguemates_total || 0}</div>
            <div class="summary-card-label">Leaguemates Joined</div>
            <div class="summary-card-sub">Have a Trade Finder account</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-value">${_leagueUnlockedCount(data)}</div>
            <div class="summary-card-label">Unlocked Trade Finder</div>
            <div class="summary-card-sub">Ready to match</div>
          </div>`;
      }

      // League scoring is auto-detected from Sleeper metadata — render as a
      // read-only badge rather than a toggle, so users can't accidentally
      // diverge from what the league actually plays.
      const leagueWrap = document.querySelector('.scoring-toggle-wrap[data-view="league-default"]');
      if (leagueWrap) {
        const defaultFmt = data.default_scoring || '1qb_ppr';
        leagueWrap.style.display = '';
        leagueWrap.innerHTML = `
          <div class="scoring-badge" title="Detected from Sleeper league settings">
            <span class="scoring-badge-label">Scoring</span>
            <span class="scoring-badge-value">${FORMAT_LABELS[defaultFmt] || FORMAT_LABELS['1qb_ppr']}</span>
          </div>`;
      }
    }

    // ── Invite share sheet ────────────────────────────────────────────
    function buildInviteUrl() {
      const origin = window.location.origin;
      const params = new URLSearchParams();
      if (currentLeagueId) params.set('league', currentLeagueId);
      const username = (window._currentUser && _currentUser.username) || '';
      if (username) params.set('ref', username);
      return `${origin}/?${params.toString()}`;
    }

    function buildInviteMessage() {
      const url = buildInviteUrl();
      const leagueName = document.getElementById('league-summary-title')?.textContent || 'our league';
      return `Join me on Dynasty Trade Finder to find trades in ${leagueName} → ${url}`;
    }

    // ── OG share-card helpers (Agent 3) ──────────────────────────────
    // Build a public share URL that resolves to an HTML page with OG meta
    // tags pointing to the server-rendered PNG. Social apps (iMessage,
    // Twitter, WhatsApp) will auto-render the image preview when these
    // URLs are pasted into messages.
    function buildTierShareUrl(pos, username) {
      const origin = window.location.origin;
      const posSeg = encodeURIComponent(String(pos || '').toLowerCase());
      const u = encodeURIComponent(String(username || (window._currentUser && _currentUser.username) || '').trim());
      if (!posSeg || !u) return origin + '/';
      // Preserve active scoring format if available so the card subtitle matches
      const fmt = (window._currentUser && _currentUser.scoring_format) || null;
      const qs = (fmt && fmt !== '1qb_ppr') ? `?fmt=${encodeURIComponent(fmt)}` : '';
      return `${origin}/s/tiers/${posSeg}/${u}${qs}`;
    }

    function buildTradeShareUrl(matchId) {
      const origin = window.location.origin;
      const mid = encodeURIComponent(String(matchId || '').trim());
      if (!mid) return origin + '/';
      return `${origin}/s/trade/${mid}`;
    }

    function openInviteModal() {
      const modal = document.getElementById('invite-modal');
      if (!modal) return;
      const urlInput = document.getElementById('invite-url-input');
      if (urlInput) urlInput.value = buildInviteUrl();
      renderInviteGrid();
      modal.classList.remove('hidden');
    }

    function closeInviteModal() {
      document.getElementById('invite-modal')?.classList.add('hidden');
    }

    function closeInviteModalIfBackdrop(e) {
      if (e.target && e.target.id === 'invite-modal') closeInviteModal();
    }

    function renderInviteGrid() {
      const grid = document.getElementById('invite-grid');
      if (!grid) return;
      const channels = [
        { key: 'email',    label: 'Email',      icon: '✉️' },
        { key: 'sms',      label: 'SMS',        icon: '💬' },
        { key: 'whatsapp', label: 'WhatsApp',   icon: '🟢' },
        { key: 'telegram', label: 'Telegram',   icon: '✈️' },
        { key: 'x',        label: 'X',          icon: '𝕏' },
        { key: 'groupme',  label: 'GroupMe',    icon: '👥' },
        { key: 'sleeper',  label: 'Sleeper',    icon: '😴' },
        { key: 'copy',     label: 'Copy Link',  icon: '🔗' },
      ];
      grid.innerHTML = channels.map(ch => `
        <button class="share-button" onclick="shareVia('${ch.key}')">
          <span class="share-button-icon">${ch.icon}</span>
          <span class="share-button-label">${ch.label}</span>
        </button>`).join('');
    }

    // True when running on a handheld where native share sheets + custom URL
    // schemes work reliably. Desktop browsers usually can't launch apps, so we
    // degrade to clipboard + clear copy there.
    function _isMobileUA() {
      return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '');
    }

    // Try the Web Share API. Resolves true if the OS share sheet was opened
    // (and the user either shared or dismissed). Resolves false if unsupported.
    async function _tryWebShare(payload) {
      if (!navigator.share) return false;
      try {
        await navigator.share(payload);
        return true;
      } catch (err) {
        // AbortError = user cancelled the sheet. Still counts as "we tried."
        if (err && err.name === 'AbortError') return true;
        return false;
      }
    }

    // Agent 4 addition — per-channel pre-filled share copy.
    // Each channel has its own tone / length tuned to where it's pasted:
    //   SMS:      terse
    //   Twitter:  tweetable one-liner (within 280 chars)
    //   WhatsApp: friendly
    //   GroupMe:  casual group-chat
    //   Telegram: WhatsApp-ish
    //   Email:    subject + explainer body
    //   Sleeper:  paste-ready DM
    //   copy:     URL only
    // Returns { title, subject, body, body_enc } — `body_enc` is pre-URI-encoded
    // for deep-link URLs; `body` is the raw version used for clipboard/Web Share.
    function buildChannelMessage(channel, ctx) {
      ctx = ctx || {};
      const url        = ctx.url        || buildInviteUrl();
      const leagueName = ctx.leagueName
        || (document.getElementById('league-summary-title')?.textContent || 'our league');
      const title   = 'Fantasy Trade Finder';
      let subject   = 'Join me on Fantasy Trade Finder';
      let body;

      switch (channel) {
        case 'sms':
          body = `${leagueName} fantasy trade finder — join me: ${url}`;
          break;
        case 'x':
        case 'twitter':
          body = `Joined @FantasyTradeFinder to find trades in ${leagueName}. Come ruin the league with me 🏈 ${url}`;
          break;
        case 'whatsapp':
          body = `Hey! Been using Fantasy Trade Finder for ${leagueName} — it finds trades both sides actually like. Join me: ${url}`;
          break;
        case 'groupme':
          body = `yo who's tired of "What you want for X?" — try this: ${url}`;
          break;
        case 'telegram':
          body = `Hey! Using Fantasy Trade Finder for ${leagueName} — it finds trades both sides actually like. Join me: ${url}`;
          break;
        case 'email':
          subject = `Join me on Fantasy Trade Finder — ${leagueName}`;
          body = [
            `Hey,`,
            ``,
            `I've been using Fantasy Trade Finder to work out trades in ${leagueName}.`,
            `You rank players how you actually value them, it figures out which of your leaguemates value them differently, and it surfaces trades you'd both say yes to — no more "what you want for X?" back-and-forth.`,
            ``,
            `Takes about 5 minutes to set up. Give it a shot:`,
            url,
            ``,
            `— sent from Fantasy Trade Finder`,
          ].join('\n');
          break;
        case 'sleeper':
          body = `Join me on Fantasy Trade Finder for ${leagueName}: ${url}`;
          break;
        case 'copy':
          body = url;
          break;
        default:
          body = `Join me on Fantasy Trade Finder for ${leagueName}: ${url}`;
          break;
      }

      return {
        title,
        subject,
        body,
        body_enc: encodeURIComponent(body),
      };
    }

    async function shareVia(channel) {
      const url = buildInviteUrl();
      const ctx = { url };
      const msg = buildChannelMessage(channel, ctx);
      const title = msg.title;
      const subjectEnc = encodeURIComponent(msg.subject);
      const bodyEnc    = msg.body_enc;
      const sharePayload = { title, text: msg.body, url };

      switch (channel) {
        case 'email':
          // mailto: accepts subject + body as URI-encoded params on all major
          // mail clients (Gmail web, Apple Mail, Outlook). The long-form
          // explainer body lives in msg.body.
          window.open(`mailto:?subject=${subjectEnc}&body=${bodyEnc}`, '_blank');
          break;

        case 'sms':
          // iOS and Android have slightly different sms: URI conventions; this
          // form works on both. Desktop browsers won't launch an app — fall
          // back to clipboard so the action isn't silently broken.
          if (_isMobileUA()) {
            window.open(`sms:?&body=${bodyEnc}`, '_blank');
          } else {
            await copyInviteToClipboard(true, channel);
            showToast('Copied — SMS only works on mobile. Paste it into any text.');
          }
          break;

        case 'whatsapp':
          // wa.me opens WhatsApp Web on desktop and the app on mobile.
          window.open(`https://wa.me/?text=${bodyEnc}`, '_blank');
          break;

        case 'telegram':
          // Telegram's share URL takes url + text as separate params; it
          // renders the text as the message body and the url as the preview.
          window.open(
            `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${bodyEnc}`,
            '_blank'
          );
          break;

        case 'x':
          // Twitter/X intent URL — tweetable one-liner lives in msg.body.
          window.open(`https://twitter.com/intent/tweet?text=${bodyEnc}`, '_blank');
          break;

        case 'groupme': {
          // GroupMe has no public share-URL. On mobile the native share sheet
          // will include GroupMe if the app is installed — that's the best
          // integration available. Fall back to clipboard everywhere else.
          const opened = await _tryWebShare(sharePayload);
          if (opened) return;
          await copyInviteToClipboard(true, channel);
          showToast('Copied — open GroupMe and paste into any group chat.');
          break;
        }

        case 'sleeper': {
          // Sleeper likewise has no public share-URL. Best-effort: on mobile we
          // try to prime the native share sheet (which surfaces Sleeper if
          // installed), then attempt the undocumented sleeper:// scheme, then
          // copy. On desktop we go straight to clipboard with clear copy.
          if (_isMobileUA()) {
            const opened = await _tryWebShare(sharePayload);
            if (opened) return;
            await copyInviteToClipboard(true, channel);
            // Nudge Sleeper's custom URL scheme. Silently fails if not
            // installed — the clipboard fallback above keeps us safe.
            try { window.location.href = 'sleeper://'; } catch (_) { /* noop */ }
            showToast('Copied — open Sleeper and paste into any DM.');
            return;
          }
          await copyInviteToClipboard(true, channel);
          showToast('Copied — open Sleeper and paste into any DM.');
          break;
        }

        case 'copy':
        default:
          await copyInviteToClipboard(false, channel);
          showToast('Link copied to clipboard');
          break;
      }
    }

    async function copyInviteToClipboard(fullMessage, channel) {
      // Agent 4 update: copied text now matches the channel's template when
      // fullMessage is true. Defaults to the generic invite message for
      // callers that don't pass a channel (back-compat).
      let text;
      if (fullMessage) {
        text = channel
          ? buildChannelMessage(channel, {}).body
          : buildInviteMessage();
      } else {
        text = buildInviteUrl();
      }
      try {
        await navigator.clipboard.writeText(text);
      } catch (_) {
        // Fallback for browsers without clipboard API
        const input = document.getElementById('invite-url-input');
        if (input) { input.select(); document.execCommand('copy'); }
      }
    }

    // ══════════════════════════════════════════════════════════════════
    //  League Contrarian Leaderboard  +  Format Empty-State Nudge
    // ══════════════════════════════════════════════════════════════════

    const _POS_META = [
      { key: 'qb', label: 'QB', emoji: '🎯' },
      { key: 'rb', label: 'RB', emoji: '🏃' },
      { key: 'wr', label: 'WR', emoji: '🙌' },
      { key: 'te', label: 'TE', emoji: '💪' },
    ];

    /**
     * Fetch and render the per-position contrarian leaderboard for the
     * active league + scoring format. Called after loadLeagueSummary().
     */
    async function loadLeagueContrarianLeaderboard() {
      const body = document.getElementById('contrarian-leaderboard-body');
      if (!body || !currentLeagueId) return;
      try {
        const fmt = getActiveFormat();
        const url = `/api/league/contrarian?league_id=${encodeURIComponent(currentLeagueId)}&format=${encodeURIComponent(fmt)}`;
        const res = await apiFetch(url);
        if (!res.ok) {
          body.innerHTML = '<div class="contrarian-leaderboard-error">Couldn\'t load leaderboard.</div>';
          return;
        }
        const data = await res.json();
        renderLeagueContrarianLeaderboard(data);
      } catch (e) {
        logDrawer.warn('loadLeagueContrarianLeaderboard failed: ' + e.message);
        body.innerHTML = '<div class="contrarian-leaderboard-error">Couldn\'t load leaderboard.</div>';
      }
    }

    /**
     * Render the contrarian leaderboard data into #contrarian-leaderboard-body.
     * Handles the insufficient-data case (fewer than 3 ranked users in the
     * league) with a single-line nudge instead of per-position rows.
     */
    function renderLeagueContrarianLeaderboard(data) {
      const body = document.getElementById('contrarian-leaderboard-body');
      if (!body) return;

      if (!data || data.insufficient_data) {
        const ranked = (data && data.ranked_users) || 0;
        const needed = (data && data.needed) || Math.max(3 - ranked, 1);
        body.innerHTML = `
          <div class="contrarian-leaderboard-empty">
            <div class="contrarian-leaderboard-empty-icon">🤝</div>
            <div class="contrarian-leaderboard-empty-title">Invite leaguemates to unlock.</div>
            <div class="contrarian-leaderboard-empty-sub">
              Need ${needed} more ranked leaguemate${needed === 1 ? '' : 's'} to compute the
              contrarian leaderboard (currently ${ranked} / 3).
            </div>
            <button class="contrarian-leaderboard-invite-btn" onclick="openInviteModal()">📨 Invite</button>
          </div>`;
        return;
      }

      const rows = _POS_META.map(pos => {
        const posData = data[pos.key];
        if (!posData || (!posData.most_contrarian.length && !posData.most_consensus.length)) {
          return `
            <div class="contrarian-leaderboard-row">
              <div class="contrarian-leaderboard-row-pos">
                <span class="contrarian-leaderboard-pos-emoji">${pos.emoji}</span>
                <span class="contrarian-leaderboard-pos-label">${pos.label}</span>
              </div>
              <div class="contrarian-leaderboard-row-body">
                <div class="contrarian-leaderboard-nodata">Not enough ${pos.label} rankings yet.</div>
              </div>
            </div>`;
        }
        const contrarian = posData.most_contrarian[0];
        const consensus  = posData.most_consensus[0];
        const cHtml = contrarian
          ? `<div class="contrarian-leaderboard-pick contrarian">
               <div class="contrarian-leaderboard-pick-label">Most contrarian</div>
               <div class="contrarian-leaderboard-pick-user">@${escapeHtml(contrarian.username)}</div>
               <div class="contrarian-leaderboard-pick-score">${contrarian.deviation.toFixed(1)} avg ELO diff</div>
             </div>`
          : '';
        const sHtml = consensus
          ? `<div class="contrarian-leaderboard-pick consensus">
               <div class="contrarian-leaderboard-pick-label">Most consensus</div>
               <div class="contrarian-leaderboard-pick-user">@${escapeHtml(consensus.username)}</div>
               <div class="contrarian-leaderboard-pick-score">${consensus.deviation.toFixed(1)} avg ELO diff</div>
             </div>`
          : '';
        return `
          <div class="contrarian-leaderboard-row">
            <div class="contrarian-leaderboard-row-pos">
              <span class="contrarian-leaderboard-pos-emoji">${pos.emoji}</span>
              <span class="contrarian-leaderboard-pos-label">${pos.label}</span>
            </div>
            <div class="contrarian-leaderboard-row-body">
              ${cHtml}
              ${sHtml}
            </div>
          </div>`;
      }).join('');

      body.innerHTML = rows;
    }

    /**
     * Show a nudge on ranking pages when the user has navigated to a format
     * they haven't started ranking in yet. Checked on view enter (switchView)
     * and on format toggle. Ignored silently if the league isn't ready or
     * the endpoint fails — this is a helper nudge, not a blocker.
     */
    async function checkFormatEmptyState(viewName) {
      const el = document.getElementById(`format-empty-state-${viewName}`);
      if (!el) return;
      if (!currentLeagueId) { el.classList.add('hidden'); return; }
      try {
        const res = await apiFetch('/api/league/format-stats?league_id=' + encodeURIComponent(currentLeagueId));
        if (!res.ok) { el.classList.add('hidden'); return; }
        const data = await res.json();
        const fmt  = getActiveFormat();
        const info = (data.formats || {})[fmt];
        const count = (info && info.ranking_count) || 0;
        if (count === 0) {
          const activeLabel = FORMAT_LABELS[fmt] || fmt;
          const otherFmt    = fmt === '1qb_ppr' ? 'sf_tep' : '1qb_ppr';
          const otherLabel  = FORMAT_LABELS[otherFmt] || otherFmt;
          const otherCount  = ((data.formats || {})[otherFmt] || {}).ranking_count || 0;
          const titleEl = document.getElementById(`format-empty-state-${viewName}-title`);
          const bodyEl  = document.getElementById(`format-empty-state-${viewName}-body`);
          if (titleEl) titleEl.textContent = `You haven't started ranking for ${activeLabel}`;
          if (bodyEl) {
            if (otherCount > 0) {
              bodyEl.textContent = `You have ${otherCount} rankings saved in ${otherLabel}. Switch formats above or keep scrolling to start ranking here.`;
            } else {
              bodyEl.textContent = `No rankings saved yet for this scoring format. Rank a few trios below to unlock trade matching.`;
            }
          }
          el.classList.remove('hidden');
        } else {
          el.classList.add('hidden');
        }
      } catch (e) {
        logDrawer.warn('checkFormatEmptyState failed: ' + e.message);
        el.classList.add('hidden');
      }
    }

    // Expose for inline handlers + format-toggle callers
    window.loadLeagueContrarianLeaderboard = loadLeagueContrarianLeaderboard;
    window.renderLeagueContrarianLeaderboard = renderLeagueContrarianLeaderboard;
    window.checkFormatEmptyState = checkFormatEmptyState;

    // ── Referral capture ──────────────────────────────────────────────
    const LS_INVITED_BY     = 'ftf_invited_by';
    const LS_INVITED_LEAGUE = 'ftf_invited_league';

    function captureReferralFromUrl() {
      const params = new URLSearchParams(window.location.search);
      const ref    = params.get('ref');
      const lg     = params.get('league');
      if (ref) localStorage.setItem(LS_INVITED_BY, ref);
      if (lg)  localStorage.setItem(LS_INVITED_LEAGUE, lg);
      if (ref || lg) {
        // Clean the URL so the attribution params don't persist in the bar
        const clean = window.location.pathname + window.location.hash;
        window.history.replaceState({}, document.title, clean);
        // Show the invited banner under the auth card (if still on login)
        showInvitedBanner(ref);
      }
    }

    function getInvitedBy() { return localStorage.getItem(LS_INVITED_BY) || ''; }
    function getInvitedLeague() { return localStorage.getItem(LS_INVITED_LEAGUE) || ''; }

    function showInvitedBanner(ref) {
      if (!ref) return;
      const card = document.querySelector('.auth-card');
      if (!card) return;
      if (card.querySelector('.invited-banner')) return;  // already shown
      const banner = document.createElement('div');
      banner.className = 'invited-banner';
      banner.textContent = `🤝 Invited by @${ref}`;
      card.appendChild(banner);
    }

    // ── Login-page carousel (Concept B: "How It Works") ────────────────
    // Dots + swipe-to-advance on the 3-step onboarding carousel.
    let cbCurrent = 0;
    function cbGoTo(idx) {
      const track = document.getElementById('cb-carousel-track');
      const dots  = document.querySelectorAll('#cb-carousel-dots .cb-dot');
      if (!track || !dots.length) return;
      cbCurrent = Math.max(0, Math.min(idx, dots.length - 1));
      track.style.transform = 'translateX(-' + (cbCurrent * 100) + '%)';
      dots.forEach((d, i) => d.classList.toggle('active', i === cbCurrent));
    }
    function _bindCarouselSwipe() {
      const track = document.getElementById('cb-carousel-track');
      if (!track || track.dataset.swipeBound === '1') return;
      const vp = track.parentElement;
      if (!vp) return;
      track.dataset.swipeBound = '1';
      let startX = 0, startY = 0, moving = false;
      vp.addEventListener('touchstart', e => {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        moving = true;
      }, { passive: true });
      vp.addEventListener('touchend', e => {
        if (!moving) return;
        moving = false;
        const dx = e.changedTouches[0].clientX - startX;
        const dy = e.changedTouches[0].clientY - startY;
        if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
          dx < 0 ? cbGoTo(cbCurrent + 1) : cbGoTo(cbCurrent - 1);
        }
      }, { passive: true });
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _bindCarouselSwipe);
    } else {
      _bindCarouselSwipe();
    }

    // ══════════════════════════════════════════════════════════════════
    //  Trends tab (Rank Players → Trends) — Agent 2
    //  Risers/Fallers · Contrarian meter · Consensus Gap
    // ══════════════════════════════════════════════════════════════════

    let _trendsData = { rf: null, contrarian: null, gap: null };
    let _trendsActivePos = 'ALL';

    async function loadTrends() {
      // Reset visual state
      _trendsActivePos = 'ALL';
      document.querySelectorAll('#trends-rf-pos-tabs .trends-pos-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.pos === 'ALL');
      });

      const riserEl  = document.getElementById('trends-risers-list');
      const fallerEl = document.getElementById('trends-fallers-list');
      const contrEl  = document.getElementById('trends-contrarian-body');
      const gapEl    = document.getElementById('trends-gap-body');
      if (riserEl)  riserEl.innerHTML  = '<div class="trends-empty">Loading…</div>';
      if (fallerEl) fallerEl.innerHTML = '<div class="trends-empty">Loading…</div>';
      if (contrEl)  contrEl.innerHTML  = '<div class="trends-empty">Loading…</div>';
      if (gapEl)    gapEl.innerHTML    = '<div class="trends-empty">Loading…</div>';

      const leagueId = currentLeagueId || '';
      const q = leagueId ? `?league_id=${encodeURIComponent(leagueId)}` : '';
      const results = await Promise.allSettled([
        apiFetch('/api/trends/risers-fallers').then(r => r.json()),
        apiFetch('/api/trends/contrarian' + q).then(r => r.json()),
        apiFetch('/api/trends/consensus-gap' + q).then(r => r.json()),
      ]);

      _trendsData.rf         = results[0].status === 'fulfilled' ? results[0].value : null;
      _trendsData.contrarian = results[1].status === 'fulfilled' ? results[1].value : null;
      _trendsData.gap        = results[2].status === 'fulfilled' ? results[2].value : null;

      renderTrendsRisersFallers();
      renderTrendsContrarian();
      renderTrendsConsensusGap();
    }

    function switchTrendsPos(pos, btn) {
      _trendsActivePos = pos;
      document.querySelectorAll('#trends-rf-pos-tabs .trends-pos-tab').forEach(b => {
        b.classList.remove('active');
      });
      if (btn) btn.classList.add('active');
      renderTrendsRisersFallers();
    }

    function _escapeHtml(s) {
      // Re-use existing escapeHtml; defensive alias in case load order differs.
      try { return escapeHtml(s); } catch { return String(s); }
    }

    function _deltaClass(d) {
      if (d > 0) return 'trends-delta-up';
      if (d < 0) return 'trends-delta-down';
      return '';
    }

    function _renderMoveRow(row, kind) {
      const delta  = row.delta || 0;
      const sign   = delta > 0 ? '+' : '';
      const pos    = row.position || '';
      const name   = _escapeHtml(row.name || row.player_id);
      const team   = row.team ? ` · ${_escapeHtml(row.team)}` : '';
      return (
        `<div class="trends-row">
           <div class="trends-row-main">
             <span class="trends-row-name">${name}</span>
             <span class="trends-row-meta">${pos}${team}</span>
           </div>
           <div class="trends-row-delta ${_deltaClass(delta)}">
             ${sign}${delta.toFixed(1)}
             <span class="trends-row-sub">ELO</span>
           </div>
         </div>`
      );
    }

    function renderTrendsRisersFallers() {
      const data     = _trendsData.rf;
      const riserEl  = document.getElementById('trends-risers-list');
      const fallerEl = document.getElementById('trends-fallers-list');
      const subEl    = document.getElementById('trends-rf-sub');
      if (!riserEl || !fallerEl) return;

      if (!data || !data.risers) {
        riserEl.innerHTML  = '<div class="trends-empty">Couldn\'t load trend data.</div>';
        fallerEl.innerHTML = '<div class="trends-empty">Couldn\'t load trend data.</div>';
        return;
      }

      if (!data.has_history || (data.sample_size || 0) === 0) {
        const msg = 'Not enough history yet — rank some players to start seeing movers.';
        riserEl.innerHTML  = `<div class="trends-empty">${msg}</div>`;
        fallerEl.innerHTML = '';
        if (subEl) subEl.textContent = 'Your biggest movers will show up here as you rank more players.';
        return;
      }

      if (subEl) {
        subEl.textContent = `Based on ${data.sample_size} players with snapshots in the last ${data.window_days} days.`;
      }

      const pos     = _trendsActivePos || 'ALL';
      const risers  = (data.risers  && data.risers[pos])  || [];
      const fallers = (data.fallers && data.fallers[pos]) || [];

      // Only show risers where delta > 0 / fallers where delta < 0
      const upRows   = risers.filter(r => (r.delta || 0) > 0);
      const downRows = fallers.filter(r => (r.delta || 0) < 0);

      riserEl.innerHTML = upRows.length
        ? upRows.map(r => _renderMoveRow(r, 'up')).join('')
        : '<div class="trends-empty">No risers in this window.</div>';
      fallerEl.innerHTML = downRows.length
        ? downRows.map(r => _renderMoveRow(r, 'down')).join('')
        : '<div class="trends-empty">No fallers in this window.</div>';
    }

    function renderTrendsContrarian() {
      const el = document.getElementById('trends-contrarian-body');
      if (!el) return;
      const data = _trendsData.contrarian;
      if (!data) {
        el.innerHTML = '<div class="trends-empty">Couldn\'t load contrarian data.</div>';
        return;
      }
      if (!data.has_baseline) {
        const n = data.baseline_user_count || 0;
        const need = Math.max(0, 3 - n);
        const msg = need > 0
          ? `Not enough community data yet — invite ${need} more leaguemate${need === 1 ? '' : 's'} so we can compare your rankings.`
          : 'Not enough overlap between your rankings and the league yet.';
        el.innerHTML = `<div class="trends-empty trends-empty-card">${msg}</div>`;
        return;
      }

      const score = Number(data.score || 0);
      const label = score >= 70 ? 'Very contrarian'
                  : score >= 40 ? 'Somewhat contrarian'
                  : score >= 20 ? 'Mostly consensus'
                  : 'Consensus';

      const rowsAbove = (data.above_consensus || []).map(r => (
        `<div class="trends-row">
           <div class="trends-row-main">
             <span class="trends-row-name">${_escapeHtml(r.name || r.player_id)}</span>
             <span class="trends-row-meta">${r.position || ''}</span>
           </div>
           <div class="trends-row-delta trends-delta-up">+${(r.delta||0).toFixed(1)}<span class="trends-row-sub">vs market</span></div>
         </div>`
      )).join('') || '<div class="trends-empty">No standout over-values.</div>';

      const rowsBelow = (data.below_consensus || []).map(r => (
        `<div class="trends-row">
           <div class="trends-row-main">
             <span class="trends-row-name">${_escapeHtml(r.name || r.player_id)}</span>
             <span class="trends-row-meta">${r.position || ''}</span>
           </div>
           <div class="trends-row-delta trends-delta-down">${(r.delta||0).toFixed(1)}<span class="trends-row-sub">vs market</span></div>
         </div>`
      )).join('') || '<div class="trends-empty">No standout fades.</div>';

      el.innerHTML = `
        <div class="trends-contrarian-meter">
          <div class="trends-score-wrap">
            <div class="trends-score-value">${score.toFixed(0)}</div>
            <div class="trends-score-label">${label}</div>
          </div>
          <div class="trends-score-bar">
            <div class="trends-score-bar-fill" style="width:${Math.min(100, score).toFixed(1)}%;"></div>
          </div>
          <div class="trends-score-sub">
            Compared against ${data.baseline_user_count} leaguemates ·
            ${data.compared_players} players in common
          </div>
        </div>
        <div class="trends-rf-grid">
          <div class="trends-rf-col">
            <div class="trends-rf-col-title">You love (above consensus)</div>
            <div class="trends-rf-list">${rowsAbove}</div>
          </div>
          <div class="trends-rf-col">
            <div class="trends-rf-col-title">You fade (below consensus)</div>
            <div class="trends-rf-list">${rowsBelow}</div>
          </div>
        </div>
      `;
    }

    function renderTrendsConsensusGap() {
      const el = document.getElementById('trends-gap-body');
      if (!el) return;
      const data = _trendsData.gap;
      if (!data) {
        el.innerHTML = '<div class="trends-empty">Couldn\'t load consensus-gap data.</div>';
        return;
      }
      if (!data.has_baseline) {
        const n = data.baseline_user_count || 0;
        const need = Math.max(0, 3 - n);
        const msg = need > 0
          ? `Not enough community data yet — invite ${need} more leaguemate${need === 1 ? '' : 's'} and we can surface your biggest sell/buy gaps.`
          : 'Not enough overlap with the league to compute consensus gaps.';
        el.innerHTML = `<div class="trends-empty trends-empty-card">${msg}</div>`;
        return;
      }

      const sells = data.easiest_sells || [];
      const buys  = data.easiest_buys  || [];

      const renderSell = (r) => (
        `<div class="trends-row trends-gap-row">
           <div class="trends-row-main">
             <span class="trends-row-name">${_escapeHtml(r.name || r.player_id)}</span>
             <span class="trends-row-meta">${r.position || ''}</span>
           </div>
           <div class="trends-gap-bar-wrap" title="Gap score ${r.score}/99">
             <div class="trends-gap-bar"><div class="trends-gap-bar-fill" style="width:${Math.max(4, r.score || 0)}%;"></div></div>
             <span class="trends-gap-score">+${(r.gap||0).toFixed(0)}</span>
           </div>
         </div>`
      );

      const renderBuy = (r) => (
        `<div class="trends-row trends-gap-row">
           <div class="trends-row-main">
             <span class="trends-row-name">${_escapeHtml(r.name || r.player_id)}</span>
             <span class="trends-row-meta">${r.position || ''} · owned by ${_escapeHtml(r.owner_username || '?')}</span>
           </div>
           <div class="trends-gap-bar-wrap" title="Gap score ${r.score}/99">
             <div class="trends-gap-bar"><div class="trends-gap-bar-fill" style="width:${Math.max(4, r.score || 0)}%;"></div></div>
             <span class="trends-gap-score">+${(r.gap||0).toFixed(0)}</span>
           </div>
         </div>`
      );

      el.innerHTML = `
        <div class="trends-rf-grid">
          <div class="trends-rf-col">
            <div class="trends-rf-col-title">Easiest sells from your roster</div>
            <div class="trends-rf-list">
              ${sells.length ? sells.map(renderSell).join('') :
                '<div class="trends-empty">No over-valued players on your roster right now.</div>'}
            </div>
          </div>
          <div class="trends-rf-col">
            <div class="trends-rf-col-title">Easiest buys around the league</div>
            <div class="trends-rf-list">
              ${buys.length ? buys.map(renderBuy).join('') :
                '<div class="trends-empty">No clear buy targets where you out-value the owner.</div>'}
            </div>
          </div>
        </div>
      `;
    }

    // Expose so inline onclick= in index.html finds it
    window.switchTrendsPos = switchTrendsPos;
    window.loadTrends      = loadTrends;

    // Kick capture immediately (before boot runs)
    captureReferralFromUrl();

    // Render toggles once DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', renderScoringToggles);
    } else {
      renderScoringToggles();
    }

    // ══════════════════════════════════════════════════════════════════
    //  Agent 1 — "I don't know this player" persistent skip (Trios page)
    // ══════════════════════════════════════════════════════════════════
    //
    // skipTrio() determines which card(s) to skip based on how the user has
    // interacted with the trio so far:
    //
    //   • 0 cards ranked → primary UX: skip ALL three players in the trio.
    //     The user truly doesn't recognize any of them.
    //   • 1–2 cards ranked → skip only the un-ranked card(s); the ranked
    //     ones the user already knew. No ELO is written for the partial
    //     ranking — we just hide the unknown card(s) and move on.
    //
    // Skips are persisted server-side via POST /api/trio/skip so they stick
    // across sessions for (user, scoring_format).
    async function skipTrio() {
      if (locked || !currentTrio) return;
      locked = true;

      const sides = ['a', 'b', 'c'];
      const unranked = sides.filter(s => !selectionOrder.includes(s));
      const targets = (selectionOrder.length === 0 ? sides : unranked);

      const players = {
        a: currentTrio.player_a,
        b: currentTrio.player_b,
        c: currentTrio.player_c,
      };
      const player_ids = targets
        .map(s => players[s] && players[s].id)
        .filter(Boolean);

      if (player_ids.length === 0) {
        locked = false;
        return;
      }

      try {
        const res = await apiFetch('/api/trio/skip', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ player_ids }),
        });
        if (!res.ok) {
          showToast('⚠️ Could not save skip — try again');
        } else {
          const count = player_ids.length;
          showToast(count === 1
            ? '🙈 Hidden from future trios'
            : `🙈 ${count} players hidden from future trios`);
        }
      } catch {
        showToast('Skip failed — check server connection');
      }

      // Reset selection + load a fresh trio (the new trio won't include
      // the just-skipped players thanks to the backend filter).
      selectionOrder = [];
      locked = false;
      loadTrio();
    }

    // Kick everything off
    boot();
