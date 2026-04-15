import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  ActivityIndicator, Animated,
} from 'react-native';
import { colors, spacing, fontSize, borderRadius, positionColor } from '../utils/theme';
import { api } from '../services/api';
import { storage } from '../utils/storage';

const SIDES = ['a', 'b', 'c'];
const RANK_COLORS = { 1: colors.gold, 2: colors.silver, 3: colors.bronze };

function valueTier(p) {
  if (!p.search_rank && p.search_rank !== 0) return null;
  const r = p.search_rank;
  if (r <= 50) return 'elite';
  if (r <= 150) return 'high';
  if (r <= 300) return 'mid';
  return 'depth';
}

const TIER_COLORS = {
  elite: '#f59e0b',
  high: '#22c55e',
  mid: '#3b82f6',
  depth: '#7a7f96',
};

function TierBadge({ player }) {
  const tier = valueTier(player);
  if (!tier) return null;
  const labels = { elite: 'Elite', high: 'High', mid: 'Mid', depth: 'Depth' };
  return (
    <View style={[styles.tierBadge, { borderColor: TIER_COLORS[tier] }]}>
      <Text style={[styles.tierText, { color: TIER_COLORS[tier] }]}>{labels[tier]}</Text>
    </View>
  );
}

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
  if (!player) return <View style={styles.cardPlaceholder}><ActivityIndicator color={colors.accent} /></View>;

  const isPick = player.pick_value != null;
  const borderColor = rank ? RANK_COLORS[rank] : colors.border;
  const borderWidth = rank ? 2 : 1;

  return (
    <TouchableOpacity
      style={[styles.card, { borderColor, borderWidth }]}
      onPress={() => onPress(side)}
      disabled={disabled}
      activeOpacity={0.7}
    >
      {rank ? (
        <View style={[styles.rankBadge, { backgroundColor: RANK_COLORS[rank] }]}>
          <Text style={styles.rankBadgeText}>{rank}</Text>
        </View>
      ) : null}

      <PosBadge position={player.position} isPick={isPick} />

      <Text style={styles.cardName}>{player.name || '—'}</Text>

      <View style={styles.cardMetaRow}>
        <Text style={styles.cardTeam}>{player.team || 'FA'}</Text>
        {isPick ? (
          <Text style={styles.cardMeta}>Dynasty value: {player.pick_value?.toFixed(1) || '—'}</Text>
        ) : (
          <Text style={styles.cardMeta}>
            Age {player.age} · {player.years_experience} yr{player.years_experience !== 1 ? 's' : ''} exp
          </Text>
        )}
      </View>

      <View style={styles.cardExtraRow}>
        <TierBadge player={player} />
        {player.years_experience === 0 && (
          <View style={[styles.rookieBadge]}>
            <Text style={styles.rookieText}>ROOKIE</Text>
          </View>
        )}
        {player.injury_status ? (
          <View style={styles.injBadge}>
            <Text style={styles.injText}>{player.injury_status === 'IR' ? 'IR' : player.injury_status}</Text>
          </View>
        ) : null}
      </View>
    </TouchableOpacity>
  );
}

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
  }, [position]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  };

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

  const selectCard = (side) => {
    if (locked || !trio) return;

    // Undo logic
    const existingIdx = selection.indexOf(side);
    if (existingIdx !== -1) {
      setSelection(selection.slice(0, existingIdx));
      return;
    }

    const newSelection = [...selection, side];

    if (newSelection.length === 2) {
      const last = SIDES.find(s => !newSelection.includes(s));
      const full = [...newSelection, last];
      setSelection(full);
      if (autoConfirm) {
        submitRanking(full);
      }
    } else {
      setSelection(newSelection);
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

      setProgress(data);
      if (data.threshold_met && data.interaction_count === data.threshold) {
        showToast('Rankings established!');
      }
    } catch {
      showToast('Submit failed');
    }

    setTimeout(() => {
      setSelection([]);
      setLocked(false);
      loadTrio();
    }, 350);
  };

  const toggleAutoConfirm = async () => {
    const newVal = !autoConfirm;
    setAutoConfirm(newVal);
    await storage.setAutoConfirm(newVal);
  };

  const getRank = (side) => {
    const idx = selection.indexOf(side);
    return idx !== -1 ? idx + 1 : 0;
  };

  const getInstruction = () => {
    const remaining = 3 - selection.length;
    if (remaining === 3) return 'Tap players in order of preference — best first';
    if (remaining === 2) return 'Good — now tap your 2nd choice';
    if (remaining === 1) return 'Last one — tap your 3rd choice';
    return 'All ranked — confirm when ready';
  };

  const pct = progress.threshold > 0
    ? Math.min(100, Math.round(progress.interaction_count / progress.threshold * 100))
    : 0;

  return (
    <View style={styles.container}>
      {/* Position Tabs */}
      <View style={styles.positionTabs}>
        {['RB', 'WR', 'QB', 'TE'].map(pos => (
          <TouchableOpacity
            key={pos}
            style={[styles.posTab, position === pos && styles.posTabActive]}
            onPress={() => setPosition(pos)}
          >
            <Text style={[styles.posTabText, position === pos && styles.posTabTextActive]}>
              {pos}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Progress Bar */}
      <View style={styles.progressWrap}>
        <View style={styles.progressMeta}>
          <Text style={styles.progressLabel}>
            {progress.interaction_count} / {progress.threshold} rankings
          </Text>
          <Text style={[styles.progressStatus, progress.threshold_met && { color: colors.green }]}>
            {progress.threshold_met ? '✓ Rankings established' : `${progress.threshold - progress.interaction_count} to go`}
          </Text>
        </View>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${pct}%` }, progress.threshold_met && { backgroundColor: colors.green }]} />
        </View>
      </View>

      {/* Instruction */}
      <Text style={styles.instruction}>{getInstruction()}</Text>

      {/* Player Cards */}
      <ScrollView style={styles.arena} contentContainerStyle={styles.arenaContent}>
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
      </ScrollView>

      {/* Auto-confirm toggle */}
      <TouchableOpacity
        style={[styles.autoBtn, autoConfirm && styles.autoBtnActive]}
        onPress={toggleAutoConfirm}
      >
        <Text style={[styles.autoBtnText, autoConfirm && styles.autoBtnTextActive]}>
          ⚡ Auto-advance {autoConfirm ? 'ON' : 'OFF'}
        </Text>
      </TouchableOpacity>

      {/* Submit + Skip */}
      {!autoConfirm && (
        <View style={styles.submitRow}>
          <TouchableOpacity
            style={[styles.submitBtn, selection.length === 3 && styles.submitBtnReady]}
            onPress={() => submitRanking()}
            disabled={selection.length < 3 || locked}
          >
            <Text style={styles.submitBtnText}>Confirm ranking →</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.skipBtn} onPress={loadTrio}>
            <Text style={styles.skipBtnText}>Skip ↩</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Toast */}
      {toast ? (
        <View style={styles.toast}>
          <Text style={styles.toastText}>{toast}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, padding: spacing.lg },
  positionTabs: {
    flexDirection: 'row',
    gap: 6,
    marginBottom: spacing.md,
    marginTop: spacing.sm,
  },
  posTab: {
    paddingVertical: 8,
    paddingHorizontal: 18,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  posTabActive: {
    backgroundColor: colors.accent + '22',
    borderColor: colors.accent,
  },
  posTabText: { color: colors.muted, fontWeight: '600', fontSize: fontSize.sm },
  posTabTextActive: { color: colors.accent },

  progressWrap: { marginBottom: spacing.md },
  progressMeta: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  progressLabel: { fontSize: fontSize.xs, color: colors.muted },
  progressStatus: { fontSize: fontSize.xs, color: colors.muted },
  progressTrack: {
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.accent,
    borderRadius: 2,
  },

  instruction: { fontSize: fontSize.sm, color: colors.muted, textAlign: 'center', marginBottom: spacing.md },

  arena: { flex: 1 },
  arenaContent: { gap: spacing.md, paddingBottom: spacing.lg },

  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardPlaceholder: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.lg,
    padding: 40,
    alignItems: 'center',
  },
  rankBadge: {
    position: 'absolute',
    top: -8,
    right: -8,
    width: 26,
    height: 26,
    borderRadius: 13,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
  },
  rankBadgeText: { color: '#000', fontWeight: '800', fontSize: 13 },
  posBadge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
    borderWidth: 1,
  },
  posBadgeText: { fontSize: 11, fontWeight: '700' },
  cardName: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text },
  cardMetaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  cardTeam: { fontSize: fontSize.sm, fontWeight: '600', color: colors.muted },
  cardMeta: { fontSize: fontSize.sm, color: colors.muted },
  cardExtraRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  tierBadge: {
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  tierText: { fontSize: 10, fontWeight: '700' },
  rookieBadge: {
    backgroundColor: colors.green + '22',
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  rookieText: { fontSize: 10, fontWeight: '700', color: colors.green },
  injBadge: {
    backgroundColor: colors.red + '22',
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  injText: { fontSize: 10, fontWeight: '700', color: colors.red },

  autoBtn: {
    alignSelf: 'center',
    paddingVertical: 4,
    paddingHorizontal: 14,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  autoBtnActive: { borderColor: colors.accent, backgroundColor: colors.accent + '15' },
  autoBtnText: { fontSize: fontSize.sm, color: colors.muted },
  autoBtnTextActive: { color: colors.accent },

  submitRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.md,
    marginBottom: spacing.sm,
  },
  submitBtn: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.sm,
    paddingVertical: 10,
    paddingHorizontal: 20,
    opacity: 0.5,
  },
  submitBtnReady: { opacity: 1, borderColor: colors.accent, backgroundColor: colors.accent },
  submitBtnText: { color: colors.text, fontWeight: '600', fontSize: fontSize.sm },
  skipBtn: {
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  skipBtnText: { color: colors.muted, fontSize: fontSize.sm },

  toast: {
    position: 'absolute',
    bottom: 100,
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
