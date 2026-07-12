# Karpathy Guidelines (applied to docs work)

Adapted from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls. Apply these while generating or refreshing docs.

## 1. Think Before Coding (writing)

- Read enough of the source to be accurate. Don't guess column types or route paths.
- If a section's source of truth is ambiguous (e.g. "is this an enum or freeform string?"), name the ambiguity, ask, don't pick silently.

## 2. Simplicity First

- The data dictionary is not a textbook. Column + type + one note line is usually enough.
- Don't pad sections with prose. Tables beat paragraphs.
- Don't invent terms that aren't in the codebase.

## 3. Surgical Changes

- In Refresh mode, never edit a doc section that didn't change. Every edit traces to a code diff.
- If you touch a doc, the change must reflect a real code change. No drive-by reformatting.

## 4. Goal-Driven Execution

- The success criterion is: "can a reader answer common questions without grepping?" Hold the docs to that bar.
- After Bootstrap, do a quick self-check: pick three plausible reader questions and verify each is answered by exactly one doc.
