---
name: living-memory-format-check
description: Audits files in the `living-memory/` folder against the FORMAT.md spec. Detects missing TOCs, stale TOC entries, missing required sections, ID-sequence gaps, non-ISO dates, and broken cross-references. Reports drift in a single table and offers per-file fixes — never auto-edits without approval. Trigger by saying "check living memory format", "audit living-memory files", "verify format compliance", or "fix format drift". Also runs after major living-memory updates as a hygiene pass.
---

# Living-Memory Format Check — Fantasy Trade Finder

You are auditing the project's `living-memory/` folder against [`living-memory/FORMAT.md`](../../../living-memory/FORMAT.md) (the project-local spec). The workspace canonical reference is at `/Users/teresadickens/Documents/Claude/Projects/Master Claude Code Best Practices/FORMAT.md`.

## Inputs
- The user's invocation message (may specify a single file with `--file <name>` or scope `--strict`/`--standard`).
- The current working directory should be the project root (`living-memory/` resolves directly).

## Process

### Step 1 — Scope
List all `.md` files in `living-memory/`. EXCLUDE:
- `README.md` (folder introduction — not a memory file)
- `FORMAT.md` (this spec itself)

If the user passed `--file <name>`, restrict to that file only.

### Step 2 — Per-file audit
For each in-scope file, check in this order:

#### 2.1 — Universal header
- [ ] File begins with `# <FileName> — Fantasy Trade Finder` H1 line.
- [ ] H1 filename matches the actual filename (case-sensitive).
- [ ] H1 includes the `— Fantasy Trade Finder` suffix.
- [ ] Next non-blank content is a blockquote with these labels (all required): `**Purpose:**`, `**Read at:**`, `**Write at:**`.
- [ ] Blockquote includes a `Companion files:` line (may say "none").
- [ ] After the blockquote, a `---` horizontal rule.
- [ ] Next is `## Table of Contents`.
- [ ] TOC contains bulleted markdown-link entries.
- [ ] After the TOC, another `---` horizontal rule before the first content section.

#### 2.2 — TOC integrity
- [ ] Extract every `## ` line in the file EXCLUDING:
  - The TOC heading itself.
  - Any `## ` line that appears inside a fenced code block (between triple-backticks).
- [ ] Compare extracted H2s to the TOC entries. Flag mismatches:
  - **Missing entries** (H2 exists but no TOC line)
  - **Stale entries** (TOC line exists but no matching H2)
  - **Order mismatch** (TOC order ≠ document order)
- [ ] Verify each TOC anchor link is well-formed (lowercase, hyphenated, no special chars beyond `-` and `_`).

#### 2.3 — Per-file required sections
Look up the file in [`../../../living-memory/FORMAT.md`](../../../living-memory/FORMAT.md) "Per-File Required Sections" table. Flag any required section that's missing.

#### 2.4 — Pattern-specific checks
Determine the file's pattern (A — date-indexed, B — ID-sequenced, or C — reference) from FORMAT.md.

- **Pattern A files:** verify at least one ISO-dated H2 exists. Verify newest date is first.
- **Pattern B files:** verify ID-sequenced H2s are monotonic with no gaps OR duplicates. Tolerated: `SUPERSEDED by D-NNN` markers.
- **Pattern C files:** verify topical H2 headers match the file's purpose (no strict check beyond the required-sections table).

#### 2.5 — Cross-reference correctness
- [ ] Sibling-file links use bare filenames (e.g. `[DECISIONS.md](DECISIONS.md)`), not `./DECISIONS.md` or absolute paths.
- [ ] Parent-folder links use `../` prefix (e.g. `[../docs/architecture.md](../docs/architecture.md)`).
- [ ] No `file://` or other absolute-path schemes.

#### 2.6 — Date format
- [ ] All dates in the file use ISO `YYYY-MM-DD`. Flag locale formats.

#### 2.7 — Project-specific check: `docs/` cross-references
This project's `living-memory/` files cross-reference [`../docs/`](../../../docs/). Verify:
- [ ] Every `../docs/...` link in a living-memory file points to an actually-existing file in `docs/`.
- [ ] Specifically check the mappings declared in `FORMAT.md` §Relationship-with-docs (e.g. `HLD.md` mentions `../docs/architecture.md`).

### Step 3 — Report
Output a single markdown table with this exact shape:

```markdown
| File | Severity | Drift items |
|---|---|---|
| FILE.md | ✅ clean | — |
| OTHER.md | ⚠️  minor | TOC missing 2 entries (Section X, Section Y) |
| WORST.md | ❌ blocking | Missing purpose blockquote; 3 stale TOC entries |
```

Severity rules:
- **✅ clean** — passes all checks.
- **⚠️  minor** — TOC drift only (stale/missing entries, ordering). Functionally fine.
- **❌ blocking** — missing required sections, missing universal header, ID-sequence violations, broken anchors. Affects readability or downstream tooling.

After the table, list the count by severity (e.g. *"15 clean, 2 minor, 1 blocking"*).

### Step 4 — Offer fixes
For each non-clean file, propose a specific fix as a bulleted list under that file's name. Examples:
- *"Add `## Table of Contents` after the purpose blockquote with these 6 entries: ..."*
- *"Update TOC entry `[Old Name](#old-name)` → `[New Name](#new-name)`."*
- *"Insert `## Outstanding / Known Gaps` at end of file."*
- *"Convert `06/15/2026` to `2026-06-15` on line 47."*
- *"Rename `D-005` → `D-006` (D-005 already used at line 41); update cross-references at lines 12, 89."*
- *"Add missing reference to `../docs/architecture.md` in HLD.md's purpose blockquote."*

**Do NOT auto-edit.** Show the proposed edits and ask: *"Apply fixes to <file>? (y/n/list-files)"*.

If the user says yes for a file, apply the edits using `Edit` with the exact strings. Verify after edit that the file now passes checks.

### Step 5 — Final summary
After all approved fixes:
- Re-run the audit table.
- Report any remaining drift.
- If everything is now clean, write a brief entry to `living-memory/CHANGELOG.md` noting "Ran living-memory-format-check; brought N files into compliance" with today's ISO date.

## TOC reconstruction algorithm

When building or rebuilding a TOC for a file:

```python
# Pseudocode
def build_toc(file_content):
    in_code_block = False
    headers = []
    for line in file_content.splitlines():
        if line.startswith('```'):
            in_code_block = not in_code_block
            continue
        if line.startswith('## ') and not in_code_block:
            title = line[3:].strip()
            if title == 'Table of Contents':
                continue
            anchor = github_anchor(title)
            headers.append((title, anchor))

    return '## Table of Contents\n' + '\n'.join(
        f'- [{title}](#{anchor})' for title, anchor in headers
    )

def github_anchor(title):
    import re
    anchor = title.lower()
    anchor = re.sub(r'[^\w\s-]', '', anchor)  # strip punctuation
    anchor = re.sub(r'\s+', '-', anchor)       # spaces → hyphens
    return anchor
```

For ID-sequenced files with >10 entries, group into a range:
- `[D-001 through D-010](#d-001--first-decision-title)` (link to the first).

## Edge cases

- **Files with substantial template/example code blocks** (`DECISIONS.md`, `MISTAKES.md`, `GOTCHAS.md`, `HANDOFF.md`): the audit must correctly distinguish real H2s from code-block-embedded `## ` lines. Track code-block state line-by-line.
- **Files with mixed Pattern A and B** (e.g. `MISTAKES.md` with both ISO-dated H2s and M-NNN entries inside): treat the H2 level as the structural layer; M-NNN can be H3 or inline.
- **Files added since the spec last changed**: if a new file isn't in the "Per-File Required Sections" table, skip pattern-specific checks but still apply universal header + TOC checks. Note in the report.
- **FORMAT.md and README.md themselves**: skip from audit. They serve a different role.
- **`docs/` cross-reference validation**: if a referenced file in `docs/` doesn't exist, flag as a blocking issue — it's a broken link that misleads readers.

## When to invoke this skill

- After running a memory sweep at session end.
- After a significant restructuring of a file.
- Before sharing the `living-memory/` folder with another agent or human teammate.
- Quarterly hygiene pass.
- After any retrofit (e.g. adding TOCs across all files).

## Output discipline
- Be concise. The report table is the main deliverable.
- Don't summarize what's clean. Summarize what's broken.
- Don't propose fixes the user didn't ask for (e.g. don't rewrite content; only fix structure/format).
- If the audit finds zero drift, say so in one line and stop.
