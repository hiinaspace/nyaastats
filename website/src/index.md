# Nyaa Download Rankings

<div class="note">
  Tracking download statistics for Fall 2025 and Winter 2026 anime seasons.
  Data updates weekly.
</div>

## Weekly Rankings

This bump chart shows how anime rankings change week over week, with line thickness proportional to download volume.

```js
// Load rankings data
const rankings = FileAttachment("data/rankings.json").json();
```

```js
// Display season info
display(html`<h3>${rankings.season}</h3>`);
display(html`<p>${rankings.weeks.length} weeks of data</p>`);
```

```js
// Prepare data for bump chart with strokeWidth channel
const bumpData = rankings.weeks.flatMap(week =>
  week.rankings.map(r => ({
    week: week.week,
    anilist_id: r.anilist_id,
    rank: r.rank,
    downloads: r.downloads,
    title: r.title,
    title_romaji: r.title_romaji,
    // Pre-calculate stroke width for line thickness
    strokeWidth: Math.sqrt(r.downloads) / 20
  }))
);
```

```js
// Bump chart visualization
// Proper bump chart: X-axis = time (weeks), Y-axis = rank (reversed, rank 1 at top)

import * as Plot from "@observablehq/plot";

display(Plot.plot({
  width: 1200,
  height: 800,
  marginLeft: 60,
  marginRight: 200,

  x: {
    label: "Week →",
    domain: rankings.weeks.map(w => w.week),
    tickFormat: d => d
  },

  y: {
    label: "Rank",
    domain: [1, 20],
    reverse: true // Rank 1 at top
  },

  color: {
    legend: true,
    domain: [...new Set(bumpData.map(d => d.title))],
    scheme: "tableau10"
  },

  marks: [
    // Lines connecting ranks week-over-week
    Plot.line(bumpData, {
      x: "week",
      y: "rank",
      stroke: "title",
      strokeWidth: "strokeWidth", // Use pre-calculated strokeWidth channel
      curve: "catmull-rom",
      tip: true
    }),

    // Points at each week
    Plot.dot(bumpData, {
      x: "week",
      y: "rank",
      fill: "title",
      r: 4,
      tip: {
        format: {
          x: false,
          y: false,
          title: true,
          downloads: true
        }
      }
    }),

    // Rank gridlines
    Plot.ruleY([1, 5, 10, 15, 20], {stroke: "#333", strokeDasharray: "2,2"})
  ]
}));
```

## Top Shows This Week

```js
// Get latest week's rankings
const latestWeek = rankings.weeks[rankings.weeks.length - 1];

display(html`<h3>Week ${latestWeek.week}</h3>`);

// Create a table of top shows
const topShows = latestWeek.rankings.slice(0, 20);

display(Inputs.table(topShows, {
  columns: ["rank", "title", "downloads"],
  header: {
    rank: "Rank",
    title: "Show",
    downloads: "Downloads"
  },
  format: {
    downloads: d => d.toLocaleString()
  },
  width: {
    rank: 60,
    title: 400,
    downloads: 120
  }
}));
```

---

<div class="note">
  Data source: Nyaa.si torrent tracker. Statistics aggregated from tracker scrapes.
  Click on a show in the chart to see detailed episode breakdowns.
</div>
