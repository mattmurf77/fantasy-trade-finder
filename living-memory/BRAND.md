# Brand & Voice — Fantasy Trade Finder

> **Purpose:** how this project *sounds* when it produces output — docs, READMEs, commit messages, in-app copy, marketing if/when. Plus the engineering posture defined by [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md). This file is voice for outputs; coding-guidelines is voice for code.
>
> **Read at:** before generating any summary, doc, commit message, or user-facing copy.
> **Write at:** when voice/style/terminology evolves.
>
> Companion files: [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md), [`GLOSSARY.md`](GLOSSARY.md).

---

## Table of Contents
- [2026-05-21 — Voice Charter](#2026-05-21--voice-charter)
- [Terminology Rules](#terminology-rules)
- [Formatting Conventions](#formatting-conventions)
- [Specific Anti-Patterns for AI-Authored Content](#specific-anti-patterns-for-ai-authored-content)
- [Output Channel Conventions](#output-channel-conventions)
- [Mascot & Visual Branding](#mascot--visual-branding)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## 2026-05-21 — Voice Charter

### Identity
A **dynasty manager's tool, built by a dynasty manager.** The reader (in docs) and the user (in app) are assumed to know dynasty fantasy football. Output should treat them as a peer, not a beginner being onboarded to the sport.

### Voice principles

| Do | Don't |
|---|---|
| Use dynasty jargon naturally ("startup," "3-for-1," "consensus value") | Define dynasty terms inline as if the reader is new to the format |
| Lead with the trade outcome, then the reasoning | Lead with framing ("In this analysis we explore…") |
| Cite specific data points (Elo numbers, value rankings, swipe counts) | Make vague claims ("strong upside") |
| Treat trades as data first, narratives second | Use hype language ("league-winner!") in app copy |
| Reference [`../docs/`](../docs/) when explaining how something works | Restate `docs/` content in chat |

### Tone

- **Terse over thorough.** "Scheffler is mis-valued by 22pp in your league" beats a paragraph of context.
- **Evidence-grounded.** Every claim either cites a value, a swipe count, or a doc reference.
- **Direct.** "This trade is +14 EV for you." Not "you might find this trade interesting because…"
- **Honest about uncertainty.** When Elo confidence is low (few swipes), say so.

---

## Terminology Rules

### Use these terms

| Term | Meaning |
|---|---|
| **Sleeper** | The Sleeper platform (capitalized) |
| **dynasty** (lowercase) | The fantasy format |
| **redraft** (lowercase) | Single-season format (used as a contrast term) |
| **trade card** | A generated trade proposal |
| **trio** / **matchup** | A 3-player ranking interaction |
| **liked trade** / **passed trade** | User's swipe disposition |
| **matched trade** | Mutual-like with leaguemate |
| **consensus value** | DynastyProcess CSV value |
| **personal Elo** | User's evolved Elo for a player |
| **pp** | Percentage points (for trade gain reporting) |
| **the operator** | The single user / project maintainer |
| **the player base** | The full Sleeper player roster |
| **the field** | All entrants in a league |
| **mascot:** *(pending)* "Tommy Tumble" or "Ricky Rumble" — see Q-009 |

### Avoid these terms

| Avoid | Use instead | Why |
|---|---|---|
| "AI" (when Claude is meant) | "Claude" | More precise |
| "the AI" | "Claude" or "the model" | Generic |
| "leverage" (verb) | "use" | Always |
| "robust" | name the property | Empty without quantification |
| "powerful" | name the capability | Empty adjective |
| "best-in-class" | omit or name the comparison | Marketing prose |
| "Sleeper team" (in app) | "roster" | Domain-correct |
| "trade calculator" | "trade finder" | Project name; we generate, not calculate |
| Emojis in docs or commit messages | omit | Project convention; CSVs and docs are emoji-free |

### Capitalization

- File paths and code identifiers: backticks, no quotes. `backend/server.py`, `POST /api/rank3`, `ANTHROPIC_API_KEY`.
- Decision IDs: D-NNN (uppercase D, hyphen, 3-digit zero-padded).
- Question / Mistake / Gotcha IDs: Q-NNN / M-NNN / G-NNN.
- Models: as Anthropic writes them. *Haiku*, *Sonnet*, *Opus*. Lowercase in running prose ("Haiku for matchup selection") when used as a generic family name.

---

## Formatting Conventions

### Markdown
- **H1** for file title only.
- **H2** for major sections, **H3** for sub-sections.
- **Tables** for comparisons of ≥3 items (vendor inventories, decisions, test results).
- **Bullets** for ≤3 items or naturally-linear lists.
- **Code blocks** for any file path or command that appears in dense prose.
- **No emojis.**
- **Horizontal rules** between top-level sections, not in running prose.

### Numbers and units
- Always include the unit on first mention (`18.4pp`, `0.890 AUC`, `2.6× info gain`).
- Round to useful precision. `~6,000 swipes` over `5,983`.
- Sign always on percent changes (`-19.5%`, `+7.33%`).
- Dollar signs and percent signs are stuck to the number (`$30`, `22%`).

### Dates
- ISO format: `2026-05-21`. No `05/21/26`.
- Include year always.
- "Today" / "yesterday" don't appear in durable files.

### Commit messages
- Format: `<scope>: <imperative-mood-summary>`. E.g. `ranking_service: fix tiebreak in 3-way Elo decomposition`.
- Body (optional): one paragraph; link to docs/ or DECISIONS.md when justifying.

---

## Specific Anti-Patterns for AI-Authored Content

Things Claude in particular drifts toward; check output for these:

- **"That's a great question!"** — never.
- **Three-pronged thesis statements** ("There are three key considerations…"). Just list.
- **Concluding paragraphs that restate the preceding paragraph.** Cut.
- **"Whether…or…"** false-binary openers. Cut the framing; state the options.
- **Em-dashes as commas at high volume.** Sparingly OK; ~3 per file cap.
- **Generic adjectives** (*powerful, robust, seamless, comprehensive*) — name the property.
- **Hedging without reason** (*might, can, potentially*) — hedge only when uncertain.
- **"Game-changer," "next-generation," "best-in-class"** — never. The reader is the operator, not a board member.

---

## Output Channel Conventions

### In-app copy (web / mobile / extension)
- Direct, dynasty-fluent. "Swipe to rank." "This trade is +14pp in your favor."
- No exclamation points in default copy. Save for genuine milestones.
- Empty states: actionable, not apologetic. "Rank 10 players to start seeing trades" vs "No trades yet, sorry!"
- Error messages: name what failed + what to try. "Couldn't reach Sleeper. Check connection or try again."

### Docs (`docs/`, `living-memory/`)
- Per [`FORMAT.md`](FORMAT.md). H1 + purpose blockquote + TOC + content.
- Cite specific files; don't restate them.

### Commit messages
- `<scope>: <action>`. Short body if needed.

---

## Mascot & Visual Branding

- **Concept:** football player avatar mid-fumble. Cartoon-style running back; ball popping out; jersey reads the mascot's name.
- **Name candidates (pending):**
  - **Tommy Tumble** — softer, more whimsical.
  - **Ricky Rumble** — more energetic, alliterative.
- **Decision pending** — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-009.

---

## Outstanding / Known Gaps
- No formal review of voice across `docs/` — they were authored over time without a unified voice doc. A sweep would surface drift.
- App copy is currently sparse; voice guidelines mostly apply to docs + commit messages.
- Mascot naming pending.
