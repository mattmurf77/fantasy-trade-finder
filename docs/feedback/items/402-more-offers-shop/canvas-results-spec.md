# Canvas-results spec — found ideas present in the calculator (operator, 2026-08-28 late)

> Operator: *"Present the found trade ideas directly in the calculator section
> where users can add players."* Multiple-choice rulings, same session:
> **(1) Deck hidden — the canvas IS the results surface** while browsing;
> clearing results returns the merged page to canvas-only.
> **(2) The ✕ keeps the current find-a-trade decline flow**: top-level reason,
> then bottom-level reason, treated as a pass — the existing two-layer
> `feedback.decline_reasons` capture, verbatim semantics.
> **(3) Edits stick to their idea while browsing**; ✓ queues the edited
> version; clearing results discards the working set.
> Ships as v1.16.11. This spec is the contract; where silent, rev-2/rev-3
> conventions apply (Chalkline, flag hygiene, suite style, sabotage, gates).

## 1. Scope and flag

- Merged guided landing only (`calc.inline_home` path, `canvasHost==='flag'`).
  Team-/player-mode decks, the pushed Real-values page, the shop window, and
  the #270 experiment path are untouched.
- New flag **`calc.canvas_results`**, shipped **true** (operator cadence;
  old clients carry no code reading it — live only from the next build).
  OFF ⇒ byte-identical to v1.16.10: the deck renders below the canvas as
  today. Kill switch: this key alone. Registered in all four places
  (features.json + FLAG_KEYS + three fixtures) with a house-style comment.
  Prerequisites named: `calc.inline_home` + `calc.merged_layout`.

## 2. The browse session

- Both search paths feed it: the D-153 fair sweep (synchronous ideas) and
  the empty-canvas model job (async — its progress state renders where the
  results will, in the canvas section, using the existing progress
  vocabulary; never a bare spinner).
- Results become a **browse session**: an ordered working set of ideas.
  The canvas renders the current idea as an **editable prefill** — the #287
  `FeaturedTradeWindow` technique (initialOpponentId/GiveIds/ReceiveIds,
  remount per idea via its key), generalized.
- **Pager**: ‹ › steps + a chalk-dim `1 / X` TickLabel adjacent to the
  canvas header. Paging emits nothing (browsing is not judging). Reaching
  either end stops; never wraps.
- **The deck does not render while a browse session exists.** With no
  session (cleared, or before any search), the merged page is canvas-only —
  under this flag the deck retires from this page. Likes-you delivery
  remains on Matches (ruled). The end-of-deck exits, lane filter, and
  deck-only chrome do not render under the flag; their code stays intact
  for flag-off.
- **Clear**: the existing anchor-receipt Clear (fair path) and a matching
  control for model-path sessions end the session and restore the blank
  canvas. State dies with the session (edits included, ruled).
- League switch / regenerate / flag-kill all end the session (the rev-3
  state-hygiene rule: browse state dies with its context).

## 3. Per-idea state (ruling 3)

- A per-idea edit map keyed by the idea's stable key: when the user edits
  the canvas (add/remove players, change partner is NOT part of an idea —
  the partner is the idea's counterparty and stays fixed while that idea is
  shown), the host snapshots {giveIds, receiveIds} for that key; paging
  back remounts with the edited version. Mechanism: a new optional
  `onSidesChange` (or equivalent minimal) callback on `InLeagueCalculator`
  — additive, undefined for every existing host, byte-identical when
  absent. The component still owns its state after mount; the host only
  listens.
- ✓ queues whatever the canvas currently holds (the edited version) via
  the existing D-152 path — idempotent, refusal copy, Elo moves. After a
  successful queue the session stays on the idea (the shop-window rule:
  the pager navigates; actions don't navigate).

## 4. The ✕ — decline reasons, verbatim semantics (ruling 2)

- A ✕ control on the browsed idea (placement: with the pager, never inside
  the action row's 50/30/20 cells — that row's proportions are D-157 and
  unchanged). Tapping it opens the existing two-layer decline-reason
  capture — the same overlay presentation the calculator-origin deck
  already uses (`trade_pass_overlay_*`), the same layer-1 tiles, layer-2
  detail, and free text, wired to the same `/api/trades/pass-reason`
  semantics (`pass_reason_elo_suppression` honored — Elo only on the
  answers that write it today).
- On completion the idea is passed: it leaves the working set, `X`
  decrements, the session advances to the next idea (or the honest empty
  state if none remain). The existing banked-pass/undo semantics of the
  reason flow apply unchanged; if the reason capture is dismissed without
  answering, whatever today's deck does in that case happens here — match
  it exactly and state it in a comment.
- The pass writes the same server state as a deck pass (decision row,
  D-067 cooldown), so a passed idea never reappears in later sessions.

## 5. Honest empties (and the audit-Q5 latent bug dies here)

- Fair sweep returns zero ideas ⇒ the canvas-results area shows the honest
  zero copy ("no fair package for this canvas…"), NEVER the "Hit Find a
  Trade to start" idle card (the 2026-08-27 audit flagged exactly this
  fall-through as a latent bug — this feature must fix it, not inherit it).
- Model path zero ⇒ its existing zero copy, rendered in the results area.
- Session exhausted by passes ⇒ "You've been through every idea" + the
  Find a Trade cell as the restart (no dead ends).

## 6. Evidence

- Structural suite: new `mobile/tests/check-canvas-results.js` (or a
  section in check-inline-home.js — builder picks per file scope, says
  why): flag registered 4 places; deck absent under flag+session and
  present flag-off (byte-identical mount); pager emits no analytics;
  ✕ routes through the existing reason machinery (no parallel pass path);
  per-idea edit map exists and dies with the session; the Q5 empty-state
  fix pinned; `onSidesChange` optional-and-absent for existing hosts.
- Analytics: reuse existing events wherever they fire naturally
  (find_trades_tapped, calc_trade_queued, trade_pass_overlay_*,
  pass-reason events). New events ONLY if an existing one genuinely cannot
  carry the meaning — and then registered same-commit, INTENT-classified
  deliberately.
- TestFlight checklist section appended to the item checklist (browse,
  edit-stick, ✕-reason flow, empties, flag-off deck-restored).
- Sabotage ≥4; full gates (tsc, all suites, testid-lint, features.json
  valid, backend pytest untouched-proof or subset if taxonomy touched).

## 7. Ship posture

Build + two-reviewer QA + fixes on branch `feat/canvas-results`; PR opens
after gates but **merges only on the operator's word** (no standing ship
order covers this feature).
