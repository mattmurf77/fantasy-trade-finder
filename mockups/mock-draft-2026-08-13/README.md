# Mock Draft Lab — 2026-08-13 (#295 / #296 / #305)

Mockups for the mock-draft repair + manual-draft-for-all-teams build. House
convention (`mockups/polish-lab-2026-08/`): today's screen beside the proposal
in 390px phone frames, rationale below, all assets inline, real captures
embedded from `../../screens/mobile/mock-draft/`. Master viewer:
[`index.html`](index.html) — **link-only** (no iframes; works over `file://`).

Binding docs: `docs/feedback/items/295-mock-user-not-in-draft/`
(`plan` / `hld` / `lld`, all 2026-08-13). Copy on every new surface is the
LLD's placeholder and is flagged `PRD COPY` on the frames — the PRD owns final
wording.

**Reconstruction labeling (house rule):** the shipped mock has never shown a
live-league user on the clock (#295's defect), so every user-turn frame is a
reconstruction of a never-shipped state and is tagged as such. The one real
on-the-clock capture (`active--on-the-clock.png`) comes from the hermetic
capture harness (`draft-pre` profile, 2026-08-11), whose seeded world reaches
the state live sessions cannot — embedded as visual reference, labeled for
what it is.

| Page | Deliverable | What it shows |
|---|---|---|
| [`setup-mode-toggle.html`](setup-mode-toggle.html) | Mode toggle (LLD §1.6/§3.2) | Capture of the shipped sheet + two proposals: `mock-setup.mode.cpu`/`.manual` segmented control below Pick order (TypeSeg verbatim, CPU default per plan §10 Q2), mode-dependent footnote branch. Notes a segment-label length budget for the PRD |
| [`on-the-clock-cpu.html`](on-the-clock-cpu.html) | CPU-mode user turn (never-existed state) | Harness capture as reference + reconstruction of post-repair live ffv3: 12-team rail, operator slot 8, clock at 1.08, `pick 8 of 48` (teams-from-order visible), Pick affordances live; the M-1 Maestro assertion annotated |
| [`manual-picking-for.html`](manual-picking-for.html) | Manual clock variant (LLD §3.4) | On-behalf turn: chalk headline "You're picking for {team}" + `mock-draft.clock.picking-for` sub-line + "{team}'s pick" confirm meta — vs the byte-identical own-slot turn (flare). Reports the ticker who-column "—" finding |
| [`blocked-user-not-in-draft.html`](blocked-user-not-in-draft.html) | Blocked entry (LLD §1.6/§3.3) | Seventh `mockBlock` arm (`mock-entry.blocked.user_not_in_draft`, muted card, dead CTA states the condition, disabled pre-POST via GET `capability`) + the session screen's `mock-draft.empty.user_not_in_draft` typed-empty. No timeline promises |
| [`recap-manual-mode.html`](recap-manual-mode.html) | Manual recap (HLD §4.3, don't-get-wrong c) | "Your draft" = the user's team's 4 picks while all 48 are `by: "user"`; round rail names every team incl. the user's tinted row. Zero layout change is the point — the frame pins the `picked_by_user_id` keying |

## Traced vs reconstructed

- **Real captures embedded:** `setup-sheet.png`, `entry--card.png`,
  `empty--no-active-mock.png`, `active--on-the-clock.png` (all 2026-08-11,
  hermetic harness — see `screens/manifest.json`).
- **Reconstructions (state has never existed):** every post-repair user-turn
  frame, both manual-mode frames, the manual recap, and both
  `user_not_in_draft` frames. Chrome is traced from the captures; only data
  and the specced deltas differ. Leaguemate handles and pick order are
  illustrative; player names are the harness rookie class.
- **Coverage gaps found:** no capture exists for any of the six shipped
  blocked-entry arms, nor for the recap (complete) state.
