# Show Statistics

```js
// Get show ID from URL parameters
const params = new URLSearchParams(window.location.search);
const anilistId = parseInt(params.get("id")) || null;

if (!anilistId) {
  display(html`<div class="warning">No show ID specified. <a href="/">Return to rankings</a></div>`);
}
```

```js
// Load episode data
const episodes = FileAttachment("data/episodes.parquet").parquet();
```

```js
// Filter data for this show
const showData = anilistId ? episodes.filter(d => d.anilist_id === anilistId) : [];

if (showData.length === 0 && anilistId) {
  display(html`<div class="warning">Show not found. <a href="/">Return to rankings</a></div>`);
}
```

```js
// Get show metadata
const showTitle = showData.length > 0 ? showData[0].title : "Unknown Show";
const showTitleRomaji = showData.length > 0 ? showData[0].title_romaji : "";

display(html`
  <div class="show-header">
    <h1>${showTitle}</h1>
    ${showTitleRomaji !== showTitle ? html`<h2 class="subtitle">${showTitleRomaji}</h2>` : ""}
    <p><a href="https://anilist.co/anime/${anilistId}" target="_blank">View on AniList →</a></p>
  </div>
`);
```

## Download Statistics

```js
// Calculate summary stats
const totalDownloads = showData.reduce((sum, d) => sum + d.downloads_daily, 0);
const uniqueEpisodes = new Set(showData.map(d => d.episode)).size;
const latestDate = showData.length > 0 ?
  new Date(Math.max(...showData.map(d => new Date(d.date)))).toLocaleDateString() :
  "N/A";

display(html`
  <div class="stats-summary">
    <div class="stat">
      <div class="stat-value">${totalDownloads.toLocaleString()}</div>
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

## Daily Downloads by Episode

This stacked area chart shows daily download activity for each episode.

```js
import * as Plot from "@observablehq/plot";

if (showData.length > 0) {
  display(Plot.plot({
    width: 1200,
    height: 600,
    marginLeft: 60,
    marginRight: 100,

    x: {
      label: "Date",
      type: "utc"
    },

    y: {
      label: "Daily Downloads",
      grid: true
    },

    color: {
      legend: true,
      domain: [...new Set(showData.map(d => d.episode))].sort((a, b) => a - b),
      scheme: "spectral",
      label: "Episode"
    },

    marks: [
      // Stacked area chart
      Plot.areaY(showData, {
        x: "date",
        y: "downloads_daily",
        fill: "episode",
        curve: "basis",
        tip: true
      }),

      // Rule at y=0
      Plot.ruleY([0])
    ]
  }));
}
```

## Cumulative Downloads

```js
// Group by episode and get final cumulative value
const episodeStats = Array.from(
  d3.group(showData, d => d.episode),
  ([episode, values]) => {
    const sorted = values.sort((a, b) => new Date(a.date) - new Date(b.date));
    const latest = sorted[sorted.length - 1];
    return {
      episode,
      cumulative_downloads: latest.downloads_cumulative,
      days_tracked: Math.max(...values.map(v => v.days_since_first_torrent))
    };
  }
).sort((a, b) => a.episode - b.episode);

display(Plot.plot({
  width: 1200,
  height: 400,
  marginLeft: 60,

  x: {
    label: "Episode",
    domain: episodeStats.map(d => d.episode)
  },

  y: {
    label: "Cumulative Downloads",
    grid: true
  },

  marks: [
    Plot.barY(episodeStats, {
      x: "episode",
      y: "cumulative_downloads",
      fill: "steelblue",
      tip: true
    }),

    Plot.ruleY([0])
  ]
}));
```

## Episode Details

```js
display(Inputs.table(episodeStats, {
  columns: ["episode", "cumulative_downloads", "days_tracked"],
  header: {
    episode: "Episode",
    cumulative_downloads: "Total Downloads",
    days_tracked: "Days Tracked"
  },
  format: {
    cumulative_downloads: d => d.toLocaleString(),
    days_tracked: d => Math.round(d)
  },
  sort: "episode",
  reverse: false
}));
```

---

<div class="note">
  <a href="/">← Back to Rankings</a>
</div>

<style>
  .show-header {
    margin-bottom: 2rem;
  }

  .subtitle {
    color: #888;
    font-weight: normal;
    font-size: 1.2rem;
    margin-top: 0.5rem;
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
</style>
