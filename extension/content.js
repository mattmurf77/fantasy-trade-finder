// Fantasy Trade Finder — content.js
// Runs on sleeper.com; scans the DOM for Sleeper player references and
// injects a tier + pos-rank badge next to each matching player name.
//
// Detection strategies, in order:
//   (1) Anchor href scan   — a[href*="/players/nfl/<id>"]. Works on trade
//                             summary, popups, some rosters.
//   (2) aria-label scan    — [aria-label*=" - "]. Format is
//                             "<prefix> - <Full Name>" per Sleeper's
//                             accessibility convention. Covers team
//                             rosters (where href="/"), trade picker,
//                             and most draft surfaces.
//   (3) Short-name fallback — elements matching [class*="player-name"]
//                             whose text is "D Maye" style (first initial
//                             + last name). Disambiguated via sibling
//                             .pos span. Covers surfaces that lack both
//                             a usable href and an aria-label.
//
// MutationObserver on <body> re-runs the scan on every subtree addition
// so SPA navigations inside Sleeper keep getting badges.
//
// De-dupe uses a WeakSet of target elements so virtualized re-renders
// don't leave stale markers blocking re-injection on remount.

(() => {
  'use strict';

  if (window.__ftfBadgeInit) return;
  window.__ftfBadgeInit = true;

  const STORAGE_KEY = 'ftf_session';
  const BADGE_CLASS = 'ftf-badge';
  const BADGE_ATTR  = 'data-ftf-pid';

  const TIER_LABELS = {
    elite:   'Elite',
    starter: 'Starter',
    solid:   'Solid',
    depth:   'Depth',
    bench:   'Bench',
  };

  // In-memory ranking state
  let rankings = {};                     // { pid: {name, pos, pos_rank, tier} }
  let nameToId = new Map();              // normalized full-name → pid
  let shortNameToId = new Map();         // "qb:d:maye" → pid
  let sessionMeta = { format: null, league_name: null, updated_at: null };
  let observer = null;
  let scanScheduled = false;

  // De-dupe using a WeakSet of target elements rather than a data-* attribute
  // on the DOM. When Sleeper's virtualized lists remount rows, the detached
  // nodes become unreachable and the set cleans up automatically — so freshly
  // mounted rows get re-scanned without stale markers blocking them.
  let injectedTargets = new WeakSet();

  // ─────────────────────────────────────────────────────────────
  //  Session + rankings bootstrap
  // ─────────────────────────────────────────────────────────────

  function loadSessionOnce(cb) {
    chrome.storage.local.get([STORAGE_KEY], (res) => {
      const sess = res[STORAGE_KEY];
      if (sess && sess.cached_rankings) {
        applyRankings(sess.cached_rankings);
      }
      cb && cb(sess);
    });
  }

  function applyRankings(data) {
    if (!data || !data.players) return;
    rankings = data.players;
    sessionMeta.format      = data.format || null;
    sessionMeta.league_name = data.league_name || null;
    sessionMeta.updated_at  = data.updated_at || null;

    // Primary: full-name → pid
    nameToId = new Map();
    // Secondary: "{pos}:{first_initial}:{last_name}" → pid  (for short names like "D Maye")
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

    clearAllBadges();
    scheduleScan();
  }

  function clearRankings() {
    rankings = {};
    nameToId = new Map();
    shortNameToId = new Map();
    injectedTargets = new WeakSet();
    clearAllBadges();
  }

  function clearAllBadges() {
    document.querySelectorAll('.' + BADGE_CLASS).forEach((el) => el.remove());
    injectedTargets = new WeakSet();
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

  // Insert a badge immediately after `anchor` (a DOM element). Idempotent.
  function injectAfter(anchor, info) {
    if (!anchor || !info || !info.pid) return;

    // Already injected for this anchor? check the DOM side too — if the
    // next-sibling badge has the same pid, nothing to do.
    const next = anchor.nextElementSibling;
    if (next && next.classList && next.classList.contains(BADGE_CLASS)) {
      if (next.getAttribute(BADGE_ATTR) === String(info.pid)) {
        injectedTargets.add(anchor);
        return;
      }
      // Pid changed (e.g., different player in the same slot) — replace
      next.remove();
    }

    if (injectedTargets.has(anchor)) {
      // Tracked but no sibling badge → Sleeper re-rendered; re-inject
      injectedTargets.delete(anchor);
    }

    const badge = makeBadge(info);
    if (anchor.parentNode) {
      anchor.parentNode.insertBefore(badge, anchor.nextSibling);
      injectedTargets.add(anchor);
    }
  }

  // ─────────────────────────────────────────────────────────────
  //  Name normalization
  // ─────────────────────────────────────────────────────────────

  function normalizeName(name) {
    if (!name) return '';
    return String(name)
      .toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')  // strip accents
      .replace(/\b(jr\.?|sr\.?|ii|iii|iv|v)\b/g, '')
      .replace(/[^\w\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Extract "Full Name" from an aria-label like "Slot QB - Drake Maye".
  // Returns null if no " - " delimiter present.
  function nameFromAriaLabel(label) {
    if (!label || typeof label !== 'string') return null;
    // Use the LAST " - " so prefixes like "Click on - QB - X" work too
    const idx = label.lastIndexOf(' - ');
    if (idx < 0) return null;
    const tail = label.slice(idx + 3).trim();
    if (!tail || tail.length < 2 || tail.length > 60) return null;
    return tail;
  }

  // Try to find the element where the player name is actually rendered so
  // the badge lands next to the visible name, not next to a position-square
  // or container. Falls back to the anchor itself.
  function findNameElement(container) {
    if (!container || !container.querySelector) return null;
    // Common Sleeper patterns, most → least specific
    return container.querySelector('[class*="player-name"]')
        || container.querySelector('[class*="player_name"]')
        || container.querySelector('[class*="player-title"]')
        || null;
  }

  // Walk up to the nearest plausible player-row container.
  function playerRowAncestor(el) {
    if (!el || !el.closest) return null;
    return el.closest('[class*="team-roster-item"]')
        || el.closest('[class*="player-row"]')
        || el.closest('[class*="player-card"]')
        || el.closest('[class*="player-item"]')
        || null;
  }

  // ─────────────────────────────────────────────────────────────
  //  Scanning
  // ─────────────────────────────────────────────────────────────

  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    requestAnimationFrame(() => {
      scanScheduled = false;
      try { scan(document); } catch (e) { /* swallow */ }
    });
  }

  function scan(root) {
    if (!rankings || Object.keys(rankings).length === 0) return;

    // Strategy 1 — anchor href scan (trade summary, popups)
    const anchors = (root.querySelectorAll
      ? root.querySelectorAll('a[href*="/players/nfl/"]')
      : []);
    anchors.forEach((a) => {
      const pid = extractPidFromHref(a.getAttribute('href') || '');
      if (!pid) return;
      const info = rankings[pid];
      if (!info) return;
      // Inject next to the name inside this anchor's row, not next to the
      // anchor itself (which may wrap only a position square).
      const row = playerRowAncestor(a);
      const nameEl = findNameElement(row) || a;
      injectAfter(nameEl, { ...info, pid });
    });

    // Strategy 2 — aria-label scan (team rosters, trade picker, draft)
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

    // Strategy 3 — short-name fallback via [class*="player-name"] text
    // For surfaces where neither href nor aria-label resolves the player.
    if (shortNameToId.size > 0) scanShortNames(root);
  }

  function extractPidFromHref(href) {
    const m = href.match(/\/players\/nfl\/([A-Za-z0-9_\-]+)/);
    return m ? m[1] : null;
  }

  function scanShortNames(root) {
    const nameEls = root.querySelectorAll
      ? root.querySelectorAll('[class*="player-name"], [class*="player_name"]')
      : [];
    nameEls.forEach((el) => {
      const text = (el.textContent || '').trim();
      if (!text || text.length > 40) return;
      // Match "D Maye" / "D. Maye" / "D. Maye Jr." — first initial + last
      const m = text.match(/^([A-Za-z])\.?\s+([A-Za-z'\-]+)(?:\s+(Jr|Sr|II|III|IV|V)\.?)?$/);
      if (!m) return;
      const firstInit = m[1].toLowerCase();
      const lastName  = m[2].toLowerCase().replace(/[^\w]/g, '');

      // Need the position to disambiguate — look for a sibling/ancestor
      // element with position text.
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

  function findPositionInRow(row) {
    if (!row || !row.querySelector) return null;
    // Sleeper commonly renders position in a small span with class .pos or
    // .position or includes it inside the position-square anchor's text.
    const cands = row.querySelectorAll('.pos, .position, [class*="pos-"], [class*="position"]');
    for (const el of cands) {
      const t = (el.textContent || '').trim().toUpperCase();
      if (['QB', 'RB', 'WR', 'TE'].includes(t)) return t;
    }
    return null;
  }

  // ─────────────────────────────────────────────────────────────
  //  Mutation observer — Sleeper is a SPA
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
      case 'ftf:signed_in':
        loadSessionOnce(() => {});
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
    loadSessionOnce(() => {
      startObserver();
      scheduleScan();
    });
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    boot();
  } else {
    window.addEventListener('DOMContentLoaded', boot, { once: true });
  }
})();
