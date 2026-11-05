# Mode: loop audit

**Use when:** before any PRD that changes a loop; when the operator asks "does the
referral loop work?"; once per season before the ramp; when a loop's numbers look wrong.
**Output:** `docs/business/product/YYYY-MM-DD-loop-audit-<slug>.md`, plus new or updated
rows in `growth-backlog.md`.

Break points get found by accident today (every `/s/*` CTA lands on `/`; invite events
missing on some surfaces). This mode finds them on purpose, hop by hop.

## The hop model

Every loop is seven hops. A loop is only as good as its weakest early hop, because a
break zeroes everything downstream.

| Hop | Question |
|---|---|
| H1 Actor acts | What does the user do, on which surfaces? |
| H2 Artifact leaves | What leaves the app (link, image, platform offer, text) and through what channel? |
| H3 Non-user sees | What does the recipient see before tapping: unfurl, OG card, message text, brand? |
| H4 Opens | Where does the tap land: app (universal link), Safari, web landing? Per install state |
| H5 Installs / joins | Can they get the app, or join without it? Is attribution (`ref`) carried? |
| H6 First value | Do they reach board usable / a first trade suggestion, and in which league? |
| H7 Sharer told | Does the sharer learn it worked (bell row, push), and does that prompt another share? |

## Live loops at the 2026-10-15 snapshot

Re-derive from `growth-surface.md` §1 before auditing. Seeds:
- **L1 Invite → join (referral):** invite CTA (League card, Trades banner, Matches empty,
  members overlay, bell empty state) → `shareInvite` → link (`/?league=&ref=`, or
  `/app/league/join/<id>?ref=` once `growth.invite_join_link` is on) → app via AASA, or
  Safari → web landing → sign-in → league pinned → first value → `referral_joined` bell row.
- **L2 Trade share → landing:** share → `POST /api/share/package` → `/s/p/<id>` → unfurl →
  open → CTA → `/` → ?
- **L3 Send-to-league:** offer sent in Sleeper/ESPN/MFL → leaguemate sees it inside their
  platform → is there any path back to the app?
- **L4 Rating prompt → store:** dormant until a public listing exists.

Not candidates unless the operator reverses a decision: tier-board share (D-039, OFF is the
resting state), public profiles (`profiles.public_pages` off).

## Procedure

1. **Pin the sha.** `git fetch origin`; run the commands in `growth-surface.md` §1 and
   keep the output.
2. **Write the hop list** for each loop in scope before dispatching anyone, so workers
   trace your model rather than invent one.
3. **Dispatch read-only `Explore` workers**, one per loop (or per platform when branches
   differ). Use the brief below. Workers trace; they don't judge.
4. **Spot-check.** Re-open the cited lines yourself for every hop a worker marks broken
   or uncertain. A claim you didn't check is labeled `worker-reported` in the output.
5. **Judge each hop:** `works`, `leaks` (works with loss you can name), `breaks`, or
   `unmeasured` (may work; no event can tell). Judgment is yours, not the worker's.
6. **Ask for numbers.** For each measurable transition, send `analytics-lead` the query
   you need (events, window, cohort) through `head-product`, or directly where the operator
   has approved a route. Never estimate a rate yourself.
7. **Frame K** (below), label every term.
8. **Rank the breaks** by downstream cost and cost to fix; each becomes or updates a
   `growth-backlog.md` row with an owner seam (seam rule in SKILL.md).

### Worker brief (paste and fill)

```
Read-only trace. Repo: <worktree path>, origin/main <sha>. Search with `git grep -n`
only; never edit, never run the app, no simulator.
Loop: <name>. Hops: <H1..H7 as written in step 2>.
For EACH hop return:
- file:line of the code that makes the hop happen (all clients: mobile/src, web/, backend/server.py)
- the analytics event that fires there: name + emitter file:line, or "GAP"
  (check backend/analytics_taxonomy.py registration; an unregistered name is dropped silently)
- every flag that gates it, with its value from config/features.json at this sha
- branches: platform (Sleeper/ESPN/MFL), auth state, app installed vs not, flag on vs off
- anything you're unsure of, marked UNCERTAIN
Return a table, then a list of UNCERTAIN items. No recommendations.
```

## K-factor framing

`K = i × c`
- `i` = invites (or shares) sent per active user per period.
- `c` = share of those that become an **activated** new user:
  `c = p(H4 open | sent) × p(H5 join | open) × p(H6 activated | joined)`.

Notes that keep the math honest here:
- A league caps `i`: at most ~9–11 leaguemates, minus those already joined. Spread past
  one league happens only when a new user brings their other leagues.
- `K < 1` still matters: each acquired user brings `1/(1−K)` users in total, so a K of
  0.3 multiplies every other channel by ~1.4.
- Report counts with their denominators, not just rates. At beta scale a rate on n<30
  is a description, not a result.

**What "measured" requires for each term** (otherwise label it `assumed`):

| Term | Needs | Known gaps to check at your sha |
|---|---|---|
| `i` | `invite_shared` on **every** invite surface (mobile and web) ÷ active users | Web invite paths emit no `invite_*` event; confirm League-tab coverage |
| `p(open)` | `invite_link_opened` ÷ `invite_shared` | Only app-side opens are evented; Safari → web landing opens may be invisible |
| `p(join)` | new users with `users.invited_by` set ÷ opens | `invited_by` is set on first insert only; `ref` is omitted when the username is unknown |
| `p(activated)` | invited cohort reaching the funnel's activation stage | Cohort query via `analytics-lead` |
| K in-product | `/api/invite/impact` | `invite.k_factor_dashboard` is off (zeroed payload) |

A measured number cites query, source (prod via `analytics-lead` under the operator's
read grant), time window and n.

## Output format

```markdown
# Loop audit — <loop(s)> — YYYY-MM-DD

**Sha:** origin/main <sha> · **Workers:** <n> Explore (briefs inline below) ·
**Spot-checked:** <hops> · **Worker-reported only:** <hops>

## Loop map: <loop name>
| Hop | What happens | Code (file:line) | Event (emitter file:line) or GAP | Flag (value) | Verdict |
|---|---|---|---|---|---|
| H1 Actor acts | | | | | |
| H2 Artifact leaves | | | | | |
| H3 Non-user sees | | | | | |
| H4 Opens | | | | | |
| H5 Installs / joins | | | | | |
| H6 First value | | | | | |
| H7 Sharer told | | | | | |

## K-factor read
i = … (label) · c = … × … × … (each labeled) · K = … · unmeasurable terms and why

## Breaks, ranked
| Rank | Loop / hop | Break | Downstream cost | Fix: decides / builds / words | Backlog row |
|---|---|---|---|---|---|

## Non-user view
(link the checklist run, `non-user-view.md`, for any H3/H4 surface in scope)

## Decisions needed
## Handoffs
```
