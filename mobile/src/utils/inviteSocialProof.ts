// Social-proof copy for the league-invite CTAs (P1-5 / audit A-14).
//
// Pure by design — ZERO runtime imports — so
// mobile/tests/check-invite-social-proof.js can transpile this exact file
// with the project's typescript and run it under plain node. Same idiom as
// utils/leagueUnlocks.ts and utils/feedbackBadge.ts. Keep it that way: the
// test's module shim throws on any require().
//
// ONE function answers BOTH "is the ask real?" and "what does it say?".
// That is deliberate. The League Home card, the Matches empty-state block,
// the inline-link suppression and the invite_cta_shown impression event all
// call this single predicate, so they can never disagree about whether a
// CTA was on screen — which is what keeps the impression denominator
// meaningful. A null return means: no sentence, no CTA, no event.
//
// Copy framing (operator decision D-P1-13 · PR-5): FACTUAL. It states a
// count, never appeals to altruism, and never names an individual
// leaguemate. The user's own incentive is carried separately by
// INVITE_RATIONALE below, beside the number rather than inside it.

/** Why the user should care, in their own interest rather than anyone
 *  else's (D-P1-13 · PR-5 operator copy direction: more leaguemates ⇒
 *  better suggestions and more trade activity). Exported so both surfaces
 *  render the identical sentence. */
export const INVITE_RATIONALE =
  'More boards to trade against means sharper suggestions — and more trades that actually happen.';

/**
 * The social-proof line for the invite CTAs, or null when the ask is not
 * real (nobody left to invite, a solo/unknown league, or counts that have
 * not arrived).
 *
 * Returns the sentence WITHOUT trailing punctuation: Maestro `text:`
 * matchers are full-match regex and a period is a wildcard, so keeping
 * punctuation out of the returned string keeps those assertions honest.
 * Callers render it inside a <Text> that supplies none.
 */
export function inviteSocialProof(
  totalMates: number,
  joinedMates: number,
): string | null {
  // C1 — non-finite input. Never guess.
  if (!Number.isFinite(totalMates) || !Number.isFinite(joinedMates)) return null;
  // C2 — solo or unknown league. Mirrors LeagueProgressModule's own
  // `totalTeams <= 1 ⇒ render nothing` discipline.
  if (totalMates <= 0) return null;
  // C3 — impossible per backend/database.py's aggregate, defended anyway.
  if (joinedMates < 0 || joinedMates > totalMates) return null;

  const notJoined = totalMates - joinedMates;
  // C4 — everyone joined. The card is ABSENT, not congratulatory
  // (D-P1-13 · PR-10): an affirmation would occupy the promoted slot with
  // a message that asks for nothing.
  if (notJoined === 0) return null;
  // C5 — a two-person league; "1 of your 1 leaguemates" reads as a bug.
  if (notJoined === 1 && totalMates === 1) return "Your leaguemate hasn't joined yet";
  // C6 — singular verb.
  if (notJoined === 1) return `1 of your ${totalMates} leaguemates hasn't joined yet`;
  // C7 — plural.
  return `${notJoined} of your ${totalMates} leaguemates haven't joined yet`;
}
