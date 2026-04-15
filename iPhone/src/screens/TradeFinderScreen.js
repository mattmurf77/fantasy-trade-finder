import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  ActivityIndicator, Modal, Switch, Alert,
} from 'react-native';
import { colors, spacing, fontSize, borderRadius, positionColor } from '../utils/theme';
import { api } from '../services/api';
import { useApp } from '../context/AppContext';
import { storage } from '../utils/storage';

const OUTLOOK_OPTIONS = [
  { value: 'championship', emoji: '🏆', name: 'Championship or Bust', desc: 'Strongly prefer proven veterans' },
  { value: 'contender', emoji: '💪', name: 'Contender', desc: 'Slight lean toward veterans' },
  { value: 'rebuilder', emoji: '🔨', name: 'Rebuilder', desc: 'Prefer young talent over veterans' },
  { value: 'jets', emoji: '🟢', name: 'NY Jets', desc: 'Young talent only — 25 and under' },
  { value: 'not_sure', emoji: '🤷', name: 'Not Sure', desc: 'No adjustment — pure ELO scoring' },
];

const POSITIONS = ['QB', 'RB', 'WR', 'TE', 'PICK'];

function valueTier(p) {
  if (!p.search_rank && p.search_rank !== 0) return null;
  const r = p.search_rank;
  if (r <= 50) return 'elite';
  if (r <= 150) return 'high';
  if (r <= 300) return 'mid';
  return 'depth';
}

const TIER_COLORS = { elite: '#f59e0b', high: '#22c55e', mid: '#3b82f6', depth: '#7a7f96' };

function TradePlayerRow({ player }) {
  const pos = (player.position || '?').toUpperCase();
  const isPick = player.pick_value != null;
  const posColor = isPick ? colors.pick : positionColor(pos);
  const tier = valueTier(player);

  return (
    <View style={tStyles.playerRow}>
      <View style={[tStyles.posBadge, { backgroundColor: posColor + '22', borderColor: posColor + '55' }]}>
        <Text style={[tStyles.posBadgeText, { color: posColor }]}>{isPick ? 'PICK' : pos}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={tStyles.playerName}>{player.name || 'Unknown'}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
          {tier && (
            <View style={[tStyles.tierBadge, { borderColor: TIER_COLORS[tier] }]}>
              <Text style={[tStyles.tierText, { color: TIER_COLORS[tier] }]}>
                {{ elite: 'Elite', high: 'High', mid: 'Mid', depth: 'Depth' }[tier]}
              </Text>
            </View>
          )}
          <Text style={tStyles.playerMeta}>
            {isPick ? `val ${player.pick_value?.toFixed(1)}` : `${player.team || 'FA'} · Age ${player.age}`}
          </Text>
        </View>
      </View>
    </View>
  );
}

function TradeCard({ trade, onSwipe }) {
  const decided = trade.decision !== null;
  const score = Math.round(trade.mismatch_score);

  return (
    <View style={[tStyles.card, decided && trade.decision === 'pass' && tStyles.cardPassed]}>
      <View style={tStyles.meta}>
        <Text style={tStyles.metaText}>
          vs <Text style={tStyles.metaUsername}>{trade.target_username}</Text>
          {trade.real_opponent
            ? <Text style={{ color: colors.green, fontSize: 10 }}> ● real</Text>
            : <Text style={{ color: colors.muted, fontSize: 10 }}> ○ est.</Text>
          }
        </Text>
        <View style={tStyles.scorePill}>
          <Text style={tStyles.scoreText}>Match {score}</Text>
        </View>
      </View>

      <View style={tStyles.sides}>
        <View style={[tStyles.side, { borderRightWidth: 1, borderRightColor: colors.border }]}>
          <Text style={tStyles.sideLabel}>You give</Text>
          {trade.give.map((p, i) => <TradePlayerRow key={i} player={p} />)}
        </View>
        <View style={tStyles.side}>
          <Text style={[tStyles.sideLabel, { color: colors.green }]}>You receive</Text>
          {trade.receive.map((p, i) => <TradePlayerRow key={i} player={p} />)}
        </View>
      </View>

      {decided ? (
        <Text style={[tStyles.decidedText, trade.decision === 'like' && { color: colors.green }]}>
          {trade.decision === 'like' ? '✅ Interested' : '✗ Passed'}
        </Text>
      ) : (
        <View style={tStyles.actions}>
          <TouchableOpacity
            style={tStyles.passBtn}
            onPress={() => onSwipe(trade.trade_id, 'pass')}
          >
            <Text style={tStyles.passBtnText}>✕ Pass</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={tStyles.likeBtn}
            onPress={() => onSwipe(trade.trade_id, 'like')}
          >
            <Text style={tStyles.likeBtnText}>✓ Interested</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

export default function TradeFinderScreen({ onSwitchToRank }) {
  const { league, setOutlook, currentOutlook } = useApp();
  const leagueId = league?.league_id;

  const [trades, setTrades] = useState([]);
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [gateProgress, setGateProgress] = useState(null);
  const [unlocked, setUnlocked] = useState(false);
  const [fairness, setFairness] = useState(75);
  const [equalOnly, setEqualOnly] = useState(false);
  const [showOutlook, setShowOutlook] = useState(false);
  const [outlookStep, setOutlookStep] = useState(1);
  const [pendingOutlook, setPendingOutlook] = useState(null);
  const [acquireChecks, setAcquireChecks] = useState([]);
  const [awayChecks, setAwayChecks] = useState([]);
  const [toast, setToast] = useState('');

  useEffect(() => {
    checkGate();
    loadTrades();
    loadMatches();
    checkOutlook();
    loadFairness();
  }, [leagueId]);

  const showToastMsg = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  };

  const loadFairness = async () => {
    const data = await storage.getFairness(leagueId);
    setFairness(data.value || 75);
    setEqualOnly(data.equal || false);
  };

  const saveFairness = async (val, eq) => {
    await storage.saveFairness(leagueId, { value: val, equal: eq });
  };

  const checkGate = async () => {
    try {
      const data = await api.getRankingsProgress();
      setGateProgress(data);
      setUnlocked(data.unlocked);
    } catch {
      setUnlocked(true); // can't tell, let trades show
    }
  };

  const loadTrades = async () => {
    if (!leagueId) return;
    try {
      const data = await api.getTrades(leagueId);
      if (!data.error) setTrades(data);
    } catch {}
  };

  const loadMatches = async () => {
    try {
      const data = await api.getMatches();
      if (Array.isArray(data)) setMatches(data);
    } catch {}
  };

  const checkOutlook = async () => {
    if (!leagueId) return;
    try {
      const data = await api.getPreferences(leagueId);
      if (!data.team_outlook) {
        setShowOutlook(true);
        setOutlookStep(1);
      } else {
        setOutlook(data.team_outlook, data.acquire_positions, data.trade_away_positions);
      }
    } catch {}
  };

  const generateTrades = async () => {
    setGenerating(true);
    try {
      const threshold = equalOnly ? 1.0 : fairness / 100;
      const data = await api.generateTrades(leagueId, threshold);
      if (data.error) { showToastMsg(data.error); return; }
      setTrades(data);
      showToastMsg(`Found ${data.length} trade ideas`);
    } catch {
      showToastMsg('Could not reach server');
    } finally {
      setGenerating(false);
    }
  };

  const handleSwipe = async (tradeId, decision) => {
    try {
      const data = await api.swipeTrade(tradeId, decision);
      if (data.error) { showToastMsg(data.error); return; }
      // Update the trade in our list
      setTrades(prev => prev.map(t =>
        t.trade_id === tradeId ? { ...t, decision, ...data } : t
      ));
      if (data.matched) {
        showToastMsg("It's a Match!");
        loadMatches();
      }
    } catch {
      showToastMsg('Failed to record decision');
    }
  };

  const handleDisposition = async (matchId, decision) => {
    try {
      const data = await api.recordDisposition(matchId, decision);
      if (data.error) { showToastMsg(data.error); return; }
      if (data.matches) setMatches(data.matches);
      else loadMatches();
      showToastMsg(decision === 'accept' ? 'Trade accepted!' : 'Trade declined');
    } catch {
      showToastMsg('Failed to record decision');
    }
  };

  const saveOutlookPrefs = async () => {
    if (!pendingOutlook) return;
    try {
      await api.savePreferences({
        league_id: leagueId,
        team_outlook: pendingOutlook,
        acquire_positions: acquireChecks,
        trade_away_positions: awayChecks,
      });
      setOutlook(pendingOutlook, acquireChecks, awayChecks);
      setShowOutlook(false);
      showToastMsg('Preferences saved');
      generateTrades();
    } catch {
      showToastMsg('Failed to save preferences');
    }
  };

  const skipPositional = async () => {
    if (!pendingOutlook) return;
    try {
      await api.savePreferences({
        league_id: leagueId,
        team_outlook: pendingOutlook,
        acquire_positions: [],
        trade_away_positions: [],
      });
      setOutlook(pendingOutlook, [], []);
      setShowOutlook(false);
      showToastMsg('Outlook saved');
      generateTrades();
    } catch {
      showToastMsg('Failed to save outlook');
    }
  };

  const togglePosCheck = (side, pos) => {
    const setter = side === 'acquire' ? setAcquireChecks : setAwayChecks;
    const current = side === 'acquire' ? acquireChecks : awayChecks;
    if (current.includes(pos)) {
      setter(current.filter(p => p !== pos));
    } else {
      setter([...current, pos]);
    }
  };

  // ── Gate screen ──
  if (!unlocked && gateProgress) {
    const threshold = gateProgress.threshold || 10;
    return (
      <View style={styles.container}>
        <ScrollView contentContainerStyle={styles.gateContent}>
          <Text style={{ fontSize: 40, textAlign: 'center' }}>🔒</Text>
          <Text style={styles.gateTitle}>Complete your rankings to unlock Trade Finder</Text>
          <Text style={styles.gateSub}>Rank at least {threshold} players per position</Text>
          {['QB', 'RB', 'WR', 'TE'].map(pos => {
            const count = Math.min(gateProgress[pos] || 0, threshold);
            const pct = Math.round(count / threshold * 100);
            const done = count >= threshold;
            return (
              <View key={pos} style={styles.gateRow}>
                <Text style={styles.gatePos}>{pos}</Text>
                <View style={styles.gateBarWrap}>
                  <View style={[styles.gateBarFill, { width: `${pct}%` }, done && { backgroundColor: colors.green }]} />
                </View>
                <Text style={styles.gateCount}>{count}/{threshold}</Text>
                {done && <Text style={{ color: colors.green }}>✓</Text>}
              </View>
            );
          })}
          <TouchableOpacity
            style={styles.gateCta}
            onPress={onSwitchToRank}
          >
            <Text style={styles.gateCtaText}>Go rank players →</Text>
          </TouchableOpacity>
        </ScrollView>
      </View>
    );
  }

  // ── Main trades view ──
  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Trade Finder</Text>
          <TouchableOpacity
            style={styles.genBtn}
            onPress={generateTrades}
            disabled={generating}
          >
            {generating ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.genBtnText}>⚡ Find Trades</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* Fairness controls */}
        <View style={styles.fairnessRow}>
          <Text style={styles.fairnessLabel}>Trade balance</Text>
          <View style={styles.sliderRow}>
            <Text style={styles.fairnessVal}>{equalOnly ? '100' : fairness}%</Text>
          </View>
          {!equalOnly && (
            <View style={styles.sliderWrap}>
              <Text style={{ color: colors.muted, fontSize: 10 }}>50%</Text>
              <View style={{ flex: 1, marginHorizontal: 8 }}>
                {/* Note: Slider from @react-native-community/slider may not be installed.
                    Fallback: just show the value and buttons to adjust. */}
                <View style={styles.fakeSlider}>
                  <TouchableOpacity onPress={() => { const v = Math.max(50, fairness - 5); setFairness(v); saveFairness(v, equalOnly); }}>
                    <Text style={styles.sliderBtn}>−</Text>
                  </TouchableOpacity>
                  <View style={[styles.sliderTrack]}>
                    <View style={[styles.sliderFill, { width: `${((fairness - 50) / 50) * 100}%` }]} />
                  </View>
                  <TouchableOpacity onPress={() => { const v = Math.min(100, fairness + 5); setFairness(v); saveFairness(v, equalOnly); }}>
                    <Text style={styles.sliderBtn}>+</Text>
                  </TouchableOpacity>
                </View>
              </View>
              <Text style={{ color: colors.muted, fontSize: 10 }}>100%</Text>
            </View>
          )}
          <View style={styles.equalRow}>
            <Switch
              value={equalOnly}
              onValueChange={(v) => { setEqualOnly(v); saveFairness(fairness, v); }}
              trackColor={{ true: colors.accent, false: colors.border }}
              thumbColor="#fff"
            />
            <Text style={styles.equalLabel}>Equal only</Text>
          </View>
        </View>

        {/* Outlook badge */}
        {currentOutlook && (
          <TouchableOpacity style={styles.outlookBadge} onPress={() => { setOutlookStep(1); setShowOutlook(true); }}>
            <Text style={styles.outlookText}>
              {OUTLOOK_OPTIONS.find(o => o.value === currentOutlook)?.emoji || ''}{' '}
              {OUTLOOK_OPTIONS.find(o => o.value === currentOutlook)?.name || currentOutlook}
            </Text>
            <Text style={{ color: colors.muted, fontSize: 11 }}>⚙ Change</Text>
          </TouchableOpacity>
        )}

        {/* Trade Cards */}
        {trades.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No trades yet</Text>
            <Text style={styles.emptyText}>
              Hit "Find Trades" to generate personalised trade suggestions based on your rankings vs your leaguemates.
            </Text>
          </View>
        ) : (
          trades.map((trade, i) => (
            <TradeCard key={trade.trade_id || i} trade={trade} onSwipe={handleSwipe} />
          ))
        )}

        {/* Matches Section */}
        {matches.length > 0 && (
          <View style={styles.matchesSection}>
            <Text style={styles.matchesTitle}>🤝 Mutual Matches</Text>
            {matches.map(m => {
              const giveStr = (m.my_give_names || m.my_give || []).join(', ') || '—';
              const recvStr = (m.my_receive_names || m.my_receive || []).join(', ') || '—';
              return (
                <View key={m.match_id} style={styles.matchCard}>
                  <Text style={styles.matchPartner}>{m.partner_name || 'Leaguemate'}</Text>
                  <Text style={styles.matchDetail}>Give: {giveStr}</Text>
                  <Text style={styles.matchDetail}>Receive: {recvStr}</Text>
                  {m.status === 'pending' && !m.my_decision && (
                    <View style={styles.matchBtns}>
                      <TouchableOpacity
                        style={styles.matchDeclineBtn}
                        onPress={() => handleDisposition(m.match_id, 'decline')}
                      >
                        <Text style={{ color: colors.red, fontWeight: '600' }}>✕ Decline</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={styles.matchAcceptBtn}
                        onPress={() => handleDisposition(m.match_id, 'accept')}
                      >
                        <Text style={{ color: colors.green, fontWeight: '600' }}>✓ Accept</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                  {m.status !== 'pending' && (
                    <Text style={[styles.matchStatus, m.status === 'accepted' && { color: colors.green }]}>
                      {m.status === 'accepted' ? '✅ Accepted' : '✗ Declined'}
                    </Text>
                  )}
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>

      {/* Outlook Modal */}
      <Modal visible={showOutlook} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            {outlookStep === 1 ? (
              <>
                <Text style={styles.modalTitle}>What's your team outlook?</Text>
                <Text style={styles.modalSub}>This shapes which trades surface for you.</Text>
                {OUTLOOK_OPTIONS.map(opt => (
                  <TouchableOpacity
                    key={opt.value}
                    style={[styles.outlookOption, pendingOutlook === opt.value && styles.outlookOptionSelected]}
                    onPress={() => {
                      setPendingOutlook(opt.value);
                      setOutlookStep(2);
                    }}
                  >
                    <Text style={{ fontSize: 24 }}>{opt.emoji}</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.outlookOptName}>{opt.name}</Text>
                      <Text style={styles.outlookOptDesc}>{opt.desc}</Text>
                    </View>
                  </TouchableOpacity>
                ))}
                {currentOutlook && (
                  <TouchableOpacity onPress={() => setShowOutlook(false)} style={{ marginTop: 12 }}>
                    <Text style={{ color: colors.muted, textAlign: 'center' }}>Cancel</Text>
                  </TouchableOpacity>
                )}
              </>
            ) : (
              <>
                <Text style={styles.modalTitle}>Positional preferences</Text>
                <Text style={styles.modalSub}>Optional — helps surface trades that match your roster needs.</Text>
                <Text style={styles.posPrefHeader}>Positions I want</Text>
                <View style={styles.checkRow}>
                  {POSITIONS.map(pos => (
                    <TouchableOpacity
                      key={pos}
                      style={[styles.checkBtn, acquireChecks.includes(pos) && styles.checkBtnActive]}
                      onPress={() => togglePosCheck('acquire', pos)}
                    >
                      <Text style={[styles.checkBtnText, acquireChecks.includes(pos) && { color: colors.accent }]}>
                        {pos === 'PICK' ? 'Picks' : pos}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.posPrefHeader}>Positions to move</Text>
                <View style={styles.checkRow}>
                  {POSITIONS.map(pos => (
                    <TouchableOpacity
                      key={pos}
                      style={[styles.checkBtn, awayChecks.includes(pos) && styles.checkBtnActive]}
                      onPress={() => togglePosCheck('away', pos)}
                    >
                      <Text style={[styles.checkBtnText, awayChecks.includes(pos) && { color: colors.accent }]}>
                        {pos === 'PICK' ? 'Picks' : pos}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity style={styles.savePrefsBtn} onPress={saveOutlookPrefs}>
                  <Text style={styles.savePrefsBtnText}>Save preferences</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={skipPositional} style={{ marginTop: 8 }}>
                  <Text style={{ color: colors.muted, textAlign: 'center' }}>Skip for now</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </View>
      </Modal>

      {/* Toast */}
      {toast ? (
        <View style={styles.toast}>
          <Text style={styles.toastText}>{toast}</Text>
        </View>
      ) : null}
    </View>
  );
}

const tStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.md,
    marginBottom: spacing.md,
    overflow: 'hidden',
  },
  cardPassed: { opacity: 0.5 },
  meta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  metaText: { color: colors.muted, fontSize: fontSize.sm },
  metaUsername: { color: colors.text, fontWeight: '600' },
  scorePill: {
    backgroundColor: colors.accent + '22',
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  scoreText: { color: colors.accent, fontSize: 11, fontWeight: '600' },
  sides: { flexDirection: 'row' },
  side: { flex: 1, padding: spacing.md, gap: spacing.sm },
  sideLabel: { fontSize: 11, fontWeight: '700', color: colors.red, textTransform: 'uppercase', marginBottom: 4 },
  playerRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  posBadge: { paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, borderWidth: 1 },
  posBadgeText: { fontSize: 10, fontWeight: '700' },
  playerName: { color: colors.text, fontSize: fontSize.sm, fontWeight: '600' },
  playerMeta: { color: colors.muted, fontSize: 11 },
  tierBadge: { borderWidth: 1, borderRadius: 3, paddingHorizontal: 4, paddingVertical: 0 },
  tierText: { fontSize: 9, fontWeight: '700' },
  actions: { flexDirection: 'row', borderTopWidth: 1, borderTopColor: colors.border },
  passBtn: { flex: 1, padding: spacing.md, alignItems: 'center', borderRightWidth: 1, borderRightColor: colors.border },
  passBtnText: { color: colors.red, fontWeight: '600', fontSize: fontSize.sm },
  likeBtn: { flex: 1, padding: spacing.md, alignItems: 'center' },
  likeBtnText: { color: colors.green, fontWeight: '600', fontSize: fontSize.sm },
  decidedText: { color: colors.muted, fontSize: fontSize.sm, textAlign: 'center', padding: spacing.md },
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, padding: spacing.lg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.lg },
  title: { fontSize: fontSize.xl, fontWeight: '700', color: colors.text },
  genBtn: { backgroundColor: colors.accent, borderRadius: borderRadius.sm, paddingVertical: 10, paddingHorizontal: 16 },
  genBtnText: { color: '#fff', fontWeight: '600', fontSize: fontSize.sm },

  fairnessRow: { marginBottom: spacing.lg },
  fairnessLabel: { color: colors.muted, fontSize: fontSize.sm, marginBottom: 4 },
  sliderRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  fairnessVal: { color: colors.text, fontWeight: '700', fontSize: fontSize.md },
  sliderWrap: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  fakeSlider: { flexDirection: 'row', alignItems: 'center', flex: 1, gap: 8 },
  sliderBtn: { color: colors.accent, fontSize: 20, fontWeight: '700', paddingHorizontal: 8 },
  sliderTrack: { flex: 1, height: 4, backgroundColor: colors.border, borderRadius: 2, overflow: 'hidden' },
  sliderFill: { height: '100%', backgroundColor: colors.accent, borderRadius: 2 },
  equalRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  equalLabel: { color: colors.muted, fontSize: fontSize.sm },

  outlookBadge: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.sm,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  outlookText: { color: colors.text, fontWeight: '600' },

  empty: { alignItems: 'center', paddingVertical: 40 },
  emptyTitle: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text, marginBottom: 8 },
  emptyText: { color: colors.muted, textAlign: 'center', lineHeight: 20 },

  matchesSection: { marginTop: spacing.xl },
  matchesTitle: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text, marginBottom: spacing.md },
  matchCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  matchPartner: { color: colors.text, fontWeight: '700', fontSize: fontSize.md, marginBottom: 4 },
  matchDetail: { color: colors.muted, fontSize: fontSize.sm, marginBottom: 2 },
  matchBtns: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.md },
  matchDeclineBtn: { flex: 1, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.red, borderRadius: borderRadius.sm },
  matchAcceptBtn: { flex: 1, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.green, borderRadius: borderRadius.sm },
  matchStatus: { color: colors.muted, fontSize: fontSize.sm, marginTop: 8 },

  // Gate
  gateContent: { flex: 1, justifyContent: 'center', padding: spacing.xl, gap: spacing.lg },
  gateTitle: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text, textAlign: 'center' },
  gateSub: { color: colors.muted, textAlign: 'center' },
  gateRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  gatePos: { width: 30, color: colors.text, fontWeight: '700' },
  gateBarWrap: { flex: 1, height: 6, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden' },
  gateBarFill: { height: '100%', backgroundColor: colors.accent, borderRadius: 3 },
  gateCount: { color: colors.muted, fontSize: fontSize.xs, width: 40 },
  gateCta: { backgroundColor: colors.accent, borderRadius: borderRadius.sm, padding: 14, alignItems: 'center', marginTop: spacing.lg },
  gateCtaText: { color: '#fff', fontWeight: '600', fontSize: fontSize.md },

  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: borderRadius.xl, padding: spacing.xxl, maxHeight: '85%' },
  modalTitle: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text, textAlign: 'center', marginBottom: 4 },
  modalSub: { color: colors.muted, textAlign: 'center', marginBottom: spacing.lg },
  outlookOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.md,
    marginBottom: spacing.sm,
  },
  outlookOptionSelected: { borderColor: colors.accent, backgroundColor: colors.accent + '11' },
  outlookOptName: { color: colors.text, fontWeight: '600', fontSize: fontSize.md },
  outlookOptDesc: { color: colors.muted, fontSize: fontSize.sm },
  posPrefHeader: { color: colors.text, fontWeight: '600', marginTop: spacing.md, marginBottom: 6 },
  checkRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  checkBtn: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 20,
  },
  checkBtnActive: { borderColor: colors.accent, backgroundColor: colors.accent + '15' },
  checkBtnText: { color: colors.muted, fontWeight: '600' },
  savePrefsBtn: { backgroundColor: colors.accent, borderRadius: borderRadius.sm, padding: 13, alignItems: 'center', marginTop: spacing.lg },
  savePrefsBtnText: { color: '#fff', fontWeight: '600' },

  toast: {
    position: 'absolute',
    bottom: 30,
    left: 20,
    right: 20,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    alignItems: 'center',
  },
  toastText: { color: colors.text, fontSize: fontSize.sm },
});
