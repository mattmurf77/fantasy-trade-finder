// Fantasy Trade Finder — content.js
// Runs on sleeper.com; auto-detects the current league from the URL and
// injects a tier + pos-rank badge next to each matching player name.
//
// League detection: parses /leagues/<id>/ from location.pathname. On SPA
// navigation (pushState, popstate, hashchange), re-checks the URL and
// swaps the active ranking set when the league changes.
//
// Ranking fetch: per-league rankings are cached in chrome.storage.local
// under rankings_cache[league_id]. If the cache for the current league is
// missing or stale (>10 min), the content script requests a fresh fetch
// via the background service worker.
//
// DOM scan strategies (unchanged from prior version):
//   (1) anchor href scan — a[href*="/players/nfl/<id>"]
//   (2) aria-label scan  — [aria-label*=" - "] where text after last " - "
//                          is the full player name
//   (3) short-name fallback — [class*="player-name"] like "D Maye" keyed
//                              by {pos}:{initial}:{lastname}

(() => {
  'use strict';

  if (window.__ftfBadgeInit) return;
  window.__ftfBadgeInit = true;

  const STORAGE_KEY = 'ftf_session';
  const BADGE_CLASS = 'ftf-badge';
  const BADGE_ATTR  = 'data-ftf-pid';
  const CACHE_STALE_MS = 10 * 60 * 1000;  // refetch if cache older than 10 min

  const TIER_LABELS = {
    elite:   'Elite',
    starter: 'Starter',
    solid:   'Solid',
    depth:   'Depth',
    bench:   'Bench',
  };

  // Ranking state (per active league)
  let rankings = {};
  let nameToId = new Map();
  let shortNameToId = new Map();
  let sessionMeta = { format: null, league_name: null, league_id: null, updated_at: null };
  let observer = null;
  let scanScheduled = false;
  let injectedTargets = new WeakSet();

  // Current league detected from URL + last-processed league
  let currentLeagueId = null;
  let loadedLeagueId  = null;
  let fetchInFlightFor = null;  // league_id currently being fetched

  // ─────────────────────────────────────────────────────────────
  //  URL parsing — detect league from sleeper.com/leagues/<id>/...
  // ─────────────────────────────────────────────────────────────

  function detectLeagueIdFromUrl() {
    const m = (location.pathname + location.hash).match(/\/leagues\/(\d+)/);
    return m ? m[1] : null;
  }

  function watchUrlChanges(onChange) {
    // Hook into pushState / replaceState so SPA nav fires our callback
    const origPush = history.pushState;
    const origReplace = history.replaceState;
    history.pushState = function () {
      const r = origPush.apply(this, arguments);
      try { onChange(); } catch (_) {}
      return r;
    };
    history.replaceState = function () {
      const r = origReplace.apply(this, arguments);
      try { onChange(); } catch (_) {}
      return r;
    };
    window.addEventListener('popstate', onChange);
    window.addEventListener('hashchange', onChange);

    // Safety net: polling backstop for SPAs that don't use pushState
    let lastUrl = location.href;
    setInterval(() => {
      if (location.href !== lastUrl) {
        lastUrl = location.href;
        try { onChange(); } catch (_) {}
      }
    }, 1000);
  }

  // ─────────────────────────────────────────────────────────────
  //  Session + rankings bootstrap
  // ─────────────────────────────────────────────────────────────

  function getSession() {
    return new Promise((resolve) => {
      chrome.storage.local.get([STORAGE_KEY], (res) => resolve(res[STORAGE_KEY] || null));
    });
  }

  function setSession(sess) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ [STORAGE_KEY]: sess }, resolve);
    });
  }

  // Load rankings for the current URL's league. Uses the per-league cache
  // when fresh; otherwise requests a fetch via background service worker.
  async function loadRankingsForCurrentLeague() {
    const leagueId = detectLeagueIdFromUrl();
    currentLeagueId = leagueId;

    if (!leagueId) {
      // Off-league page (homepage, player browser, etc.) — clear badges
      if (loadedLeagueId) {
        loadedLeagueId = null;
        clearRankings();
      }
      return;
    }

    if (leagueId === loadedLeagueId) return;  // already loaded for this league

    const sess = await getSession();
    if (!sess || !sess.token) return;

    const cache = sess.rankings_cache && sess.rankings_cache[leagueId];
    const now = Date.now();
    const stale = !cache || !cache.fetched_at || (now - cache.fetched_at > CACHE_STALE_MS);

    if (cache && !stale) {
      applyRankingsPayload(cache, leagueId);
      return;
    }

    // Request fresh fetch via background
    if (fetchInFlightFor === leagueId) return;
    fetchInFlightFor = leagueId;
    try {
      const resp = await sendBgMessage({ type: 'ftf:fetch_rankings', league_id: leagueId });
      fetchInFlightFor = null;
      if (resp && resp.ok && resp.data) {
        applyRankingsPayload(resp.data, leagueId);
      } else if (resp && resp.expired) {
        clearRankings();
      } else if (cache) {
        // Network failed but we have stale cache — show it so the user
        // still gets badges. Next nav or manual refresh will retry.
        applyRankingsPayload(cache, leagueId);
      }
    } catch (_) {
      fetchInFlightFor = null;
    }
  }

  function sendBgMessage(msg) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) resolve(null);
          else resolve(resp);
        });
      } catch (_) { resolve(null); }
    });
  }

  function applyRankingsPayload(data, leagueId) {
    if (!data || !data.players) return;
    rankings = data.players;
    sessionMeta.format      = data.format || null;
    sessionMeta.league_id   = leagueId || data.league_id || null;
    sessionMeta.league_name = data.league_name || null;
    sessionMeta.updated_at  = data.updated_at || null;

    nameToId = new Map();
    shortNameToId = new Map();
    for (const [pid, info] of Object.entries(rankings)) {
      if (!info || !info.name) continue;
      const key = normalizeName(info.name);
      if (key) nameToId.set(key, pid);

      const parts = info.name.trim().split(/\s+/).filter(Boolean);
      if (parts.length >= 2 && info.pos) {
        const firstInitial = parts[0][0].toLowerCase();
        const lastName = parts[parts.length - 1].toLowerCase()
          .replace(/[^\w]/g, '')
          .replace(/(jr|sr|ii|iii|iv|v)$/, '');
        if (lastName) {
          const sk = `${info.pos.toLowerCase()}:${firstInitial}:${lastName}`;
          shortNameToId.set(sk, pid);
        }
      }
    }

    loadedLeagueId = leagueId;
    injectedTargets = new WeakSet();
    clearAllBadges();
    scheduleScan();
  }

  function clearRankings() {
    rankings = {};
    nameToId = new Map();
    shortNameToId = new Map();
    injectedTargets = new WeakSet();
    loadedLeagueId = null;
    clearAllBadges();
  }

  function clearAllBadges() {
    document.querySelectorAll('.' + BADGE_CLASS).forEach((el) => el.remove());
  }

  // ─────────────────────────────────────────────────────────────
  //  Badge construction + insertion
  // ─────────────────────────────────────────────────────────────

  function makeBadge(info) {
    const b = document.createElement('span');
    b.className = `${BADGE_CLASS} ftf-tier-${info.tier}`;
    b.setAttribute(BADGE_ATTR, info.pid || '');
    const tierLabel = TIER_LABELS[info.tier] || info.tier;
    b.textContent = `${tierLabel} · ${info.pos}${info.pos_rank}`;
    const leagueStr = sessionMeta.league_name ? ` · ${sessionMeta.league_name}` : '';
    const fmtStr    = sessionMeta.format === 'sf_tep' ? 'SF TEP' : '1QB PPR';
    b.title = `Your ranking · ${fmtStr}${leagueStr}`;
    return b;
  }

  function injectAfter(anchor, info) {
    if (!anchor || !info || !info.pid) return;

    const next = anchor.nextElementSibling;
    if (next && next.classList && next.classList.contains(BADGE_CLASS)) {
      if (next.getAttribute(BADGE_ATTR) === String(info.pid)) {
        injectedTargets.add(anchor);
        return;
      }
      next.remove();
    }

    if (injectedTargets.has(anchor)) injectedTargets.delete(anchor);

    const badge = makeBadge(info);
    if (anchor.parentNode) {
      anchor.parentNode.insertBefore(badge, anchor.nextSibling);
      injectedTargets.add(anchor);
    }
  }

  // ─────────────────────────────────────────────────────────────
  //  Name normalization + helpers
  // ─────────────────────────────────────────────────────────────

  function normalizeName(name) {
    if (!name) return '';
    return String(name)
      .toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/\b(jr\.?|sr\.?|ii|iii|iv|v)\b/g, '')
      .replace(/[^\w\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function nameFromAriaLabel(label) {
    if (!label || typeof label !== 'string') return null;
    const idx = label.lastIndexOf(' - ');
    if (idx < 0) return null;
    const tail = label.slice(idx + 3).trim();
    if (!tail || tail.length < 2 || tail.length > 60) return null;
    return tail;
  }

  function findNameElement(container) {
    if (!container || !container.querySelector) return null;
    return container.querySelector('[class*="player-name"]')
        || container.querySelector('[class*="player_name"]')
        || container.querySelector('[class*="player-title"]')
        || null;
  }

  function playerRowAncestor(el) {
    if (!el || !el.closest) return null;
    return el.closest('[class*="team-roster-item"]')
        || el.closest('[class*="player-row"]')
        || el.closest('[class*="player-card"]')
        || el.closest('[class*="player-item"]')
        || null;
  }

  function findPositionInRow(row) {
    if (!row || !row.querySelector) return null;
    const cands = row.querySelectorAll('.pos, .position, [class*="pos-"], [class*="position"]');
    for (const el of cands) {
      const t = (el.textContent || '').trim().toUpperCase();
      if (['QB', 'RB', 'WR', 'TE'].includes(t)) return t;
    }
    return null;
  }

  function extractPidFromHref(href) {
    const m = href.match(/\/players\/nfl\/([A-Za-z0-9_\-]+)/);
    return m ? m[1] : null;
  }

  // ─────────────────────────────────────────────────────────────
  //  Scanning
  // ─────────────────────────────────────────────────────────────

  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    requestAnimationFrame(() => {
      scanScheduled = false;
      try { scan(document); } catch (_) {}
    });
  }

  function scan(root) {
    if (!rankings || Object.keys(rankings).length === 0) return;

    // Strategy 1 — href scan
    const anchors = (root.querySelectorAll
      ? root.querySelectorAll('a[href*="/players/nfl/"]')
      : []);
    anchors.forEach((a) => {
      const pid = extractPidFromHref(a.getAttribute('href') || '');
      if (!pid) return;
      const info = rankings[pid];
      if (!info) return;
      const row = playerRowAncestor(a);
      const nameEl = findNameElement(row) || a;
      injectAfter(nameEl, { ...info, pid });
    });

    // Strategy 2 — aria-label scan
    const labeled = (root.querySelectorAll
      ? root.querySelectorAll('[aria-label*=" - "]')
      : []);
    labeled.forEach((el) => {
      const fullName = nameFromAriaLabel(el.getAttribute('aria-label') || '');
      if (!fullName) return;
      const key = normalizeName(fullName);
      const pid = nameToId.get(key);
      if (!pid) return;
      const info = rankings[pid];
      if (!info) return;
      const row = playerRowAncestor(el);
      const nameEl = findNameElement(row) || el;
      injectAfter(nameEl, { ...info, pid });
    });

    // Strategy 3 — short-name fallback
    if (shortNameToId.size > 0) scanShortNames(root);
  }

  function scanShortNames(root) {
    const nameEls = root.querySelectorAll
      ? root.querySelectorAll('[class*="player-name"], [class*="player_name"]')
      : [];
    nameEls.forEach((el) => {
      const text = (el.textContent || '').trim();
      if (!text || text.length > 40) return;
      const m = text.match(/^([A-Za-z])\.?\s+([A-Za-z'\-]+)(?:\s+(Jr|Sr|II|III|IV|V)\.?)?$/);
      if (!m) return;
      const firstInit = m[1].toLowerCase();
      const lastName  = m[2].toLowerCase().replace(/[^\w]/g, '');

      const row = playerRowAncestor(el);
      if (!row) return;
      const pos = findPositionInRow(row);
      if (!pos) return;

      const sk = `${pos.toLowerCase()}:${firstInit}:${lastName}`;
      const pid = shortNameToId.get(sk);
      if (!pid) return;
      const info = rankings[pid];
      if (!info) return;
      injectAfter(el, { ...info, pid });
    });
  }

  // ─────────────────────────────────────────────────────────────
  //  MutationObserver — Sleeper is an SPA
  // ─────────────────────────────────────────────────────────────

  function startObserver() {
    if (observer) return;
    observer = new MutationObserver((mutations) => {
      let touched = false;
      for (const m of mutations) {
        if ((m.addedNodes && m.addedNodes.length)
            || m.type === 'attributes') {
          touched = true;
          break;
        }
      }
      if (touched) scheduleScan();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['aria-label', 'href'],
    });
  }

  // ─────────────────────────────────────────────────────────────
  //  Message bus from popup / background
  // ─────────────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || !msg.type) return;
    switch (msg.type) {
      case 'ftf:rankings_updated':
        // Background finished a refresh — reload for the current league
        loadRankingsForCurrentLeague();
        break;
      case 'ftf:signed_in':
        loadRankingsForCurrentLeague();
        break;
      case 'ftf:signed_out':
      case 'ftf:session_expired':
        clearRankings();
        break;
    }
  });

  // ─────────────────────────────────────────────────────────────
  //  Boot
  // ─────────────────────────────────────────────────────────────

  function boot() {
    startObserver();
    loadRankingsForCurrentLeague();
    watchUrlChanges(loadRankingsForCurrentLeague);
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    boot();
  } else {
    window.addEventListener('DOMContentLoaded', boot, { once: true });
  }
})();
