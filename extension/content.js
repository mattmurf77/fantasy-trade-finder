// Fantasy Trade Finder — content.js
// Runs on sleeper.com; scans the DOM for Sleeper player references and
// injects a tier + pos-rank badge next to each matching name.
//
// Two detection strategies, layered:
//   (1) Primary:   anchors matching /players/nfl/<id>  — stable DOM contract
//                  that covers player popups, trade tabs, and roster rows.
//   (2) Secondary: text-node name match — for draft boards and any surface
//                  that renders plain player names without anchors.
//
// A MutationObserver on <body> re-runs the scan on every subtree addition
// so SPA navigations inside Sleeper keep getting badges.

(() => {
  'use strict';

  // Avoid double-init if the content script gets injected twice (some SPA
  // quirks can cause this).
  if (window.__ftfBadgeInit) return;
  window.__ftfBadgeInit = true;

  const STORAGE_KEY = 'ftf_session';
  const BADGE_CLASS = 'ftf-badge';
  const BADGE_ATTR  = 'data-ftf-pid';
  const SCANNED_ATTR = 'data-ftf-scanned';

  const TIER_LABELS = {
    elite:   'Elite',
    starter: 'Starter',
    solid:   'Solid',
    depth:   'Depth',
    bench:   'Bench',
  };

  // In-memory ranking map: { pidString: {name, pos, pos_rank, tier} }
  let rankings = {};
  // Name → id map for text-fallback matching, pre-lowercased
  let nameToId = new Map();
  let sessionMeta = { format: null, league_name: null, updated_at: null };
  let observer = null;
  let scanScheduled = false;

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
    nameToId = new Map();
    for (const [pid, info] of Object.entries(rankings)) {
      if (info && info.name) {
        const key = normalizeName(info.name);
        if (key) nameToId.set(key, pid);
      }
    }
    clearAllBadges();
    scheduleScan();
  }

  function clearRankings() {
    rankings = {};
    nameToId = new Map();
    clearAllBadges();
  }

  function clearAllBadges() {
    document.querySelectorAll('.' + BADGE_CLASS).forEach((el) => el.remove());
    document.querySelectorAll(`[${SCANNED_ATTR}]`).forEach((el) => el.removeAttribute(SCANNED_ATTR));
  }

  // ─────────────────────────────────────────────────────────────
  //  Badge construction
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

  // Insert a badge after the given element. Safe to call repeatedly —
  // checks de-dupe marker to avoid stacking badges on every mutation.
  function injectAfter(el, info) {
    if (!el || !info) return;
    if (el.hasAttribute(SCANNED_ATTR)) {
      // Already has a badge for this pid? check the sibling
      const next = el.nextElementSibling;
      if (next && next.classList && next.classList.contains(BADGE_CLASS)
          && next.getAttribute(BADGE_ATTR) === info.pid) {
        return;  // still correct
      }
      // PID changed — remove and replace
      if (next && next.classList && next.classList.contains(BADGE_CLASS)) next.remove();
    }
    el.setAttribute(SCANNED_ATTR, '1');
    const badge = makeBadge(info);
    if (el.parentNode) el.parentNode.insertBefore(badge, el.nextSibling);
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

  // ─────────────────────────────────────────────────────────────
  //  Scanning
  // ─────────────────────────────────────────────────────────────

  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    // Use requestAnimationFrame so we batch DOM work per paint cycle.
    requestAnimationFrame(() => {
      scanScheduled = false;
      try { scan(document); } catch (e) { /* swallow */ }
    });
  }

  function scan(root) {
    if (!rankings || Object.keys(rankings).length === 0) return;

    // Strategy 1: anchor-href scan
    const anchors = root.querySelectorAll
      ? root.querySelectorAll('a[href*="/players/nfl/"]')
      : [];
    anchors.forEach((a) => {
      const pid = extractPidFromHref(a.getAttribute('href') || '');
      if (!pid) return;
      const info = rankings[pid];
      if (!info) return;
      injectAfter(a, { ...info, pid });
    });

    // Strategy 2: name-text match on elements that look like a player name.
    // We're conservative — only match short text nodes (1–40 chars) whose
    // parent is an inline element in a clearly list-like container.
    if (nameToId.size > 0) scanTextNodes(root);
  }

  function extractPidFromHref(href) {
    // matches /players/nfl/<id> or /players/nfl/<id>/...
    const m = href.match(/\/players\/nfl\/([A-Za-z0-9_\-]+)/);
    return m ? m[1] : null;
  }

  function scanTextNodes(root) {
    // Walk text nodes under root, but skip subtrees we've already scanned.
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(n) {
          const t = n.nodeValue;
          if (!t || t.length < 3 || t.length > 40) return NodeFilter.FILTER_REJECT;
          const p = n.parentElement;
          if (!p) return NodeFilter.FILTER_REJECT;
          if (p.closest(`.${BADGE_CLASS}`)) return NodeFilter.FILTER_REJECT;
          if (p.hasAttribute(SCANNED_ATTR)) return NodeFilter.FILTER_REJECT;
          // Skip if this is inside a link — the anchor strategy already handled it
          if (p.closest('a[href*="/players/nfl/"]')) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        },
      }
    );

    const hits = [];
    let node;
    while ((node = walker.nextNode())) {
      const text = node.nodeValue.trim();
      const key  = normalizeName(text);
      if (!key) continue;
      const pid = nameToId.get(key);
      if (!pid) continue;
      const info = rankings[pid];
      if (!info) continue;
      hits.push({ node, info, pid });
    }
    // Process after walk to avoid mutating while iterating
    for (const { node, info, pid } of hits) {
      const target = node.parentElement;
      if (target) injectAfter(target, { ...info, pid });
    }
  }

  // ─────────────────────────────────────────────────────────────
  //  Mutation observer (Sleeper is a SPA)
  // ─────────────────────────────────────────────────────────────

  function startObserver() {
    if (observer) return;
    observer = new MutationObserver((mutations) => {
      let touched = false;
      for (const m of mutations) {
        if (m.addedNodes && m.addedNodes.length) { touched = true; break; }
      }
      if (touched) scheduleScan();
    });
    observer.observe(document.body, { childList: true, subtree: true });
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
