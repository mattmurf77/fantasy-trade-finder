# OG cards (static, 1200×630)

| File | What | Served as |
|---|---|---|
| `og-invite-1200x630.png` | Invite card: `FLEECED.` logotype + `Dynasty Trade Finder`, ram box (variant ii) | `/img/og-invite.png`, the join landing's `og:image` |
| `og-trade-expired-1200x630.png` | Expired trade link: `FLEECED.` + `This trade link has expired.` | The P29 `/s/trade` miss image |

**Approved strings.** `Dynasty Trade Finder` is marketing's OG lockup: under the logotype, smaller, never standalone (`docs/plans/org-bringup/leads/marketing-lead-referral-approval.md:110`). `This trade link has expired.` is `p29.og_line`, one Archivo line at ≥48px (`docs/plans/org-bringup/leads/marketing-lead-copy.md:192`). The logotype's ice period is the only ice on either card (D-15). The line's trailing period is chalk-dim.

**Type.** Logotype: Barlow Condensed 700, 148px. Invite line: Archivo 600, 52px. Expired line: 48px, because at 50px and 52px it runs into the 48px (`xxxl`) gutter beside the ram box. Ram: `mobile/assets/mascot/ram/neutral@3x.png` at its native 288×288.

**Re-render.** `python3 -I docs/design/og/source/render.py` (headless Chrome, offline; `CHROME=` overrides the path). `source/og.html?card=invite|expired` is the template, and `source/fonts/` holds the vendored OFL TTFs with their licence texts.

**Checks.** `render.py` asserts that both fonts loaded, that the line stays on one line outside the gutter, that nothing reaches the rule, and that the output is 1200×630 RGB with an `#0C0E11` corner. It writes an sRGB chunk. By hand: `sips -g pixelWidth -g pixelHeight -g hasAlpha -g space` (1200, 630, `no`, RGB), read a ~300px-wide thumbnail, and sweep `source/` for banned styles (see `CLAUDE.md` UI rules).
