# ${showMeta?.title_romaji || "Show Statistics"}

```js
// Get show ID from route params
const anilistId = observable.params.id;
```

```js
// Load data
const episodesRaw = FileAttachment("../data/episodes.parquet").parquet();
const showsData = FileAttachment("../data/shows.json").json();
```

```js
// Use Arquero to filter episodes for this show
const episodes = aq.from(episodesRaw);
const showData = episodes.filter(aq.escape(d => d.anilist_id == anilistId));

// Find show metadata from shows.json
const allShows = Object.values(showsData).flat();
const showMeta = allShows.find(s => String(s.id) === String(anilistId));
```

```js
// Show header with poster
const showDataArray = showData.objects();
const title = showMeta?.title_romaji || (showDataArray.length > 0 ? showDataArray[0].title : "Unknown Show");
const titleEnglish = showMeta?.title || (showDataArray.length > 0 ? showDataArray[0].title_english : "");
const coverUrl = showMeta?.cover_image_url;
const coverColor = showMeta?.cover_image_color || "#1a1a2e";
const currentRank = showMeta?.rank;

display(html`
  <div class="show-header">
    <div class="show-header-content">
      ${coverUrl ? html`<img src="${coverUrl}" alt="${title}" class="show-poster" />` : ""}
      <div class="show-info">
        <h1>${title}</h1>
        ${titleEnglish && titleEnglish !== title ? html`<h2 class="subtitle">${titleEnglish}</h2>` : ""}
        ${currentRank ? html`<p class="rank">Current Rank: <strong>#${currentRank}</strong></p>` : ""}
        <p><a href="https://anilist.co/anime/${anilistId}" target="_blank">View on AniList →</a></p>
      </div>
    </div>
  </div>
`);
```

```js
// Handle missing data
if (showData.numRows() === 0) {
  display(html`<div class="warning">No download data found for this show. <a href="/">Return to rankings</a></div>`);
}
```

## Download Statistics

```js
// Calculate summary stats using Arquero
const { op } = aq;
const totalDownloads = showData.rollup({ total: d => op.sum(d.downloads_daily) }).get("total", 0) || 0;
const uniqueEpisodes = showData.rollup({ count: d => op.distinct(d.episode) }).get("count", 0) || 0;
const latestDate = showData.numRows() > 0
  ? new Date(showData.rollup({ max: d => op.max(d.date) }).get("max", 0)).toLocaleDateString()
  : "N/A";

display(html`
  <div class="stats-summary">
    <div class="stat">
      <div class="stat-value">${Number(totalDownloads).toLocaleString()}</div>
      <div class="stat-label">Total Downloads</div>
    </div>
    <div class="stat">
      <div class="stat-value">${uniqueEpisodes}</div>
      <div class="stat-label">Episodes</div>
    </div>
    <div class="stat">
      <div class="stat-value">${latestDate}</div>
      <div class="stat-label">Latest Data</div>
    </div>
  </div>
`);
```

## Downloads by Episode

```js
// Calculate first week vs rest downloads per episode
const { op: op2 } = aq;

// Sum downloads for first 7 days and after
const episodeBreakdown = showData
  .derive({
    period: aq.escape(d => d.days_since_first_torrent <= 7 ? "First Week" : "After First Week")
  })
  .groupby("episode", "period")
  .rollup({
    downloads: d => op2.sum(d.downloads_daily)
  })
  .orderby("episode", "period");

const stackedData = episodeBreakdown.objects().map(d => ({
  episode: Number(d.episode),
  period: d.period,
  downloads: Number(d.downloads)
}));

// Also get totals per episode for the table
const episodeStats = showData
  .groupby("episode")
  .rollup({
    cumulative_downloads: d => op2.max(d.downloads_cumulative),
    days_tracked: d => op2.max(d.days_since_first_torrent)
  })
  .orderby("episode");
```

```js
// Stacked bar chart: first week vs rest
if (stackedData.length > 0) {
  display(Plot.plot({
    width: 1000,
    height: 400,
    marginLeft: 60,
    marginBottom: 40,

    x: {
      label: "Episode",
      tickFormat: d => d
    },

    y: {
      label: "Downloads",
      grid: true
    },

    color: {
      domain: ["First Week", "After First Week"],
      range: [coverColor, "#666"],
      legend: true
    },

    marks: [
      Plot.barY(stackedData, {
        x: "episode",
        y: "downloads",
        fill: "period",
        order: d => d.period === "First Week" ? 0 : 1,
        tip: true
      }),
      Plot.ruleY([0])
    ]
  }));
}
```

## Episode Details

```js
if (episodeStats.numRows() > 0) {
  display(Inputs.table(episodeStats, {
    columns: ["episode", "cumulative_downloads", "days_tracked"],
    header: {
      episode: "Episode",
      cumulative_downloads: "Total Downloads",
      days_tracked: "Days Tracked"
    },
    format: {
      cumulative_downloads: d => Number(d).toLocaleString(),
      days_tracked: d => Math.round(Number(d))
    },
    sort: "episode",
    reverse: false
  }));
}
```

---

<div class="note">
  <a href="/">← Back to Rankings</a>
</div>

<style>
  .show-header {
    margin-bottom: 2rem;
  }

  .show-header-content {
    display: flex;
    gap: 1.5rem;
    align-items: flex-start;
  }

  .show-poster {
    width: 180px;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }

  .show-info {
    flex: 1;
  }

  .show-info h1 {
    margin: 0 0 0.5rem 0;
  }

  .subtitle {
    color: #888;
    font-weight: normal;
    font-size: 1.2rem;
    margin: 0 0 0.5rem 0;
  }

  .rank {
    font-size: 1.1rem;
    margin: 0.5rem 0;
  }

  .rank strong {
    color: #4a9eff;
  }

  .stats-summary {
    display: flex;
    gap: 2rem;
    margin: 2rem 0;
    padding: 1rem;
    background: #1a1a1a;
    border-radius: 8px;
  }

  .stat {
    flex: 1;
    text-align: center;
  }

  .stat-value {
    font-size: 2rem;
    font-weight: bold;
    color: #4a9eff;
  }

  .stat-label {
    color: #888;
    margin-top: 0.5rem;
  }

  .warning {
    padding: 1rem;
    background: #442;
    border-radius: 8px;
    margin: 1rem 0;
  }
</style>
