import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
import {
  getNotifications,
  markAllNotificationsRead,
  dismissAllNotifications,
} from '../api/notifications';
import { getLeagueSummary } from '../api/league';
import { track } from '../api/events';
import { inviteSocialProof, INVITE_RATIONALE } from '../utils/inviteSocialProof';
import { shareInvite } from './InviteLeaguematesBanner';
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
//
// CROSS-CLIENT (docs/cross-client-invariants.md § Notification types): web
// keeps a SECOND, independent map in web/js/app.js (notifTypeIcon) and a
// second tap router (clickNotif). A type added here and not there renders
// as an anonymous grey bell with a dead tap on the other client — no error,
// no warning, nothing in a log. Add to both, always. Pinned by
// mobile/tests/check-notif-glyphs.js.
const ROW_GLYPHS: Record<string, { name: IconName; color: string }> = {
  trade_match:    { name: 'match', color: ice.base },
  new_match:      { name: 'match', color: ice.base },
  first_match:    { name: 'match', color: ice.base },
  trade_accepted: { name: 'check', color: semantic.pos },
  match_accepted: { name: 'check', color: semantic.pos },
  trade_declined: { name: 'x',     color: semantic.neg },
  // notif-inbox-growth, 2026-08-13. `referral_joined` and
  // `league_member_joined` share the `plus` glyph because they are the same
  // object — a person arrived. The COLOR carries the difference: flare is
  // the informational highlight, reserved here for the one row that says
  // the user's own invite worked. Everything else is ice.
  referral_joined:               { name: 'plus',  color: flare.base },
  league_member_joined:          { name: 'plus',  color: ice.base },
  // They finished a board — a RANKED counterparty is what the matching
  // engine actually needs, so the rank glyph, not another person glyph.
  league_member_unlocked_trades: { name: 'rank',  color: ice.base },
  match_expiring:                { name: 'match', color: semantic.warn },
  deck_replenished:              { name: 'trade', color: ice.base },
  // No backend emitter today (it is a bucket mapping and two client kind
  // sets, nothing more). Mapped anyway so that if the kind ever ships it
  // renders correctly on day one instead of grey-belling until someone
  // notices. Costs one line; the alternative is a silent regression.
  counter_offer:                 { name: 'swap',  color: ice.base },
  // ADR-011 / YR-8: the weekly roster sweep hit an expired stored ESPN
  // cookie — a credential problem became a visible re-auth ask instead of
  // a silent gap in the user's season history. warn = action wanted.
  espn_reconnect:                { name: 'reload', color: semantic.warn },
};
const DEFAULT_ROW_GLYPH: { name: IconName; color: string } = {
  name: 'bell',
  color: chalk.dim,
};

// #247 — the header format tile. The session's activeFormat IS the active
// league's scoring format (detected per league, per-session override via
// the SF/1QB toggle — see useSession). Two formats exist app-wide
// (shared/types ScoringFormat); labels compress the FormatToggle wording
// to tile size ("SF TEP" keeps the TE-premium distinction the data
// carries; PPR is implied for 1QB everywhere else in the app).
const FORMAT_TILE_LABEL: Record<string, string> = {
  '1qb_ppr': '1QB',
  sf_tep: 'SF TEP',
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
  // #247 — active league's scoring format for the header tile.
  const activeFormat = useSession((s) => s.activeFormat);
  const formatLabel = activeFormat
    ? FORMAT_TILE_LABEL[activeFormat] ?? null
    : null;
  // Platform for the invite events comes from the CACHED LEAGUE LIST, never
  // from the active-league slice (SavedLeague carries no platform) and never
  // inferred from the id shape. Same derivation MatchesScreen uses.
  const leagues   = useSession((s) => s.leagues);
  const platform  =
    leagues.find((lg) => lg.league_id === league?.league_id)?.platform ?? "unknown";
  const [switcherOpen, setSwitcherOpen] = useState(false);
  // S5 PRD-02 (flag `notif.tap_routing_v2`): the bell hydrates from the
  // server inbox on open (the in-memory feed resets on relaunch, so without
  // this the sheet claims "all caught up" over real unread rows), rows are
  // tappable via their stored payload metadata, and reads sync back via the
  // existing endpoints. Flag off: in-session feed only, rows inert — today's
  // behavior exactly.
  const tapV2 = useFlag('notif.tap_routing_v2');
  const [open, setOpen] = useState(false);

  // ── Empty-state invite (GD-1) ────────────────────────────────────────
  // The invite ask lives HERE and never as a standing inbox row. A row that
  // is true for every user every day is not news, and the bell is the one
  // surface where everything currently is — a permanent ask is how you
  // teach someone to stop opening it. The empty state is structurally
  // incapable of burying a receipt: it only exists when there is nothing to
  // bury, and it disappears the moment the surface has content.
  //
  // Same <50%-penetration rule that already shipped on MatchesScreen
  // (D-P1-13 PR-6), reading the SAME query key as League Home and Matches
  // so the three surfaces share one cache entry and can never quote
  // different numbers. Fetched only while the sheet is open on an empty
  // list — the bell must not put a request on every app launch.
  const summaryQuery = useQuery({
    queryKey: ['league-summary', league?.league_id],
    queryFn:  () => getLeagueSummary(league!.league_id),
    enabled:  open && items.length === 0 && !!league?.league_id,
    staleTime: 60_000,
    placeholderData: (prev: any) => prev,
  });
  const summary = summaryQuery.data as any;
  // int | null. NULL IS HONEST, 0 IS A LIE — the bell is global and opens
  // with no active league at all, and before the summary lands. Neither
  // case is "everyone joined".
  const totalMates: number | null =
    typeof summary?.leaguemates_total === 'number' ? summary.leaguemates_total : null;
  const joinedMates: number | null =
    typeof summary?.leaguemates_joined === 'number' ? summary.leaguemates_joined : null;
  const inviteProof =
    totalMates !== null && joinedMates !== null
      ? inviteSocialProof(totalMates, joinedMates)
      : null;
  const invitePenetration =
    totalMates !== null && joinedMates !== null && totalMates > 0
      ? joinedMates / totalMates
      : 1;
  const inviteOffered = inviteProof !== null && invitePenetration < 0.5;

  const openSheet = () => {
    // BEFORE markAllRead() — after it, unreadCount is always 0 and the
    // event measures nothing. row_count is deliberately the PRE-hydration
    // count: the server fetch below is async, and firing after it settles
    // would lose every open that happens offline or mid-flight. Read it as
    // "rows the user saw immediately".
    track('notif_inbox_opened', {
      unread_count: unreadCount,
      row_count:    items.length,
    }, 'TopBar');
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
  const onRowTap = (it: AppNotification, position: number) => {
    // Fired BEFORE the routing decision, on purpose. A row that is tapped
    // and goes nowhere is the single most useful thing this event can
    // record — it is exactly the referral_joined bug this batch fixes, and
    // the only way anyone catches the next one. Moving this below the
    // early return would make unroutable rows invisible.
    track('notif_row_tapped', {
      type:      String(it.data?.type ?? ''),
      position,
      age_hours: Math.max(0, Math.floor((Date.now() - it.receivedAt) / 3_600_000)),
    }, 'TopBar');
    const target = resolveNotificationTarget(it.data);
    if (!target) return;
    setOpen(false);
    routeNotificationTap(target.tab, target.matchId);
  };

  // Fires once per open onto an empty list. Waits for the summary fetch so
  // the counts are real rather than a transient null — but only while it is
  // actually in flight: with no active league the query is disabled, never
  // fetches, and the event fires immediately with honest nulls.
  const emptyShownRef = React.useRef(false);
  React.useEffect(() => {
    if (!open || items.length !== 0) { emptyShownRef.current = false; return; }
    if (summaryQuery.isFetching) return;
    if (emptyShownRef.current) return;
    emptyShownRef.current = true;
    track('notif_empty_state_shown', {
      not_joined:     totalMates !== null && joinedMates !== null
        ? totalMates - joinedMates : null,
      total_mates:    totalMates,
      invite_offered: inviteOffered,
    }, 'TopBar');
    if (inviteOffered) {
      // ⚠ MOUNT COUNTER, not an impression counter — same D-P1-04 caveat
      // the matches_empty surface carries. The empty state renders inside a
      // plain <View> with no scroll ancestry. The sheet is short enough
      // that clipping is unlikely, but this event witnesses a mount.
      track('invite_cta_shown', {
        surface:     'notif_empty',
        not_joined:  totalMates !== null && joinedMates !== null
          ? totalMates - joinedMates : null,
        total_mates: totalMates,
        platform:    platform,
      }, 'TopBar');
    }
  }, [open, items.length, summaryQuery.isFetching, totalMates, joinedMates,
      inviteOffered, platform]);

  const onInviteFromInbox = () => {
    setOpen(false);
    void shareInvite({
      leagueId:   league?.league_id || '',
      leagueName: league?.league_name,
      username:   useSession.getState().user?.username,
      surface:    'notif_empty',
      notJoined:  totalMates !== null && joinedMates !== null
        ? totalMates - joinedMates : null,
      totalMates,
      platform:   platform,
      screen:     'TopBar',
    });
  };

  // "Clear all" now means it (GD-4). The server stamp lands first and is
  // best-effort; the local clear runs either way so the button is never
  // unresponsive on a flaky connection. A dropped server call costs a
  // re-hydration on the next open — today's behavior, not a regression.
  const onClearAll = () => {
    void dismissAllNotifications().catch(() => {});
    clearAll();
    setOpen(false);
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
              accessibilityLabel={`League: ${league.league_name}${
                formatLabel ? `, ${formatLabel} format` : ''
              }`}
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
                  {/* #247 — the league's scoring format as a solid-ice tile
                      beside the name (ice = identity/action-adjacent; the
                      cluster is the switcher affordance). 11px floor,
                      radius ≤8 per Chalkline. The Pressable container
                      swallows child text on iOS, so the format is also
                      spoken via the accessibilityLabel above. */}
                  {formatLabel ? (
                    <View testID="topbar.format" style={styles.formatTile}>
                      <Text style={styles.formatTileText}>{formatLabel}</Text>
                    </View>
                  ) : null}
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
                testID="topbar.notif-clear-all"
                label="Clear all"
                variant="ghost"
                compact
                onPress={onClearAll}
              />
            )}
          </View>

          {items.length === 0 ? (
            // The most-viewed state on this surface, and until now it did
            // nothing. Two jobs: say what fills the bell (which teaches the
            // loop without asking for anything), and — only under 50%
            // penetration — carry the invite ask.
            <View style={styles.empty} testID="topbar.notif-empty">
              <Icon name="bell" size={32} color={chalk.faint} />
              <Text style={styles.emptyTitle}>You're all caught up</Text>
              <Text style={styles.emptyBody}>
                You'll hear when leaguemates rank players, match a trade, or join.
              </Text>
              {inviteOffered ? (
                <>
                  <Text testID="topbar.notif-empty-proof" style={styles.emptyProof}>
                    {inviteProof}
                  </Text>
                  <Text style={styles.emptyBody}>{INVITE_RATIONALE}</Text>
                  <Button
                    testID="topbar.notif-empty-invite"
                    label="Invite leaguemates"
                    variant="primary"
                    onPress={onInviteFromInbox}
                  />
                </>
              ) : null}
            </View>
          ) : (
            <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
              {items.map((it, idx) => {
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
                    onPress={() => onRowTap(it, idx)}
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
  // #247 — solid-ice format tile (data micro-label on ice fill; 11px is
  // the Chalkline type floor, radii.xs ≤ 8).
  formatTile: {
    height: 18,
    paddingHorizontal: 5,
    borderRadius: radii.xs,
    backgroundColor: ice.base,
    alignItems: 'center',
    justifyContent: 'center',
  },
  formatTileText: {
    fontFamily: fonts.dataSemi,
    fontSize: 11,
    lineHeight: 13,
    letterSpacing: 0.4,
    color: ice.on,
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
  // The social-proof line states a fact about THIS league, so it reads as
  // content rather than as a nag — chalk-base, one step up from the body.
  emptyProof: {
    ...type.bodySm,
    color: chalk.base,
    textAlign: 'center',
    marginTop: space.sm,
  },
});
