# Mode: non-user view

**Use when:** before any PRD, or any review you give, that touches a page or message
whose audience is a non-user or a not-yet-joined leaguemate: `/s/*` share landings, OG
cards, invite links and invite text, `LeagueJoin`, the web landing, `referral_joined`
and invite-joined pushes, anything that leaves the app. Also as hops H3–H5 of a loop audit.
**Output:** a filled checklist, either inline in the memo/PRD or as
`docs/business/product/YYYY-MM-DD-non-user-view-<slug>.md`.

Generic web audits measure speed and accessibility. This checklist asks one question:
**a stranger got this link from a leaguemate; what do they see, and can they act on it?**

## How to run it

1. Pin the sha. Find the surface's code with the `growth-surface.md` §1 commands (the
   `cta_url=` / `image_url=` grep shows every `/s/*` CTA at once).
2. Read the code path, not a recollection of it. Per D-039: whether a surface is gated
   is answered by reading the route, not by remembering which flag was flipped.
3. Where runtime matters (the unfurl in iMessage, a universal link opening the app),
   write the manual TestFlight / device steps for the operator; don't claim it from code.
4. Fill every row. "Unknown" is allowed if you say what would settle it.

## Checklist

| # | Check | What "pass" looks like | Evidence (file:line, or the operator step that proves it) |
|---|---|---|---|
| 1 | **OG title** | Says what this is, in words a stranger understands, and uses the shipped name | |
| 2 | **OG image** | Renders (not the placeholder card); `og:image` is an **absolute** URL; 1200×630 | |
| 3 | **OG description** | One line that gives the reason to tap | |
| 4 | **Unfurl actually renders** | Robots and crawler rules let the unfurlers fetch the page and image (`robots.txt` disallows `/s/` and `/og/` at the snapshot); confirm with each platform's card validator or a device test | |
| 5 | **CTA text** | Names the next action the non-user can take | |
| 6 | **CTA target** | Goes somewhere that converts: App Store / public TestFlight, or a web path that lets them act. `/` with only a "request access" form is a dead end. Before a public listing exists, the target is an operator decision | |
| 7 | **Act without installing?** | Can a non-user get any value (see the trade, join the league, rank) on web first, within D-173's Companion posture? If not, say so | |
| 8 | **Install state branches** | App installed → universal link opens the right screen (AASA claims the path); not installed → Safari path still converts | |
| 9 | **Attribution carried** | `ref` (or the league id) survives every redirect and lands in `users.invited_by`; what happens when `ref` is absent | |
| 10 | **Events** | Every hop on this surface fires a registered event, or the gap is named | |
| 11 | **Indexing intent** | Deliberate: `noindex` / `Disallow` / sitemap entry match the intent (thin per-user pages stay out of the index; an acquisition page meant to rank is in it). SEO calls belong to `marketing-lead` (`mkt-seo`) | |
| 12 | **Privacy** | Nothing private is exposed to an unauthenticated viewer (league names only from public platform APIs; no username enumeration via guessable URLs) | |
| 13 | **Words owner** | Every string a non-user reads is assigned to `marketing-lead`; you specify the job of the words, not the final words | |
| 14 | **Shipped name (D-057)** | Copy says **Fleeced: Dynasty Trade Finder** (or the approved short form), not "Fantasy Trade Finder" / "Dynasty Trade Finder" / "DTF" | |
| 15 | **Visual system** | Page follows Chalkline (`docs/design/design-system.md`): no gradients, blur, system font stacks, radius over 8px except specced pills. Review goes to `design-lead` | |
| 16 | **Spam test** | A leaguemate receiving it twice in a week would not feel spammed; frequency caps stated | |

## Output format

```markdown
## Non-user view — <surface> — YYYY-MM-DD (origin/main <sha>)
| # | Check | Verdict (pass / fail / unknown) | Evidence |
|---|---|---|---|
...
**Fails, ranked:** 1. … (decides `growth-pm`; builds `engagement-eng` | `onboarding-eng`; words `marketing-lead`)
**Operator checks needed:** numbered device / TestFlight steps with expected results
```
