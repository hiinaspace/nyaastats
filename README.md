# Nyaastats

A torrent tracker statistics monitoring system for nyaa.si that tracks download, seed, and leech counts over time, providing market data for western anime viewership.

## Features

- **RSS Monitoring**: Automatically discovers new torrents from nyaa.si RSS feeds
- **Metadata Extraction**: Uses guessit to extract structured data from torrent filenames (series, episode, quality, etc.)
- **Time-Decay Scraping**: Intelligent scheduling that scrapes torrents more frequently when new, less frequently as they age
- **BitTorrent Protocol**: Native BitTorrent HTTP scrape protocol support for accurate statistics
- **SQLite Storage**: Efficient time-series data storage with WAL mode for concurrent access
- **Batch Processing**: Optimized scraping with configurable batch sizes and time windows
- **Dead Torrent Detection**: Automatically identifies and stops tracking dead torrents
- **Cron-Friendly**: Designed for cron-based execution, not long-running daemons

## Quick Start

```bash
# Install dependencies
uv sync

# Run once (fetches RSS, scrapes due torrents, prints stats)
uv run nyaastats

# Set up hourly cron job
echo "0 * * * * cd $(pwd) && uv run nyaastats" | crontab -
```

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd nyaastats

# Install dependencies (automatically handled by uv)
uv sync
```

## Usage

### Main Command

```bash
# Run with default settings
uv run nyaastats

# Custom database path
uv run nyaastats --db-path /path/to/custom.db

# More frequent RSS checks (every 30 minutes)
uv run nyaastats --rss-fetch-interval-hours 0.5

# Larger batch sizes for faster scraping
uv run nyaastats --scrape-batch-size 40

# Debug logging
uv run nyaastats --log-level DEBUG
```

### Backfill Historical Data

```bash
# Backfill last 100 pages of torrents
uv run nyaastats-backfill

# Backfill specific number of pages
uv run nyaastats-backfill 50

# Backfill specific user or search query
uv run nyaastats-backfill --url "https://nyaa.si/user/subsplease"
uv run nyaastats-backfill --url "https://nyaa.si/?f=0&c=1_2&q=underwater"
```

### Cron Setup Examples

```bash
# Every hour (recommended)
0 * * * * cd /path/to/nyaastats && uv run nyaastats

# Every 30 minutes (more frequent updates)
*/30 * * * * cd /path/to/nyaastats && uv run nyaastats

# With logging
0 * * * * cd /path/to/nyaastats && uv run nyaastats >> /var/log/nyaastats.log 2>&1

# With custom configuration
0 * * * * cd /path/to/nyaastats && NYAA_SCRAPE_WINDOW_MINUTES=60 uv run nyaastats
```

## Configuration

All settings can be configured via command-line arguments or environment variables with `NYAA_` prefix:

| Setting | CLI Argument | Environment Variable | Default | Description |
|---------|--------------|---------------------|---------|-------------|
| Database path | `--db-path` | `NYAA_DB_PATH` | `nyaastats.db` | Path to SQLite database |
| RSS URL | `--rss-url` | `NYAA_RSS_URL` | `https://nyaa.si/?page=rss&c=1_2&f=0` | Nyaa RSS feed URL |
| RSS interval | `--rss-fetch-interval-hours` | `NYAA_RSS_FETCH_INTERVAL_HOURS` | `1` | Hours between RSS fetches |
| Tracker URL | `--tracker-url` | `NYAA_TRACKER_URL` | `http://nyaa.tracker.wf:7777/scrape` | BitTorrent scrape URL |
| Batch size | `--scrape-batch-size` | `NYAA_SCRAPE_BATCH_SIZE` | `20` | Torrents per scrape batch |
| Batch window | `--scrape-window-minutes` | `NYAA_SCRAPE_WINDOW_MINUTES` | `30` | Minutes ahead for batching |
| Log level | `--log-level` | `NYAA_LOG_LEVEL` | `INFO` | Logging verbosity |

## How It Works

### Time-Decay Algorithm

Torrents are scraped at decreasing frequency based on age:
- **First 48 hours**: Every hour
- **Days 3-7**: Every 4 hours  
- **Week 2-4**: Every day
- **Month 2-6**: Every week
- **After 6 months**: Never (automatically archived)

### Data Storage

- **Torrents table**: Metadata including filename, publication date, size, and guessit-extracted information
- **Stats table**: Time-series data with seeders, leechers, and download counts
- **SQLite with WAL**: Enables concurrent reads while writing

### Execution Model

Each run performs these steps:
1. Check if RSS should be fetched (based on interval)
2. Parse new torrents and extract metadata with guessit
3. Query for torrents due for scraping (with batching window)
4. Scrape statistics using BitTorrent protocol
5. Update database and print summary statistics
6. Exit (cron handles scheduling)

## Project Structure

```
nyaastats/
├── nyaastats/           # Main package
│   ├── main.py          # Entry point and orchestration
│   ├── database.py      # SQLite operations and schema
│   ├── rss_fetcher.py   # RSS parsing with guessit
│   ├── tracker.py       # BitTorrent HTTP scrape protocol
│   ├── scheduler.py     # Time-decay algorithm
│   ├── config.py        # Pydantic configuration
│   ├── models.py        # Data models
│   ├── html_scraper.py  # HTML page scraping for backfill
│   └── backfill.py      # Historical data collection
├── tests/               # Test suite
├── design.md           # Detailed technical documentation
└── pyproject.toml      # Project configuration
```

## Development

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=nyaastats --cov-report=term-missing
```

### Code Quality

```bash
# Auto-fix linting issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Type checking (beta)
uvx ty check
```

### Adding Dependencies

```bash
# Runtime dependency
uv add package-name

# Development dependency
uv add --dev package-name
```

## Technical Details

For detailed technical information including database schema, algorithms, and operational considerations, see [design.md](design.md).

## License

This project is licensed under the WTFPL (Do What The Fuck You Want To Public License). See [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting: `uv run pytest tests/ -v && uv run ruff check --fix .`
5. Submit a pull request

The codebase follows the existing conventions and uses uv for dependency management.