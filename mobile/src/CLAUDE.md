# mobile/src/ — Notes for Claude

All app source. Subfolders are organized by concern (not by feature).

| Dir | Use it for |
|---|---|
| `api/` | Network calls only — no UI, no state mutation |
| `components/` | Stateless / presentational pieces shared across screens |
| `hooks/` | Cross-cutting custom hooks |
| `navigation/` | Stack/tab definitions |
| `screens/` | One file per top-level route |
| `shared/` | Cross-cutting types |
| `state/` | Context providers + state hooks (session, flags, notifications) |
| `theme/` | Design tokens (colors, spacing) — change here, not inline |
| `utils/` | Pure functions, no React |

When adding a feature: data fetch → `api/`, screen → `screens/`, reusable bits → `components/`.
