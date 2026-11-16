#!/usr/bin/env node
// The Home playoff card with the server's `team_direction` block (flag
// `league.direction_card`; spec docs/plans/league-projections/direction-pages/
// spec.md §4, §7, §9, §10.1; D-265, D-270).
//
// RENDERS the real HomePlayoffBanner against host stubs (tests/
// direction-card-harness.js) and EXECUTES utils/directionCard: the card shows
// what the block says and decides nothing itself; the two figures, the
// owned-by line, the hidden and "last saved" pick; the stacked layout; zero
// buttons (the button row, cells A and B, is deferred by D-270); today's row
// when the flag is off or the block is absent; both hosts; the
// `direction_card_shown` impression. The half sheet is check-direction-sheet.js.
//
// Run: node tests/check-direction-card.js
'use strict';

const h = require('./direction-card-harness');
const { check, mount, render, byId, byType, words, block, forecast, state, cardUtil: u, props, read, readRoot, strip } = h;

const bannerSrc = strip(read('src/components/home/HomePlayoffBanner.tsx'));
const utilSrc = read('src/utils/directionCard.ts');
const hub = strip(read('src/components/home/HomeHub.tsx'));
const ls = strip(read('src/screens/LeagueSummaryScreen.tsx'));
const spec = readRoot('docs/plans/league-projections/direction-pages/spec.md');
const view = (b, p, st) => Object.assign(forecast(p, st), b === undefined ? {} : { team_direction: b });

// ═══ A. Which block the card honours (H-12) ═══════════════════════════════
{
  check(u.cardBlock(view(block()), false) === null, 'A1. flag off: no block, whatever the read holds');
  check(u.cardBlock(view(undefined), true) === null, 'A2. no block on the read (older server): today\'s row');
  check(u.cardBlock(view(block({ version: 2 })), true) === null && u.cardBlock(view(block({ options: null })), true) === null,
    'A3. an unknown version or a block without options: today\'s row');
  const b = block();
  check(u.cardBlock(view(b), true) === view(b).team_direction || JSON.stringify(u.cardBlock(view(b), true)) === JSON.stringify(b),
    'A4. a version-1 block is honoured as sent');
}

// ═══ B. Today's row when the flag is off or the block is absent (H-12) ═════
for (const [name, data, flags] of [
  ['flag off, block on the read', view(block()), { 'league.direction_card': false }],
  ['flag on, no block', view(undefined), {}],
  ['flag on, unknown version', view(block({ version: 9 })), {}],
]) {
  const tree = mount(data, flags);
  const viewLink = byId(tree, 'home.playoff.view');
  check(!byId(tree, 'home.playoff.figures') && !byId(tree, 'home.playoff.pick') && words(tree).includes('Playoff chance'),
    `B1. ${name}: today's one row, no projected pick`);
  check(viewLink && viewLink.props.onPress === props.onDetails && viewLink.props.accessibilityLabel === 'View full projections',
    `B2. ${name}: "View" opens Standings as today`);
  check(state.tracked.length === 0 && byType(tree, 'DirectionSheet').length === 0, `B3. ${name}: no impression, no sheet`);
}

// ═══ C. The two figures (H-1 to H-3) ═══════════════════════════════════════
{
  const tree = mount(view(block()), { 'league.direction_view_sheet': false });
  const playoff = byId(tree, 'home.playoff.figure.playoff');
  const pick = byId(tree, 'home.playoff.pick');
  check(byId(tree, 'home.playoff.figures') && playoff && pick, 'C1. two figures side by side in one row');
  check(words(playoff).includes('Playoff chance') && JSON.stringify(words(byId(tree, 'home.playoff.details'))) === '["62.4%"]',
    'C2. H-2: playoff chance unchanged: the saved run\'s figure through playoffOdds, as a link to Standings');
  check(byId(tree, 'home.playoff.details').props.onPress === props.onDetails, 'C3. the percentage still opens Standings');
  check(words(pick).includes('Projected pick') && JSON.stringify(words(byId(tree, 'home.playoff.pick.value'))) === '["1.08"]',
    'C4. H-3: "Projected pick" with the server\'s label');
  const odd = mount(view(block({ projected_pick: { label: '1.11', slot: 3, owns_own_pick: true, owner_name: 'x' } })));
  check(JSON.stringify(words(byId(odd, 'home.playoff.pick.value'))) === '["1.11"]',
    'C5. the label is printed as sent (the card never derives it from the slot)');
  check(byId(tree, 'home.playoff.explain') && byId(tree, 'home.playoff.view'), 'C6. H-7: the info toggle and "View ›" stay');
}

// ═══ D. "owned by" (H-4) ══════════════════════════════════════════════════
{
  const owned = mount(view(block({ projected_pick: { label: '1.03', slot: 3, owns_own_pick: false, owner_name: 'Rivals FC' } })));
  check(JSON.stringify(words(byId(owned, 'home.playoff.pick.owner'))) === '["owned by Rivals FC"]'
      && JSON.stringify(words(byId(owned, 'home.playoff.pick.value'))) === '["1.03"]',
    'D1. another team owns the pick: the figure still shows, a second line reads "owned by [team]"');
  const nameless = mount(view(block({ projected_pick: { label: '1.03', slot: 3, owns_own_pick: false, owner_name: '' } })));
  check(JSON.stringify(words(byId(nameless, 'home.playoff.pick.owner'))) === '["owned by another team"]', 'D2. no name sent: "owned by another team"');
  check(!byId(mount(view(block())), 'home.playoff.pick.owner'), 'D3. your own pick: no second line');
  check(byId(owned, 'home.playoff.pick').props.accessibilityLabel === 'Projected pick 1.03, owned by Rivals FC',
    'D4. one spoken label for the figure');
}

// ═══ E. Hidden pick (H-5, H-6) ═════════════════════════════════════════════
{
  const hidden = mount(view(block({ projected_pick: null })));
  check(byId(hidden, 'home.playoff.figures') && !byId(hidden, 'home.playoff.pick'),
    'E1. H-5 / H-6: the server sends no pick (non-max-PF draft order, no saved run): the cell is hidden');
  check(!/draft_order|reverse_standings|lottery|slot_ranks|label_slot/.test(bannerSrc + utilSrc),
    'E2. the card reads no draft order and ranks nothing: the server hides the pick');
  const stale = mount(view(block({ state: 'unavailable', reason: 'stale', band: null, primary: null }), 0.624, 'stale'));
  const notes = words(stale).filter((w) => w === 'last saved').length;
  check(byId(stale, 'home.playoff.pick') && notes === 2 && /, last saved$/.test(byId(stale, 'home.playoff.pick').props.accessibilityLabel),
    'E3. H-6: a forecast that is not current keeps the pick under the same "last saved" note as the percentage');
  const noEstimate = mount(view(block(), null, 'no_run'));
  check(!byId(noEstimate, 'home.playoff.pick') && byId(noEstimate, 'home.playoff.status'),
    'E4. no playoff-chance figure (no saved estimate): no projected pick either; the status shows');
}

// ═══ F. The explanation (H-7) ══════════════════════════════════════════════
{
  const SENTENCE = 'Projected pick is where your own first-round pick lands if the season follows the forecast.';
  check(spec.includes(`"${SENTENCE}"`), 'F1. the sentence is the spec\'s, verbatim');
  let tree = mount(view(block()));
  byId(tree, 'home.playoff.explain').props.onPress(); tree = render();
  check(words(byId(tree, 'home.playoff.explanation')).includes(SENTENCE), 'F2. the explanation gains the sentence');
  tree = mount(view(block({ projected_pick: null })));
  byId(tree, 'home.playoff.explain').props.onPress(); tree = render();
  check(!words(byId(tree, 'home.playoff.explanation')).includes(SENTENCE), 'F3. no pick shown: no sentence about it');
}

// ═══ G. No button row in this build (H-8; D-270 defers cells A and B) ══════
{
  for (const b of ['low', 'middle', 'high']) {
    for (const primary of ['playoffs', 'draft_pick', null]) {
      for (const sheet of [true, false]) {
        const tree = mount(view(block({ band: b, primary })), { 'league.direction_view_sheet': sheet });
        const improve = words(tree).filter((w) => /Improve/.test(w));
        check(byType(tree, 'Button').length === 0 && improve.length === 0,
          `G1. band ${b}, primary ${primary}, sheet ${sheet}: no button on the card`);
      }
    }
  }
  check(!/<Button\b|from '\.\.\/chalkline'.*Button/.test(bannerSrc), 'G2. the card imports and draws no Button');
}

// ═══ H. Order, layout and targets (H-9, H-10) ══════════════════════════════
{
  const rec = { status: 'available', reason: null, playoff_probability: 0.624, recommended_outlook: 'contender', current_outlook: 'rebuilder',
    differs: true, suggestion: 's', explanation: 'e', captured_at: '2026-11-07T14:00:00Z' };
  const tree = mount(Object.assign(view(block()), { outlook_recommendation: rec }));
  const kids = tree.children.flat().filter((n) => n && typeof n === 'object' && n.type !== 'DirectionSheet');
  check(kids[0].props.testID === 'home.playoff.figures' && kids[kids.length - 1].props.testID === 'home.playoff.recommendation',
    'H1. H-9: the figures first, "Consider [outlook] · Review outlook" last and unchanged');
  check(/figures: \{ flex: 1, minWidth: 0, flexDirection: 'row', flexWrap: 'wrap'/.test(bannerSrc) && /figure: \{ minWidth: 120/.test(bannerSrc),
    'H2. H-10: the figures wrap: at large text sizes the second stacks under the first');
  const v = byId(tree, 'home.playoff.view');
  const i = byId(tree, 'home.playoff.explain');
  const d = byId(tree, 'home.playoff.details');
  const s = (x) => x.props.hitSlop;
  check(v.props.style.minHeight + s(v).top + s(v).bottom >= 44 && v.props.style.flexShrink === 0
      && i.props.style.height + s(i).top + s(i).bottom >= 44 && i.props.style.width + s(i).left + s(i).right >= 44
      && 20 + s(d).top + s(d).bottom >= 44, 'H3. every control keeps a 44pt target');
}

// ═══ I. The card decides nothing (spec §5.1) ═══════════════════════════════
{
  check(!/0\.35|0\.65|0\.45|REBUILDING|probability\s*[<>]=?|[<>]=?\s*0?\.\d|band\s*[<>]|Math\.(round|floor|ceil)/.test(bannerSrc + utilSrc),
    'I1. no cut, no comparison of a probability, no rounding in the card or its util');
  // Executed: the pick shows at any playoff chance the run holds.
  const at = [0.001, 0.2, 0.45, 0.5, 0.65, 0.9, 0.999, 1].filter((p) => !byId(mount(view(block(), p)), 'home.playoff.pick'));
  check(at.length === 0, 'I5. the projected pick shows at every playoff chance (the card hides nothing by probability)', at.join(','));
  check(!/direction\.playoff_probability|direction!?\.band|direction!?\.primary/.test(bannerSrc),
    'I2. the card reads neither the band nor the primary to draw anything (only the impression passes them on)');
  // A block whose band and primary disagree with the run: shown as sent, never re-derived.
  mount(view(block({ band: 'high', primary: 'draft_pick' }), 0.1));
  const ev = state.tracked[0];
  check(ev && ev[1].band === 'high' && ev[1].primary === 'draft_pick', 'I3. the server\'s band and primary pass through verbatim');
  check(JSON.stringify(u.shownProps(block({ band: 'weird', primary: 'other' }), false, false))
      === JSON.stringify({ band: 'none', primary: 'none', shown: 'none', sheet: false, pick_shown: false }),
    'I4. an unknown band or primary reads none; nothing is computed in its place');
}

// ═══ J. direction_card_shown (spec §9) ═════════════════════════════════════
{
  let tree = mount(view(block()));
  render(); render();
  check(state.tracked.length === 1 && state.tracked[0][0] === 'direction_card_shown', 'J1. once per mount, however often the card re-renders');
  check(JSON.stringify(state.tracked[0][1]) === JSON.stringify({ band: 'middle', primary: 'playoffs', shown: 'none', sheet: true, pick_shown: true })
      && state.tracked[0][2] === 'Home', 'J2. props: band, primary, shown (none: no buttons), sheet, pick_shown; screen = the host');
  mount(view(block({ band: null, primary: null, state: 'unavailable', reason: 'stale', projected_pick: null })),
    { 'league.direction_view_sheet': false });
  check(JSON.stringify(state.tracked[0][1]) === JSON.stringify({ band: 'none', primary: 'none', shown: 'none', sheet: false, pick_shown: false }),
    'J3. unusable forecast, sheet off, pick hidden: none / none / none / false / false');
  props.screen = 'LeagueRankings';
  mount(view(block()));
  check(state.tracked[0][2] === 'LeagueRankings', 'J4. H-11: the event carries the host screen');
  props.screen = 'Home';
  mount(view(undefined));
  check(state.tracked.length === 0, 'J5. no block: no impression');
  tree = mount(view(block()), { 'league.direction_card': false });
  check(state.tracked.length === 0 && tree, 'J6. flag off: no impression');
  const tax = readRoot('backend/analytics_taxonomy.py');
  const q = readRoot('backend/analytics_queries.py');
  const nonIntent = (q.match(/NON_INTENT_EVENTS[^=]*=[\s\S]*?\n\}\)/) || [''])[0];
  check(/"direction_card_shown":\s+frozenset\(\{"band", "primary", "shown", "sheet", "pick_shown"\}\)/.test(tax)
      && /"direction_card_shown"/.test(nonIntent), 'J7. registered with exactly these props, and an impression (NON_INTENT_EVENTS)');
}

// ═══ K. Both hosts (H-11) ═════════════════════════════════════════════════
{
  const homeMount = (/<HomePlayoffBanner[\s\S]*?\/>/.exec(hub) || [''])[0];
  const lsMount = (/<HomePlayoffBanner[\s\S]*?\/>/.exec(ls) || [''])[0];
  check(/screen="Home"/.test(homeMount) && /onDirectionTap=\{onDirectionTap\}/.test(homeMount), 'K1. Home mounts the card with screen "Home"');
  check(/screen=\{route\.name\}/.test(lsMount) && /onDirectionTap=\{onTileDirection\}/.test(lsMount),
    'K2. League Rankings mounts the same card with its route name');
  check(/useFlag\(DIRECTION_CARD_FLAG\)/.test(bannerSrc) && !/direction_card|DIRECTION_CARD_FLAG/.test(hub + ls),
    'K3. the card reads its own flag; neither host does');
}

// ═══ L. Flags and registration ════════════════════════════════════════════
{
  const features = JSON.parse(readRoot('config/features.json'));
  const flagsPy = readRoot('backend/feature_flags.py');
  check(features['league.direction_card'] === true && /"league\.direction_card",/.test(flagsPy)
      && u.DIRECTION_CARD_FLAG === 'league.direction_card', 'L1. league.direction_card: registered, true in features.json (ON from 2026-11-15, D-271)');
  for (const name of ['release', 'onboarding-v2', 'profiles-on']) {
    check(JSON.parse(readRoot(`backend/tests/fixtures/flags/${name}.json`))['league.direction_card'] === true, `L2. fixture ${name}.json mirrors it (true)`);
  }
  const pkg = JSON.parse(read('package.json'));
  check(pkg.scripts['test:direction-card'] === 'node tests/check-direction-card.js', 'L3. npm run test:direction-card');
  check(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(bannerSrc) && !/flare|gradient|blur/.test(bannerSrc), 'L4. Chalkline: tokens only, no flare');
}

h.finish('direction-card');
