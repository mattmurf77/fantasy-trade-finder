// Referral loop FR-10 / PRD §7.1 — the public invite id `t`.
//
// The ONE mobile copy of the shape rule. The server mints 12 URL-safe chars
// (`secrets.token_urlsafe(9)`) and accepts any well-formed `t` in this range;
// the client stores and forwards only values that match, so a hand-edited or
// truncated link never reaches session init or an event prop.
//
// `t` names an invite. It grants no access and must never be used as an auth
// or session credential (analytics addendum C3).
//
// Pure, zero runtime imports, so a tests/check-*.js guard can transpile and
// run it under plain node.

export const INVITE_ID_RE = /^[A-Za-z0-9_-]{8,64}$/;

export function isInviteId(x: unknown): x is string {
  return typeof x === 'string' && INVITE_ID_RE.test(x);
}
