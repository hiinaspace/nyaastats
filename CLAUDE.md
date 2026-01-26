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
uv run nyaastats-etl --db nyaastats.db --output output/

# Run ETL with custom fuzzy matching threshold
uv run nyaastats-etl --db nyaastats.db --output output/ --fuzzy-threshold 80

# Example cron setup for hourly execution
# Add to crontab with: crontab -e
# 0 * * * * cd /path/to/nyaastats && uv run nyaastats
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
