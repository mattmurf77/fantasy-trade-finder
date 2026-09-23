# Artifact validation follow-up — 2026-09-22

## Observed boundary and scope

PR306 merge2cff90c7 became live22:47:29UTC after7183/1skip hosted and local
backend results and all four CI gates. A fresh one-team canary0ae2dca1223e427c82227609dba32bd1
began22:48:46 and failed22:50:58 with `InvalidArtifact`, saving zero artifacts.
The prior cross-batch error is not reported in this run. Numeric cache rollout
was restored1→0 at22:51:39, with unrelated settings unchanged.

The exception class does not establish a size failure. The current log omits its
safe failure category and phase. Do not increase storage/memory limits, truncate
offers, guess team ownership, or claim all-team readiness from this evidence.

## Next bounded implementation

1. Add explicit allowlisted artifact failure codes and bounded integer statistics
   (card count, logical/encoded bytes, applicable byte limit). Unknown exception
   text remains undisclosed; never log identities, terms, credentials or raw JSON.
2. Annotate fixed preparation phases around before/after receipt validation and
   artifact save. Persist only a safe machine reason in the existing target
   status, and log sanitized phase/numeric details. No new analytics, tables,
   model settings, prices, generation budgets or resource limits.
3. Pressure-test a denser actual synthetic constructor under unchanged16/4096/60000
   production search budgets. Record exact failure category, full offer count,
   proof/order integrity, serialized/compressed bytes and peak memory. Local size
   reproduction is evidence about capacity, not proof of the live failure cause.
4. Qualify and release any correction through the existing full/hosted/review gates.
   Retry one fresh-key canary, inspect safe evidence, then expand only when justified.
   If resource design must change, document and validate the bounded design first;
   do not silently raise limits on the existing Standard instance.

## Verification

Named negative controls must prove arbitrary exception strings, forged codes,
unknown phases, IDs and non-integer statistics never escape. Existing strict JSON,
compression, graph identity, rollback, privacy and no-exposure tests remain gates.
Owner's build/deploy authorization remains active; caching is currently OFF.
