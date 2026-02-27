# Data/markets/

This directory holds **market snapshot JSON files** produced by the ingestion scripts.

## Convention

| File pattern | Description |
|---|---|
| `predictfun_YYYYMMDD_HHMMSS.json` | Snapshot from Predict.fun |
| `probable_YYYYMMDD_HHMMSS.json` | Snapshot from Probable |
| `*_meta.json` | Sidecar manifest (who produced it, which LLM model, market count) |

## Workflow

1. **Teammate A** (ingestion): runs `python -m Ingestion.ingest_predictfun` → JSON files appear here → commits & pushes.
2. **Teammate B** (matching): does `git pull` → runs `Engine/build/arb-engine.exe` → engine loads all `*.json` from this directory.

## Notes

- Files are **tracked by Git** (not ignored) — this is intentional for the two-person workflow.
- The engine loads **all** `.json` files (excluding `*_meta.json`) from this directory at startup.
- Newer snapshots overwrite older data for the same `(platform, market_id)` composite key via deduplication.
- Keep snapshots small and clean; delete stale ones before committing to avoid bloat.
