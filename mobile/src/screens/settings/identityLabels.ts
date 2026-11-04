// The "Signed in with …" label for a linked sign-in identity (GET /api/account
// `account.identities[].provider`). One map for both Settings surfaces that
// list identities: the hub's Account page (sections/AccountIdentitySection)
// and the flag-off flat list (SettingsScreen).
//
// The keys are the server's `linked_identities.provider` values. `espn` and
// `mfl` are platforms-eng's frozen values (2026-10-26): a proven ESPN or MFL
// sign-in mints an acct_* account with that identity.
//
// An unknown provider has NO label, and the caller renders no row. The old
// two-way ternary read every non-Apple identity as "Signed in with Google";
// no row is better than a wrong one.
//
// Zero runtime imports: tests/check-signin-identity-labels.js runs this file
// under plain node.

export const IDENTITY_LABELS: Readonly<Record<string, string>> = {
  apple: 'Signed in with Apple',
  google: 'Signed in with Google',
  espn: 'Signed in with ESPN',
  mfl: 'Signed in with MFL',
};

export function identityLabel(provider: string | null | undefined): string | null {
  if (!provider || !Object.prototype.hasOwnProperty.call(IDENTITY_LABELS, provider)) return null;
  return IDENTITY_LABELS[provider];
}
