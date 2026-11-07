# ADR-027 — Frozen paired outlook calibration

Date: 2026-11-06. Status: accepted for default-off implementation; activation requires review/CI.

The user requested a new all-app-user exercise comparing current and candidate owner trade arms, with trades prepared for connected leagues in advance. The old exercise mixes a previously served deck with freshly built value-core/fit suggestions, which cannot establish a fair current-versus-candidate comparison.

Create a new round namespace, capture once, and generate both exact owner versions through the same frozen final gates. Preserve old sessions and feedback. Use equal bounded review selections, merge shared offers once with dual attribution, record all inventory denominators, and balance randomized presentation. Small valid inventories remain eligible with explicit descriptive sample labels; zero-arm/error cases cannot borrow another engine's cards.

Retain current/value_core wire aliases for installed-client compatibility, while canonical versions remain authoritative in private evidence and reports. Feedback is immutable and retry-safe. A serial durable queue prepares only already connected authorized account/league pairs; unknown provider coverage is unavailable. Normal serving stays unchanged.

Keep durable as-of exercises rather than expiring every15minutes. Known changes refresh only unanswered sessions; started exercises remain frozen. There is no claim that pregeneration eliminates every possible wait or that subjective grades validate future-production forecasts. Participant deletion remains an explicit exception to replay immutability.

See [architecture and operating limits](../plans/outlook-calibration-round/architecture.md) and [scope](../plans/outlook-calibration-round/scope.md).
