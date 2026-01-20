---
toc: false
---

# Nyaastats: __SEASON_TITLE__


```js
// Load precomputed seasonal data
const season = FileAttachment("../data/season-__SEASON_SLUG__.json").json();
const episodesData = FileAttachment("../data/episodes-__SEASON_SLUG__.json").json();
const seasonLabel = "__SEASON_LABEL__";
const seasonTitle = "__SEASON_TITLE__";
import {addWatermark} from "../components/watermark.js";
```

```js
// Destructure season data
const { weeks, shows: rawShows, percentiles, start_date, end_date } = season;

// Sort shows by total downloads to get season rank
const shows = [...rawShows].sort((a, b) => b.total_downloads - a.total_downloads);

// Add season rank to each show
shows.forEach((s, i) => { s.season_rank = i + 1; });

// Create lookup maps
const showLookup = new Map(shows.map(s => [s.anilist_id, s]));

// Show colors lookup
const showColors = Object.fromEntries(
  shows.map(s => [s.anilist_id, s.cover_image_color || "#4a9eff"])
);

// Flatten rankings for charts
const allRankings = weeks.flatMap(w =>
  w.rankings.map(r => ({
    ...r,
    weekStart: w.start_date,
    week: w.week
  }))
);

const weekLabels = weeks.map(w => w.start_date);

// Format number as K/M
function formatCompact(n) {
  if (n >= 1000000) return `${(n/1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n/1000).toFixed(0)}K`;
  return String(n);
}

// Max downloads for scaling bars
const maxDownloads = d3.max(shows, s => s.total_downloads) || 1;
const maxEndurance = d3.max(shows.filter(s => s.endurance && s.endurance > 0), s => s.endurance) || 1;
const maxLateStarters = d3.max(shows.filter(s => s.late_starters != null), s => s.late_starters) || 0.5;
const clampWidth = (value, min, max) => Math.max(min, Math.min(max, value || min));
const plotWidth = clampWidth(width, 720, 1600);

// Bucket shows by Episode 1 downloads (low/mid/high)
const ep1Values = shows.map(s => s.ep1_downloads).filter(d => d > 0).sort(d3.ascending);
const ep1Q1 = d3.quantile(ep1Values, 0.33) || 0;
const ep1Q2 = d3.quantile(ep1Values, 0.66) || ep1Q1;
const bucketOrder = [
  `Small premieres (<=${formatCompact(ep1Q1)})`,
  `Medium premieres (${formatCompact(ep1Q1)}-${formatCompact(ep1Q2)})`,
  `Big premieres (>=${formatCompact(ep1Q2)})`
];

function bucketLabel(ep1Downloads) {
  if (!ep1Downloads || ep1Downloads <= ep1Q1) return bucketOrder[0];
  if (ep1Downloads <= ep1Q2) return bucketOrder[1];
  return bucketOrder[2];
}
```

```js
// Calculate metrics needed for table
// Episode data by show for sparklines
const episodesByShow = d3.group(episodesData, d => d.anilist_id);

// Weekly rank data by show for sparklines
const weeklyRanksByShow = d3.group(allRankings, d => d.anilist_id);

// Metrics (endurance + late_starters) are precomputed in ETL
```

```js
// Selection comes from the table (treemap updates table selection)

// All shows are now pre-filtered by season in ETL
const filteredShows = shows;
```

```js
// Prepare data for treemap (filtered by toggle)
const treemapShows = filteredShows;
const treemapData = {
  name: "root",
  children: treemapShows.map(s => ({
    ...s,
    value: s.total_downloads
  }))
};

// Create treemap layout
const treemapWidth = plotWidth;
const treemapHeight = Math.round(treemapWidth * 0.56);

const treemapRoot = d3.hierarchy(treemapData)
  .sum(d => d.value)
  .sort((a, b) => b.value - a.value);

d3.treemap()
  .tile(d3.treemapSquarify.ratio(0.7))
  .size([treemapWidth, treemapHeight])
  .padding(2)
  .round(true)(treemapRoot);

// Create SVG
const treemapSvg = d3.create("svg")
  .attr("viewBox", [0, 0, treemapWidth, treemapHeight])
  .attr("width", treemapWidth)
  .attr("height", treemapHeight)
  .style("font-family", "system-ui, sans-serif");

// Define gradient
const treemapDefs = treemapSvg.append("defs");
const treemapGradientId = "treemap-text-gradient";
const treemapGradient = treemapDefs.append("linearGradient")
  .attr("id", treemapGradientId)
  .attr("x1", "0%").attr("y1", "0%")
  .attr("x2", "0%").attr("y2", "100%");
treemapGradient.append("stop")
  .attr("offset", "0%")
  .attr("stop-color", "rgba(0,0,0,0)");
treemapGradient.append("stop")
  .attr("offset", "100%")
  .attr("stop-color", "rgba(0,0,0,0.85)");

// Add cells with click handler
const treemapLeaf = treemapSvg.selectAll("g")
  .data(treemapRoot.leaves())
  .join("g")
  .attr("transform", d => `translate(${d.x0},${d.y0})`)
  .style("cursor", "pointer")
  .style("opacity", 1)
  .on("click", (event, d) => {
    event.stopPropagation();
    const id = d.data.anilist_id;
    toggleFocusedId(id);
  });

// Clip paths
treemapLeaf.append("clipPath")
  .attr("id", (d, i) => `treemap-clip-${i}`)
  .append("rect")
  .attr("width", d => d.x1 - d.x0)
  .attr("height", d => d.y1 - d.y0);

// Background rectangles
treemapLeaf.append("rect")
  .attr("width", d => d.x1 - d.x0)
  .attr("height", d => d.y1 - d.y0)
  .attr("fill", d => d.data.cover_image_color || "#1a1a2e")
  .attr("stroke", d => selectedIds.has(d.data.anilist_id) ? "#fff" : "#222")
  .attr("stroke-width", d => selectedIds.has(d.data.anilist_id) ? 3 : 1);

// Cover images
treemapLeaf.filter(d => d.data.cover_image_url)
  .append("image")
  .attr("href", d => d.data.cover_image_url)
  .attr("width", d => d.x1 - d.x0)
  .attr("height", d => d.y1 - d.y0)
  .attr("preserveAspectRatio", "xMidYMid slice")
  .attr("clip-path", (d, i) => `url(#treemap-clip-${i})`)
  .style("pointer-events", "none");

// Text background for top shows
const textBgHeight = 80;
treemapLeaf.filter((d, i) => i < 40)
  .append("rect")
  .attr("y", d => Math.max(0, (d.y1 - d.y0) - textBgHeight))
  .attr("width", d => d.x1 - d.x0)
  .attr("height", d => Math.min(d.y1 - d.y0, textBgHeight))
  .attr("fill", `url(#${treemapGradientId})`)
  .style("pointer-events", "none");

// Text styling
const textShadow = "0 0 3px black, 1px 1px 3px black";

// Helper: calculate text y positions from bottom
const getTextY = (d, line) => {
  const h = d.y1 - d.y0;
  const hasEnglishTitle = d.data.title && d.data.title !== d.data.title_romaji;
  const bottomPad = 6;
  if (line === "downloads") return h - bottomPad;
  if (line === "english") return h - bottomPad - 14;
  if (line === "romaji") return hasEnglishTitle ? h - bottomPad - 28 : h - bottomPad - 14;
  if (line === "rank") return hasEnglishTitle ? h - bottomPad - 43 : h - bottomPad - 29;
  return h - bottomPad;
};

// Title and downloads for top shows
const textGroup = treemapLeaf.filter((d, i) => i < 40)
  .append("g")
  .attr("clip-path", (d, i) => `url(#treemap-clip-${i})`)
  .style("pointer-events", "none");

// Downloads (bottom)
textGroup.append("text")
  .attr("x", 4)
  .attr("y", d => getTextY(d, "downloads"))
  .attr("font-size", "10px")
  .attr("fill", "#ddd")
  .style("text-shadow", textShadow)
  .text(d => formatCompact(d.data.total_downloads));

// English title (if different)
textGroup.append("text")
  .attr("x", 4)
  .attr("y", d => getTextY(d, "english"))
  .attr("font-size", "10px")
  .attr("fill", "#ccc")
  .style("text-shadow", textShadow)
  .text(d => d.data.title && d.data.title !== d.data.title_romaji ? d.data.title : "");

// Romaji title
textGroup.append("text")
  .attr("x", 4)
  .attr("y", d => getTextY(d, "romaji"))
  .attr("font-size", "11px")
  .attr("font-weight", "600")
  .attr("fill", "#fff")
  .style("text-shadow", textShadow)
  .text(d => d.data.title_romaji);

// Rank
const rankText = textGroup.append("text")
  .attr("x", 4)
  .attr("y", d => getTextY(d, "rank"))
  .attr("font-size", "13px")
  .attr("font-weight", "bold")
  .style("text-shadow", textShadow);

rankText.append("tspan")
  .attr("fill", "#fff")
  .text(d => `#${d.data.season_rank}`);

// Add watermark overlay
const treemapTitleLines = seasonLabel.split(" ");
const isInProgress = seasonTitle !== seasonLabel;
const todayFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date());
const treemapSubtitleLines = isInProgress
  ? [`total downloads (up to ${todayFmt})`, "nyaastats"]
  : ["total downloads", "nyaastats"];
addWatermark(treemapSvg, treemapWidth, treemapHeight, treemapTitleLines, treemapSubtitleLines);

display(html`<figure class="chart-figure">
  ${treemapSvg.node()}
</figure>`);
```

```js
// Focus chips
const focusChips = html`<div class="focus-chips">
  <div class="focus-title">Focused shows</div>
  <div class="focus-list">
    ${focused.size === 0
      ? html`<span class="focus-empty">Click on show to focus data</span>`
      : Array.from(focused)
          .map(id => showLookup.get(id))
          .filter(Boolean)
          .map(show => html`<button class="focus-chip" onclick=${() => toggleFocusedId(show.anilist_id)}>
            <span class="focus-chip-title">${show.title_romaji}</span>
            <span class="focus-chip-x">×</span>
          </button>`)}
  </div>
  <button class="focus-clear" onclick=${() => setFocused(new Set())}>Clear focus</button>
</div>`;
display(focusChips);
```

```js
// Search input - just for highlighting, doesn't filter
const searchQuery = view(Inputs.text({
  placeholder: "Search shows...",
  width: 300
}));
```

```js
// Score shows by search match (higher = better match)
function scoreMatch(show, query) {
  if (!query || query.trim() === "") return 0;
  const q = query.toLowerCase();
  const title = (show.title || "").toLowerCase();
  const romaji = (show.title_romaji || "").toLowerCase();
  if (title === q || romaji === q) return 100;
  if (title.startsWith(q) || romaji.startsWith(q)) return 80;
  if (title.includes(q) || romaji.includes(q)) return 50;
  return 0;
}

// Sort shows: matched first (by score), then by season rank
const sortedShows = [...filteredShows].sort((a, b) => {
  const scoreA = scoreMatch(a, searchQuery);
  const scoreB = scoreMatch(b, searchQuery);
  if (scoreA !== scoreB) return scoreB - scoreA;
  return a.season_rank - b.season_rank;
});

// Track which shows match the search
const matchedIds = new Set(
  sortedShows.filter(s => scoreMatch(s, searchQuery) > 0).map(s => s.anilist_id)
);
```

```js
// Sparkline generators
function makeRankSparkline(showId) {
  const ranks = weeklyRanksByShow.get(showId) || [];
  if (ranks.length === 0) return html`<span style="color:#666">—</span>`;
  const sorted = [...ranks].sort((a, b) => new Date(a.weekStart) - new Date(b.weekStart));
  const width = 50, height = 18;
  const x = d3.scaleLinear().domain([0, sorted.length - 1]).range([2, width - 2]);
  const y = d3.scaleLinear().domain([40, 1]).range([height - 2, 2]);
  const line = d3.line().x((d, i) => x(i)).y(d => y(Math.min(d.rank, 40)));
  const path = line(sorted);
  return html`<svg width="${width}" height="${height}" style="vertical-align:middle">
    <path d="${path}" fill="none" stroke="${showColors[showId]}" stroke-width="1.5"/>
  </svg>`;
}

function sparkbar(max, color, format) {
  const base = d3.hsl(color || "#4a9eff");
  const muted = base.copy({ s: Math.min(0.5, base.s), l: Math.max(0.25, base.l * 0.55) }).formatHex();
  return (x) => html`<div style="
    background: ${muted};
    color: #fff;
    text-shadow: 0 0 3px rgba(0,0,0,0.8), 1px 1px 2px rgba(0,0,0,0.8);
    font: 10px/1.6 var(--sans-serif);
    width: ${Math.min(100, (100 * x) / max)}%;
    float: right;
    padding-right: 4px;
    box-sizing: border-box;
    overflow: visible;
    display: flex;
    justify-content: end;">${format ? format(x) : x.toLocaleString("en-US")}</div>`;
}

function makeDownloadsCell(show) {
  if (!show?.total_downloads) return html`<span style="color:#666">—</span>`;
  const color = showColors[show.anilist_id] || "#4a9eff";
  return sparkbar(maxDownloads, color)(show.total_downloads);
}

function makeEnduranceCell(show) {
  if (!show || show.endurance == null) return html`<span style="color:#666">—</span>`;
  const eps = episodesByShow.get(show.anilist_id) || [];
  if (eps.length === 0) return html`<span style="color:#666">—</span>`;
  const sorted = [...eps].sort((a, b) => a.episode - b.episode);
  const minEp = sorted[0]?.episode || 1;
  const capped = sorted
    .map(e => ({...e, ordinal: e.episode - minEp + 1}))
    .filter(e => e.ordinal <= 14);
  if (capped.length === 0) return html`<span style="color:#666">—</span>`;
  const firstDl = capped[0]?.downloads_cumulative || 0;
  if (firstDl <= 0) return html`<span style="color:#666">—</span>`;
  const values = capped.map(d => d.downloads_cumulative / firstDl);
  const width = 80, height = 20;
  const x = d3.scaleLinear().domain([0, values.length - 1]).range([2, width - 2]);
  const maxVal = Math.max(1.1, d3.max(values) || 1);
  const y = d3.scaleLinear().domain([0, maxVal]).range([height - 2, 2]);
  const line = d3.line().x((d, i) => x(i)).y(d => y(d));
  const path = line(values);
  const pct = `${(show.endurance * 100).toFixed(0)}%`;
  const baselineY = y(1);
  const color = showColors[show.anilist_id] || "#4a9eff";
  return html`<div style="display:flex;align-items:center;gap:6px;justify-content:flex-end">
    <svg width="${width}" height="${height}" style="display:block">
      <line x1="2" x2="${width - 2}" y1="${baselineY}" y2="${baselineY}" stroke="#333" stroke-dasharray="2,2"></line>
      <path d="${path}" fill="none" stroke="${color}" stroke-width="1.5"></path>
    </svg>
    <span style="font-size:11px;color:#ccc">${pct}</span>
  </div>`;
}

function makeLateStartersCell(show) {
  if (!show || show.late_starters == null) return html`<span style="color:#666">—</span>`;
  const color = showColors[show.anilist_id] || "#4a9eff";
  return sparkbar(maxLateStarters, color, x => `${(x * 100).toFixed(0)}%`)(show.late_starters);
}
```

```js
// Interactive table with multi-select
const table = Inputs.table(sortedShows, {
  columns: ["cover_image_url", "title_romaji", "season_rank", "total_downloads", "endurance", "late_starters"],
  header: {
    cover_image_url: "",
    title_romaji: "Title",
    season_rank: "Rank",
    total_downloads: "Downloads",
    // the <b> wrapping is since inputs.css has some odd empty span rule that's margin-block and 0 width,
    // so the default html span also gets that rule and throws off the html.
    endurance: html`<b>Endurance <a href="/about#what-is-endurance" class="info-icon" title="How well shows maintain viewership after episode 1. Click for details.">ⓘ</a></b>`,
    late_starters: html`<b>Late Starters <a href="/about#what-are-late-starters" class="info-icon" title="Percentage of viewers who started after premiere week. Click for details.">ⓘ</a></b>`
  },
  align: {
    endurance: 'left',
    late_starters: 'left'
  },
  format: {
    cover_image_url: url => url ? html`<img src="${url}" style="height:45px;border-radius:4px;object-fit:cover">` : "",
    title_romaji: (_, i, data) => {
      const show = data[i];
      const romaji = show.title_romaji || "";
      const english = show.title && show.title !== show.title_romaji ? show.title : "";
      return html`<div style="max-width:220px">
        <a href="https://anilist.co/anime/${show.anilist_id}" target="_blank"
           style="color:#4a9eff;text-decoration:none;font-weight:500">${romaji}</a>
        ${english ? html`<div style="font-size:10px;color:#888;margin-top:2px">${english}</div>` : ""}
      </div>`;
    },
    season_rank: (_, i, data) => {
      const show = data[i];
      return html`<div style="display:flex;align-items:center;gap:6px;justify-content:flex-end">
        ${makeRankSparkline(show.anilist_id)}
        <strong>#${show.season_rank}</strong>
      </div>`;
    },
    total_downloads: (_, i, data) => makeDownloadsCell(data[i]),
    endurance: (_, i, data) => makeEnduranceCell(data[i]),
    late_starters: (_, i, data) => makeLateStartersCell(data[i])
  },
  width: {
    cover_image_url: 55,
    title_romaji: 220,
    season_rank: 100,
    total_downloads: 140,
    endurance: 150,
    late_starters: 120
  },
  align: {
    season_rank: "right",
    endurance: "right"
  },
  multiple: true,
  value: [],
  rows: 15,
  style: (d) => matchedIds.has(d.anilist_id) && searchQuery
    ? "background: rgba(74, 158, 255, 0.15)"
    : ""
});

const initialFocusIds = new Set(
  (new URLSearchParams(window.location.search).get("focus") || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map(id => Number.parseInt(id, 10))
    .filter(Number.isFinite)
);
const focused = Mutable(initialFocusIds);
let isSyncingTable = false;

function updateFocusParam(set) {
  const url = new URL(window.location.href);
  if (set.size === 0) {
    url.searchParams.delete("focus");
  } else {
    url.searchParams.set("focus", Array.from(set).join(" "));
  }
  window.history.replaceState(null, "", url);
}

function syncTableToFocus() {
  isSyncingTable = true;
  table.value = Array.from(focused.value)
    .map(showId => showLookup.get(showId))
    .filter(Boolean);
  table.dispatchEvent(new Event("input"));
  isSyncingTable = false;
}

function setFocused(next, fromTable = false) {
  focused.value = next;
  if (!fromTable) {
    syncTableToFocus();
  }
  updateFocusParam(next);
}

function toggleFocusedId(id) {
  const next = new Set(focused.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  setFocused(next);
}

table.addEventListener("input", () => {
  if (isSyncingTable) return;
  const nextIds = new Set(table.value.map(s => s.anilist_id));
  if (nextIds.size === shows.length && focused.value.size <= 1) {
    setFocused(new Set());
    return;
  }
  setFocused(nextIds, true);
});

const tableSelection = view(table);
syncTableToFocus();
```

```js
// Combine table and treemap selections
const selectedIds = new Set(focused);
const selectedCount = selectedIds.size;
const focusMode = selectedCount > 0 && selectedCount < 10;
const highlightMode = selectedCount > 0;

// Get selected show objects
const selectedShows = shows.filter(s => selectedIds.has(s.anilist_id));

// Get active show set (respects long-running filter)
const activeShowIds = new Set(filteredShows.map(s => s.anilist_id));
```

---

```js
// Filter to top 25 and active shows
const bumpChartData = allRankings.filter(r =>
  r.rank <= 25 && activeShowIds.has(r.anilist_id)
);

// Get last week for end labels
const lastWeekStart = weekLabels[weekLabels.length - 1];
const lastWeekRankings = bumpChartData.filter(r => r.weekStart === lastWeekStart);

const bumpLegend = focusMode ? html`<div class="bump-legend">
  <span class="bump-legend-label">Focused shows</span>
  ${selectedShows.map(show => html`<span class="bump-legend-item">
    <span class="bump-legend-swatch" style="background:${showColors[show.anilist_id] || "#4a9eff"}"></span>
    ${show.title_romaji}
  </span>`)}
</div>` : null;
if (bumpLegend) display(bumpLegend);

display(Plot.plot({
  title: `${seasonTitle} Weekly Rank Over Time`,
  subtitle: "Downloads per week (all episodes) • NyaaStats",
  height: 650,
  width: plotWidth,
  marginRight: 220,
  marginBottom: 100,
  insetBottom: 28,
  insetLeft: 12,
  insetRight: 50,
  y: {
    reverse: true,
    label: "Rank",
    domain: [1, 25],
    grid: true
  },
  x: {
    label: null,
    type: "band",
    domain: weekLabels,
    tickRotate: -30,
    tickFormat: d => `Week of ${new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" })}`
  },
  marks: [
    // Lines - thicker for interactivity
    Plot.line(bumpChartData, {
      x: "weekStart",
      y: "rank",
      z: "anilist_id",
      stroke: d => highlightMode
        ? (selectedIds.has(d.anilist_id) ? showColors[d.anilist_id] : "#333")
        : showColors[d.anilist_id],
      strokeWidth: d => highlightMode && selectedIds.has(d.anilist_id) ? 4 : 2,
      strokeOpacity: d => highlightMode && !selectedIds.has(d.anilist_id) ? 0.15 : 0.7,
      curve: "monotone-x"
    }),
    // Poster markers at each data point (always visible)
    Plot.image(bumpChartData, {
      x: "weekStart",
      y: "rank",
      src: "cover_image_url",
      width: 16,
      height: 24,
      opacity: d => highlightMode && !selectedIds.has(d.anilist_id) ? 0.1 : 0.9
    }),
    // Larger poster on hover with tip
    Plot.image(bumpChartData, Plot.pointer({
      x: "weekStart",
      y: "rank",
      src: "cover_image_url",
      width: 24,
      height: 36
    })),
    // Tip for hover
    Plot.tip(bumpChartData, Plot.pointer({
      x: "weekStart",
      y: "rank",
      title: d => `${d.title_romaji}\nWeek: ${d.week}\n#${d.rank} • ${formatCompact(d.downloads)} downloads`
    })),
    // End labels with posters
    Plot.image(lastWeekRankings, {
      x: "weekStart",
      y: "rank",
      src: "cover_image_url",
      width: 28,
      height: 42,
      dx: 55,
      opacity: d => highlightMode && !selectedIds.has(d.anilist_id) ? 0.15 : 1
    }),
    Plot.text(lastWeekRankings, {
      x: "weekStart",
      y: "rank",
      text: d => d.title_romaji?.slice(0, 22) + (d.title_romaji?.length > 22 ? "..." : ""),
      dx: 85,
      textAnchor: "start",
      fill: d => highlightMode && !selectedIds.has(d.anilist_id) ? "#555" : showColors[d.anilist_id],
      fontSize: 10,
      fontWeight: "500"
    })
  ]
}));
```

---

```js
// For each show, calculate episode ordinal (1-based relative to season)
const episodesNormalized = [];
for (const [anilist_id, eps] of episodesByShow) {
  if (!activeShowIds.has(anilist_id)) continue;
  const sorted = [...eps].sort((a, b) => a.episode - b.episode);
  const minEp = sorted[0]?.episode || 1;
  for (const e of sorted) {
    episodesNormalized.push({
      ...e,
      episode_ordinal: e.episode - minEp + 1,
      show: showLookup.get(anilist_id)
    });
  }
}

// Cap display at 14 episodes (typical season)
const maxDisplayEp = 14;
const episodesFiltered = episodesNormalized.filter(e => e.episode_ordinal <= maxDisplayEp);

// Filter for selected shows
const selectedEpisodes = episodesFiltered.filter(e => selectedIds.has(e.anilist_id));

// Dynamic y domain based on selection
const yDomainEpisodes = focusMode && selectedEpisodes.length > 0
  ? [0, d3.max(selectedEpisodes, d => d.downloads_cumulative) * 1.1]
  : [0, d3.max(episodesFiltered, d => d.downloads_cumulative)];

// Recalculate percentiles for ordinal episodes
const episodeOrdinalGroups = d3.group(episodesFiltered, d => d.episode_ordinal);
const episodePercentileData = Array.from(episodeOrdinalGroups, ([ep, data]) => {
  const downloads = data.map(d => d.downloads_cumulative).sort((a, b) => a - b);
  return {
    episode: ep,
    p25: d3.quantile(downloads, 0.25) || 0,
    p50: d3.quantile(downloads, 0.5) || 0,
    p75: d3.quantile(downloads, 0.75) || 0
  };
}).sort((a, b) => a.episode - b.episode);

display(Plot.plot({
  title: `${seasonTitle} Downloads per Episode`,
  subtitle: "Cumulative over the season • NyaaStats",
  height: 400,
  width: plotWidth,
  marginLeft: 70,
  marginRight: focusMode ? 150 : 20,
  y: {
    label: "Downloads (Cumulative per Episode)",
    grid: true,
    domain: yDomainEpisodes,
    tickFormat: d => formatCompact(d)
  },
  x: {
    label: "Episode (Ordinal)",
    domain: d3.range(1, maxDisplayEp + 1)
  },
  color: focusMode && selectedShows.length > 0 ? {
    legend: true,
    domain: selectedShows.map(s => s.title_romaji),
    range: selectedShows.map(s => showColors[s.anilist_id])
  } : undefined,
  marks: [
    // Percentile band (when no selection)
    Plot.areaY(episodePercentileData, {
      x: "episode",
      y1: "p25",
      y2: "p75",
      fill: "#4a9eff",
      fillOpacity: focusMode ? 0.08 : 0.15,
      curve: "monotone-x"
    }),
    // Median line
    Plot.line(episodePercentileData, {
      x: "episode",
      y: "p50",
      stroke: "#4a9eff",
      strokeWidth: 1.8,
      strokeDasharray: "4,4",
      curve: "monotone-x"
    }),
    // Base spaghetti lines
    Plot.line(episodesFiltered, {
      x: "episode_ordinal",
      y: "downloads_cumulative",
      z: "anilist_id",
      stroke: "#777",
      strokeWidth: 0.8,
      strokeOpacity: highlightMode ? 0.3 : 0.55,
      curve: "monotone-x"
    }),
    // Focused lines on top
    highlightMode ? Plot.line(episodesFiltered.filter(d => selectedIds.has(d.anilist_id)), {
      x: "episode_ordinal",
      y: "downloads_cumulative",
      z: "anilist_id",
      stroke: d => showColors[d.anilist_id],
      strokeWidth: focusMode ? 2.5 : 1.8,
      strokeOpacity: 1,
      curve: "monotone-x"
    }) : null,
    // Tips for all shows when nothing is selected
    !focusMode ? Plot.tip(episodesFiltered, Plot.pointer({
      x: "episode_ordinal",
      y: "downloads_cumulative",
      title: d => `${d.show?.title_romaji}\nEp ${d.episode}\n${formatCompact(d.downloads_cumulative)} downloads`
    })) : null,
    // Dots and tips for selected shows
    focusMode ? Plot.dot(selectedEpisodes, Plot.pointer({
      x: "episode_ordinal",
      y: "downloads_cumulative",
      fill: d => showColors[d.anilist_id],
      r: 6
    })) : null,
    focusMode ? Plot.tip(selectedEpisodes, Plot.pointer({
      x: "episode_ordinal",
      y: "downloads_cumulative",
      title: d => `${d.show?.title_romaji}\nEp ${d.episode}\n${formatCompact(d.downloads_cumulative)} downloads`
    })) : null,
    Plot.ruleY([0])
  ].filter(Boolean)
}));
```

---

```js
// Normalize each show's downloads to first episode = 100%
const firstEpByShow = new Map();
for (const e of episodesNormalized) {
  if (e.episode_ordinal === 1) {
    firstEpByShow.set(e.anilist_id, e.downloads_cumulative);
  }
}

const episodesNormalizedPct = episodesFiltered
  .filter(e => firstEpByShow.has(e.anilist_id) && firstEpByShow.get(e.anilist_id) > 0)
  .map(e => ({
    ...e,
    downloads_pct: e.downloads_cumulative / firstEpByShow.get(e.anilist_id)
  }));

const selectedEpisodesNorm = episodesNormalizedPct.filter(e => selectedIds.has(e.anilist_id));

// Percentiles for normalized data
const normPercentileGroups = d3.group(episodesNormalizedPct, d => d.episode_ordinal);
const normPercentileData = Array.from(normPercentileGroups, ([ep, data]) => {
  const vals = data.map(d => d.downloads_pct).sort((a, b) => a - b);
  return {
    episode: ep,
    p25: d3.quantile(vals, 0.25) || 0,
    p50: d3.quantile(vals, 0.5) || 0,
    p75: d3.quantile(vals, 0.75) || 0
  };
}).sort((a, b) => a.episode - b.episode);

// Dynamic y domain
const yDomainNorm = focusMode && selectedEpisodesNorm.length > 0
  ? [0, Math.max(1.5, d3.max(selectedEpisodesNorm, d => d.downloads_pct) * 1.1)]
  : [0, Math.max(1.5, d3.max(episodesNormalizedPct, d => d.downloads_pct) || 1.5)];

display(Plot.plot({
  title: `${seasonTitle} Downloads per Episode (Normalized)`,
  subtitle: "Episode 1 = 100% • NyaaStats",
  height: 400,
  width: plotWidth,
  marginLeft: 70,
  marginRight: focusMode ? 150 : 20,
  y: {
    label: "Downloads (% of First Episode)",
    grid: true,
    domain: yDomainNorm,
    tickFormat: d => `${(d * 100).toFixed(0)}%`
  },
  x: {
    label: "Episode (Ordinal)",
    domain: d3.range(1, maxDisplayEp + 1)
  },
  color: focusMode && selectedShows.length > 0 ? {
    legend: true,
    domain: selectedShows.map(s => s.title_romaji),
    range: selectedShows.map(s => showColors[s.anilist_id])
  } : undefined,
  marks: [
    // Reference line at 100%
    Plot.ruleY([1], { stroke: "#666", strokeDasharray: "4,4" }),
    // Percentile band (when no selection)
    Plot.areaY(normPercentileData, {
      x: "episode",
      y1: "p25",
      y2: "p75",
      fill: "#4a9eff",
      fillOpacity: focusMode ? 0.08 : 0.15,
      curve: "monotone-x"
    }),
    // Median line
    Plot.line(normPercentileData, {
      x: "episode",
      y: "p50",
      stroke: "#4a9eff",
      strokeWidth: 1.8,
      strokeDasharray: "4,4",
      curve: "monotone-x"
    }),
    // Base spaghetti lines
    Plot.line(episodesNormalizedPct, {
      x: "episode_ordinal",
      y: "downloads_pct",
      z: "anilist_id",
      stroke: "#777",
      strokeWidth: 0.8,
      strokeOpacity: highlightMode ? 0.3 : 0.55,
      curve: "monotone-x"
    }),
    // Focused lines on top
    highlightMode ? Plot.line(episodesNormalizedPct.filter(d => selectedIds.has(d.anilist_id)), {
      x: "episode_ordinal",
      y: "downloads_pct",
      z: "anilist_id",
      stroke: d => showColors[d.anilist_id],
      strokeWidth: focusMode ? 2.5 : 1.8,
      strokeOpacity: 1,
      curve: "monotone-x"
    }) : null,
    // Tips for all shows when nothing is selected
    !focusMode ? Plot.tip(episodesNormalizedPct, Plot.pointer({
      x: "episode_ordinal",
      y: "downloads_pct",
      title: d => `${d.show?.title_romaji}\nEp ${d.episode}: ${(d.downloads_pct * 100).toFixed(0)}% of Ep 1`
    })) : null,
    // Tips for selected
    focusMode ? Plot.tip(selectedEpisodesNorm, Plot.pointer({
      x: "episode_ordinal",
      y: "downloads_pct",
      title: d => `${d.show?.title_romaji}\nEp ${d.episode}: ${(d.downloads_pct * 100).toFixed(0)}% of Ep 1`
    })) : null,
    Plot.ruleY([0])
  ].filter(Boolean)
}));
```

---

```js
// Build endurance data for filtered shows
const enduranceData = filteredShows
  .filter(s => s.endurance !== null && s.endurance > 0)
  .map(s => ({ ...s, ep1_bucket: bucketLabel(s.ep1_downloads) }));

const enduranceDomain = [0.3, Math.min(1.4, maxEndurance * 1.05)];

display(html`<div class="facet-stack">
  ${bucketOrder.map(bucket => {
    const bucketData = enduranceData.filter(d => d.ep1_bucket === bucket);
    const median = d3.median(bucketData, d => d.endurance);
    return html`<div class="facet-block">
      ${Plot.plot({
        title: `${seasonTitle} Endurance (${bucket})`,
        subtitle: `How well shows maintain viewership after episode 1 • NyaaStats`,
        height: 460,
        width: plotWidth,
        marginLeft: 70,
        marginRight: 40,
        marginBottom: 40,
        marginTop: 20,
        x: {
          label: "Viewership retained after episode 1",
          domain: enduranceDomain,
          tickFormat: d => `${(d * 100).toFixed(0)}%`
        },
        y: { axis: null },
        marks: [
          Plot.ruleX([1], { stroke: "#666", strokeDasharray: "4,4" }),
          median ? Plot.ruleX([median], { stroke: "#aaa", strokeDasharray: "2,2" }) : null,
          Plot.dot(
            bucketData,
            Plot.dodgeY({
              x: "endurance",
              r: 22,
              anchor: "middle",
              fill: d => highlightMode && !selectedIds.has(d.anilist_id) ? "#333" : showColors[d.anilist_id],
              fillOpacity: d => highlightMode && !selectedIds.has(d.anilist_id) ? 0.45 : 0.85,
              stroke: d => selectedIds.has(d.anilist_id) ? "#fff" : "none",
              strokeWidth: 2
            })
          ),
          Plot.image(
            bucketData,
            Plot.dodgeY({
              x: "endurance",
              src: "cover_image_url",
              width: 36,
              height: 54,
              r: 22,
              anchor: "middle",
              opacity: d => highlightMode && !selectedIds.has(d.anilist_id) ? 0.35 : 1
            })
          ),
          focusMode && selectedShows.length > 0 ? Plot.text(
            bucketData,
            Plot.dodgeY({
              x: "endurance",
              text: d => selectedIds.has(d.anilist_id) ? d.title_romaji?.slice(0, 18) : "",
              r: 22,
              anchor: "middle",
              dx: 27,
              dy: 5,
              fill: d => selectedIds.has(d.anilist_id) ? showColors[d.anilist_id] : "none",
              fontSize: 10,
              fontWeight: "600",
              textAnchor: "start"
            })
          ) : null,
          Plot.tip(bucketData, Plot.pointer(Plot.dodgeY({
            x: "endurance",
            r: 22,
            anchor: "middle",
            title: d => `${d.title_romaji}\nEndurance: ${(d.endurance * 100).toFixed(0)}%\nTotal: ${formatCompact(d.total_downloads)}`
          })))
        ].filter(Boolean)
      })}
    </div>`;
  })}
</div>`);
```

```js
// Build late_starters data
const lateStartersData = filteredShows
  .filter(s => s.late_starters !== null && s.late_starters > 0.01)
  .map(s => ({ ...s, ep1_bucket: bucketLabel(s.ep1_downloads) }));

const lateStartersDomain = [0, Math.min(0.8, maxLateStarters * 1.1)];

display(html`<div class="facet-stack">
  ${bucketOrder.map(bucket => {
    const bucketData = lateStartersData.filter(d => d.ep1_bucket === bucket);
    const median = d3.median(bucketData, d => d.late_starters);
    return html`<div class="facet-block">
      ${Plot.plot({
        title: `${seasonTitle} Late Starters (${bucket})`,
        subtitle: `Percentage of viewers starting after premiere week • NyaaStats`,
        height: 460,
        width: plotWidth,
        marginLeft: 70,
        marginRight: 40,
        marginBottom: 40,
        marginTop: 20,
        x: {
          label: "Viewers who started after premiere week",
          domain: lateStartersDomain,
          tickFormat: d => `${(d * 100).toFixed(0)}%`
        },
        y: { axis: null },
        marks: [
          median ? Plot.ruleX([median], { stroke: "#aaa", strokeDasharray: "2,2" }) : null,
          Plot.dot(
            bucketData,
            Plot.dodgeY({
              x: "late_starters",
              r: 22,
              anchor: "middle",
              fill: d => {
                if (highlightMode && !selectedIds.has(d.anilist_id)) return "#333";
                return d.late_starters >= 0.35 ? "#4ade80" : d.late_starters <= 0.15 ? "#f87171" : showColors[d.anilist_id];
              },
              fillOpacity: d => highlightMode && !selectedIds.has(d.anilist_id) ? 0.45 : 0.85,
              stroke: d => selectedIds.has(d.anilist_id) ? "#fff" : "none",
              strokeWidth: 2
            })
          ),
          Plot.image(
            bucketData,
            Plot.dodgeY({
              x: "late_starters",
              src: "cover_image_url",
              width: 36,
              height: 54,
              r: 22,
              anchor: "middle",
              opacity: d => highlightMode && !selectedIds.has(d.anilist_id) ? 0.35 : 1
            })
          ),
          focusMode && selectedShows.length > 0 ? Plot.text(
            bucketData,
            Plot.dodgeY({
              x: "late_starters",
              text: d => selectedIds.has(d.anilist_id) ? d.title_romaji?.slice(0, 18) : "",
              r: 22,
              anchor: "middle",
              dx: 27,
              dy: 5,
              fill: d => selectedIds.has(d.anilist_id) ? showColors[d.anilist_id] : "none",
              fontSize: 10,
              fontWeight: "600",
              textAnchor: "start"
            })
          ) : null,
          Plot.tip(bucketData, Plot.pointer(Plot.dodgeY({
            x: "late_starters",
            r: 22,
            anchor: "middle",
            title: d => {
              const pct = (d.late_starters * 100).toFixed(0);
              return `${d.title_romaji}\nLate Starters: ${pct}%\nEpisode 1: ${formatCompact(d.ep1_downloads || 0)}\nTotal: ${formatCompact(d.total_downloads)}`;
            }
          })))
        ].filter(Boolean)
      })}
    </div>`;
  })}
</div>`);
```

<style>
  .note {
    background: #1a1a1a;
    border-left: 3px solid #4a9eff;
    padding: 0.75rem 1rem;
    margin: 1rem 0;
    font-size: 0.9rem;
    color: #aaa;
  }

  /* Table styling */
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

  /* Ensure images in table cells don't overflow */
  td img {
    display: block;
  }

  /* Highlighted search matches */
  tr[style*="background"] {
    font-weight: 500;
  }

  /* Better link styling */
  a:hover {
    text-decoration: underline !important;
  }

  /* Info icon in table headers */
  .info-icon {
    display: inline-block;
    margin-left: 4px;
    color: #888;
    text-decoration: none !important;
    font-size: 0.85em;
    vertical-align: middle;
    cursor: help;
  }

  .info-icon:hover {
    color: #4a9eff;
    text-decoration: none !important;
  }

  .focus-chips {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin: 0.5rem 0 1rem;
  }

  .focus-title {
    font-size: 0.85rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .focus-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .focus-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(74, 158, 255, 0.15);
    border: 1px solid rgba(74, 158, 255, 0.4);
    color: #cfe3ff;
    font-size: 0.8rem;
    padding: 0.25rem 0.5rem;
    border-radius: 999px;
    cursor: pointer;
  }

  .focus-chip:hover {
    background: rgba(74, 158, 255, 0.25);
  }

  .focus-chip-title {
    white-space: nowrap;
  }

  .focus-chip-x {
    font-weight: 700;
    color: #88b9ff;
  }

  .focus-empty {
    color: #666;
    font-size: 0.85rem;
  }

  .focus-clear {
    align-self: flex-start;
    background: transparent;
    border: 1px solid #333;
    color: #aaa;
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    cursor: pointer;
  }

  .focus-clear:hover {
    border-color: #4a9eff;
    color: #cfe3ff;
  }

  .bump-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 0.75rem;
    align-items: center;
    margin: 0.4rem 0 0.6rem;
    font-size: 0.8rem;
    color: #bbb;
  }

  .bump-legend-label {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    color: #777;
  }

  .bump-legend-item {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }

  .bump-legend-swatch {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    display: inline-block;
  }

  .facet-stack {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .facet-block {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .chart-figure {
    margin: 0;
  }
</style>
