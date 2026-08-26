// Mascot naming — the one place the guide's name is written (D-155).
//
// Pure: no React, no imports, no module state, so `tests/check-*.js` can
// transpile and run it under plain node.
//
// `AnalystAvatar` swaps the artwork behind `onboarding.mascot_ram`; these
// helpers swap the words that name it, so the two never disagree. Callers
// pass the resolved flag rather than reading it here — `utils/` must stay
// free of the flag store, and the three consumers already have it.
//
// ROLE vs NAME, which is the distinction that keeps the copy honest:
//   • "Fleeced" is the character's NAME. It replaces "The Analyst" only where
//     the text is naming *who is speaking*.
//   • "the guided tour" is the FEATURE. Settings talks about the feature, so
//     Settings copy stays feature-worded and does not chase the name.
// Getting this backwards produces "Turn off Fleeced", which reads as a
// billing complaint rather than a preference.

/** The Analyst's role name — the shipped default, and what renders whenever
 *  `onboarding.mascot_ram` is off. */
export const MASCOT_NAME_ANALYST = 'The Analyst';

/** Fleeced — the ram's character name (D-155). Shares a token with the
 *  product, so never write a sentence where it could mean either. */
export const MASCOT_NAME_RAM = 'Fleeced';

/** Who is speaking, by flag state. */
export function mascotName(ramOn: boolean): string {
  return ramOn ? MASCOT_NAME_RAM : MASCOT_NAME_ANALYST;
}

/** Settings → Guided tour: the toggle's title.
 *  Names the character, because the row sits under a "Guided tour" banner
 *  that already names the feature — the title answers "whose bubbles?". */
export function guideToggleTitle(ramOn: boolean): string {
  return mascotName(ramOn);
}

/** Settings → Guided tour: the toggle's description in the OFF state.
 *  Feature-worded on purpose (see the role/name note above). */
export function guideToggleDescriptionOff(ramOn: boolean): string {
  return `In-app guide bubbles on relevant screens. Turn off to dismiss ${mascotName(
    ramOn,
  )} everywhere.`;
}
