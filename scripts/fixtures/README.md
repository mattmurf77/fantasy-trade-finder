# Local ranking seed fixtures

`fantasypros-2025.json` and `fantasypros-2026.json` preserve the original ranking
snapshots, test-user identities, and profile-specific Sleeper name aliases.
`seed_rankings.py` owns their shared matching, swipe-generation, and database logic.

Run from the repository root with the backend Python environment:

```bash
python3 scripts/seed_test_user.py --dry-run
python3 scripts/seed_test_user_2.py --dry-run
```

Omit `--dry-run` to seed the local database; add `--clear` to replace that profile's
existing swipes. Both compatibility commands retain their original defaults.
Never configure these commands against production.
