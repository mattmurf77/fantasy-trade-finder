# Feature Evaluation: Player Ranking Screen

**Date:** 2026-04-12
**Files reviewed:**
- `iPhone/src/screens/RankPlayersScreen.js`
- `iPhone/src/context/AppContext.js`
- `iPhone/src/utils/theme.js`
- `iPhone/src/services/api.js`
- `iPhone/src/utils/storage.js`

## Summary

The Player Ranking Screen is a well-organized React Native component that handles the core user interaction of ranking three players at a time. It successfully implements the trio-selection pattern, progress tracking, and auto-confirm feature with clean UI. The main opportunities for improvement lie in error resilience (particularly around stale data and network failures), performance optimization (memoization to prevent unnecessary re-renders), and better separation of concerns (extracting state logic from the main component).

## Findings

### Performance: Missing useMemo and useCallback for nested components

**Severity:** Medium
**Location:** `RankPlayersScreen.js`, lines 29-100 (TierBadge, PosBadge, PlayerCard components)

The `PlayerCard`, `TierBadge`, and `PosBadge` components are recreated on every render of the parent component, even though their props may not have changed. The `getRank` function is called multiple times per render. This causes unnecessary re-renders of card components, which is particularly problematic on slower devices when rendering multiple cards in quick succession.

**Current code:**
```javascript
function PosBadge({ position, isPick }) {
  const label = isPick ? 'PICK' : position;
  const bg = isPick ? colors.pick : positionColor(position);
  return (
    <View style={[styles.posBadge, { backgroundColor: bg + '22', borderColor: bg + '55' }]}>
      <Text style={[styles.posBadgeText, { color: bg }]}>{label}</Text>
    </View>
  );
}

function PlayerCard({ player, side, rank, onPress, disabled }) {
  // ... component body
}

// In RankPlayersScreen:
{SIDES.map(side => {
  const player = trio ? trio[`player_${side}`] : null;
  return (
    <PlayerCard
      key={side}
      player={player}
      side={side}
      rank={getRank(side)}
      onPress={selectCard}
      disabled={locked}
    />
  );
})}
```

**Suggested improvement:**
```javascript
const PosBadge = React.memo(({ position, isPick }) => {
  const label = isPick ? 'PICK' : position;
  const bg = isPick ? colors.pick : positionColor(position);
  return (
    <View style={[styles.posBadge, { backgroundColor: bg + '22', borderColor: bg + '55' }]}>
      <Text style={[styles.posBadgeText, { color: bg }]}>{label}</Text>
    </View>
  );
});

const PlayerCard = React.memo(({ player, side, rank, onPress, disabled }) => {
  // ... component body
});

// In RankPlayersScreen, wrap selectCard with useCallback:
const selectCard = useCallback((side) => {
  if (locked || !trio) return;
  // ... rest of logic
}, [locked, trio, selection, autoConfirm]);

// And wrap getRank:
const getRank = useCallback((side) => {
  const idx = selection.indexOf(side);
  return idx !== -1 ? idx + 1 : 0;
}, [selection]);
```

---

### Error Handling: Limited resilience for network and stale data scenarios

**Severity:** High
**Location:** `RankPlayersScreen.js`, lines 124-139 (loadTrio), 165-195 (submitRanking)

The error handling catches network failures and reports them via toast, but several edge cases are not well-managed:

1. **Stale trio handling** (line 174-178): When a `stale_trio` error occurs, the component reloads the trio but doesn't clarify to the user that their ranking was rejected. A user might think their ranking was accepted.

2. **Silent failures on API calls**: The `getProgress` call in `loadTrio` (line 131) doesn't check for errors—if it fails, the progress state silently doesn't update.

3. **No timeout handling**: If the API is slow or unresponsive, users could be blocked indefinitely waiting for a trio to load.

4. **Incomplete error messages**: Generic "Could not reach server" message doesn't distinguish between network unavailable, server down, or timeout.

**Current code:**
```javascript
const loadTrio = async () => {
  setSelection([]);
  setLocked(false);
  setTrio(null);
  try {
    const [trioData, prog] = await Promise.all([
      api.getTrio(position),
      api.getProgress(position),
    ]);
    if (trioData.error) { showToast(trioData.error); return; }
    setTrio(trioData);
    if (prog) setProgress(prog);
  } catch (e) {
    showToast('Could not reach server');
  }
};

const submitRanking = async (order = selection) => {
  if (locked || order.length < 3 || !trio) return;
  setLocked(true);

  const players = { a: trio.player_a, b: trio.player_b, c: trio.player_c };
  const ranked = order.map(s => players[s].id);

  try {
    const data = await api.submitRanking(ranked);
    if (data.error === 'stale_trio') {
      showToast('Player data refreshed — ranking again');
      setLocked(false);
      loadTrio();
      return;
    }
    if (data.error) { showToast(data.error); setLocked(false); return; }
    // ...
  } catch {
    showToast('Submit failed');
  }
};
```

**Suggested improvement:**
```javascript
const loadTrio = async () => {
  setSelection([]);
  setLocked(false);
  setTrio(null);
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
    
    const [trioData, prog] = await Promise.all([
      api.getTrio(position, { signal: controller.signal }),
      api.getProgress(position, { signal: controller.signal }),
    ]);
    clearTimeout(timeoutId);
    
    if (trioData.error) { 
      showToast(trioData.error); 
      return; 
    }
    setTrio(trioData);
    
    if (prog?.error) {
      console.warn('Progress fetch failed:', prog.error);
      // Set reasonable defaults, don't fail the whole load
      setProgress({ interaction_count: 0, threshold: 10, threshold_met: false });
    } else if (prog) {
      setProgress(prog);
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      showToast('Server is taking too long — check your connection');
    } else {
      showToast('Could not reach server');
    }
    console.error('loadTrio error:', e);
  }
};

const submitRanking = async (order = selection) => {
  if (locked || order.length < 3 || !trio) return;
  setLocked(true);

  const players = { a: trio.player_a, b: trio.player_b, c: trio.player_c };
  const ranked = order.map(s => players[s].id);

  try {
    const data = await api.submitRanking(ranked);
    if (data.error === 'stale_trio') {
      showToast('Player data refreshed — your ranking was not recorded. Please rank again.');
      setLocked(false);
      setSelection([]);
      loadTrio();
      return;
    }
    if (data.error) { 
      showToast(data.error); 
      setLocked(false); 
      return; 
    }

    setProgress(data);
    if (data.threshold_met && data.interaction_count === data.threshold) {
      showToast('Rankings established!');
    }
    
    setTimeout(() => {
      setSelection([]);
      setLocked(false);
      loadTrio();
    }, 350);
  } catch (e) {
    showToast('Submit failed — your ranking was not recorded');
    setLocked(false);
    console.error('submitRanking error:', e);
  }
};
```

---

### Structure & Design: State complexity and mixed concerns

**Severity:** Medium
**Location:** `RankPlayersScreen.js`, lines 102-219 (component state and logic)

The component manages 8 pieces of state (`position`, `trio`, `selection`, `locked`, `autoConfirm`, `progress`, `toast`) and coordinates between them, plus handles API calls, local storage persistence, and UI logic all in one place. This creates several problems:

1. **Hard to test**: The component ties together API calls, UI state, and business logic tightly. Unit testing any one piece requires mocking everything.
2. **Difficult to extend**: Adding features like "undo multiple rankings" or "batch ranking submissions" would require significant refactoring.
3. **State synchronization bugs**: The `autoConfirm` toggle loads from storage in a useEffect with no dependency array, then depends on it in the selection logic.
4. **Unclear data flow**: It's not immediately obvious which state changes trigger which API calls.

**Current code:**
```javascript
export default function RankPlayersScreen() {
  const [position, setPosition] = useState('RB');
  const [trio, setTrio] = useState(null);
  const [selection, setSelection] = useState([]);
  const [locked, setLocked] = useState(false);
  const [autoConfirm, setAutoConfirm] = useState(false);
  const [progress, setProgress] = useState({ interaction_count: 0, threshold: 10, threshold_met: false });
  const [toast, setToast] = useState('');

  useEffect(() => {
    storage.getAutoConfirm().then(setAutoConfirm);
  }, []);

  useEffect(() => {
    loadTrio();
  }, [position]); // Missing dependencies: if loadTrio uses selection, this won't update
```

**Suggested improvement:**

Extract ranking logic into a custom hook:

```javascript
// useRankingState.js
export function useRankingState(position) {
  const [trio, setTrio] = useState(null);
  const [selection, setSelection] = useState([]);
  const [locked, setLocked] = useState(false);
  const [progress, setProgress] = useState({ interaction_count: 0, threshold: 10, threshold_met: false });
  const [error, setError] = useState('');

  const loadTrio = useCallback(async () => {
    setSelection([]);
    setLocked(false);
    setTrio(null);
    try {
      const [trioData, prog] = await Promise.all([
        api.getTrio(position),
        api.getProgress(position),
      ]);
      if (trioData.error) { 
        setError(trioData.error); 
        return; 
      }
      setTrio(trioData);
      if (prog) setProgress(prog);
      setError('');
    } catch (e) {
      setError('Could not reach server');
    }
  }, [position]);

  const submitRanking = useCallback(async (order = selection) => {
    // ... ranking submission logic
  }, [selection, trio, locked]);

  useEffect(() => {
    loadTrio();
  }, [position, loadTrio]);

  return { trio, selection, setSelection, locked, progress, error, loadTrio, submitRanking };
}

// RankPlayersScreen.js
export default function RankPlayersScreen() {
  const [position, setPosition] = useState('RB');
  const { trio, selection, setSelection, locked, progress, error, loadTrio, submitRanking } = 
    useRankingState(position);
  const [autoConfirm, setAutoConfirm] = useState(false);

  useEffect(() => {
    storage.getAutoConfirm().then(setAutoConfirm);
  }, []);

  // ... UI code only
}
```

---

### Readability & Naming: Magic numbers and inline style calculations

**Severity:** Low
**Location:** `RankPlayersScreen.js`, lines 10-27, 44, 293-295

The component uses several magic numbers and inline string concatenations that hurt readability:

1. **Tier thresholds** (lines 16-19): Magic numbers `50`, `150`, `300` defining tier ranks
2. **Color opacity calculations** (line 44, 248): `colors.gold + '22'` and similar inline hex concatenations
3. **Toast duration** (line 121): `3000` ms hardcoded
4. **Submit delay** (line 194): `350` ms hardcoded with no explanation
5. **Timeout assumptions** (line 217): Progress percentage calculation assumes `threshold > 0`

**Current code:**
```javascript
function valueTier(p) {
  if (!p.search_rank && p.search_rank !== 0) return null;
  const r = p.search_rank;
  if (r <= 50) return 'elite';
  if (r <= 150) return 'high';
  if (r <= 300) return 'mid';
  return 'depth';
}

// In PlayerCard:
<View style={[styles.posBadge, { backgroundColor: bg + '22', borderColor: bg + '55' }]}>

// In showToast:
setTimeout(() => setToast(''), 3000);

// In submitRanking:
setTimeout(() => {
  setSelection([]);
  setLocked(false);
  loadTrio();
}, 350);
```

**Suggested improvement:**
```javascript
const RANKING_TIERS = {
  ELITE: { max: 50, label: 'Elite', color: '#f59e0b' },
  HIGH: { max: 150, label: 'High', color: '#22c55e' },
  MID: { max: 300, label: 'Mid', color: '#3b82f6' },
  DEPTH: { max: Infinity, label: 'Depth', color: '#7a7f96' },
};

const UI_TIMING = {
  TOAST_DURATION_MS: 3000,
  SUBMIT_ANIMATION_DELAY_MS: 350, // Allow animation to complete before reloading
  API_TIMEOUT_MS: 10000,
};

const COLOR_OPACITY = {
  BADGE_BG: '22',   // ~13% opacity
  BADGE_BORDER: '55', // ~33% opacity
};

function valueTier(p) {
  if (!p.search_rank && p.search_rank !== 0) return null;
  const r = p.search_rank;
  for (const [key, tier] of Object.entries(RANKING_TIERS)) {
    if (r <= tier.max) return key.toLowerCase();
  }
}

// In PlayerCard:
<View style={[styles.posBadge, { 
  backgroundColor: bg + COLOR_OPACITY.BADGE_BG, 
  borderColor: bg + COLOR_OPACITY.BADGE_BORDER 
}]}>

// In showToast:
setTimeout(() => setToast(''), UI_TIMING.TOAST_DURATION_MS);

// In submitRanking:
setTimeout(() => {
  setSelection([]);
  setLocked(false);
  loadTrio();
}, UI_TIMING.SUBMIT_ANIMATION_DELAY_MS);
```

---

### Testability: Tight coupling to API and storage modules

**Severity:** Medium
**Location:** `RankPlayersScreen.js`, lines 7-8 (imports), 124-139 (loadTrio), 124-201 (submitRanking)

The component directly imports and calls `api` and `storage` modules, making it difficult to unit test without mocking at the module level. There's no way to inject test doubles or verify call arguments easily. The component also doesn't expose loading states for the trio or progress independently, making it hard to test UI behavior during different async phases.

**Current code:**
```javascript
import { api } from '../services/api';
import { storage } from '../utils/storage';

const loadTrio = async () => {
  // ... directly calls api.getTrio, api.getProgress
};

const submitRanking = async (order = selection) => {
  // ... directly calls api.submitRanking
};

const toggleAutoConfirm = async () => {
  // ... directly calls storage.setAutoConfirm
};
```

**Suggested improvement:**

Create a custom hook that accepts API and storage dependencies:

```javascript
export function useRankingState(position, { api: apiService, storage: storageService } = {}) {
  const api = apiService || require('../services/api').api;
  const storage = storageService || require('../utils/storage').storage;

  // ... hook implementation
}

// In tests:
const mockApi = {
  getTrio: jest.fn(),
  getProgress: jest.fn(),
  submitRanking: jest.fn(),
};

const mockStorage = {
  getAutoConfirm: jest.fn(),
  setAutoConfirm: jest.fn(),
};

const { trio, submitRanking } = useRankingState('RB', { 
  api: mockApi, 
  storage: mockStorage 
});
```

---

### Structure & Design: Auto-confirm feature tightly coupled to selection logic

**Severity:** Medium
**Location:** `RankPlayersScreen.js`, lines 156-159 (selectCard), 197-201 (toggleAutoConfirm)

The auto-confirm feature is checked inside the `selectCard` function, which means the selection logic is aware of the auto-confirm setting. This creates a hidden dependency: if you want to test "what happens when 3 cards are selected", you need to know about auto-confirm. It also means adding other "auto-behavior" features would require more branching in this hot function.

**Current code:**
```javascript
const selectCard = (side) => {
  if (locked || !trio) return;

  const existingIdx = selection.indexOf(side);
  if (existingIdx !== -1) {
    setSelection(selection.slice(0, existingIdx));
    return;
  }

  const newSelection = [...selection, side];

  if (newSelection.length === 3) {
    const last = SIDES.find(s => !newSelection.includes(s));
    const full = [...newSelection, last];
    setSelection(full);
    if (autoConfirm) {  // Hidden coupling
      submitRanking(full);
    }
  } else {
    setSelection(newSelection);
  }
};
```

**Suggested improvement:**
```javascript
// Separate the auto-behavior logic into an effect
useEffect(() => {
  if (selection.length === 3 && autoConfirm && !locked) {
    submitRanking(selection);
  }
}, [selection, autoConfirm, locked, submitRanking]);

const selectCard = useCallback((side) => {
  if (locked || !trio) return;

  const existingIdx = selection.indexOf(side);
  if (existingIdx !== -1) {
    setSelection(selection.slice(0, existingIdx));
    return;
  }

  const newSelection = [...selection, side];

  if (newSelection.length === 3) {
    const last = SIDES.find(s => !newSelection.includes(s));
    const full = [...newSelection, last];
    setSelection(full);
    // Let the useEffect handle auto-confirm logic
  } else {
    setSelection(newSelection);
  }
}, [locked, trio, selection]);
```

---

## Scores

| Dimension | Score (1-5) | Notes |
|---|---|---|
| Structure & Design | 3 | Component handles too many concerns; state logic could be extracted into hooks. |
| Readability & Naming | 3 | Magic numbers and color opacity calculations should be constants. Function names are clear but logic is dense. |
| Performance | 3 | Missing memoization on child components and callback functions causes unnecessary re-renders. |
| Error Handling | 2 | Limited resilience for stale data, network timeouts, and progress fetch failures. Ambiguous error messages. |
| Security | 4 | No obvious vulnerabilities; input is properly encoded in API calls and storage is local. |
| Testability | 2 | Tight coupling to api and storage modules makes unit testing difficult. State changes are tangled. |
| Maintainability | 3 | Adding new features (batch actions, undo, filtering) would require significant refactoring due to monolithic state management. |

**Overall: 2.9/5**

## Top 3 Recommendations

1. **Extract ranking logic into a custom hook (`useRankingState`)** — This is the highest-impact change. It will immediately improve testability, make the component easier to extend, and clarify the data flow. You'll be able to test ranking submission, error handling, and progress updates independently of the UI.

2. **Improve error resilience in `loadTrio` and `submitRanking`** — Add timeout handling, better error messages, and ensure the stale-trio flow clearly communicates that a ranking wasn't accepted. This prevents user confusion and reduces support burden.

3. **Memoize child components and wrap callbacks with `useCallback`** — This is a quick win that improves performance on lower-end devices, especially when users are rapidly selecting cards. Wrap `PlayerCard`, `TierBadge`, and `PosBadge` with `React.memo`, and wrap `selectCard`, `submitRanking`, and `getRank` with `useCallback`.
