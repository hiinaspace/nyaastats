---
toc: false
---

# Nyaastats: Movies

```js
const moviesData = FileAttachment("data/movies.json").json();
```

```js
const { movies } = moviesData;

function formatCompact(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
  return String(n);
}

const maxDownloads = d3.max(movies, (m) => m.total_downloads) || 1;
const plotWidth = Math.max(720, Math.min(1600, width));

const showColors = Object.fromEntries(
  movies.map((m) => [m.anilist_id, m.cover_image_color || "#4a9eff"])
);
```

```js
// Movie table
const table = Inputs.table(movies, {
  columns: [
    "cover_image_url",
    "title_romaji",
    "total_downloads",
    "first_torrent_date",
  ],
  header: {
    cover_image_url: "",
    title_romaji: "Title",
    total_downloads: "Total Downloads",
    first_torrent_date: "Release Date",
  },
  format: {
    cover_image_url: (url) =>
      url
        ? html`<img
            src="${url}"
            style="height:45px;border-radius:4px;object-fit:cover"
          />`
        : "",
    title_romaji: (_, i, data) => {
      const m = data[i];
      const romaji = m.title_romaji || "";
      const english =
        m.title && m.title !== m.title_romaji ? m.title : "";
      return html`<div style="max-width:280px">
        <a
          href="https://anilist.co/anime/${m.anilist_id}"
          target="_blank"
          style="color:#4a9eff;text-decoration:none;font-weight:500"
          >${romaji}</a
        >
        ${english
          ? html`<div style="font-size:10px;color:#888;margin-top:2px">
              ${english}
            </div>`
          : ""}
      </div>`;
    },
    total_downloads: (_, i, data) => {
      const m = data[i];
      const color = showColors[m.anilist_id] || "#4a9eff";
      const base = d3.hsl(color);
      const muted = base
        .copy({
          s: Math.min(0.5, base.s),
          l: Math.max(0.25, base.l * 0.55),
        })
        .formatHex();
      return html`<div
        style="
        background: ${muted};
        color: #fff;
        text-shadow: 0 0 3px rgba(0,0,0,0.8), 1px 1px 2px rgba(0,0,0,0.8);
        font: 10px/1.6 var(--sans-serif);
        width: ${Math.min(100, (100 * m.total_downloads) / maxDownloads)}%;
        float: right;
        padding-right: 4px;
        box-sizing: border-box;
        overflow: visible;
        display: flex;
        justify-content: end;"
      >
        ${m.total_downloads.toLocaleString("en-US")}
      </div>`;
    },
    first_torrent_date: (d) =>
      d
        ? new Date(d).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
            timeZone: "UTC",
          })
        : "—",
  },
  width: {
    cover_image_url: 55,
    title_romaji: 280,
    total_downloads: 180,
    first_torrent_date: 130,
  },
  rows: 20,
});
display(table);
```

---

```js
// Cumulative downloads over time, aligned to week 0 = release
const cumulativeData = movies.flatMap((m) =>
  m.weekly_downloads.map((d) => ({
    anilist_id: m.anilist_id,
    title_romaji: m.title_romaji,
    weeks_since_release: d.weeks_since_release,
    downloads_cumulative: d.downloads_cumulative,
  }))
);

const maxWeeks = d3.max(cumulativeData, (d) => d.weeks_since_release) || 10;

display(
  Plot.plot({
    title: "Cumulative Downloads Since Release",
    subtitle: "Week 0 = first torrent appearance on Nyaa",
    height: 450,
    width: plotWidth,
    marginLeft: 70,
    marginRight: 150,
    y: {
      label: "Cumulative Downloads",
      grid: true,
      tickFormat: (d) => formatCompact(d),
    },
    x: {
      label: "Weeks Since Release",
      domain: [0, maxWeeks],
    },
    color: {
      legend: true,
      domain: movies.map((m) => m.title_romaji),
      range: movies.map((m) => showColors[m.anilist_id] || "#4a9eff"),
    },
    marks: [
      Plot.line(cumulativeData, {
        x: "weeks_since_release",
        y: "downloads_cumulative",
        z: "anilist_id",
        stroke: "title_romaji",
        strokeWidth: 2.5,
        curve: "monotone-x",
      }),
      Plot.tip(
        cumulativeData,
        Plot.pointer({
          x: "weeks_since_release",
          y: "downloads_cumulative",
          title: (d) =>
            `${d.title_romaji}\nWeek ${d.weeks_since_release}\n${formatCompact(d.downloads_cumulative)} cumulative`,
        })
      ),
      Plot.ruleY([0]),
    ],
  })
);
```

---

```js
// Absolute weekly downloads (calendar time)
const weeklyData = movies.flatMap((m) =>
  m.weekly_downloads
    .filter((d) => d.week_start)
    .map((d) => ({
      anilist_id: m.anilist_id,
      title_romaji: m.title_romaji,
      week_start: d.week_start,
      downloads_weekly: d.downloads_weekly,
    }))
);

display(
  Plot.plot({
    title: "Weekly Downloads",
    subtitle: "Downloads per week (absolute calendar time)",
    height: 450,
    width: plotWidth,
    marginLeft: 70,
    marginRight: 150,
    marginBottom: 50,
    y: {
      label: "Downloads per Week",
      grid: true,
      tickFormat: (d) => formatCompact(d),
    },
    x: {
      label: null,
      type: "utc",
      tickRotate: -30,
      tickFormat: (d) =>
        new Date(d).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        }),
    },
    color: {
      legend: true,
      domain: movies.map((m) => m.title_romaji),
      range: movies.map((m) => showColors[m.anilist_id] || "#4a9eff"),
    },
    marks: [
      Plot.line(weeklyData, {
        x: "week_start",
        y: "downloads_weekly",
        z: "anilist_id",
        stroke: "title_romaji",
        strokeWidth: 2,
        curve: "monotone-x",
      }),
      Plot.tip(
        weeklyData,
        Plot.pointer({
          x: "week_start",
          y: "downloads_weekly",
          title: (d) =>
            `${d.title_romaji}\nWeek of ${d.week_start}\n${formatCompact(d.downloads_weekly)} downloads`,
        })
      ),
      Plot.ruleY([0]),
    ],
  })
);
```

<style>
  table {
    font-size: 0.85rem;
  }
  th {
    font-weight: 600;
  }
  td {
    vertical-align: top;
    padding: 4px 8px !important;
  }
  td img {
    display: block;
  }
  a:hover {
    text-decoration: underline !important;
  }
</style>
