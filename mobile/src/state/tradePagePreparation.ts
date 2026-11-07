import { AppState } from 'react-native';
import { getSessionRevision } from '../api/client';
import { hydrateDevicePages, refreshDevicePage, type DevicePageTarget } from './devicePageStore';
import { useSession } from './useSession';
import { useFeatureFlags } from './useFeatureFlags';
import { devicePageKey } from '../utils/devicePage';

/** One lifecycle boundary for passive preparation from tabs, focus and foreground.
 * Disk recovery is independent; fresh server work joins session readiness while
 * the caller reads its request preferences. Neither may adopt across a context change. */
export async function prepareTradePage(
  key: string,
  loadTarget: () => Promise<DevicePageTarget | null>,
  shouldContinue: () => boolean,
): Promise<void> {
  const current = () => {
    const s = useSession.getState();
    return shouldContinue() && AppState.currentState === 'active'
      && !!useFeatureFlags.getState().flags['trade.first_page_store']
      && s.hasToken && !s.switching && !s.isDemo
      && devicePageKey(s.user?.user_id, s.league?.league_id, s.activeFormat) === key;
  };
  if (!current()) return;
  void hydrateDevicePages();
  try {
    const [target] = await Promise.all([loadTarget(), useSession.getState().revalidateSession()]);
    if (!target || target.key !== key || !current()
        || target.format !== useSession.getState().activeFormat) return;
    // The readiness join may itself replace the token. Bind after that join.
    const revision = getSessionRevision();
    await refreshDevicePage(target, Date.now(), () => current() && getSessionRevision() === revision);
  } catch { /* passive preparation never blocks navigation */ }
}
