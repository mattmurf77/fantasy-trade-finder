> **Owner:** marketing-lead. Copied verbatim 2026-10-23 from marketing-lead's working file; the launch-slice authority for referral wording (head-product, 2026-10-23).

# marketing-lead: referral-loop copy, operator approval package (MKT-S8)

> **APPROVED by the operator 2026-10-23 (§2, all 26 entries).** Was: for the operator's one-pass approval (PRD #348 D-5). The referral loop is in the launch scope, and its strings ship in the 2026-11-06 binary. Release is 2026-11-18.
> - **Owner:** `marketing-lead` (Business Operations), under `head-bizops`.
> - **Workers:** `mkt-writer` drafted this; `marketing-lead` accepted it on 2026-10-23 with the lead calls below.
> - **Basis:** PRD `docs/plans/referral-loop/prd.md` at `91f1cc29` (the `plan/referral-loop` tip). Copy from `leads/marketing-lead-wave2.md`, which is identical to the vendored `marketing-inputs.md` at `91f1cc29`.
> - **Nothing here is built, sent or committed.**
>
> **Lead calls (`marketing-lead`, 2026-10-23):**
> - **Drift D1–D7 (§5) all go to the PRD's text,** including D6: one invite line everywhere ("Join me on Fleeced to find trades we both like → {url}"), with no league name, SMS included. The X line keeps its own wording. **The copy batch's three `m3` invite rows are aligned to D6 in the same pass** (`marketing-lead-copy.md`), so §6 D there and this block agree.
> - **Rewordings confirmed:**
>   - `gp.join.og_title`: "{leagueName}: trades built for both sides";
>   - `gp.join.valueprop`, intent form;
>   - `gp.join.desktop.qr_a11y`: "QR code: opens this invite on your iPhone" (already confirmed to `growth-pm`).
> - **Persona settled:** all 7 O5 rows read correctly in the assistant-GM register, with the ram as the face. No rewording was needed.
> - **This file is now the launch-slice authority for referral wording.** `marketing-lead-wave2.md` and the vendored `marketing-inputs.md` stay as the drafting record. `growth-pm` folds D4, D5, D6 and the `og_title`/`valueprop` text into the PRD, through `head-bizops` → `head-product`.

> `mkt-writer` for `marketing-lead`, 2026-10-23. This file packages the referral-loop strings for the operator's one-pass approval (PRD D-5). It's DRAFT. Nothing here is built, sent or committed.
> **Sources:**
> - `marketing-lead-wave2.md`: §A, the lab addendum, FR-25 and the `ux-lead` strings. It matches `docs/plans/referral-loop/marketing-inputs.md` @ `91f1cc29` except for the vendored header line.
> - PRD `docs/plans/referral-loop/prd.md` @ `91f1cc29`: J1–J2, §5, FR-3, FR-7, FR-18/19, FR-25, §12 launch slice, D-5.
> - The copy batch, `marketing-lead-copy.md` §0 items 2, 5 and 7, plus its `m3.*` / `m4.348.*` rows.
> - `legal-lead.md` R21 and R22.1/R22.5.
>
> **Decisions applied:**
> - Persona settled (operator, 2026-10-23): the assistant-GM register, with the ram as the face. Every O5 mark is cleared.
> - The iPhone install labels flip at release by `IOS_INSTALL_URL` host (R22.1/R22.5, PRD AC-7g).
> - "Fleeced" is never a sentence subject (§0.2).
> - Outcome → intent wherever the R21 #8 qualifier can't fit (§0.5).

## 1. Summary

**Launch slice**, as the PRD defines it (§12):
- the 11-06 binary strings (FR-3);
- the server strings that must be live for the 11-16/11-18 flips: the join landing (FR-7), the `/s/*` device CTA (FR-25) and the FR-18 join row;
- the TestFlight "What to Test" line (Phase 0, D-2).

| Bucket | Rows | By type |
|---|---|---|
| **All referral rows** (§A 75, lab addendum 7, OG lockup 1, `/s/*` iPhone note 1, `ux-lead` 8, PRD-only QR name 1) | **93** | name 14 · typo 3 · voice 8 · meaning 10 · new 35 · keep 21 · dropped 2 |
| **In the launch slice (#348)** | **33** | meaning 5 · new 23 · name 1 · typo 3 · keep 1 |
| → **need approval** (meaning + new) | **28 keys = 26 entries** below | Two keys only reuse another key's approved text: `h2.web.default` = `gp.invite.msg`, `s.cta.A_ios` = `gp.join.cta.A_ios`. One entry is contingent (`gp.join.iab_wayout`) |
| Ship by launch through the copy batch (name-only twins, no approval here) | 13 | name 13 |
| Keep, outside the launch slice | 20 | keep 20 |
| Later slice | 25 | new 12 · meaning 4 · voice 8 · parked 1 (`msg_league`, meaning) |
| Dropped or superseded | 2 | — |

## 2. OPERATOR APPROVAL

> **APPROVED by the operator 2026-10-23**, in `head-bizops`' session, relayed by `head-bizops`. Verbatim: "Approve all three as written: the App Store listing §5 (recommended subtitle "Your rankings. Deals for both."), the copy file §6 meaning changes, and the referral package §2 (26 entries)."
> All 26 entries are approved as written. That includes the contingent `gp.join.iab_wayout` (it ships only if checklist 4b fails) and the host-keyed install labels (they flip at release).

Approving this block approves the exact text below: every variant (by host or by fallback) and every fallback. Counts leave out `{vars}`. URLs run 84–92 characters.

Legal column:
- **A**: approved in R22.1, as this row or its `m3`/`m4` twin.
- **I**: intent form that R21 #8 / R22.1 approve; the row itself wasn't reviewed.
- **n/a**: no legal or data claim.

Overlaps with the copy batch §6: §6 A (store pair), §6 B (`og_desc`) and §6 D (invite messages) carry the same strings. **One approval covers both docs.** For §6 D, see drift D6 first.

### H1 entry
None. The launch only re-spells "league-mates" as "leaguemates" (typo, §3).

### H2 link / share text
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.invite.msg` (+ `h2.web.default` rides on it) | Mobile share sheet `InviteLeaguematesBanner.tsx:132`; web modal `app.js:5834` | `Join me on Fleeced to find trades we both like → {url}` | 49 + URL = 133–141 | Old name out. "find trades in {league}" becomes "trades we both like". **One line everywhere, with no league name** (PRD FR-3, J1) | A |
| `h2.web.sms` | Web SMS channel `app.js:6082` | `Join me on Fleeced to find trades we both like → {url}` | 49 + URL | Replaces "{league} fantasy trade finder — join me". Uses the standard line, not `msg_league` (D6) | A |
| `h2.web.x` | Web X channel `app.js:6086` | `Finding dynasty trades in {leagueName} on Fleeced. Join me → {url}` | 49 + name + URL | Drops the unverified @FantasyTradeFinder handle and "Come ruin the league with me" | A |

### H3a join landing: every device
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.join.headline` (FR-7 / FR-11 ladder) | Landing H1 | `{display name} invited you to {league}` → `{display name} invited you to their league` → `A leaguemate invited you to {league}` → `A leaguemate invited you` | 16+vars / 28+name / 28+league / 24 | New page. The name is resolved server-side from `t`, never read from the URL. Replaces "@{ref} invited you to Fleeced" | n/a (the R13/L9 disclosure is legal's own open item) |
| `gp.join.valueprop` | Value line under H1 | `Rank your players, then see trades built to work for both sides in {leagueName}.`; fallback `…in your league.` | 68+name / 79 | New line, **reworded in this pass**: "where both sides come out ahead" → intent (§0.5). The league name goes last | I |

### H3a join landing: iPhone (step list)
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.join.step1` | Step-1 heading | `Install Fleeced` | 15 | New | n/a |
| `gp.join.cta.A_ios` | Ice primary, by host | testflight: `Get the iOS beta` · apps.apple.com: `Get the iPhone app` | 16 / 18 | New. Flips on 11-18 when `IOS_INSTALL_URL` becomes the App Store URL. No date in code | A (`m4.348.cta_ios`; the timing is met by the host rule) |
| `gp.join.cta.A_ios_help` | Help under it, by host | `Installs through Apple's TestFlight app.` · `Opens the App Store.` | 40 / 20 | New; same flip | A (`m4.348.cta_ios_help`) |
| `gp.join.step2` | Step 2 (text, no link) | `Tap the invite again, or rescan its code, to join {leagueName}.`; fallback `…to join your league.` | 51+name / 62 | New. The re-tap credits by token | n/a |
| A2 note | `IOS_INSTALL_URL` unset or invalid: no button | `The iPhone beta isn't open to the public yet. Already have it? Tap the invite again, or rescan its code.` | 104 (the file says 101) | New. See U4 for after release | n/a |
| `gp.join.iab_wayout` **(contingent, checklist 4b)** | A1/A2 line for installed users | `Have the app and still seeing this page? Open this link in Safari, or tap it in Messages.`; if Safari doesn't hand off: `Have the app and still seeing this page? Tap the invite in Messages.` | 89 / 68 | Ships only if 4b fails. On A2 it replaces the note's last sentence | n/a |

### H3a join landing: desktop (`IOS_INSTALL_URL` set: QR primary; unset: web app primary)
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.join.desktop.qr_title` | TickLabel (renders in caps) | `Join on your iPhone` | 19 | New | n/a |
| `gp.join.desktop.qr_help` | Under the QR | `Scan with your iPhone camera. After installing, scan again to join.` | 67 | New | n/a |
| `gp.join.desktop.qr_a11y` | The QR's accessible name | `QR code: opens this invite on your iPhone` | 41 | **New, worded in this pass**. It adopts the PRD's example (D5) | n/a |
| `gp.join.desktop.ipad` | Ghost link in the QR block, by host | `On an iPad? Get the iOS beta, then tap the invite again.` · `On an iPad? Get the iPhone app, then tap the invite again.` | 56 / 58 | New. The store form adopts `growth-pm`'s placeholder verbatim (D4) | n/a (the flip is met by the host rule) |
| `gp.join.desktop.ext_lead` | Secondary-path line | `Have the Fleeced extension for Chrome or Edge?` | 46 | New | n/a |
| `gp.join.cta.A_desktop` | Button (secondary when set, primary when unset) | `Open the web app` | 16 | New | n/a |
| `gp.join.cta.A_desktop_help` | Help line, unset state. **Also reused on the `/s/*` desktop branch** | `Sign-in uses the Fleeced extension for Chrome or Edge.` | 54 | New | n/a |

### H3a join landing: Android and other phones
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.join.android_note` (= `m4.348.android_note`; also used on `/s/*`) | Note, no button | `Available on iPhone and desktop web for now.` | 44 | New. "Fleeced" is no longer the subject (§0.2) | n/a |

### H3a OG card and page head
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.join.page_title` | `<title>` | `{leagueName} on Fleeced: Dynasty Trade Finder`; fallback `Your league on Fleeced: Dynasty Trade Finder` | 33+name / 44 | New | n/a |
| `gp.join.og_title` | og:title | `{leagueName}: trades built for both sides`; fallback `Dynasty trades built for both sides` | 29+name (≤60, so names up to 31; AC-7b's 27-character cut still holds) / 35 | New, **reworded in this pass**: "trades that work for both sides" → intent, to match the `og_desc` under it (§0.5) | I |
| `gp.join.og_desc` (= `m3.web.og_desc`) | og:description | `Rank your players on Fleeced and see trades built to work for both sides. Works with Sleeper, ESPN and MFL.` | 107 | Outcome → intent. "Free." stays cut | A |
| OG lockup (lab answer 2) | Static 1200×630 card, under the `FLEECED.` logotype | `Dynasty Trade Finder` | 20 | New. Locked up, smaller, never standalone. The ice period belongs to the logotype only (D-15) | n/a |

### H3b / H4 / H5
None in the launch slice. The rewrites are in the later slice. See U2 for FR-11.

### H7 notifications
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.push.joined_inbox_body` | `referral_joined` bell row, body (FR-18) | `Once they rank, trades with them can use their board, not just consensus.` | 73 | New. Today the body repeats the title (AC-18) | n/a |

### S share landings (FR-25: `/s/p`, `/s/trade`)
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `/s/*` iPhone note | iPhone, `IOS_INSTALL_URL` unset or invalid: no button | `The iPhone beta isn't open to the public yet. Already have it? Open Fleeced.` | 76 | New. It promises the app, not the shared trade (GB-03) | n/a |

The iPhone set branch reuses the `gp.join.cta.A_ios` pair. The desktop branch keeps its labels and adds `gp.join.cta.A_desktop_help`. The Android branch reuses `gp.join.android_note`. None of these needs a separate approval.

### TestFlight "What to Test"
| key | surface | final text | chars | what changes | legal |
|---|---|---|---|---|---|
| `gp.testflight.what_to_test` | App Store Connect, beside TestFlight's Open button (the operator pastes it) | `Here from a league invite? After installing, go back and tap the invite again, or rescan its code. That opens the app on your invite.` | 133 | New. It goes on the 11-06 TestFlight build. App Store installs never see it | n/a |

## 3. Not needing approval (keys only)

- **Launch slice (#348), typo/name/keep/reuse:**
  - `h1.banner.title`, `h1.banner.a11y`, `h1.banner.body`: re-spelled "leaguemates" only (AC-3b);
  - `gp.push.joined_inbox_title`: name, A via `m3.push.joined`;
  - `gp.join.og_site`: keep;
  - `h2.web.default`: = `gp.invite.msg`;
  - `s.cta.A_ios`: = `gp.join.cta.A_ios` pair.
- **Ship by launch through the copy batch** (name twins, built once under #348):
  - `h1.web.members`, `h1.web.unlock`, `h3a.index_title`, `h6.web.logo`, `h6.web.rm_logo`;
  - `s0.image.mark`, `s0.trades.msg`, `s0.calc.cap`, `s0.inleague.cap`, `s0.proposal.sig`;
  - `s4.title`, `s4.brand`, `s4.og_footer`.
- **Keep:**
  - `h1.banner.btn`, `h1.proof`, `h1.cta`, `h1.progress`, `h1.bell_empty`, `h1.calc_note`, `h1.web.modal`;
  - `h2.web.sleeper`, `h3a.web.invited`, `h3b.join.loading`, `h3b.join.fail_cta`;
  - `h4.picker.notice`, `h4.picker.empty`, `h7.peer.push`, `h7.peer.inbox`, `h8`;
  - `s0.image.btn`, `s1.trade.cta`, `s2.pkg.cta`, `s3.tiers`.

## 4. Later slice (not in the 11-06 binary; not in this approval)

- **The FR-19 activation row** ("can wait until after launch", §12): `gp.inbox.activated_title`, `gp.inbox.activated_body`. The binary registers only the type. If `head-eng` lands the row by 11-16, approve these two with this block.
- **Phase 2:**
  - pushes and "Your invites": `gp.push.referral_title`, `gp.push.referral_body`, `gp.push.referral_inbox`;
  - lab §5 labels 1 and 2, the "Activated" explainer, the zero-join line and the empty-state prompt;
  - the OG variant (iii) line.
- **GB-02** (FR-25 keeps `og:*` unchanged): `s1.trade.title`, `s1.trade.desc`, `s2.pkg.title`, `s2.pkg.desc`, `s4.og_site`.
- **No build home in the PRD** (a later voice and claims pass):
  - `h1.card.tick`, `h1.rationale`, the `h1.banner.body` rewrite (D7);
  - `h2.web.chat`, `h2.web.groupme`, `h2.web.email`;
  - `h3b.join.fail`, `h5.signin.invite`, `h5.signin.invite_noref`.
- **Parked:** `gp.invite.msg_league` (D6).
- **Dropped:**
  - `gp.join.retap`, replaced by `gp.join.step2`;
  - `gp.join.cta.B`, because option B wasn't chosen.

## 5. Drift: marketing's file vs the PRD @ `91f1cc29` (7)

| # | key | marketing file | PRD | marketing recommends |
|---|---|---|---|---|
| D1 | `gp.join.og_desc` | "…see trades where both sides come out ahead. Works with…" (110) | "…see trades built to work for both sides. Works with…" (107) | **PRD** (copy batch §0.5; R22.1 approved) |
| D2 | `gp.join.android_note` (and the file's FR-25 Android row) | "Fleeced runs on iPhone and desktop web for now." | "Available on iPhone and desktop web for now." | **PRD** (§0.2, `m4.348.android_note`) |
| D3 | `gp.join.cta.A_ios` / `_help`, `s.cta.A_ios` | Beta pair only | Host-keyed: the beta pair, plus "Get the iPhone app" / "Opens the App Store." | **PRD** (= `m4.348.*`; the host rule satisfies R22.1/R22.5) |
| D4 | `gp.join.desktop.ipad` | Beta form only | Adds the store form "On an iPad? Get the iPhone app, then tap the invite again." (a placeholder, pending marketing) | **Adopt the placeholder verbatim** (58) |
| D5 | QR accessible name | No row | Example: "QR code: opens this invite on your iPhone" (words pending marketing) | **Adopt verbatim** as `gp.join.desktop.qr_a11y` (41) |
| D6 | Invite message, league name or not | The file's §A Notes, `h2.web.default` and `h2.web.sms` use `msg_league` when a name is known. The copy batch's `m3.invite.msg`, `m3.app.invite_msg` and `m3.app.invite_sms` do the same. Only the file's §0.1 says "default: no league name" | FR-3 and J1: `gp.invite.msg`, with no league name, on mobile and web | **PRD**, on every channel including SMS. The X line keeps its own wording. It fits in about 140 characters with the token URL, the recipient is already in the league, and the landing names it. `marketing-lead` aligns the three `m3` rows before §6 D is approved. Both forms are legal-approved (R22.1), so legal doesn't need to review again |
| D7 | `h1.banner.body` | A rewrite: "These trades use consensus values. Mutual matches start once one leaguemate ranks." | FR-3: a spelling-only change in this build | **PRD for 11-06** (re-spell only). The rewrite moves to the later slice |

Count nits, not drift: A2 measures 104 (the file says 101). The iPad beta line measures 56 (the file says 55).

## 6. Rewordings in this pass, O5 check, unresolved

**Reworded here** (worker drafts; `marketing-lead` to confirm):
- `gp.join.og_title`, launch. Outcome → intent: "trades built for both sides". The R21 #8 qualifier can't fit in a preview, and the old form sat above an `og_desc` that is already intent. The name budget stays at 27 or more.
- `gp.join.valueprop`, launch. Intent form, with the league name last.
- `gp.join.desktop.qr_a11y`, launch. Worded.
- `h2.web.chat`, later. "Been using Fleeced for {leagueName}. It finds trades…" makes Fleeced the subject through "It", and it states an outcome. The fix, for when it gets a build home: `Been using Fleeced for {leagueName} to find trades built to work for both sides. Join me → {url}` (79 + name + URL).
- OG variant (iii) line, later. `Trades built for both sides` (27).

**"Fleeced" as subject:** after D2 and the `h2.web.chat` fix, no referral row has it. "Install Fleeced", "Open Fleeced", "on Fleeced" and "the Fleeced extension" are objects or modifiers.

**O5:** I re-read all 7 O5 rows in the assistant-GM register:
- `gp.join.headline` (now the ladder);
- `gp.join.valueprop`;
- `gp.push.joined_inbox_body`;
- `gp.push.referral_body`;
- `h1.banner.body`;
- `h1.rationale`;
- `h1.bell_empty`.

None is first person. None speaks as the ram. None says "I'm Fleeced". **All marks are cleared, and no row needed rewording for persona.** The `valueprop` edit comes from §0.5, not from the persona.

**Unresolved:**
- **U1:** the J4 league-switch confirmation (R-F4) has no words yet. It's contingent: I'll draft it only if checklist step 7b fails.
- **U2, FR-11 isn't in §12's binary row.** That row lists FR-1/2/10/12/13. Without FR-11, a token-only link shows SignIn's shipped no-inviter line, "You were invited to {league} — sign in and we'll take you straight there." If FR-11 makes the 11-06 binary, it reuses the ladder approved above. → `growth-pm` / `head-eng`.
- **U3, §12 doesn't name FR-18.** I placed it in the launch slice, since it rides on attribution, target 11-16. If it slips, the shipped row ("…joined Fantasy Trade Finder via your invite.", said twice) carries the old name at launch, unless `m3.push.joined` lands through the copy batch. → `growth-pm`.
- **U4, beta-era unset notes after release.** From 11-18, an unset or invalid `IOS_INSTALL_URL` shows "The iPhone beta isn't open to the public yet", which is false once the app is released. Today that's only a config error, logged once. Recommendation: on release day, check that the host is `apps.apple.com`, and later add a store-era unset note. Not a blocker. → `growth-pm`, `release-lead`.
- **U5:** `gp.join.iab_wayout` depends on checklist 4b. `gp.inbox.activated_body` is tied to the "They're interested" pill label (`TradeCard.tsx:525`).

**Blockers:** none for approval. D6 needs `marketing-lead` to align the copy batch's `m3` invite rows before the operator signs §6 D.

## Claims audit (launch strings)

| claim | source |
|---|---|
| "built to work for both sides" | Intent form, R21 #8 and R22.1 (`m3.web.og_desc` and `m3.web.mobile_sub` approved) |
| "Works with Sleeper, ESPN and MFL" | `config/features.json` `espn.link` and `mfl.link`; R21 #1. Web sign-in is Sleeper and extension only, which the desktop help line states |
| "Get the iPhone app" / "Opens the App Store." | True only from release. AC-7g's host rule; R22.5 |
| "Installs through Apple's TestFlight app." / "rescan its code" / "scan again to join" | **Assumed** Apple behavior, until checklist steps 4b, 11b and 15b run |
| "Once they rank, trades with them can use their board" | The divergence engine needs a ranked counterparty. The "can" hedge is from D-052 |
| "isn't open to the public yet" | True only while the URL is unset before release (U4) |
| "{display name} invited you" | Resolved server-side from `t` (FR-11, §8.2). Never URL-supplied |

## Handoffs

- **`marketing-lead`:** confirm the rewordings and D4–D6; align the `m3` invite rows; route this block → `head-bizops` → the operator.
- **`growth-pm`:**
  - fold D4, D5, D6 and the `og_title`/`valueprop` text into the PRD;
  - answer U2, U3 and U4.
- **`head-eng`:** FR-11's binary scope (U2).
- **`legal-lead`:** nothing new on words. The ladder's inviter name rides on R13/L9.
