# Nyaastats Pipeline & Website - Design Document

## 1. Overview & Goals

**Purpose**: Transform raw torrent scrape data into user-facing popularity rankings and per-show analytics for seasonal anime.

**Target Users**:
- "Number goes up/down" fans who want to track seasonal anime popularity trends (similar to posting Steam Charts for newly released games)
- Viewers interested in specific show performance and episode-level analytics

**Key Features**:
- **Front page**: Compact weekly ranking bump chart with river width encoding download volume
- **Per-show pages**: Daily download time series with episode breakdowns and cumulative stats
- **MVP Scope**: Fall 2025 season only (first complete data season)

## 2. System Architecture

```
┌─────────────────┐
│  nyaastats.db   │ (Existing scraper output)
│  - torrents     │ (infohash, filename, pubdate, guessit_data)
│  - stats        │ (timestamp, seeders, leechers, downloads)
└────────┬────────┘
         │
         ↓
┌─────────────────────────────────┐
│   ETL Pipeline (Python)         │
│  ┌──────────────────────────┐   │
│  │ 1. AniList Query         │   │
│  │ 2. Torrent Filtering     │   │
│  │ 3. Fuzzy Matching        │   │
│  │ 4. Episode Attribution   │   │
│  │ 5. Download Aggregation  │   │
│  │ 6. Time Normalization    │   │
│  │ 7. Weekly Rankings       │   │
│  └──────────────────────────┘   │
└────────┬────────────────────────┘
         │
         ↓
┌─────────────────────────────────┐
│  Output Files                   │
│  - episodes.parquet (detailed)  │
│  - rankings.json (bump chart)   │
└────────┬────────────────────────┘
         │
         ↓
┌─────────────────────────────────┐
│  Observable Framework Website   │
│  - Front page: Bump chart       │
│  - Show pages: Episode charts   │
└─────────────────────────────────┘
```

**Run Cadence**: Weekly ETL execution with full regeneration of output files.

**Deployment Strategy**: Standalone ETL script (Option A) - ETL runs separately and outputs files to `website/src/data/`. This keeps the ETL independent from Observable's build process and allows the production database to remain separate from the repo.

## 3. Data Flow Details

### 3.1 Input Data (from existing nyaastats.db)

**Torrents Table**:
- `infohash` (TEXT): Unique torrent identifier
- `filename` (TEXT): Full torrent name
- `pubdate` (TEXT): Publication timestamp (ISO format)
- `guessit_data` (TEXT): JSON blob with parsed metadata
  - `title`: Detected show title
  - `episode`: Episode number(s)
  - `season`: Season number
  - `release_group`: Fansub group
  - `screen_size`: Resolution (720p, 1080p, etc.)
  - Additional metadata from guessit

**Stats Table**:
- `infohash` (TEXT): Links to torrents
- `timestamp` (TEXT): Scrape time (ISO format)
- `downloads` (INTEGER): Absolute download count from tracker
- `seeders` (INTEGER): Current seeders
- `leechers` (INTEGER): Current leechers

### 3.2 ETL Processing Steps

#### Step 1: AniList Query
Query AniList GraphQL API for Fall 2025 anime (airing/aired between Oct-Dec 2025):

```graphql
query {
  Page(page: 1, perPage: 100) {
    media(season: FALL, seasonYear: 2025, type: ANIME) {
      id
      title {
        romaji
        english
        native
      }
      synonyms
      episodes
      status
      airingSchedule {
        nodes {
          episode
          airingAt
        }
      }
    }
  }
}
```

**Extract**:
- `anilist_id`: Unique show identifier
- `title`: Romaji, English, synonyms for fuzzy matching
- `episodes`: Total episode count
- `airingSchedule`: Episode air dates for time windowing
- `status`: RELEASING, FINISHED, etc.

**Rate Limiting**: Use GraphQL library with automatic rate limiting (90 req/min limit). No local caching for MVP.

#### Step 2: Torrent Filtering
Exclude torrents that complicate attribution:

- **Batch torrents**: Skip if guessit returns `episode` as list/range (e.g., `[1, 2, 3]` or `"1-12"`)
- **v2 torrents**: Check filename for "v2" patterns (BitTorrent v2 protocol causes double-counting)
- **Failed parsing**: Skip torrents with `status = 'guessit_failed'`
- **Date range**: Only process torrents with `pubdate >= 2025-10-01` (Fall season start)

#### Step 3: Fuzzy Matching (Torrent Title → AniList ID)

**Algorithm**:
1. Extract `title` from `guessit_data`
2. Normalize both torrent and AniList titles:
   - Lowercase
   - Remove punctuation (keep only alphanumeric + spaces)
   - Collapse multiple spaces
3. Calculate similarity score using `thefuzz` library (Levenshtein-based)
4. Match if score exceeds threshold (TBD by manual inspection, bias toward avoiding false positives)

**Manual Override Dictionary** (hardcoded in ETL script):
```python
TITLE_OVERRIDES = {
    "Boku no Hero": 123456,  # Maps to specific AniList ID
    "Dungeon Meshi": 789012,
    # ... add cases as needed during tuning
}
```

**Matching Strategy**:
- Check override dictionary first
- Then try fuzzy match against: romaji, english, synonyms
- Take highest scoring match above threshold
- Record match method (`exact`, `fuzzy`, `manual_override`) for debugging

**Unmatched Torrents**: Output diagnostic log with:
- Count of unmatched torrents
- Sample of unmatched titles
- Distribution of match scores for inspection

#### Step 4: Episode Attribution

- Extract `episode` number from `guessit_data`
- **Single episode torrents**: Use episode number directly
- **Batch torrents**: Skipped in Step 2
- **Special episodes**: TBD - investigate AniList schema and guessit patterns
  - Episode 0, decimals (e.g., 6.5 for recaps), OVAs
  - Requires further research during implementation

#### Step 5: Download Delta Calculation

For each torrent, calculate download increments between scrapes:

```python
for infohash in matched_torrents:
    stats = get_stats_ordered_by_timestamp(infohash)
    for i in range(1, len(stats)):
        delta = stats[i].downloads - stats[i-1].downloads
        if delta > 0:  # Only positive deltas (downloads increase monotonically)
            yield (infohash, stats[i].timestamp, delta)
```

**Aggregation**: Sum deltas across all torrents for same `(anilist_id, episode)` pair.

**Assumption**: Average viewer downloads only one version per episode (doesn't download both 720p and 1080p, or multiple fansub groups). This makes summing across torrents a reasonable proxy for unique viewers.

#### Step 6: Time Normalization

**Per-episode normalization**:
- Find `first_torrent_timestamp` = earliest `pubdate` across all torrents for that `(anilist_id, episode)`
- For each data point, calculate:
  ```python
  days_since_first_torrent = (timestamp - first_torrent_timestamp).total_seconds() / 86400
  ```
- This aligns all episodes to a common timeline (T=0 at first release)

**Purpose**: Allows comparing episode performance without being affected by different air dates or release timing.

#### Step 7: Daily Aggregation (for per-show charts)

Group by `(anilist_id, episode, date)` where `date = floor(timestamp to day)`:
- Sum download deltas per day
- Calculate cumulative downloads per episode

**Output**: Episode-level daily time series

#### Step 8: Weekly Ranking (for bump chart)

**Calendar Week Aggregation**:
- Use ISO week numbering (Monday start, format: `2025-W40`)
- Group by `(anilist_id, iso_week)`
- Sum total downloads per show per week

**Ranking**:
- Within each week, rank shows by total downloads (1 = highest)
- Track week-over-week rank changes for bump chart transitions

**Post-Airing Cutoff** (TBD for MVP):
- Detect when show finishes airing (last episode + N weeks buffer, probably 4-6 weeks)
- Option A: Use AniList `status = 'FINISHED'` + buffer
- Option B: Detect last episode from `airingSchedule` + buffer
- Truncate data collection at cutoff for cleaner charts (post-airing downloads less interesting)

### 3.3 Output Files

#### `episodes.parquet`
Detailed per-episode time series for show detail pages.

**Schema**:
```
anilist_id (int64): AniList show ID
episode (int32): Episode number
date (timestamp): Aggregated daily timestamp
downloads_daily (int32): Downloads on this day for this episode
downloads_cumulative (int32): Cumulative downloads for this episode up to this date
days_since_first_torrent (float64): Normalized time axis
title (string): Show title (for convenience, denormalized)
```

**Sorted by**: `anilist_id`, `episode`, `date`

**Size estimate**: ~100 shows × ~12 episodes × ~60 days = ~72k rows (very manageable)

#### `rankings.json`
Pre-aggregated weekly ranking data for front page bump chart.

**Schema**:
```json
{
  "season": "Fall 2025",
  "weeks": [
    {
      "week": "2025-W40",
      "start_date": "2025-10-06",
      "rankings": [
        {
          "anilist_id": 123,
          "rank": 1,
          "downloads": 50000,
          "title": "Show A",
          "title_romaji": "Show A Romaji"
        },
        {
          "anilist_id": 456,
          "rank": 2,
          "downloads": 45000,
          "title": "Show B",
          "title_romaji": "Show B Romaji"
        }
      ]
    }
  ]
}
```

**Size estimate**: ~12 weeks × ~50 top shows = ~600 entries (small enough to potentially inline in HTML)

## 4. Data Models (ETL Intermediate)

### Python Dataclasses

```python
@dataclass
class AniListShow:
    """Metadata from AniList API."""
    id: int
    title_romaji: str
    title_english: str | None
    synonyms: list[str]
    episodes: int | None
    status: str
    airing_schedule: list[tuple[int, datetime]]  # (episode, air_date)

@dataclass
class MatchedTorrent:
    """Torrent matched to AniList show and episode."""
    infohash: str
    anilist_id: int
    episode: int
    pubdate: datetime
    guessit_title: str
    matched_method: str  # "exact" | "fuzzy" | "manual_override"
    match_score: float | None  # Fuzzy match score (0-100)

@dataclass
class EpisodeStats:
    """Aggregated statistics per episode and date."""
    anilist_id: int
    episode: int
    date: date
    downloads_daily: int
    downloads_cumulative: int
    days_since_first_torrent: float

@dataclass
class WeeklyRanking:
    """Weekly ranking for bump chart."""
    week: str  # ISO week "2025-W40"
    anilist_id: int
    rank: int
    downloads: int
    title: str
    title_romaji: str
```

## 5. Frontend Components (Observable Framework)

### 5.1 Technology Stack
- **Observable Framework**: Static site generator with reactive data
- **Parquet WASM** + **Arquero**: Load and query Parquet client-side (lightweight, no DuckDB overhead)
- **Observable Plot**: Declarative visualization library
- **Hosting**: Static hosting (Vercel, Cloudflare Pages, GitHub Pages, etc.)

### 5.2 Front Page (`/`)

**Bump Chart Specification**:
- **Y-axis (vertical)**: Time (calendar weeks, top = earliest, bottom = latest)
- **X-axis (horizontal)**: Rank (1 = leftmost/most prominent)
- **Lines**: Show rank movement week-over-week, colored by show
- **River width**: Line thickness scales linearly with download count
  - Area under curve directly proportional to weekly downloads
  - Minimum thickness for visibility
- **Mobile-friendly**: Vertical layout fits mobile viewport naturally

**Data Loading**:
```javascript
const rankings = FileAttachment("data/rankings.json").json();
```

**Interactions**:
- Hover to see show name, rank, download count
- Click to navigate to show detail page

### 5.3 Show Detail Page (`/show/:anilist_id`)

**Header**:
- Show title (romaji, english)
- Poster image (from AniList API, check caching policies)
- Metadata: Episode count, airing status, AniList link

**Stacked Area Chart**:
- **X-axis**: Days since first torrent release (normalized time)
- **Y-axis (primary)**: Daily downloads
- **Y-axis (secondary)**: Cumulative downloads
- **Layers**: Each episode is a colored band (stacked area)
- **Purpose**: Visualize episode-by-episode download patterns

**Stats Table**:
- Daily average downloads
- Weekly average downloads
- Total downloads
- Current seasonal rank (or final rank if finished airing)

**Data Loading**:
```javascript
const episodes = FileAttachment("data/episodes.parquet").parquet();
const showData = episodes.filter(d => d.anilist_id === params.anilist_id);
```

### 5.4 Observable Data Loaders (Future Option)

Observable Framework supports [data loaders](https://observablehq.com/framework/loaders) that can run Python scripts as part of the build process. For MVP, we use standalone ETL (Option A), but could migrate to integrated loaders (Option B) later:

**Option B (future)**:
- Create `website/src/data/episodes.parquet.py`
- Observable runs this automatically on build
- Requires database access during build (more complex deployment)

## 6. File Structure (New Additions)

```
nyaastats/
├── nyaastats/
│   ├── etl/                      # New ETL module
│   │   ├── __init__.py
│   │   ├── anilist_client.py    # GraphQL queries, rate limiting
│   │   ├── fuzzy_matcher.py     # Title matching with thefuzz
│   │   ├── aggregator.py        # Download aggregation logic
│   │   ├── exporter.py          # Parquet/JSON export
│   │   └── config.py            # ETL configuration (season dates, thresholds)
│   ├── etl_main.py              # Entry point: python -m nyaastats.etl_main
│   └── ...                       # Existing scraper code
├── website/                      # Observable Framework site (new)
│   ├── src/
│   │   ├── index.md             # Front page (bump chart)
│   │   ├── show.md              # Show detail template
│   │   └── data/
│   │       ├── episodes.parquet  # Generated by ETL
│   │       └── rankings.json     # Generated by ETL
│   ├── observablehq.config.js   # Framework config
│   └── package.json
├── scripts/
│   └── generate_fake_data.py    # Generate synthetic data for development
├── tests/
│   ├── test_etl/                # ETL tests (new)
│   │   ├── test_anilist_client.py
│   │   ├── test_fuzzy_matcher.py
│   │   ├── test_aggregator.py
│   │   └── test_exporter.py
│   └── ...
├── pyproject.toml               # Add new deps: pyarrow, thefuzz, gql
├── PIPELINE_DESIGN.md           # This document
└── README.md
```

## 7. Dependencies (New)

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing deps
    "pyarrow>=15.0.0",        # Parquet export
    "thefuzz>=0.20.0",        # Fuzzy string matching
    "python-Levenshtein>=0.21.0",  # Faster fuzzy matching
    "gql>=3.5.0",             # GraphQL client
    "aiohttp>=3.9.0",         # Async HTTP for gql
]
```

## 8. Implementation Phases

### Phase 1: Fake Data Generator
- [ ] Script to generate synthetic `nyaastats.db` with realistic data
- [ ] Useful for development and testing without production database
- [ ] Should mimic real data structure: torrents with guessit metadata, time-series stats

### Phase 2: ETL Core
- [ ] AniList GraphQL client with rate limiting
- [ ] Fuzzy matching module with thefuzz
- [ ] Torrent filtering logic (batches, v2, date range)
- [ ] Episode attribution from guessit
- [ ] Download delta calculation

### Phase 3: Aggregation & Export
- [ ] Daily episode aggregation
- [ ] Weekly ranking calculation
- [ ] Time normalization logic
- [ ] Parquet export with pyarrow
- [ ] JSON export for bump chart
- [ ] Manual tuning of fuzzy match threshold with real data

### Phase 4: Observable Framework Scaffold
- [ ] Initialize Observable Framework project
- [ ] Front page with rankings.json loaded
- [ ] Show detail page routing and data loading
- [ ] Basic chart placeholders

### Phase 5: Visualizations
- [ ] Bump chart with river width encoding
- [ ] Stacked area charts for episodes
- [ ] Styling and mobile responsiveness
- [ ] Metadata integration (AniList posters, links)

### Phase 6: Deployment
- [ ] CI/CD for ETL (weekly runs)
- [ ] Static site deployment
- [ ] Production testing with Fall 2025 data

## 9. Open Questions & Research Items

### For Implementation Phase

1. **AniList Special Episodes**: How does AniList represent OVAs, specials, and episode 0? Does `airingSchedule` include them?

2. **Guessit Edge Cases**: What does guessit output for:
   - Episode 0 (pre-air specials)
   - Decimal episodes (6.5 for recaps)
   - Missing episode numbers
   - OVA labeling

3. **Fuzzy Match Threshold**: What score (0-100) provides good precision/recall? Requires manual inspection of ~100 Fall 2025 shows.

4. **Post-Airing Cutoff**: How many weeks after final episode should data collection stop? 4 weeks? 6 weeks? Based on diminishing download activity.

5. **AniList Caching Policy**: Can we cache poster images and metadata locally/on CDN, or must we hotlink? Check AniList API ToS.

### Future Enhancements (Post-MVP)

- **Multi-season support**: Remove Fall 2025 hardcoding, support Winter 2026+
- **Incremental ETL**: Process only new data since last run (checkpointing)
- **Resolution/group breakdowns**: Add dimensions to Parquet (filter by 1080p vs 720p, etc.)
- **Local AniList cache**: SQLite table to reduce API calls
- **Manual matching UI**: Web interface to override fuzzy matches
- **Historical comparisons**: Compare show performance across seasons
- **Ongoing vs finished segmentation**: Separate treatment for airing vs completed shows

## 10. Success Metrics (MVP)

- **ETL Success Rate**: >90% of torrents successfully matched to AniList IDs
- **False Positive Rate**: <5% incorrect matches (manual inspection)
- **Data Completeness**: All Fall 2025 shows with >1000 downloads represented
- **Website Performance**: Front page loads in <2s, show pages in <1s (on good connection)
- **Mobile Usability**: Bump chart readable on mobile viewport without horizontal scroll

## 11. Non-Goals (Explicitly Out of Scope for MVP)

- Real-time updates (ETL runs weekly, not live)
- User accounts or personalization
- Commenting or social features
- Comparison across multiple seasons
- Raw data download or API access
- Search functionality (small dataset, can browse)
- Filter by resolution, fansub group, codec
- Ongoing show special handling (post-airing cutoff TBD)
