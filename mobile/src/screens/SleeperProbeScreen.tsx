// Sleeper reachability probe — TEMPORARY, operator-only diagnostic.
//
// WHY THIS EXISTS
// Moving authenticated Sleeper calls onto the device (ADR-011) rests on one
// untested assumption: that Sleeper's Cloudflare edge accepts a request
// originating from inside an iOS app at all. backend/sleeper_write.py:43-59
// records Cloudflare error 1010 against automation-looking signatures, and the
// server's answer is a spoofed desktop-Chrome User-Agent. Nobody has checked
// what happens when that same spoof is sent from an iPhone's network stack.
//
// THE NON-OBVIOUS PART: spoofing Chrome from iOS may be WORSE than not spoofing.
// Cloudflare fingerprints the TLS handshake, not just the User-Agent header. A
// request claiming desktop Chrome while its connection signature says iOS
// NSURLSession is a mismatch, and mismatch is itself a bot signal. So the probe
// runs BOTH header sets and reports them side by side — the answer may be that
// honest iOS headers pass where the spoof fails.
//
// SAFETY
//  * The query is Sleeper's own no-op (`{ __typename }`, the same body
//    sleeper_write.verify_token_live uses). It reads nothing and writes
//    nothing — it cannot touch a league, a roster, or a trade.
//  * Gated behind `debug.sleeper_probe`, default false everywhere. This ships
//    in a production TestFlight binary, so a __DEV__ guard would make it inert
//    exactly where it needs to run; the flag is the gate instead.
//  * The JWT is never rendered, logged, or reported — only whether one exists.
//
// DELETE THIS SCREEN once ADR-011's reachability question is settled and the
// result is recorded in the HLD.

import React, { useCallback, useState } from 'react';
import { ActivityIndicator, ScrollView, View, Text, StyleSheet, Pressable } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { ink, chalk, ice, space, radii, type } from '../theme/chalkline';

const SLEEPER_GRAPHQL_URL = 'https://sleeper.com/graphql';
const SECURE_SLEEPER_JWT_KEY = 'sleeper.link.jwt';

// Mirrors backend/sleeper_write.py:_BROWSER_HEADERS verbatim. If that changes,
// this must change with it or the probe stops testing the real thing.
const SPOOFED_HEADERS: Record<string, string> = {
  'user-agent':
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  origin: 'https://sleeper.com',
  referer: 'https://sleeper.com/',
  accept: '*/*',
  'accept-language': 'en-US,en;q=0.9',
};

// Nothing spoofed — let iOS send its own User-Agent and TLS signature.
const HONEST_HEADERS: Record<string, string> = { accept: '*/*' };

interface ProbeResult {
  label: string;
  status: number | null;
  verdict: 'PASS' | 'BLOCKED' | 'AUTH-REJECTED' | 'ERROR';
  detail: string;
}

// Cloudflare answers a blocked request with an HTML challenge page, not JSON —
// so the body shape is the signal, not the status code alone.
function classify(status: number, body: string): { verdict: ProbeResult['verdict']; detail: string } {
  const head = body.slice(0, 300).replace(/\s+/g, ' ');
  const looksHtml = /^\s*<(!doctype|html)/i.test(body);
  const cloudflare = /cloudflare|cf-ray|error code: 1010|attention required/i.test(body);

  if (looksHtml || cloudflare) {
    return { verdict: 'BLOCKED', detail: `Cloudflare/HTML challenge. ${head}` };
  }
  try {
    const parsed = JSON.parse(body);
    if (parsed?.data?.__typename) {
      return { verdict: 'PASS', detail: `GraphQL answered: __typename=${parsed.data.__typename}` };
    }
    if (status === 401 || /token is invalid/i.test(body)) {
      // Reached Sleeper's auth layer — the EDGE let us through, which is what
      // this probe actually measures. A dead token is a separate problem.
      return { verdict: 'AUTH-REJECTED', detail: `Edge passed, token rejected. ${head}` };
    }
    return { verdict: 'ERROR', detail: `JSON but unexpected shape. ${head}` };
  } catch {
    return { verdict: 'ERROR', detail: `Non-JSON body (status ${status}). ${head}` };
  }
}

async function runOne(label: string, token: string, extra: Record<string, string>): Promise<ProbeResult> {
  const body = JSON.stringify({
    operationName: 'ftf_token_probe',
    variables: {},
    query: 'query ftf_token_probe { __typename }',
  });
  try {
    const res = await fetch(SLEEPER_GRAPHQL_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: token, ...extra },
      body,
    });
    const text = await res.text();
    const { verdict, detail } = classify(res.status, text);
    return { label, status: res.status, verdict, detail };
  } catch (e) {
    // A transport failure here is itself informative — an outright TLS reset is
    // a different signal from an HTTP-level block.
    return { label, status: null, verdict: 'ERROR', detail: `Request threw: ${String(e).slice(0, 200)}` };
  }
}

export default function SleeperProbeScreen() {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<ProbeResult[] | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const run = useCallback(async () => {
    setRunning(true);
    setResults(null);
    setNote(null);
    try {
      const raw = await SecureStore.getItemAsync(SECURE_SLEEPER_JWT_KEY);
      if (!raw) {
        setNote('No Sleeper token on this device. Link Sleeper first, then re-run.');
        return;
      }
      const token: string = JSON.parse(raw)?.token;
      if (!token) {
        setNote('Stored Sleeper entry has no token field.');
        return;
      }
      // Sequential, not parallel — two simultaneous requests from one IP is
      // itself a mildly abusive signature, and this probe should not be the
      // thing that trips the system it is measuring.
      const spoofed = await runOne('Chrome-spoofed headers', token, SPOOFED_HEADERS);
      const honest = await runOne('Honest iOS headers', token, HONEST_HEADERS);
      setResults([spoofed, honest]);
    } finally {
      setRunning(false);
    }
  }, []);

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content} testID="sleeper-probe.screen">
      <Text style={styles.h1}>Sleeper reachability probe</Text>
      <Text style={styles.body}>
        Sends Sleeper's own no-op query twice — once pretending to be desktop Chrome, once as an
        honest iPhone request. It reads nothing and changes nothing.
      </Text>
      <Text style={styles.body}>
        Run it once on Wi-Fi and once on cellular, and note which is which — different networks
        carry different reputations, and your users will be on both.
      </Text>

      <Pressable
        testID="sleeper-probe.run"
        accessibilityRole="button"
        onPress={run}
        disabled={running}
        style={({ pressed }) => [styles.btn, pressed && styles.btnPressed, running && styles.btnDisabled]}
      >
        {running ? <ActivityIndicator color={ice.on} /> : <Text style={styles.btnLabel}>Run probe</Text>}
      </Pressable>

      {note ? <Text style={styles.note} testID="sleeper-probe.note">{note}</Text> : null}

      {results?.map((r) => (
        <View key={r.label} style={styles.card} testID={`sleeper-probe.result`}>
          <Text style={styles.cardTitle}>{r.label}</Text>
          <Text style={[styles.verdict, r.verdict === 'BLOCKED' ? styles.bad : styles.good]}>
            {r.verdict}
            {r.status !== null ? `  ·  HTTP ${r.status}` : '  ·  no response'}
          </Text>
          <Text style={styles.detail} selectable>{r.detail}</Text>
        </View>
      ))}

      {results ? (
        <Text style={styles.note}>
          PASS or AUTH-REJECTED on either row means Sleeper's edge accepts an iPhone request —
          the device-side move is viable. BLOCKED on both means it is not.
        </Text>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  content: { padding: space.lg, gap: space.md },
  h1: { ...type.heading },
  body: { ...type.body },
  note: { ...type.bodySm },
  btn: {
    backgroundColor: ice.base,
    borderRadius: radii.md,
    paddingVertical: space.md,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
  },
  btnPressed: { opacity: 0.85 },
  btnDisabled: { opacity: 0.6 },
  btnLabel: { ...type.title, color: ice.on },
  card: {
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.md,
    gap: space.xs,
  },
  cardTitle: { ...type.title },
  verdict: { ...type.title },
  good: { color: ice.base },
  bad: { color: chalk.base },
  detail: { ...type.bodySm },
});
