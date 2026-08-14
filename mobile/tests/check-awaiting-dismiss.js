#!/usr/bin/env node
// #318 (mobile half) — dismiss from "Awaiting them": affordance placement,
// surface segmentation, the wire contract, and the fake-success guard.
//
// Named sabotages (plan 2026-08-13; S-8 RE-SCOPED — see below):
//   S-6 deck-leak:    render the Dismiss affordance from any deck mount (or
//       inside TradeCard itself) → the swipe deck grows a dismiss it must
//       never have. Pinned: `matches.awaiting-dismiss` lives ONLY in
//       MatchesScreen's awaiting footer; TradeCard authors no new Dismiss.
//   S-7 surface:      switch the awaiting mount to variant="match" → the
//       send button's surface flips awaiting→match and silently corrupts
//       sleeper_send_* segmentation. Pinned: awaiting keeps variant="swipe"
//       and TradeCard's non-match send keeps surface="awaiting".
//   S-8 contract bytes (RE-SCOPED from the plan's flag sabotage — C-7
//       resolved to NO new flag, D-035 precedent, so there is no flag gate
//       to sabotage): wrong path, or CROSSED my_give/my_receive, or a
//       row-id-shaped body → the server 400s or dismisses the WRONG like.
//       Pinned: POST /api/trades/awaiting/dismiss with
//       {league_id, my_give ← my_side_player_ids,
//        my_receive ← their_side_player_ids, partner_id ← counterparty_user_id}.
//       Plus the C-7 pin itself: no `awaiting_dismiss` flag key anywhere.
//   S-9 fake-success: delete the onError snapshot-restore → a failed POST
//       leaves the row invisibly un-dismissed and the user believes it's
//       gone. Pinned: rollback branch + the exact error-toast copy.
//
// Comment-strip before every absence assertion. Seed-independent.
//
// Run: node tests/check-awaiting-dismiss.js

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const SRC_DIR = path.join(MOBILE, 'src');
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));

function filesContaining(needle) {
  const out = [];
  (function walkDir(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walkDir(p);
      else if (/\.(tsx?|ts)$/.test(entry.name)
        && stripComments(fs.readFileSync(p, 'utf8')).includes(needle)) {
        out.push(path.relative(MOBILE, p));
      }
    }
  })(SRC_DIR);
  return out;
}

const SCREEN = stripComments(read('src/screens/MatchesScreen.tsx'));
const TC = stripComments(read('src/components/TradeCard.tsx'));
const API = stripComments(read('src/api/trades.ts'));

// ── S-6: the affordance lives ONLY in the Matches awaiting footer ──────────
{
  const hosts = filesContaining('matches.awaiting-dismiss');
  assert(
    hosts.length === 1 && hosts[0] === 'src/screens/MatchesScreen.tsx',
    '1. S-6 — matches.awaiting-dismiss authored ONLY by MatchesScreen',
    `found in: ${hosts.join(', ') || 'nowhere'}`,
  );
}
{
  // Inside the awaiting mount's footer: the Dismiss button and the awaiting
  // list's MatchValueSection share one footer stack, and the mount that
  // carries it is variant="swipe".
  const flat = SCREEN.replace(/\s+/g, ' ');
  const footerIdx = flat.indexOf('footer={ <View style={styles.awaitingFooter}>');
  assert(footerIdx > -1, '2. S-6 — Dismiss rides the awaiting card\'s footer stack');
  const around = flat.slice(Math.max(0, footerIdx - 3000), footerIdx);
  assert(
    /variant="swipe"/.test(around) && !/variant="match"/.test(around.slice(around.lastIndexOf('<TradeCardComp'))),
    '3. S-7 — the awaiting mount keeps variant="swipe"',
  );
  const footerBlock = flat.slice(footerIdx, flat.indexOf('ItemSeparatorComponent', footerIdx));
  assert(
    /testID="matches\.awaiting-dismiss"/.test(footerBlock)
      && /variant="pass"/.test(footerBlock)
      && /label="Dismiss"/.test(footerBlock)
      && /onPress=\{\(\) => handleDismissAwaiting\(item\)\}/.test(footerBlock),
    '4. Dismiss button: pass variant, wired to handleDismissAwaiting',
  );
}
assert(
  !/matches\.awaiting-dismiss/.test(TC)
    && (TC.match(/label="Dismiss"/g) || []).length === 1,
  '5. S-6 — TradeCard authors NO new Dismiss (its single Dismiss stays the match variant\'s)',
);
assert(
  /surface="awaiting"/.test(TC),
  '6. S-7 — TradeCard\'s non-match send keeps surface="awaiting"',
);

// ── S-8 (re-scoped): the wire contract, byte for byte ──────────────────────
{
  const m = API.replace(/\s+/g, ' ').match(
    /export async function dismissAwaitingTrade\(row: AwaitingTrade\) \{ return api\.post[^(]*\( '([^']+)', \{ ([^}]*) \}, \); \}/,
  );
  assert(!!m, '7. S-8 — dismissAwaitingTrade is the single api.post wrapper');
  const bodySrc = m ? m[2] : '';
  assert(
    m && m[1] === '/api/trades/awaiting/dismiss',
    '8. S-8 — POST path is /api/trades/awaiting/dismiss',
    m ? `path is ${m[1]}` : undefined,
  );
  assert(
    /league_id: row\.league_id/.test(bodySrc),
    '9. S-8 — body.league_id ← row.league_id',
  );
  assert(
    /my_give: row\.my_side_player_ids/.test(bodySrc),
    '10. S-8 — body.my_give ← my_side_player_ids (yours-perspective, UNCROSSED)',
  );
  assert(
    /my_receive: row\.their_side_player_ids/.test(bodySrc),
    '11. S-8 — body.my_receive ← their_side_player_ids (UNCROSSED)',
  );
  assert(
    /partner_id: row\.counterparty_user_id/.test(bodySrc),
    '12. S-8 — body.partner_id ← counterparty_user_id',
  );
}
{
  // C-7 pin: NO new feature flag for this affordance (operator decision,
  // D-035 precedent). A half-registered flag key is worse than none.
  const flagged = filesContaining('awaiting_dismiss');
  assert(
    flagged.length === 0,
    '13. C-7 — no `awaiting_dismiss` flag key anywhere in mobile/src',
    `found in: ${flagged.join(', ')}`,
  );
}

// ── S-9: honest failure — rollback + toast, undo delays the POST ───────────
{
  const flat = SCREEN.replace(/\s+/g, ' ');
  const mutIdx = flat.indexOf('const dismissAwaitingMutation = useMutation(');
  assert(mutIdx > -1, '14. dismissAwaitingMutation exists');
  const mut = flat.slice(mutIdx, flat.indexOf('const pendingDismissRef', mutIdx));
  assert(
    /onMutate:.*getQueryData<AwaitingTrade\[\]>\(\['awaiting-trades'\]\)/.test(mut),
    '15. S-9 — onMutate snapshots the awaiting cache',
  );
  const onErrIdx = mut.indexOf('onError:');
  const onErr = mut.slice(onErrIdx, mut.indexOf('onSuccess:'));
  assert(
    /setQueryData\(\['awaiting-trades'\], ctx\.prev\)/.test(onErr),
    '16. S-9 — onError RESTORES the snapshot (row never silently vanishes)',
  );
  assert(
    /Could not dismiss — try again/.test(onErr),
    '17. S-9 — onError surfaces the honest toast copy',
  );
  assert(
    /invalidateQueries\(\{ queryKey: \['awaiting-trades'\] \}\)/.test(onErr),
    '18. S-9 — undo-flag path refetches so a post-window failure restores the row',
  );
}
{
  const flat = SCREEN.replace(/\s+/g, ' ');
  const h = flat.slice(
    flat.indexOf('function handleDismissAwaiting'),
    flat.indexOf('async function handleOpenInCalc'),
  );
  assert(
    /if \(!swipeUndoOn\) \{ dismissAwaitingMutation\.mutate\(a\); return; \}/.test(h),
    '19. undo flag OFF posts immediately (ux.swipe_undo honoured, no new flag)',
  );
  assert(
    /kind: 'awaiting'/.test(h) && /UNDO_HOLD_MS/.test(h)
      && /action: \{ label: 'Undo', onPress: undoDismiss \}/.test(h),
    '20. undo flag ON delays the POST behind the 5 s window with an Undo action',
  );
  // The generalized flush must route awaiting holds to the awaiting mutation
  // (unmount commits both kinds through the same shared ref).
  assert(
    /function flushPendingDismiss\(\) \{.*?dismissAwaitingMutation\.mutate\(p\.row\)/.test(flat),
    '21. unmount/next-dismiss flush commits awaiting holds via the awaiting mutation',
  );
}

console.log(failures ? `\n${failures} FAILURE(S)` : '\nALL CHECKS PASSED (21)');
process.exit(failures ? 1 : 0);
