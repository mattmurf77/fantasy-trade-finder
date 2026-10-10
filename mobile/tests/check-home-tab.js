#!/usr/bin/env node
// Home tab (flag `nav.home_tab`, docs/plans/home-tab/plan.md).
//
// WHY THIS EXISTS. The Home tab is one static screen, but it moves the
// app's front door, and three of its properties are exactly the kind that
// regress silently under D-056 (no simulator):
//   1. The flag is read IMPERATIVELY, ONCE at mount. A `useFlag` read would
//      let a mid-session revalidation insert/remove a tab — rewriting the
//      navigator's route array under the user — or rewrite the launch tab.
//   2. The launch tab keeps the first-run carve-out: while
//      `onboarding.trades_first` is live and the user has not swiped, the
//      app still opens on Trades (every analyst-guide step is scripted
//      against that screen). Everyone else opens on Home. Flag off ⇒
//      `initialTab`, whose block is pinned byte-identical here and by
//      check-canvas-results.js §10.
//   3. The flag must agree everywhere it is stated. `revalidateFlags`
//      replaces the whole map, so a key present in the baked default but
//      missing server-side flips the tab set between first paint and the
//      next launch.
// Also pinned: Home is the FIRST tab; the four option labels / targets /
// testIDs; the flag-gated Usage Trends row; no second FeedbackFAB
// (#196/#197); the `app/home` route.
//
// Dependency-free: text assertions over comment-stripped source.
// Run: node tests/check-home-tab.js
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const SRC = path.join(MOBILE, 'src');
const ROOT = path.join(MOBILE, '..');

let failures = 0;
const assert = (cond, name, why) => {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};

const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
// Block comments, JSX comments and whole-line `//` comments. Trailing `//`
// comments are left alone so a URL inside a string can never be eaten.
const stripComments = (s) =>
  s
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
// Read a repo-root file the OTHER half of this feature owns. Missing or
// unparseable is a failure of that assertion, never a crash of the suite.
const readRoot = (rel) => {
  try {
    return fs.readFileSync(path.join(ROOT, rel), 'utf8');
  } catch {
    return null;
  }
};
const readRootJson = (rel) => {
  try {
    return JSON.parse(readRoot(rel));
  } catch {
    return null;
  }
};

const tabNavRaw = read('navigation/TabNav.tsx');
const tabNav = stripComments(tabNavRaw);

// ═══════════════════════════════════════════════════════════════════════
// 1 — the flag read: imperative, once at mount.
// ═══════════════════════════════════════════════════════════════════════
const showAt = tabNav.indexOf('const [showHomeTab] = useState(');
const launchAt = tabNav.indexOf('const [launchTab] = useState(');
const initialAt = tabNav.indexOf('const [initialTab] = useState(');
{
  const seg = showAt >= 0 ? tabNav.slice(showAt, showAt + 160) : '';
  assert(/^const \[showHomeTab\] = useState\(\s*\(\) => !!useFeatureFlags\.getState\(\)\.flags\['nav\.home_tab'\],?\s*\);/.test(seg),
    '1a. showHomeTab reads nav.home_tab imperatively inside a useState initializer (decide-once)',
    'a conditional <Tab.Screen> rewrites the route array — the bar may change at most once per launch');
  // No reactive read of the flag anywhere in the app.
  const offenders = [];
  const walk = (dir) => {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(p);
      else if (/\.tsx?$/.test(ent.name)
        && /use(Flag|OnboardingFeature)\(\s*['"]nav\.home_tab['"]/.test(fs.readFileSync(p, 'utf8'))) {
        offenders.push(path.relative(SRC, p));
      }
    }
  };
  walk(SRC);
  assert(offenders.length === 0,
    '1b. nav.home_tab is never read through useFlag',
    `reactive read in: ${offenders.join(', ')}`);
  assert(!/setShowHomeTab|setLaunchTab/.test(tabNav),
    '1c. neither decision has a setter — nothing can change it after mount');
}

// ═══════════════════════════════════════════════════════════════════════
// 2 — the launch tab: trades-first carve-out, initialTab fallback.
// ═══════════════════════════════════════════════════════════════════════
{
  // The flag-off behavior, byte-identical (also check-canvas-results §10).
  const INITIAL_TAB = [
    'const [initialTab] = useState(() =>',
    "    !!useFeatureFlags.getState().flags['nav.trades_landing'] ||",
    "    (onboardingEnabled('onboarding.trades_first') &&",
    '      !getOnboardingState().firstSwipeDone)',
    "      ? 'Trades'",
    "      : 'Rank',",
    '  );',
  ].join('\n');
  assert(tabNavRaw.includes(INITIAL_TAB),
    '2a. the initialTab block is byte-identical (it IS the flag-off launch behavior)');
  assert(initialAt >= 0 && showAt >= 0 && launchAt > initialAt && launchAt > showAt,
    '2b. launchTab is declared after both initialTab and showHomeTab',
    'its initializer closes over both — declared earlier it reads a TDZ binding');
  const end = launchAt >= 0 ? tabNav.indexOf(');', launchAt) : -1;
  const seg = (end >= 0 ? tabNav.slice(launchAt, end + 2) : '').replace(/\s+/g, ' ');
  assert(seg === "const [launchTab] = useState(() => showHomeTab && !(onboardingEnabled('onboarding.trades_first') && !getOnboardingState().firstSwipeDone) ? 'Home' : initialTab, );",
    '2c. launchTab = Home only when the tab exists AND the user is not a trades-first first-run; else initialTab',
    `got: ${seg}`);
  assert(/initialRouteName=\{launchTab\}/.test(tabNav) && !/initialRouteName=\{initialTab\}/.test(tabNav),
    '2d. the navigator opens on launchTab');
}

// ═══════════════════════════════════════════════════════════════════════
// 3 — Home is the first tab, conditionally rendered, tap is tracked.
// ═══════════════════════════════════════════════════════════════════════
{
  assert(tabNav.split('<Tab.Navigator').length === 2, '3. exactly one Tab.Navigator');
  const navAt = tabNav.indexOf('<Tab.Navigator');
  const firstScreen = tabNav.indexOf('<Tab.Screen', navAt);
  const secondScreen = tabNav.indexOf('<Tab.Screen', firstScreen + 1);
  const home = tabNav.slice(firstScreen, secondScreen);
  assert(/^<Tab\.Screen\s+name="Home"/.test(home),
    '3a. the first Tab.Screen in the navigator is Home');
  assert(/\{showHomeTab \? \(\s*$/.test(tabNav.slice(navAt, firstScreen))
    && /\/>\s*\) : null\}\s*$/.test(home),
    '3b. …rendered only under showHomeTab (flag off ⇒ the screen is never constructed)');
  assert(/component=\{HomeScreen\}/.test(home)
    && /^import HomeScreen from '\.\.\/screens\/HomeScreen';$/m.test(tabNav),
    '3c. it mounts HomeScreen directly — no nested stack');
  assert(/tabBarIcon: tabIcon\('home'\)/.test(home) && /tabBarButtonTestID: 'tab\.home'/.test(home),
    "3d. home icon + testID 'tab.home'");
  assert(/tabPress: \(\) => \{\s*trackTab\('home', navigation\);\s*\}/.test(home),
    "3e. the tap emits tab_selected {tab:'home'} and does nothing else");
  assert(!/preventDefault/.test(home), '3f. the tap is never intercepted');
  const icon = stripComments(read('components/chalkline/Icon.tsx'));
  assert(/\|\s*'home'/.test(icon) && /^\s*home: </m.test(icon),
    "3g. the Icon set carries a 'home' glyph (name + path)");
}

// ═══════════════════════════════════════════════════════════════════════
// 4 — HomeScreen: exact copy, targets, testIDs; no second FeedbackFAB.
// ═══════════════════════════════════════════════════════════════════════
{
  const home = stripComments(read('screens/HomeScreen.tsx'));
  assert(/>\s*What would you like to do today\?\s*</.test(home),
    '4a. heading copy is exact');
  assert(/testID="home\.screen"/.test(home), '4b. root testID home.screen');
  const rows = [
    ['Rank', 'Rank', 'home.option.rank'],
    ['Find a Trade', 'Trades', 'home.option.trades'],
    ['See Matches', 'Matches', 'home.option.matches'],
    ['View my Leagues', 'League', 'home.option.league'],
  ];
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  let last = -1;
  let ordered = true;
  for (const [label, tab, id] of rows) {
    const m = new RegExp(
      `\\{\\s*label: '${esc(label)}',\\s*tab: '${esc(tab)}',\\s*testID: '${esc(id)}',?\\s*\\}`,
    ).exec(home);
    assert(!!m, `4c. "${label}" → ${tab} (${id})`);
    if (!m || m.index < last) ordered = false;
    if (m) last = m.index;
  }
  assert(ordered, '4d. the options render in the specced order');
  const optionsBlock = (/const OPTIONS = \[([\s\S]*?)\] as const;/.exec(home) || [])[1] || '';
  assert((optionsBlock.match(/testID: 'home\.option\./g) || []).length === 4,
    '4e. exactly four tab options');
  assert(/onPress=\{\(\) => navigation\.navigate\(o\.tab\)\}/.test(home)
    && /testID=\{o\.testID\}/.test(home)
    && /accessibilityRole="button"/.test(home),
    '4f. each row is a button that navigates to its own tab and carries its own testID');
  assert(!/FeedbackFAB/.test(home),
    '4g. no FeedbackFAB in HomeScreen',
    "RootNav's global mount covers tab screens — a second one is the #196/#197 double-FAB bug");
  assert(!/useQuery|useState|useEffect|fetch\(/.test(home),
    '4h. no data fetching and no local state');
  // Usage Trends (docs/plans/usage-trends/scope.md): one extra row, a
  // root-stack push rather than a tab jump, rendered only under its flag.
  assert(/const TRENDS_ROW = \{ label: 'Usage Trends', route: 'UsageTrends', testID: 'home\.option\.trends' \} as const;/.test(home)
    && /const trendsOn = useFlag\('usage_trends\.enabled'\);/.test(home)
    && /\{trendsOn \? \(\s*<Pressable\s+testID=\{TRENDS_ROW\.testID\}/.test(home)
    && /onPress=\{\(\) => navigation\.navigate\(TRENDS_ROW\.route\)\}/.test(home),
    '4i. a Usage Trends row pushes UsageTrends, only while usage_trends.enabled is on');
}

// ═══════════════════════════════════════════════════════════════════════
// 5 — the route table.
// ═══════════════════════════════════════════════════════════════════════
{
  const links = stripComments(read('utils/deepLinks.ts'));
  const mainAt = links.indexOf('Main: {');
  const seg = mainAt >= 0 ? links.slice(mainAt, links.indexOf('Rank: {', mainAt)) : '';
  assert(/path: 'app',\s*screens: \{\s*Home: 'home',\s*$/.test(seg),
    "5a. Home: 'home' sits under Main.screens (→ app/home)");
}

// ═══════════════════════════════════════════════════════════════════════
// 6 — flag parity: features.json, baked default, fixtures, FLAG_KEYS.
// ═══════════════════════════════════════════════════════════════════════
{
  const features = readRootJson('config/features.json');
  assert(!!features && features['nav.home_tab'] === true
    && typeof features['_comment_nav_home_tab'] === 'string',
    '6a. nav.home_tab is true in config/features.json with a house comment');
  assert(/^\s*'nav\.home_tab': true,$/m.test(stripComments(read('state/useFeatureFlags.ts'))),
    '6b. the baked default states it true',
    "absent, a fresh install's first boot (no cached map) has no Home tab");
  for (const f of ['release', 'onboarding-v2', 'profiles-on']) {
    const j = readRootJson(`backend/tests/fixtures/flags/${f}.json`);
    assert(!!j && j['nav.home_tab'] === true, `6c. ${f}.json mirrors it true`);
  }
  assert(/"nav\.home_tab",/.test(readRoot('backend/feature_flags.py') || ''),
    '6d. registered in FLAG_KEYS');
  const pkg = JSON.parse(fs.readFileSync(path.join(MOBILE, 'package.json'), 'utf8'));
  assert(pkg.scripts['test:home-tab'] === 'node tests/check-home-tab.js',
    '6e. npm run test:home-tab runs this suite');
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nhome-tab: all checks passed');
