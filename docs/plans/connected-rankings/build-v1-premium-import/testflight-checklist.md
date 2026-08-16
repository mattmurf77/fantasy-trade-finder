# Operator TestFlight checklist — Premium Rankings Import v1

> The only runtime proof this feature can get (Maestro retired, D-056). Run on a TestFlight
> build cut from `feat/premium-import-v1` **after a full EAS build** (new native dep
> `expo-document-picker` — an OTA update will NOT carry it). Flip
> `ranks.source.dynasty_nerds` ON for your device (or globally, both are dark otherwise)
> before testing rows 2–7. Uses your own Dynasty Nerds subscription.

| # | Step | Pass looks like |
|---|---|---|
| 1 | Open the rankings import entry point (where paste import lived) | Half sheet shows: Upload CSV file, Paste rankings — and with the DN flag on, a Dynasty Nerds row with "requires your own subscription" caption |
| 2 | Tap Dynasty Nerds | In-app browser opens dynastynerds.com dynasty rankings; hint bar: "Log in, then tap the site's Export CSV button" |
| 3 | Log in on the site (your account), tap the site's **Export CSV** | App captures the file and returns to the sheet's confirmation step — no re-typing, no share-sheet detour |
| 4 | Confirmation step | Shows detected source (Dynasty Nerds) + inferred set/format from the filename; PPR maps to 1QB-PPR, SF-TEP to SF-TEP exactly; confirm control enabled |
| 5 | Confirm → preview → apply | Existing import preview (match results, unmatched); apply reorders your board; player ORDER matches the DN export |
| 6 | Re-open the half sheet | DN row shows "imported today/N weeks ago" staleness line |
| 7 | Export the **Contender** set on the site instead, capture it | Confirmation step blocks with the win-now warning; apply disabled until explicit override |
| 8 | Upload CSV file row with any non-preset CSV | Falls back to the generic mapping/paste flow — never guesses |
| 9 | Sanity: leaguemate view unchanged in kind | Your board change propagates exactly as any hand-edit would; no "Dynasty Nerds" label appears anywhere another user can see |

Failures → set `ranks.source.dynasty_nerds` false (kill switch) and file the symptom; the
sheet's Upload/Paste rows are unflagged and unaffected.
