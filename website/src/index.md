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
// Prepare data for bump chart
const bumpData = rankings.weeks.flatMap(week =>
  week.rankings.map(r => ({
    week: week.week,
    anilist_id: r.anilist_id,
    rank: r.rank,
    downloads: r.downloads,
    title: r.title,
    title_romaji: r.title_romaji
  }))
);
```

```js
// Bump chart visualization
// TODO: Implement river-width bump chart
// For now, show a simple line chart with rank over time

import * as Plot from "@observablehq/plot";

display(Plot.plot({
  width: 1200,
  height: 800,
  marginLeft: 200,
  marginRight: 150,

  y: {
    label: "Week →",
    reverse: false, // Latest at top per design doc
    domain: rankings.weeks.map(w => w.week),
    tickFormat: d => d
  },

  x: {
    label: "Rank",
    domain: [1, 20],
    reverse: false // Rank 1 at left
  },

  color: {
    legend: true,
    domain: [...new Set(bumpData.map(d => d.title))],
    scheme: "tableau10"
  },

  marks: [
    // Lines connecting ranks week-over-week
    Plot.line(bumpData, {
      x: "rank",
      y: "week",
      stroke: "title",
      strokeWidth: d => Math.sqrt(d.downloads) / 20, // Scale by downloads
      curve: "catmull-rom",
      tip: true
    }),

    // Points at each week
    Plot.dot(bumpData, {
      x: "rank",
      y: "week",
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

    // Rank axis
    Plot.ruleX([1, 5, 10, 15, 20], {stroke: "#333", strokeDasharray: "2,2"})
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
