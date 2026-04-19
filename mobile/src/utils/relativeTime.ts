// Tiny "2h ago" / "just now" formatter. Accepts ISO strings or ms epochs.
// Deliberately string-returning so every caller can compose with their
// own label ("New match 2h ago").

export function relativeTime(input: string | number | Date | null | undefined): string {
  if (!input) return '';
  const then =
    typeof input === 'number'
      ? input
      : typeof input === 'string'
      ? Date.parse(input)
      : input.getTime();
  if (Number.isNaN(then)) return '';
  const diff = Date.now() - then;
  if (diff < 45_000) return 'just now';
  const mins = Math.round(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(diff / (60 * 60_000));
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(diff / (24 * 60 * 60_000));
  if (days < 14) return `${days}d ago`;
  const weeks = Math.round(days / 7);
  return `${weeks}w ago`;
}
