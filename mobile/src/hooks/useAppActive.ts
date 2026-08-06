// `true` while the app is in the FOREGROUND (AppState === 'active').
//
// Added for the Draft Room's live poll (rookie-draft M4), which is this
// app's first recurring fetch and must issue literally ZERO requests while
// backgrounded. `useIsFocused` alone is not enough: a focused screen stays
// focused when the user swipes to the home screen.
//
// 'inactive' (app switcher, Control Center, an incoming call banner)
// deliberately counts as NOT active. It is a brief interruption, but the
// user cannot see the screen during it, so a fetch then is a fetch nobody
// asked for — and treating it as inactive is the conservative direction:
// the worst case is one skipped 15 s tick, resolved on the next one.

import { useEffect, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';

export function useAppActive(): boolean {
  const [active, setActive] = useState(
    () => AppState.currentState === 'active',
  );

  useEffect(() => {
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      setActive(next === 'active');
    });
    return () => sub.remove();
  }, []);

  return active;
}

export default useAppActive;
