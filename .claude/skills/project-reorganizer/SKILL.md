---
name: project-reorganizer
description: >
  Reorganize a messy or flat project folder into a clean, conventional structure
  by separating source code (frontend, backend) from config, data, docs, and scripts.
  Use this skill whenever the user asks to "reorganize", "restructure", "clean up",
  "refactor the folder layout", "separate frontend and backend", "fix project structure",
  or mentions that their project files are disorganized, flat, or hard to navigate.
  Also triggers on "move files into folders", "split the codebase", or
  "organize by concern". Works with any language or framework.
---

# Project Reorganizer

You are performing a careful, methodical project folder reorganization. The goal is to
move files into a conventional structure (separating source code from config, data, docs,
and scripts) while updating every cross-reference so nothing breaks.

This is high-stakes refactoring — a missed import or path update means the project won't
run. The two-table methodology below exists specifically to prevent that. Do not skip or
abbreviate it.

## Phase 1: Scan and Understand

Before proposing any changes, build a complete mental model of the project.

1. **List every file and directory** recursively. Note file types, sizes, and modification dates.
2. **Categorize each file** into one of these buckets:

   | Category | Examples |
   |----------|---------|
   | Backend source | `.py`, `.go`, `.java`, `.rb`, `.rs` — application logic, services, models, DB layer |
   | Frontend source | `.html`, `.css`, `.js`, `.jsx`, `.tsx`, `.vue`, `.svelte` — UI code |
   | Config | `requirements.txt`, `package.json`, `Makefile`, `.env.example`, `Dockerfile`, `pyproject.toml` |
   | Data / artifacts | `.db`, `.sqlite`, cache files, `.log`, generated output |
   | Docs / reference | `.md` (non-README), PRDs, specs, design docs, `.pdf` reference material |
   | Scripts / tooling | One-off scripts, demos, seed scripts, CLI utilities |
   | Build artifacts | `__pycache__`, `node_modules`, `dist/`, `.pyc`, compiled output |
   | Entry points | `main.py`, `run.py`, `index.js`, `app.py` — the file that starts the application |

3. **Map every cross-reference** between files. This means reading each source file and recording:
   - Import/require statements and what they resolve to
   - File path references (DB paths, cache paths, template dirs, static folder configs)
   - Framework-specific wiring (Flask's `static_folder`, Express's `express.static()`, etc.)
   - Relative URL paths in frontend code that hit backend routes (these usually do NOT change)

This scanning phase is not optional. Read the files. Grep for imports. The tables you build
next are only as good as your understanding of the codebase.

## Phase 2: Propose Target Structure

Based on the scan, propose a target directory layout. Follow the conventions of the
project's language/framework ecosystem. Common patterns:

**Python projects:**
```
project/
├── backend/  (or src/, or the package name)
│   ├── __init__.py
│   ├── server.py
│   ├── database.py
│   └── services/
├── data/
├── docs/
├── scripts/
├── .gitignore
├── requirements.txt
└── run.py
```

**Node/JS projects:**
```
project/
├── src/
│   ├── server.js
│   ├── routes/
│   └── models/
├── public/  (or static/)
├── docs/
├── scripts/
├── .gitignore
└── package.json
```

Present the proposed structure to the user and get confirmation before proceeding.
If the user has specific preferences (folder names, grouping), incorporate them.

## Phase 3: Build the Two Cross-Reference Tables

This is the most important phase. Build two tables and present them together.

### Table 1 — Where Each File Is Currently Referenced FROM

For every file that will move, find every place it is referenced. Each row is one reference.

| # | Source File | Line | Reference Code | Target File |
|---|-------------|------|---------------|-------------|
| 1 | server.py:57 | 57 | `from database import ...` | database.py |
| 2 | server.py:600 | 600 | `Flask(__name__, static_folder="static")` | static/ dir |
| ... | ... | ... | ... | ... |

Include:
- Import statements (Python `import`/`from`, JS `require`/`import`)
- Path literals (DB connection strings, cache file paths, template dirs)
- Framework config (static folder, template folder, middleware paths)
- Build tool references (if applicable)

### Table 2 — Where Each Reference Needs To Be Updated TO

For every row in Table 1, specify exactly what the new reference should be after the move.
Also add rows for any NEW files (like an entry-point script or `__init__.py`).

| # | File to Update | Line | Current Reference | New Reference |
|---|---------------|------|------------------|---------------|
| 1 | backend/server.py:57 | 57 | `from database import ...` | `from .database import ...` |
| 2 | backend/server.py:600 | 600 | `Flask(__name__, static_folder="static")` | `Flask(__name__, static_folder=str(ROOT / "static"))` |
| ... | ... | ... | ... | ... |

### Cross-Compare

After building both tables, verify:
- Every row in Table 1 has a corresponding row in Table 2 (nothing was missed)
- Every row in Table 2 that isn't a "new file" has a corresponding row in Table 1
- Report any mismatches and resolve them before proceeding

Present both tables and the comparison result to the user. Get confirmation before executing.

## Phase 4: Execute File Moves

Do the structural changes first, code updates second. This order matters because you need
files in their final locations before editing references.

1. Create all new directories
2. Move files to their target locations
3. Create any new files (e.g., `__init__.py` for Python packages, entry-point scripts)
4. Verify the directory tree matches the proposed structure

Keep a checklist and mark off each move. If a move fails (permissions, etc.), note it
and continue — don't abandon the entire operation.

## Phase 5: Update All Code References

Work through Table 2 row by row. For each update:

1. Read the file at the line indicated (the line number may have shifted if earlier edits
   changed the file — use grep to find the exact reference if needed)
2. Make the edit
3. Mark the row as done

After completing all rows, do a sweep for any references you might have missed:
- Grep the entire project for bare module names that should now be relative/qualified
- Check for stale path literals pointing to old locations
- Look for any hardcoded references to the old structure

This sweep is important because the initial scan sometimes misses lazy imports, conditional
imports, or references buried inside string literals.

## Phase 6: Verify

Run a layered verification:

1. **Syntax check** — Parse every source file to catch typos in the edits
   - Python: `python3 -c "import ast; ast.parse(open('file.py').read())"`
   - JS/TS: Use the project's linter or `node --check file.js`

2. **Import verification** — Confirm every import/require resolves
   - Grep for all import statements and verify the target exists at the new path
   - Check for stale bare imports that should now be relative

3. **Path verification** — Confirm file path references resolve
   - For each path literal, verify the file exists at the resolved location

4. **Unit tests** — If the project has tests, run them. If not, test each module
   in isolation (import it, call key functions with simple inputs, verify no crashes)

5. **Integration test** — Attempt to start the application and verify it initializes
   without errors. For web apps, check that the server starts and serves the index page.

If any test fails, diagnose the issue (usually a missed reference update), fix it,
and re-run that test. Don't declare victory until all five layers pass.

## Language-Specific Reference Patterns

When scanning for cross-references (Phase 1) and updating them (Phase 5), here's what to
look for in common languages. These patterns are easy to miss if you only grep for `import`.

### Python
- `from X import Y` and `import X` — the obvious ones
- `from .X import Y` — relative imports (already inside a package)
- Lazy imports inside functions: `def foo(): from X import Y`
- `__import__("X")` — rare but exists
- `importlib.import_module("X")`
- `os.path.join(__file__, ...)` — path construction relative to the file
- `pathlib.Path(__file__).parent` — same pattern, pathlib style
- `open("relative/path")` — relative file paths in code
- Flask: `static_folder=`, `template_folder=`, `send_from_directory()`
- Django: `INSTALLED_APPS`, `ROOT_URLCONF`, `TEMPLATES[DIRS]`
- SQLAlchemy: connection string with `sqlite:///path`

### JavaScript / TypeScript
- `require("./module")` and `import X from "./module"`
- `import("./module")` — dynamic imports
- `express.static("public")` — static file serving
- `path.join(__dirname, ...)` — path construction
- `process.cwd()` — working directory references
- Webpack/Vite config: entry points, aliases, output paths

### Go
- `import "project/pkg/name"` — module-path imports
- `go.mod` — module declaration affects all import paths
- `//go:embed` — embedded file references

### General (all languages)
- CI/CD configs (`.github/workflows/`, `Makefile`) — file paths in build steps
- Docker: `COPY` and `WORKDIR` directives in `Dockerfile`
- Config files: `.env`, `config.yaml`, `settings.json` with path values

## Common Pitfalls

These are mistakes that frequently cause "it worked before the reorg" breakage:

- **Forgetting `__init__.py`**: Moving Python files into a subdirectory makes it a package.
  Without `__init__.py`, relative imports fail silently.
- **Stale `__pycache__`**: Old `.pyc` files can mask import errors by resolving from cache.
  Delete `__pycache__/` after the move.
- **`__file__` path shifts**: Any code that builds paths relative to `__file__` will break
  when the file moves deeper into the tree. You need to add `..` or `.parent` calls.
- **Entry point confusion**: If `server.py` used to run with `python server.py`, it can't
  use relative imports. Create a `run.py` at the project root that imports and launches.
- **Static file serving**: Web frameworks resolve static/template paths relative to the app
  file or project root. Moving the app file without updating these paths = broken CSS/JS.
- **Missing the sweep**: The initial scan catches ~90% of references. The remaining 10% are
  lazy imports, conditional imports, and string-based references. Always do the post-move
  grep sweep in Phase 5.
