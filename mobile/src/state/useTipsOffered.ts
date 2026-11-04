import { useQuery } from '@tanstack/react-query';

import { getPaywallConfig, type PaywallConfig } from '../api/billing';

// The Settings tip-jar row's gate (head-eng's B8, 2026-10-27): the row shows
// only while the server offers tips, i.e. the cached /api/paywall/config
// `tips` is a non-empty array. SUBSCRIBED to the React Query cache, NEVER
// fetching (`enabled: false`): unknown or empty → hidden. The server serves
// `tips: []` at launch, so the row stays hidden and comes back with a server
// change, no binary. The TipJar route stays registered.

/** Pure: the config offers at least one tip. */
export function tipsOffered(config: PaywallConfig | null | undefined): boolean {
  return Array.isArray(config?.tips) && config.tips.length > 0;
}

/** Settings' tip-row gate: the cached paywall config offers a tip. */
export function useTipsOffered(): boolean {
  const { data } = useQuery<PaywallConfig>({
    queryKey: ['paywall-config', 'ios'],
    queryFn: () => getPaywallConfig('ios'),
    enabled: false,
  });
  return tipsOffered(data);
}
