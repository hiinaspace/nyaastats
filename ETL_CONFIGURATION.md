# ETL Configuration and Season Matching

This document contains detailed configuration information for the nyaastats ETL pipeline.

## Overview

The ETL pipeline uses a three-layer enhancement strategy for matching torrents to AniList shows.

## AniList API Rate Limiting

The ETL pipeline includes robust rate limiting and retry logic for AniList API queries:

- **Per-page delay**: 1 second between pages (conservative 60 req/min, well below 90 req/min limit)
- **Between seasons**: 2 second delay between fetching different seasons
- **Retry logic**: 3 attempts with exponential backoff (1s, 2s, 4s) for transient failures
- **Error handling**: Graceful failure with detailed logging

This prevents 500 errors from rate limiting during large queries.

## Layer 1: Title Corrections (Pre-processing)

Fixes systematic guessit parsing errors before matching. Configured in `nyaastats/etl/title_corrections.py`:

```python
TITLE_CORRECTIONS = {
    "oshi no": "oshi no ko",  # Guessit drops "Ko" (false Korean detection)
    # Add more corrections as discovered
}
```

**When to add corrections:**
- Guessit consistently misparses a show title
- Common parsing errors affecting multiple releases

## Layer 2: Season-Aware Matching

Uses season markers from guessit to prefer correct season entries in AniList. Automatically applied when guessit provides integer season numbers.

**How it works:**
- Extracts season number from guessit_data
- Boosts fuzzy match score for shows with matching season indicators in title
- Falls back to season-agnostic matching if no match found

**Example:** "One-Punch Man S3" with season=3 will prefer "One-Punch Man Season 3" over "One-Punch Man Season 2"

## Layer 3: Episode-Range Mapping (Continuing Series)

Maps continuous episode numbers to specific season AniList IDs. Configured in `nyaastats/etl/config.py`:

```python
EPISODE_SEASON_MAPPINGS = {
    "spy x family": [
        (26, 50, 177937),  # Season 3 (Fall 2025) - eps 26+ map to S3
    ],
    "jujutsu kaisen": [
        (48, 75, 172463),  # Season 3: The Culling Game Part 1 (Winter 2026)
    ],
}
```

**When to add episode mappings:**
- Shows with continuous episode numbering across seasons
- Use database query to find episode ranges per show
- Look up AniList IDs for each season

**Finding episode ranges:**
```sql
SELECT
    json_extract(guessit_data, '$.title') as title,
    MIN(CAST(json_extract(guessit_data, '$.episode') AS INTEGER)) as min_ep,
    MAX(CAST(json_extract(guessit_data, '$.episode') AS INTEGER)) as max_ep
FROM torrents
WHERE json_extract(guessit_data, '$.title') = 'Show Name'
  AND json_extract(guessit_data, '$.episode') NOT LIKE '%[%'
GROUP BY title;
```

## Manual Title Overrides

For unmatchable titles or explicit mappings. Configured in `nyaastats/etl/config.py`:

```python
TITLE_OVERRIDES = {
    "oshi no ko": 182587,  # [Oshi no Ko] 3rd Season (Winter 2026)
    "yuushakei ni shosu": 167152,  # Sentenced to Be a Hero (Winter 2026)
}
```

**When to add overrides:**
- Fuzzy matching score below threshold due to long subtitles or different naming conventions
- Special characters or punctuation cause normalization issues

**Important:** Keys must be normalized (lowercase, no punctuation). Test normalization:
```python
import re
def normalize(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title
```

## Matching Priority Order

1. **Episode-range mapping** (highest priority) - for continuing series
2. **Manual overrides** - explicit title → AniList ID
3. **Season-aware fuzzy matching** - uses guessit season + title
4. **Season-agnostic fuzzy matching** (fallback) - title-only

## Configuration Files

- `nyaastats/etl/config.py` - Episode mappings, manual overrides, thresholds
- `nyaastats/etl/title_corrections.py` - Title parsing corrections

## Unmatched Torrents Report

The ETL pipeline generates `unmatched_torrents_report.json` showing the top 100 unmatched torrents by download count. Use this to identify:

- **Movies**: Often don't match seasonal shows (legitimate)
- **Continuing series**: Need episode-range mapping
- **Title variations**: Need manual overrides or corrections

## Maintenance Workflow

### 1. Run ETL and Check Unmatched Report

```bash
uv run nyaastats-etl --db nyaastats.db --output website/src/data
cat website/src/data/unmatched_torrents_report.json
```

The top 10 are also logged during ETL execution.

### 2. Investigate High-Download Unmatched Shows

For each unmatched show with significant downloads:

**A. Check if it's a movie or special:**
- Movies won't match seasonal TV shows (expected behavior)
- Consider adding movie support or filtering them out

**B. Test fuzzy matching score:**
```python
from thefuzz import fuzz
torrent_title = "normalized torrent title"
anilist_title = "normalized anilist title"
score = fuzz.token_sort_ratio(torrent_title, anilist_title)
print(f"Score: {score}, Threshold: 85")
```

If score < 85:
- Add to `TITLE_OVERRIDES` in `nyaastats/etl/config.py`

**C. Check for continuous episode numbering:**
```sql
SELECT
    json_extract(guessit_data, '$.title') as title,
    json_extract(guessit_data, '$.episode') as episode,
    pubdate
FROM torrents
WHERE json_extract(guessit_data, '$.title') = 'Show Name'
ORDER BY pubdate;
```

If episodes are numbered continuously across seasons:
- Add to `EPISODE_SEASON_MAPPINGS` in `nyaastats/etl/config.py`

**D. Check for guessit parsing errors:**
```sql
SELECT
    filename,
    json_extract(guessit_data, '$.title') as parsed_title
FROM torrents
WHERE filename LIKE '%Show Name%'
LIMIT 5;
```

If guessit consistently misparsed:
- Add to `TITLE_CORRECTIONS` in `nyaastats/etl/title_corrections.py`

### 3. Verify AniList IDs

Look up shows on https://anilist.co/ to find correct IDs:
- Search for the show
- Check the URL: `https://anilist.co/anime/{ID}/`
- Verify it's the correct season/year

### 4. Test Changes

```bash
uv run nyaastats-etl --db nyaastats.db --output website/src/data
```

Check the logs:
- Match methods should show increased counts for your changes
- Previously unmatched shows should no longer appear in top 10

### 5. Verify Episode Data

```python
import json
with open("website/src/data/episodes-{season}.json") as f:
    data = json.load(f)
    for ep in data:
        if ep["anilist_id"] == YOUR_ID:
            print(f"Ep {ep['episode']}: {ep['downloads_cumulative']:,} downloads")
```

## Troubleshooting

### "StructFieldNotFoundError: title"
The `extract_metadata()` function must always return a dict with all fields, never `None`.

### "Match score too low"
Fuzzy matching requires score ≥ 85. For lower scores, use manual overrides.

### "Episode not matching"
Check if episode numbering is continuous vs. seasonal. Use episode-range mapping for continuous numbering.

### "Rate limiting (500 errors)"
Increase delays in `anilist_client.py` or reduce number of seasons queried simultaneously.
