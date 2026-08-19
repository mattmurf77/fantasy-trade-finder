# HLD delta — "Avoiding" positions (#360 / #361)

**n/a because** there is no architecture shift: no new module, no new client, no
new route, no new data flow — one additive column, one feature flag, and one
predicate threaded through call signatures that already carry its two siblings
on adjacent lines. The entire delta is low-level and lives in
[`lld-delta.md`](lld-delta.md).

---

That is the whole answer. The rest of this file exists so the "n/a" is
falsifiable rather than asserted, per the CLAUDE.md rule that a docs row is
answered or explicitly waived with a reason.

**What an architecture shift would have looked like here, and why none of it
happened.** The design was chosen partly *because* it is architecturally inert
(`prd.md` D-093):

| Would have been an HLD change | Did it happen? |
|---|---|
| A new generator path, or a new stage in an existing one | **No.** The filter lands inside four existing receive-pool constructions. |
| A new scoring term, `model_config` knob, or tuning surface | **No** — and this is the direct dividend of choosing a hard pool exclusion over reviving the dormant `pos_conflict_penalty` multiplier. A soft multiplier *would* have been an HLD-level change: it re-introduces a retired scoring architecture, adds a knob to calibrate, and edits the knob-inventory golden. |
| A new route, or a change to an existing route's shape | **No.** `/api/league/preferences` gains one additive array field on GET and POST. No route added, renamed, or removed; no response restructured. |
| A new persistence surface | **No.** One column on an existing table, via the existing additive-`ALTER` mechanism in `_migrate_db()`. |
| A new client, or a new screen | **No.** One row inside an existing sheet, on the one live client. |
| A change in *where* a rule is enforced (a new enforcement layer) | **No.** Receive-side exclusion at pool construction is an existing, shipped pattern — #163 `not_interested` is the same mechanism at player granularity, and this feature is deliberately modeled on it seam for seam. |

**The one genuinely architectural statement this feature makes** is a
*convention*, not a structure, which is why it belongs in
`living-memory/LLD.md` and not `HLD.md`:

> Negative receive constraints are applied at pool construction, never as a
> package gate — which is what makes them structurally un-relaxable by the #189
> relaxed pass. Positions (#360) join players (#163) under that rule.

That line is the LLD update named in `scope.md` §4. `living-memory/HLD.md` and
`docs/architecture.md` are both correctly untouched.
