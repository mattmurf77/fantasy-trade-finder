import React from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView } from 'react-native';

import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';

// FB #156 (Trade-Finding Hub, Variant B) — the lateral quick-switch chip row
// carried at the top of every focused mode. #246 (guided-first landing,
// approved mock mockups/polish-lab-2026-08/acquire-landing-guided-first.html
// frame B1): with the launcher hub unrouted this strip IS the mode-switching
// home — the "‹ Hub" back chevron is gone, the hint line renders only when
// the host asks (cold start, mock B2 — dropped once a deck exists), and a
// fifth chip, Free Agents, navigates to the FA finder (operator override of
// the mock's tail-section placement). The three deck modes (Guided / Team /
// Player) switch IN PLACE via `onSwitch` (navigation.setParams — the same
// TradesScreen instance, so pinned targets persist across the switch);
// Calculator (`onCalculator`) and Free Agents (`onFreeAgents`) are pushed
// screens, not deck modes — same chip construction (the Calc chip set that
// precedent; no visual distinction). Purely presentational — the host owns
// navigation.

export type FinderMode = 'guided' | 'team' | 'player';

const COPY: Record<FinderMode, { title: string; hint: string }> = {
  guided: {
    title: 'Fully Guided',
    hint: 'We read your roster & league and walk you to the best deals.',
  },
  team: {
    title: 'Specific Team',
    hint: 'Only mutual-gain deals with one league-mate.',
  },
  player: {
    title: 'Specific Player',
    hint: 'Name players to trade for, away, or both — the engine fills the rest.',
  },
};

type ChipKey = FinderMode | 'calc' | 'free-agents' | 'draft';

const CHIPS: { key: ChipKey; label: string }[] = [
  { key: 'guided', label: 'Guided' },
  { key: 'team', label: 'Team' },
  { key: 'player', label: 'Player' },
  { key: 'calc', label: 'Calc' },
  { key: 'free-agents', label: 'Free agents' },
];

// rookie-draft placement, option B (operator decision 2026-08-06, approved
// mock `mockups/polish-lab-2026-08/draft-surface-placement.html` frame B1) —
// the draft is the third way to acquire a player (trade for him, pick him
// up, draft him), and the other two already live in this strip.
//
// It LEADS, and that is not a style choice: the five shipped chips already
// measure ≈402pt against ≈361pt of usable width, so the strip is genuinely
// scrolled — an APPENDED sixth chip would sit off-screen and never be seen
// (mock finding, Option B implementation row). Same push-chip construction
// as Calc and Free agents, which set the precedent that a chip may navigate
// rather than switch deck mode, with deliberately no visual distinction.
const DRAFT_CHIP: { key: ChipKey; label: string } = { key: 'draft', label: 'Draft' };

interface Props {
  mode: FinderMode;
  /** In-place switch between the three deck modes (setParams). */
  onSwitch: (mode: FinderMode) => void;
  /** Jump to the Manual Calculator screen. */
  onCalculator: () => void;
  /** Jump to the Free Agent finder (root-stack `FreeAgents`, #246). */
  onFreeAgents: () => void;
  /** Jump to the Draft Room (root-stack `DraftRoom`, rookie-draft option B).
   *  OMIT to render today's five chips exactly — the host passes this only
   *  when `draft.room` is on, so the flag gates the chip's existence. */
  onDraft?: () => void;
  /** Team mode: the scoped league-mate's display name, if chosen. */
  teamName?: string | null;
  /** Render the one-line mode hint (cold start only, #246 mock B2). */
  showHint?: boolean;
  /** #269 (flag `trades.sheet_targeting`) — Team and Player selection moved
   *  into the #257 full sheet (a league picker + single-select "Trade with"
   *  block), so their chips here are redundant and go away. Omit entirely
   *  (flag off) to render today's five/six chips exactly. */
  hideTeamAndPlayer?: boolean;
}

export default function TradeFinderModeBar({
  mode,
  onSwitch,
  onCalculator,
  onFreeAgents,
  onDraft,
  teamName,
  showHint = false,
  hideTeamAndPlayer = false,
}: Props) {
  const copy = COPY[mode];
  const baseChips = hideTeamAndPlayer
    ? CHIPS.filter((c) => c.key !== 'team' && c.key !== 'player')
    : CHIPS;
  // Draft LEADS when present (see DRAFT_CHIP); absent ⇒ the array is the
  // shipped five, identical object identity and order.
  const chips = onDraft ? [DRAFT_CHIP, ...baseChips] : baseChips;
  const hint =
    mode === 'team' && teamName
      ? `Only mutual-gain deals with ${teamName}.`
      : copy.hint;

  return (
    <View style={styles.wrap}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipRow}
      >
        {chips.map((c) => {
          const active = c.key === mode;
          return (
            <Pressable
              key={c.key}
              testID={`trades.finder-mode.${c.key}`}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={c.label}
              onPress={() =>
                c.key === 'calc'
                  ? onCalculator()
                  : c.key === 'free-agents'
                    ? onFreeAgents()
                    : c.key === 'draft'
                      ? onDraft?.()
                      : onSwitch(c.key)
              }
              style={({ pressed }) => [
                styles.chip,
                active && styles.chipActive,
                pressed && styles.chipPressed,
              ]}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>
                {c.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <Text style={styles.title} accessibilityRole="header">
        {copy.title}
      </Text>
      {showHint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: space.md, gap: space.xs },
  chipRow: { gap: space.sm, paddingVertical: space.xs },
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
    minHeight: 36,
    justifyContent: 'center',
  },
  chipActive: { borderColor: ice.base, backgroundColor: ink.ink2 },
  chipPressed: { backgroundColor: ink.ink3 },
  chipText: { ...type.bodySm, color: chalk.dim, fontFamily: fonts.uiSemi },
  chipTextActive: { color: chalk.base },
  title: { ...type.heading, marginTop: space.xs },
  hint: { ...type.bodySm },
});
