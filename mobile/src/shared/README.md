# mobile/src/shared/

One file: `types.ts` — the wire types used by `api/`, `screens/`, and `components/` at once (`Player`, `Trade`, `League`, `QueuedTrade`, `Position`, …).

Rules are short enough to live in [CLAUDE.md](CLAUDE.md); the essentials:

- **This is for types shared across layers.** A type used by exactly one `api/` module stays in that module.
- **Keep it aligned with the backend's JSON** — the contract of record is [docs/api-reference.md](../../../docs/api-reference.md) and [docs/data-dictionary.md](../../../docs/data-dictionary.md). A field that exists here but not there is drift.
- **Optional means optional.** Fields a server may omit (`draft_status`, `source`, `pick_id`, `season`) are declared optional so an older server response still type-checks; the client degrades rather than crashing.
- **No runtime values.** Enums that clients must agree on are cross-client invariants — those live in [docs/cross-client-invariants.md](../../../docs/cross-client-invariants.md) with their implementation in `utils/` or `api/`, not here.
