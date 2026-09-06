# Status — replace with initiative or feedback item name

```project-status
{
  "status": "needs-review",
  "updated": "",
  "summary": "A concise description of the initiative or item, at most 240 characters.",
  "evidence": "Link the scope, canonical item, PR, release record, or review needed to establish this status."
}
```

Copy this file into an initiative/item folder as `status.md`. Flat Markdown plans
carry this block in the plan itself. Keep exactly one block and update it; other
documents link here rather than maintaining another current status.

`updated` is the known date this status became true (`YYYY-MM-DD`), or an empty string
when unknown. It is not the last file-edit date. `evidence` preserves qualifications,
covered feedback IDs, and the canonical folder for a shared fix. Do not paste secrets
or user data into the status source.

| Status | Meaning |
|---|---|
| planned | Spec exists; implementation has not begun |
| active | Current initiative in planning or discovery |
| in-progress | Implementation or validation is underway |
| built-unmerged | Implementation exists; merge is not complete |
| built-dark | Merged implementation is behind a disabled gate |
| partly-shipped | Only part of the scope/platforms has shipped; name the remainder |
| shipped | Scope reached users; cite release evidence and any QA limitation |
| blocked | A named dependency prevents progress |
| deferred | Intentionally postponed; record the revisit trigger |
| superseded | Replaced by named work or a decision |
| abandoned | Intentionally stopped; record the decision |
| declined | Owner declined the requested work |
| reference | Research/evidence, with no implementation claim |
| needs-review | Missing or conflicting evidence prevents a reliable disposition |

Never turn "built", "complete", a flag value, or an old index row into new shipment
proof. Preserve the old claim and use `needs-review` until it is reconciled. For
shipped/built/superseded/abandoned/declined states, provide a concrete evidence reference.

Regenerate with `python3 scripts/project_hygiene.py --write`, then validate with
`python3 scripts/project_hygiene.py --check`. Both commands run from the repository
root and require only Python's standard library.
