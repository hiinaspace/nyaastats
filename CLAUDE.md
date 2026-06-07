# Nyaastats Project - Claude Reference

Quick reference for project setup and common commands.

## Project Overview
- **Name**: Nyaastats
- **Description**: Nyaa torrent tracker statistics monitoring system
- **Language**: Python 3.11+
- **Package Manager**: uv (NOT pip)

## Key Commands

### Testing
```bash
# Run all tests
uv run pytest tests/ -v

# Run tests with coverage
uv run pytest tests/ --cov=nyaastats --cov-report=term-missing
```

### Linting and Formatting
```bash
# Check code style and auto-fix code style issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# run static typechecker (in beta, so may crash/have false positives)
uvx ty check
```

### Running the Application
```bash
# Run once (for cron or manual execution)
uv run nyaastats

# Run backfill script
uv run nyaastats-backfill --help

# Run ETL pipeline to generate analytics
uv run nyaastats-etl --db nyaastats.db --output website/src/data

# Run ETL with custom fuzzy matching threshold
uv run nyaastats-etl --db nyaastats.db --output website/src/data --fuzzy-threshold 80
```

### Development Setup
```bash
# Install dependencies (automatically done by uv run)
uv sync

# Add new dependencies
uv add <package>

# Add dev dependencies
uv add --dev <package>
```

## Important Notes

1. **Use uv, not pip**: This project uses `uv` for dependency management and virtual environments
2. **Always run commands with `uv run`**: Don't activate venv manually, use `uv run <command>`
3. **Ruff for linting**: Use `uv run ruff check` and `uv run ruff format` for code quality
4. **Testing**: Use `uv run pytest` for running tests
5. **Dependencies**: Add dependencies with `uv add`, not pip install

## Project Structure
```
nyaastats/
├── nyaastats/           # Main package
│   ├── __init__.py
│   ├── database.py      # SQLite operations
│   ├── rss_fetcher.py   # RSS parsing with guessit
│   ├── tracker.py       # BitTorrent scraping
│   ├── scheduler.py     # Time-decay algorithm with batching
│   ├── config.py        # Pydantic configuration
│   ├── main.py          # Main run-once execution
│   ├── backfill.py      # Historical data script
│   ├── etl_main.py      # ETL pipeline orchestration
│   └── etl/             # ETL pipeline components
│       ├── config.py           # ETL configuration and mappings
│       ├── anilist_client.py   # AniList GraphQL API client
│       ├── fuzzy_matcher.py    # Title matching logic
│       ├── title_corrections.py # Title parsing corrections
│       ├── aggregator.py       # Download aggregation
│       ├── exporter.py         # JSON export
│       └── seasonal_exporter.py # Seasonal data export
├── tests/               # Test modules
│   └── etl/             # ETL-specific tests
├── pyproject.toml       # Project config and dependencies
├── CLAUDE.md           # This file
└── ETL_CONFIGURATION.md # Detailed ETL configuration guide
```

## Key Technologies
- **SQLite**: Database with WAL mode
- **httpx**: HTTP client
- **feedparser**: RSS parsing
- **guessit**: Media metadata extraction
- **bencodepy**: BitTorrent protocol
- **pydantic**: Configuration management
- **pytest**: Testing framework
- **ruff**: Linting and formatting

## ETL Pipeline Quick Reference

For detailed ETL configuration (season matching, episode mappings, etc.), see **[ETL_CONFIGURATION.md](ETL_CONFIGURATION.md)**.

**Quick tips:**
- ETL generates `unmatched_torrents_report.json` - use this to find shows that need configuration
- Three-layer matching: episode-range → manual overrides → season-aware → fuzzy
- Configuration files: `nyaastats/etl/config.py` and `nyaastats/etl/title_corrections.py`

**External ratings (cross-source join):**
- AniList scores (`averageScore`, `meanScore`, `popularity`, `favourites`, `idMal`)
  come from the existing AniList query (`nyaastats/etl/anilist_client.py`).
- MyAnimeList scores are fetched via Jikan (`nyaastats/etl/jikan_client.py`), keyed by
  AniList's `idMal`, and cached in the `external_ratings` table (7-day TTL) so reruns
  don't re-hit the API.
- Niconico per-episode survey ratings (公式アンケート, 5-point scale) are ingested by
  `nyaastats/etl/niconico_client.py` from the full CSV export of the fan DB
  `nicolive-anime-survey.info` (cached in `external_ratings`, source `niconico_csv`).
  Rows are matched to shows by AniList **native** (Japanese) title — exact, then
  length-gated `partial_ratio` fuzzy — with `NICONICO_TITLE_MAP` in `config.py` for
  manual overrides, and stored per-episode in the `niconico_survey` table. Season
  codes map via `niconico_season_code()` (e.g. Spring 2026 → `2026B`). This source
  has survey *ratings* only — not Niconico view counts.
- `nyaastats/etl/metrics.py` merges these into per-show fields and computes
  `rank_delta_dl_vs_mal` / `rank_delta_dl_vs_anilist` (download rank − rating rank;
  positive = underrated by downloads). Emitted per show in `season-*.json` and
  visualized as premiere-size-bucketed rank-delta beehives + a score-vs-downloads
  scatter (with a log-space regression line, residual segments, and outlier labels)
  on season pages. AniList/MAL/Niconico scores also appear as table columns.

## Common Tasks

### Before making changes:
1. Run tests: `uv run pytest tests/ -v`
2. Check linting: `uv run ruff check .`

### After making changes:
1. Format code: `uv run ruff format .`
2. Fix linting: `uv run ruff check --fix .`
3. Run tests: `uv run pytest tests/ -v`
4. Commit changes with appropriate message

### Adding new features:
1. Write tests first
2. Implement feature
3. Ensure all tests pass
4. Check code quality with ruff
5. Update documentation if needed
