# Retired skill workspaces — 2026-08-08

Five role skills retired as part of the context-overload remediation pass:

- `legal-privacy`
- `ux-design`
- `ux-research`
- `fin-budget`
- `fin-forecast`

## Rationale

All five are memo-producing roles with **zero deliverables since creation on
2026-07-18**. Their expected output directories were never even created:
`docs/business/design/` and `docs/business/legal/` do not exist in the repo.
A month-plus of the role suite being live produced no artifacts from these
five, while the other 30 role skills did. Keeping unused, description-heavy
skills in `.claude/skills/` costs context budget on every session without
offsetting value, so they were moved out of the active skill set rather than
deleted outright.

## Restore

If one of these roles is needed again:

```
mv archive/skill-workspaces/retired-2026-08-08/<skill-name> .claude/skills/<skill-name>
```

then re-verify the SKILL.md frontmatter still parses and the skill still
triggers as expected before relying on it.
