import React, { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { chalk, ink, radii, space } from '../../theme/chalkline';
import { Button, Text } from '../chalkline';
import { listFounderPages, type FounderPageSummary } from '../../api/founder';
import { notesLabel, updatedLabel } from '../../utils/founderPages';
import FounderPageViewer from './FounderPageViewer';

// Founders' review, "Review pages" — the list of the operator's review
// documents (docs/plans/founder-review/pages-design.md §4). FounderReview
// mounts this only after GET /api/founder/pages listed at least one page (a
// 404 or an empty list hides the choice), so this file reads no flag. Tapping
// a page opens FounderPageViewer full screen; closing it refreshes the counts.

const COPY = {
  title: 'Review pages',
  intro: 'Documents to review. Your comments save as you type.',
  readFailed: 'Couldn’t load the review pages.',
  tryAgain: 'Try again',
} as const;

export const founderPagesKey = ['founder', 'pages'] as const;

/** One query definition for the list and for FounderReview's availability check. */
export function founderPagesQuery() {
  return {
    queryKey: founderPagesKey,
    queryFn: ({ signal }: { signal: AbortSignal }) => listFounderPages({ signal }),
    retry: false,
    staleTime: 0,
  };
}

export default function FounderPagesReview() {
  const qc = useQueryClient();
  const pagesQ = useQuery(founderPagesQuery());
  const [open, setOpen] = useState<FounderPageSummary | null>(null);

  if (pagesQ.isPending) {
    return (
      <View style={styles.center} testID="founder-review.pages.list-loading">
        <ActivityIndicator color={chalk.dim} />
      </View>
    );
  }
  if (pagesQ.isError) {
    return (
      <View style={styles.block} testID="founder-review.pages.list-error">
        <Text variant="body">{COPY.readFailed}</Text>
        <Button testID="founder-review.pages.list-retry" label={COPY.tryAgain} variant="secondary"
          onPress={() => { void pagesQ.refetch(); }} />
      </View>
    );
  }

  const pages = pagesQ.data ?? [];
  return (
    <>
      <ScrollView contentContainerStyle={styles.content} testID="founder-review.pages.list">
        <Text variant="heading">{COPY.title}</Text>
        <Text variant="bodySm" style={styles.dim}>{COPY.intro}</Text>
        {pages.map((p) => (
          <Pressable
            key={p.slug}
            testID="founder-review.pages.row"
            accessibilityRole="button"
            accessibilityLabel={`${p.title}, ${updatedLabel(p.updated_at)}, ${notesLabel(p.notes)}`}
            onPress={() => setOpen(p)}
            style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
          >
            <Text variant="title">{p.title}</Text>
            <Text variant="data" style={styles.dim}>{`${updatedLabel(p.updated_at)} · ${notesLabel(p.notes)}`}</Text>
          </Pressable>
        ))}
      </ScrollView>
      {open ? (
        <FounderPageViewer
          slug={open.slug}
          title={open.title}
          onClose={() => {
            setOpen(null);
            void qc.invalidateQueries({ queryKey: founderPagesKey });
          }}
        />
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, gap: space.md, paddingBottom: space.xxxl },
  block: { gap: space.lg, padding: space.lg },
  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: space.xxxl },
  dim: { color: chalk.dim },
  row: {
    gap: space.xs, padding: space.md, minHeight: 44, borderWidth: 1, borderColor: ink.line,
    borderRadius: radii.sm, backgroundColor: ink.ink1,
  },
  rowPressed: { backgroundColor: ink.ink3 },
});
