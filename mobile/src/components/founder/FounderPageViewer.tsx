import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Modal, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import type { ShouldStartLoadRequest } from 'react-native-webview/lib/WebViewTypes';
import { useQuery } from '@tanstack/react-query';

import { chalk, ink, semantic, space } from '../../theme/chalkline';
import { Button, Text } from '../chalkline';
import { ApiError } from '../../api/client';
import { getFounderPage, saveFounderPageNotes } from '../../api/founder';
import { openWebLink } from '../../utils/openExternal';
import {
  FLUSH_SCRIPT,
  MAX_KEYS_PER_SAVE,
  STORAGE_SHIM,
  bridgeScript,
  isPermanentFailure,
  navigationDecision,
  parseBridgeMessage,
  retryDelayMs,
  saveStateText,
  settle,
  takeBatch,
  type PendingNotes,
  type SaveState,
} from '../../utils/founderPages';

// Founders' review, "Review pages" — one page, full screen
// (docs/plans/founder-review/pages-design.md §4). A Modal, not a view inside
// Calibration's scroll view (a nested web view does not scroll). The HTML is
// fetched through the normal API client and handed to the web view as a
// string on about:blank: the page never sees a session token, a cookie or the
// API URL, and it cannot navigate anywhere (http(s) links open in the system
// browser, everything else is dropped). Comments come back over the message
// bridge, are validated (utils/founderPages.parseBridgeMessage), batched and
// saved here; a failed save retries with backoff. Close flushes the page's
// pending boxes and the batch, and asks before leaving if a save still fails.

const COPY = {
  close: 'Close',
  loading: 'Loading the page…',
  readFailed: 'Couldn’t load this page.',
  tryAgain: 'Try again',
  leaveTitle: 'Comments not saved',
  leaveBody: (n: number) => `${n} ${n === 1 ? 'comment' : 'comments'} could not be saved. Leave without saving?`,
  leaveStay: 'Keep trying',
  leaveGo: 'Leave',
} as const;

const FLUSH_WAIT_MS = 1500;
const BATCH_WAIT_MS = 400;

export default function FounderPageViewer({ slug, title, onClose }: { slug: string; title: string; onClose: () => void }) {
  const pageQ = useQuery({
    queryKey: ['founder', 'page', slug],
    queryFn: ({ signal }) => getFounderPage(slug, { signal }),
    retry: false,
    gcTime: 0,                 // about 2.5 MB: never kept after the page closes
    staleTime: Infinity,       // and never refetched under the open page (that would reload it)
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const doc = pageQ.data ?? null;

  const webRef = useRef<WebView>(null);
  const pending = useRef<PendingNotes>({});
  const run = useRef<Promise<boolean> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attempt = useRef(0);
  const flushWaiter = useRef<(() => void) | null>(null);
  const mounted = useRef(true);
  const loaded = useRef(false);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [closing, setClosing] = useState(false);
  // The insets come from the app's SafeAreaProvider, read here, outside the
  // Modal, and applied as padding (the TopBar / TradeDnaSheet pattern). A
  // SafeAreaView inside a native Modal has no provider in the modal's native
  // view tree and measured zero insets on device, which left Close under the
  // status bar and Dynamic Island, where taps did not reach it, and nothing
  // kept the web view off the home indicator. statusBarTranslucent +
  // navigationBarTranslucent pin the modal edge to edge on Android (already
  // forced by edgeToEdgeEnabled) so the same window insets apply there.
  const insets = useSafeAreaInsets();

  useEffect(() => () => {
    mounted.current = false;
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const show = (s: SaveState) => { if (mounted.current) setSaveState(s); };

  // Plain functions over refs (slug is fixed for the viewer's life), so a timer set in an
  // earlier render still drives the same queue.
  async function drain(): Promise<boolean> {
    for (;;) {
      const batch = takeBatch(pending.current, MAX_KEYS_PER_SAVE);
      if (Object.keys(batch).length === 0) {
        attempt.current = 0;
        show('saved');
        return true;
      }
      show('saving');
      try {
        await saveFounderPageNotes(slug, batch);
      } catch (e) {
        const status = e instanceof ApiError ? e.status : undefined;
        if (isPermanentFailure(status)) {
          show('failed');
          return false;
        }
        show('retrying');
        schedule(retryDelayMs(attempt.current));
        attempt.current += 1;
        return false;
      }
      pending.current = settle(pending.current, batch);
    }
  }

  /** One save at a time: a second caller waits on the one in flight. */
  function save(): Promise<boolean> {
    if (run.current) return run.current;
    const p: Promise<boolean> = drain().finally(() => { if (run.current === p) run.current = null; });
    run.current = p;
    return p;
  }

  function schedule(ms: number) {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { timer.current = null; void save(); }, ms);
  }

  function onMessage(e: WebViewMessageEvent) {
    const msg = parseBridgeMessage(e.nativeEvent.data);
    if (msg === null) return;                       // anything else from the page is ignored
    if (msg.type === 'flushed') {
      flushWaiter.current?.();
      return;
    }
    pending.current = { ...pending.current, [msg.k]: { label: msg.label, body: msg.v } };
    // While a retry is waiting, the retry carries this change too.
    if (attempt.current === 0 || !timer.current) schedule(BATCH_WAIT_MS);
  }

  const onShouldStart = useCallback((req: ShouldStartLoadRequest) => {
    const decision = navigationDecision(req);
    if (decision === 'external') void openWebLink(req.url);
    return decision === 'load';
  }, []);

  /** Ask the page to post its boxes still inside their debounce; wait for its answer. */
  const flushPage = () => new Promise<void>((resolve) => {
    if (!webRef.current || !loaded.current) { resolve(); return; }
    const done = () => { clearTimeout(t); flushWaiter.current = null; resolve(); };
    const t = setTimeout(done, FLUSH_WAIT_MS);
    flushWaiter.current = done;
    webRef.current.injectJavaScript(FLUSH_SCRIPT);
  });

  const requestClose = async () => {
    if (closing) return;
    setClosing(true);
    await flushPage();
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    await save();
    if (Object.keys(pending.current).length > 0) await save();   // changes that arrived mid-save
    const left = Object.keys(pending.current).length;
    if (left === 0) {
      onClose();
      return;
    }
    if (mounted.current) setClosing(false);
    Alert.alert(COPY.leaveTitle, COPY.leaveBody(left), [
      { text: COPY.leaveStay, style: 'cancel', onPress: () => schedule(0) },
      { text: COPY.leaveGo, style: 'destructive', onPress: onClose },
    ]);
  };

  // One document per open: the source and the bridge are built once from the fetched page.
  const source = useMemo(() => (doc ? { html: doc.html, baseUrl: 'about:blank' } : null), [doc]);
  const bridge = useMemo(() => (doc ? bridgeScript(doc.notes) : ''), [doc]);
  const stateText = saveStateText(saveState);

  return (
    <Modal visible animationType="slide" presentationStyle="fullScreen" statusBarTranslucent navigationBarTranslucent
      onRequestClose={() => { void requestClose(); }}>
      <View
        style={[styles.root, { paddingTop: insets.top, paddingBottom: insets.bottom, paddingLeft: insets.left, paddingRight: insets.right }]}
      >
        <View style={styles.bar}>
          <Pressable
            testID="founder-review.pages.close"
            accessibilityRole="button"
            accessibilityLabel="Close the page"
            onPress={() => { void requestClose(); }}
            disabled={closing}
            hitSlop={8}
            style={styles.closeBtn}
          >
            {closing ? <ActivityIndicator color={chalk.base} /> : <Text variant="label" style={styles.closeText}>{COPY.close}</Text>}
          </Pressable>
          <Text variant="title" numberOfLines={1} style={styles.title}>{title}</Text>
          <Text
            variant="data"
            testID="founder-review.pages.save-state"
            accessibilityLiveRegion="polite"
            style={[styles.state, (saveState === 'retrying' || saveState === 'failed') && styles.stateBad]}
          >
            {stateText}
          </Text>
        </View>
        {pageQ.isPending ? (
          <View style={styles.center} testID="founder-review.pages.loading">
            <ActivityIndicator color={chalk.dim} />
            <Text variant="bodySm" style={styles.dim}>{COPY.loading}</Text>
          </View>
        ) : pageQ.isError || !source ? (
          <View style={styles.center} testID="founder-review.pages.error">
            <Text variant="body">{COPY.readFailed}</Text>
            <Button testID="founder-review.pages.retry" label={COPY.tryAgain} variant="secondary"
              onPress={() => { void pageQ.refetch(); }} />
          </View>
        ) : (
          <WebView
            ref={webRef}
            testID="founder-review.pages.webview"
            source={source}
            // Every request reaches onShouldStartLoadWithRequest ('*'): a narrower list would
            // hand non-matching URLs (mailto:, tel:, app schemes) straight to the OS.
            originWhitelist={['*']}
            onShouldStartLoadWithRequest={onShouldStart}
            setSupportMultipleWindows={false}
            javaScriptCanOpenWindowsAutomatically={false}
            injectedJavaScriptBeforeContentLoaded={STORAGE_SHIM}
            injectedJavaScript={bridge}
            onMessage={onMessage}
            onLoadEnd={() => { loaded.current = true; }}
            incognito
            sharedCookiesEnabled={false}
            thirdPartyCookiesEnabled={false}
            allowFileAccess={false}
            allowsLinkPreview={false}
            style={styles.web}
          />
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  bar: {
    flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: 48,
    paddingHorizontal: space.lg, borderBottomWidth: 1, borderBottomColor: ink.line,
  },
  closeBtn: { minHeight: 44, minWidth: 56, justifyContent: 'center' },
  closeText: { color: chalk.base },
  title: { flexShrink: 1, flexGrow: 1 },
  state: { color: chalk.dim },
  stateBad: { color: semantic.warn },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg, padding: space.lg },
  dim: { color: chalk.dim },
  web: { flex: 1, backgroundColor: ink.ink0 },
});
