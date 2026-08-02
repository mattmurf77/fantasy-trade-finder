import React, { useState } from 'react';
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Modal,
  ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ink, chalk, ice, flare, semantic, space, radii, type, fonts, shadowSheet, scrim } from '../theme/chalkline';
import { Icon, Button } from './chalkline';
import type { IconName } from './chalkline';
import { useNotifications, type AppNotification } from '../state/useNotifications';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { getNotifications, markAllNotificationsRead } from '../api/notifications';
import { relativeTime } from '../utils/relativeTime';
// Circular at module-load (TopBar ← TabNav ← RootNav), but `navigationRef`
// is a top-level const created at RootNav import time and only *read*
// lazily inside onPress below. If you refactor navigationRef into the
// component body, this circular import will break silently. The same
// applies to utils/deepLinks (deepLinks ← RootNav): its exports are only
// *called* from event handlers, never at module-eval time.
import { navigationRef } from '../navigation/RootNav';
import { resolveNotificationTarget, routeNotificationTap } from '../utils/deepLinks';
import LeagueSwitcherSheet from './LeagueSwitcherSheet';

// Global top bar that sits above the tab navigator. Chalkline TopNav,
// #223/#224 header-league-switcher treatment (approved mock:
// mockups/polish-lab-2026-08/header-league-switcher.html): the LEFT half
// carries the ACTIVE league — brand tick, 11px "LEAGUE" micro-label over a
// truncating league name, ice chevron-down (ice = tappable) — and tapping
// it opens the shared LeagueSwitcherSheet from ANY tab (this is the one
// global sheet instance; the per-screen mounts were removed with the pills
// they served). Sessions with no active league (account-only) fall back to
// the app wordmark. Bell + settings stay on the right; per the mock the
// bell sits inboard of the gear so its unread badge is away from the
// screen edge.
//
// Sized at 52pt (44pt pre-#223 — grown to fit the two-line label/name
// stack at the 11px type floor) + the system top inset so it sits flush
// under the status bar without overlapping screen content. Screens below
// this should opt out of the top safe-area inset (e.g. SafeAreaView
// edges={['bottom']}) so we don't double-pad.
export const TOP_BAR_HEIGHT = 52;

// #225: backend notification templates no longer carry emoji anywhere
// (titles or bodies), but rows stored before the de-chalk pass persist in
// the DB with emoji prefixes. Strip on render — titles AND bodies — so
// history looks clean too. Mirrors the regex in web/js/app.js
// _renderNotifList.
const LEADING_LEGACY_EMOJI_RE =
  /^\s*(?:🤝|✅|❌|🎯|🎉|⏳|📰|👀|🏈|👋|🔥|🔓|🌅|🔔)\s*/u;
function stripLegacyEmoji(text: string): string {
  return text.replace(LEADING_LEGACY_EMOJI_RE, '');
}

// NotificationRow glyphs (#225, components.md spec + the approved
// notifications-dechalk mock): 20px Chalkline stroke icon in the status
// color — the emoji's old job, moved from decoration to structure.
// match = ice link glyph · accepted = pos check · declined = neg x ·
// everything else = chalk-dim bell. Keys are `data.type` (backend
// notification types + push kinds).
const ROW_GLYPHS: Record<string, { name: IconName; color: string }> = {
  trade_match:    { name: 'match', color: ice.base },
  new_match:      { name: 'match', color: ice.base },
  first_match:    { name: 'match', color: ice.base },
  trade_accepted: { name: 'check', color: semantic.pos },
  match_accepted: { name: 'check', color: semantic.pos },
  trade_declined: { name: 'x',     color: semantic.neg },
};
const DEFAULT_ROW_GLYPH: { name: IconName; color: string } = {
  name: 'bell',
  color: chalk.dim,
};

export default function TopBar() {
  const insets = useSafeAreaInsets();
  const items       = useNotifications((s) => s.items);
  const unreadCount = useNotifications((s) => s.unreadCount);
  const markAllRead = useNotifications((s) => s.markAllRead);
  const clearAll    = useNotifications((s) => s.clear);
  const hydrateFromServer = useNotifications((s) => s.hydrateFromServer);
  const userId = useSession((s) => s.user?.user_id ?? null);
  // #223 — the active league IS the header. Same session slice LeaguePill
  // read, so the name updates the moment a switch completes; `switching`
  // dims/disables the affordance while a swap is in flight (sessionInit
  // can take seconds on Render free tier — no concurrent switches).
  const league    = useSession((s) => s.league);
  const switching = useSession((s) => s.switching);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  // S5 PRD-02 (flag `notif.tap_routing_v2`): the bell hydrates from the
  // server inbox on open (the in-memory feed resets on relaunch, so without
  // this the sheet claims "all caught up" over real unread rows), rows are
  // tappable via their stored payload metadata, and reads sync back via the
  // existing endpoints. Flag off: in-session feed only, rows inert — today's
  // behavior exactly.
  const tapV2 = useFlag('notif.tap_routing_v2');
  const [open, setOpen] = useState(false);

  const openSheet = () => {
    setOpen(true);
    // Mark read when the sheet is opened so the dot disappears.
    markAllRead();
    if (tapV2 && userId) {
      getNotifications(userId)
        .then((res) => {
          const rows: AppNotification[] = (res?.notifications ?? []).map((row) => ({
            id: String(row.id),
            title: row.title || 'Notification',
            body: row.body || '',
            receivedAt: Date.parse(row.created_at) || Date.now(),
            // The sheet is open — everything shown is being read right now.
            read: true,
            data: { type: row.type, ...(row.metadata ?? {}) },
          }));
          hydrateFromServer(rows);
          // Server-side mark-read so the next launch's inbox agrees with
          // what the user has seen. Best-effort.
          void markAllNotificationsRead().catch(() => {});
        })
        .catch(() => {
          /* offline / server hiccup — keep the in-session feed */
        });
    }
  };

  // Row tap (flag on): close the sheet and route through the same tap
  // router pushes use, off the row's stored payload (`data.type`,
  // `data.match_id`). Unroutable kinds are inert.
  const onRowTap = (it: AppNotification) => {
    const target = resolveNotificationTarget(it.data);
    if (!target) return;
    setOpen(false);
    routeNotificationTap(target.tab, target.matchId);
  };

  return (
    <>
      <View
        style={[
          styles.bar,
          { paddingTop: insets.top, height: insets.top + TOP_BAR_HEIGHT },
        ]}
      >
        <View style={styles.row}>
          {league ? (
            // #223 — active-league affordance: whole left cluster is one
            // ≥44pt hit target opening the switcher. Ice chevron = "tap to
            // switch" (ice = action, Chalkline); pressed = ink-3 fill like
            // the icon buttons. Long names tail-truncate (~200pt).
            <Pressable
              testID="topbar.league"
              onPress={() => setSwitcherOpen(true)}
              disabled={switching}
              accessibilityRole="button"
              accessibilityLabel={`League: ${league.league_name}`}
              accessibilityHint="Opens the league switcher"
              accessibilityState={{ disabled: switching, busy: switching }}
              style={({ pressed }) => [
                styles.leagueBtn,
                pressed && !switching && styles.iconBtnPressed,
                switching && styles.leagueBtnSwitching,
              ]}
            >
              <View style={styles.leagueTick} />
              <View style={styles.leagueStack}>
                <Text style={styles.leagueLabel}>League</Text>
                <View style={styles.leagueNameRow}>
                  <Text style={styles.leagueName} numberOfLines={1}>
                    {league.league_name}
                  </Text>
                  <Icon name="chevron-down" size={14} color={ice.base} />
                </View>
              </View>
            </Pressable>
          ) : (
            // Account-only session (no active league) — wordmark fallback.
            <View style={styles.wordmark}>
              <View style={styles.wordmarkTick} />
              <Text style={styles.wordmarkText}>Trade Finder</Text>
            </View>
          )}
          <View style={styles.actions}>
            <Pressable
              onPress={openSheet}
              hitSlop={12}
              style={({ pressed }) => [
                styles.iconBtn,
                { marginRight: space.sm },
                pressed && styles.iconBtnPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel={
                unreadCount > 0
                  ? `Notifications, ${unreadCount} unread`
                  : 'Notifications'
              }
            >
              <Icon name="bell" color={chalk.dim} />
              {unreadCount > 0 && (
                <View style={styles.dot}>
                  <Text style={styles.dotText}>
                    {unreadCount > 9 ? '9+' : String(unreadCount)}
                  </Text>
                </View>
              )}
            </Pressable>
            <Pressable
              onPress={() => {
                if (navigationRef.isReady()) {
                  navigationRef.navigate('Settings');
                }
              }}
              hitSlop={12}
              style={({ pressed }) => [
                styles.iconBtn,
                pressed && styles.iconBtnPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel="Settings"
              testID="topbar.settings"
            >
              <Icon name="settings" color={chalk.dim} />
            </Pressable>
          </View>
        </View>
      </View>

      {/* #223 — THE league switcher sheet: single global instance, opened
          from the header on any tab (the former per-screen mounts on
          Trades/League/hub were removed with their pills). No onSwitched —
          screens react to the zustand league slice / query keys changing,
          same as the old Trades mount. #199 add-a-league rides along:
          close, then route to the root-stack LeaguePicker (link flows in
          its footer). */}
      <LeagueSwitcherSheet
        visible={switcherOpen}
        onClose={() => setSwitcherOpen(false)}
        onAddLeague={() => {
          setSwitcherOpen(false);
          if (navigationRef.isReady()) {
            navigationRef.navigate('LeaguePicker');
          }
        }}
      />

      <Modal
        visible={open}
        transparent
        animationType="slide"
        onRequestClose={() => setOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setOpen(false)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <View style={styles.sheetHead}>
            <Text style={type.heading} accessibilityRole="header">Notifications</Text>
            {items.length > 0 && (
              <Button
                label="Clear all"
                variant="ghost"
                compact
                onPress={() => {
                  clearAll();
                  setOpen(false);
                }}
              />
            )}
          </View>

          {items.length === 0 ? (
            <View style={styles.empty}>
              <Icon name="bell" size={32} color={chalk.faint} />
              <Text style={styles.emptyTitle}>You're all caught up</Text>
              <Text style={styles.emptyBody}>
                Trade matches and other alerts will appear here.
              </Text>
            </View>
          ) : (
            <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
              {items.map((it) => {
                const glyph =
                  ROW_GLYPHS[String(it.data?.type ?? '')] ?? DEFAULT_ROW_GLYPH;
                const body = (
                  <>
                    <View style={styles.itemGlyph}>
                      <Icon name={glyph.name} size={20} color={glyph.color} />
                    </View>
                    <View style={styles.itemContent}>
                      <Text style={styles.itemTitle}>{stripLegacyEmoji(it.title)}</Text>
                      {it.body ? (
                        <Text style={styles.itemBody}>{stripLegacyEmoji(it.body)}</Text>
                      ) : null}
                      <Text style={styles.itemTime}>
                        {relativeTime(new Date(it.receivedAt).toISOString())}
                      </Text>
                    </View>
                    {!it.read && <View style={styles.itemUnreadDot} />}
                  </>
                );
                // Flag on: rows route like push taps. Flag off: inert rows,
                // byte-identical to today.
                return tapV2 ? (
                  <Pressable
                    key={it.id}
                    testID={`topbar.notif-row.${it.id}`}
                    onPress={() => onRowTap(it)}
                    style={({ pressed }) => [
                      styles.item,
                      !it.read && styles.itemUnread,
                      pressed && { backgroundColor: ink.ink3 },
                    ]}
                    accessibilityRole="button"
                  >
                    {body}
                  </Pressable>
                ) : (
                  <View
                    key={it.id}
                    style={[styles.item, !it.read && styles.itemUnread]}
                  >
                    {body}
                  </View>
                );
              })}
            </ScrollView>
          )}
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  bar: {
    width: '100%',
    backgroundColor: ink.ink0,
    borderBottomColor: ink.line,
    borderBottomWidth: 1,
  },
  row: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.md,
  },
  wordmark: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  // #223 — header league affordance (mock: .lgBtn/.lgStack). Fills the bar
  // height so the whole cluster is a ≥44pt target; shrinks before the
  // icon buttons do and truncates the name.
  leagueBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    alignSelf: 'stretch',
    marginRight: space.sm,
    borderRadius: radii.sm,
    minWidth: 0,
  },
  leagueBtnSwitching: { opacity: 0.45 },
  leagueTick: { width: 3, height: 22, backgroundColor: ice.base },
  leagueStack: { flexShrink: 1, minWidth: 0 },
  leagueLabel: {
    fontFamily: fonts.uiSemi,
    fontSize: 11,
    lineHeight: 12,
    letterSpacing: 0.88,
    textTransform: 'uppercase',
    color: chalk.faint,
  },
  leagueNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    minWidth: 0,
  },
  leagueName: {
    fontFamily: fonts.uiSemi,
    fontSize: 15,
    lineHeight: 19,
    color: chalk.base,
    flexShrink: 1,
    maxWidth: 200,
  },
  wordmarkTick: { width: 3, height: 14, backgroundColor: ice.base },
  wordmarkText: {
    fontFamily: fonts.displaySemi,
    fontSize: 16,
    letterSpacing: 0.48,
    textTransform: 'uppercase',
    color: chalk.base,
  },
  actions: { flexDirection: 'row', alignItems: 'center' },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  iconBtnPressed: { backgroundColor: ink.ink3 },
  dot: {
    position: 'absolute',
    top: -2,
    right: -2,
    minWidth: 18,
    height: 18,
    borderRadius: radii.pill,
    backgroundColor: semantic.neg,
    paddingHorizontal: 4,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: ink.ink0,
  },
  dotText: { color: chalk.base, fontFamily: fonts.data, fontSize: 10 },

  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: scrim,
  },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    maxHeight: '80%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  handle: {
    alignSelf: 'center',
    width: 32, height: 4, borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sheetHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  list: { maxHeight: 480 },
  // NotificationRow (#225, components.md): hairline-separated row — 20px
  // stroke glyph in status color · title/body/time stack · unread = flare
  // 6px SQUARE (not circle) + one-surface-step row fill. The sheet itself
  // sits on ink-2, so the unread fill takes ink-3 (the spec's "--ink-2
  // fill" is one step above the web panel's ink-1 ground — same intent).
  item: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.md,
    paddingHorizontal: space.sm,
  },
  itemUnread: { backgroundColor: ink.ink3 },
  itemGlyph: { marginTop: 1 },
  itemContent: { flex: 1, minWidth: 0, gap: 2 },
  itemUnreadDot: {
    width: 6,
    height: 6,
    marginTop: 6,
    backgroundColor: flare.base,
  },
  itemTitle: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    lineHeight: 19,
    color: chalk.base,
  },
  itemBody:  type.bodySm,
  itemTime:  { fontFamily: fonts.data, fontSize: 11, fontVariant: ['tabular-nums'], color: chalk.faint, marginTop: 2 },

  empty: {
    paddingVertical: space.xxl,
    alignItems: 'center',
    gap: space.sm,
  },
  emptyTitle: type.heading,
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
  },
});
