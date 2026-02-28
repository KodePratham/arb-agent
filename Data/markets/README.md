# Data/markets

Local snapshot directory used by the C++ matcher.

## File patterns

- `probable_YYYYMMDD_HHMMSS.json`
- `opinion_trade_YYYYMMDD_HHMMSS.json`
- `*_meta.json` (ingestion metadata)

## Usage

1. Run ingestion scripts to create snapshots.
2. Run engine; it loads all non-meta JSON files from this directory into RAM.
3. Engine deduplicates by `(platform, market_id)`.

## Repository policy

- This folder keeps `.gitkeep` so the path exists in a fresh clone.
- Generated snapshots are not committed by default.