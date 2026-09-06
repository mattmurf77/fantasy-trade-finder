# ADR-019: Joint owner intent constructs candidates; market values set terms

Date: 2026-09-06
Status: Accepted for experimental implementation; activation is separate

## Context

The owner interview promises help acquiring preferred players and selling
disfavored players at workable market terms, with both managers' outlook and
roster purpose considered. Applying those preferences only after a legacy
generator has discarded candidates cannot test that promise. The owner also
requested smaller packages and preserving the successful existing arms.

## Decision

Build `owner_v1` as a separate constructor shared by organic and selected
entrances. Personal rankings, outlook and needs jointly choose candidate assets
before pool truncation. Market package pricing then constrains and assembles
terms; stronger preference does not automatically inflate the offered price.
Small organic shapes are structural, not a final visual preference. Both-sided
utility may justify bounded dynasty losses without rewriting user tiers.

Retain historical controls and distinct model attribution. Separate generation
from exposure with default-off include/serve knobs. Capture exact inputs and
market limits privately; measure real views and package-linked outcomes. Preserve
server trial ordering on mobile rather than compare incompatible model scores.

## Alternatives considered

- Rerank existing survivors: cannot recover useful packages excluded upstream.
- Market-led target selection followed by a fit check: can lose the owner's
  intended buys/sells before outlook and need are applied.
- Replace the three controls: would remove the live comparison the owner asked
  to retain and make historical arm labels misleading.

## Consequences

The trial changes actual construction and can establish candidate sensitivity
to rankings and outlook. Utility coefficients remain provisional, lineup
usefulness is a market-based proxy, and incomplete league context is labelled.
Independent tests, final roster safety, exposure linkage and stratified trial
analysis are required. This does not complete offer lifecycle, causal Undo or
future-pick projection work.

See [scope](../plans/owner-engine-challenger/scope.md) and
[trial protocol](../plans/owner-engine-challenger/trial-protocol.md).
