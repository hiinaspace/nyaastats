---
toc: false
head: '<link rel="alternate" type="application/rss+xml" title="Nyaastats Weekly Rankings" href="/data/feed.xml">'
---

```js
// Load rankings data
const rankings = FileAttachment("data/rankings.json").json();
import {addWatermark} from "./components/watermark.js";
import {formatRankingLineHTML} from "./components/rankings.js";
```

# Nyaastats: Weekly Rankings

<a href="/data/feed.xml" target="_blank" rel="noopener">Subscribe via RSS </a>

```js
const clampWidth = (value, min, max) => Math.max(min, Math.min(max, value || min));
const plotWidth = clampWidth(width, 720, 1600);

// Get latest 4 weeks (most recent first for display)
const recentWeeks = rankings.weeks.slice(-4).reverse();

function formatCompact(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
  return String(n);
}

function isoWeekToMonday(weekStr) {
  const [yearStr, weekNumStr] = weekStr.split("-W");
  const year = Number(yearStr);
  const week = Number(weekNumStr);
  const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
  const dow = simple.getUTCDay();
  const isoMonday = new Date(simple);
  isoMonday.setUTCDate(simple.getUTCDate() - ((dow + 6) % 7));
  return isoMonday;
}

function formatDateRange(weekStr, startDate) {
  const start = startDate ? new Date(startDate) : isoWeekToMonday(weekStr);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const sameMonth = start.getMonth() === end.getMonth();
  const sameYear = start.getFullYear() === end.getFullYear();
  const startFmt = start.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric"
  });
  const endFmt = end.toLocaleDateString("en-US", {
    month: sameMonth ? "short" : "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric"
  });
  const yearFmt = end.toLocaleDateString("en-US", { year: "numeric" });
  return `${startFmt} – ${endFmt}, ${yearFmt}`;
}

// Returns stacked date lines for watermark: ["Jan 11–", "Jan 17", "2026"]
function formatDateStacked(weekStr, startDate) {
  const start = startDate ? new Date(startDate) : isoWeekToMonday(weekStr);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const startFmt = start.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const endFmt = end.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const yearFmt = end.toLocaleDateString("en-US", { year: "numeric" });
  return [startFmt, `–${endFmt}`, yearFmt];
}

// Build a map of previous week's ranks for calculating deltas
function getRankChanges(weekIndex) {
  const currentWeek = recentWeeks[weekIndex];
  const prevWeekData = recentWeeks[weekIndex + 1];

  if (!prevWeekData) return new Map();

  const prevRanks = new Map(
    prevWeekData.rankings.map(r => [r.anilist_id, r.rank])
  );
  return prevRanks;
}

// Build previous downloads map for delta
function getDownloadChanges(weekIndex) {
  const prevWeekData = recentWeeks[weekIndex + 1];
  if (!prevWeekData) return new Map();
  return new Map(
    prevWeekData.rankings.map(r => [r.anilist_id, r.downloads])
  );
}
```

```js
// Treemap rendering function
function renderTreemap(weekData, weekIndex, titleLines, subtitleLines) {
  const prevRanks = getRankChanges(weekIndex);
  const prevDownloads = getDownloadChanges(weekIndex);

  // Prepare hierarchical data for d3.treemap
  const hierarchyData = {
    name: "root",
    children: weekData.rankings.map(r => ({
      ...r,
      value: r.downloads,
      rankChange: prevRanks.has(r.anilist_id)
        ? prevRanks.get(r.anilist_id) - r.rank
        : null,
      downloadChange: prevDownloads.has(r.anilist_id)
        ? r.downloads - prevDownloads.get(r.anilist_id)
        : null,
      downloadChangePct: prevDownloads.has(r.anilist_id) && prevDownloads.get(r.anilist_id) > 0
        ? (r.downloads - prevDownloads.get(r.anilist_id)) / prevDownloads.get(r.anilist_id)
        : null,
      isNew: !prevRanks.has(r.anilist_id)
    }))
  };

  // Create treemap layout (~20% larger)
  const width = plotWidth;
  const height = Math.round(width * 0.66);

  const root = d3.hierarchy(hierarchyData)
    .sum(d => d.value)
    .sort((a, b) => b.value - a.value);

  // Use squarify with target aspect ratio ~0.7 (poster-ish)
  d3.treemap()
    .tile(d3.treemapSquarify.ratio(0.7))
    .size([width, height])
    .padding(2)
    .round(true)(root);

  // Create SVG
  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, width, height])
    .attr("width", width)
    .attr("height", height)
    .style("font-family", "system-ui, sans-serif");

  // Define gradient for text background
  const defs = svg.append("defs");
  const gradientId = `text-gradient-${weekIndex}`;
  const gradient = defs.append("linearGradient")
    .attr("id", gradientId)
    .attr("x1", "0%").attr("y1", "0%")
    .attr("x2", "0%").attr("y2", "100%");
  gradient.append("stop")
    .attr("offset", "0%")
    .attr("stop-color", "rgba(0,0,0,0)");
  gradient.append("stop")
    .attr("offset", "100%")
    .attr("stop-color", "rgba(0,0,0,0.85)");

  // Add rectangles
  const leaf = svg.selectAll("a")
    .data(root.leaves())
    .join("a")
    .attr("href", d => `https://anilist.co/anime/${d.data.anilist_id}`)
    .attr("target", "_blank")
    .attr("rel", "noopener")
    .style("cursor", "pointer");

  const leafGroup = leaf.append("g")
    .attr("transform", d => `translate(${d.x0},${d.y0})`);

  // Define clip paths for cells
  leafGroup.append("clipPath")
    .attr("id", (d, i) => `cell-clip-${weekIndex}-${i}`)
    .append("rect")
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0);

  // Rectangle background (fallback color or default)
  leafGroup.append("rect")
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0)
    .attr("fill", d => d.data.cover_image_color || "#1a1a2e")
    .attr("stroke", "#222")
    .attr("stroke-width", 1);

  // Cover image background
  leafGroup.filter(d => d.data.cover_image_url)
    .append("image")
    .attr("href", d => d.data.cover_image_url)
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0)
    .attr("preserveAspectRatio", "xMidYMid slice")
    .attr("clip-path", (d, i) => `url(#cell-clip-${weekIndex}-${i})`);

  // Only add text elements for top 40 shows
  const textLeaf = leafGroup.filter(d => d.data.rank <= 40);

  // Text background gradient (bottom portion only)
  const textBgHeight = 80;
  textLeaf.append("rect")
    .attr("y", d => Math.max(0, (d.y1 - d.y0) - textBgHeight))
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => Math.min(d.y1 - d.y0, textBgHeight))
    .attr("fill", `url(#${gradientId})`);

  // Text container clipped to cell bounds
  const textGroup = textLeaf.append("g")
    .attr("clip-path", (d, i) => `url(#cell-clip-${weekIndex}-${i})`);

  // Text styling with shadow for contrast
  const textShadow = "0 0 3px black, 1px 1px 3px black";

  // Helper: calculate text y positions from bottom
  // Line heights: rank=15, romaji=13, english=12, downloads=12
  // Padding from bottom: 6px
  const getTextY = (d, line) => {
    const h = d.y1 - d.y0;
    const hasTwoTitles = d.data.title !== d.data.title_romaji;
    const bottomPad = 6;
    // Stack from bottom: downloads, english (if different), romaji, rank
    if (line === "downloads") return h - bottomPad;
    if (line === "english") return h - bottomPad - 14;
    if (line === "romaji") return hasTwoTitles ? h - bottomPad - 28 : h - bottomPad - 14;
    if (line === "rank") return hasTwoTitles ? h - bottomPad - 43 : h - bottomPad - 29;
    return h - bottomPad;
  };

  // Download count (bottom line)
  textGroup.append("text")
    .attr("x", 4)
    .attr("y", d => getTextY(d, "downloads"))
    .attr("font-size", "10px")
    .attr("fill", "#ddd")
    .style("text-shadow", textShadow)
    .call(text => {
      text.append("tspan")
        .text(d => formatCompact(d.data.downloads));
      text.append("tspan")
        .attr("fill", d => {
          if (d.data.downloadChangePct > 0) return "#4ade80";
          if (d.data.downloadChangePct < 0) return "#f87171";
          return "#aaa";
        })
        .text(d => {
          if (d.data.downloadChangePct == null || d.data.downloadChangePct === 0) return "";
          const sign = d.data.downloadChangePct > 0 ? "+" : "";
          return ` (${sign}${(d.data.downloadChangePct * 100).toFixed(0)}%)`;
        });
    });

  // English title (secondary, above downloads)
  textGroup.append("text")
    .attr("x", 4)
    .attr("y", d => getTextY(d, "english"))
    .attr("font-size", "10px")
    .attr("fill", "#ccc")
    .style("text-shadow", textShadow)
    .text(d => d.data.title !== d.data.title_romaji ? d.data.title : "");

  // Romaji title (primary, above english)
  textGroup.append("text")
    .attr("x", 4)
    .attr("y", d => getTextY(d, "romaji"))
    .attr("font-size", "11px")
    .attr("font-weight", "600")
    .attr("fill", "#fff")
    .style("text-shadow", textShadow)
    .text(d => d.data.title_romaji || d.data.title);

  // Rank number and change indicator (above titles)
  const rankText = textGroup.append("text")
    .attr("x", 4)
    .attr("y", d => getTextY(d, "rank"))
    .attr("font-size", "13px")
    .attr("font-weight", "bold")
    .style("text-shadow", textShadow);

  // Rank number
  rankText.append("tspan")
    .attr("fill", "#fff")
    .text(d => `#${d.data.rank}`);

  const isOldestWeek = weekIndex === recentWeeks.length - 1;

  // Change indicator in color
  rankText.append("tspan")
    .attr("fill", d => {
      if (isOldestWeek) return "#888";
      if (d.data.isNew) return "#aaa";
      if (d.data.rankChange > 0) return "#4ade80";
      if (d.data.rankChange < 0) return "#f87171";
      return "#888";
    })
    .text(d => {
      if (isOldestWeek) return "";
      if (d.data.isNew) return " NEW";
      if (d.data.rankChange > 0) return ` ▲${d.data.rankChange}`;
      if (d.data.rankChange < 0) return ` ▼${Math.abs(d.data.rankChange)}`;
      return " —";
    });

  // For ranks >40, just show the rank number (no title/details)
  const smallLeaf = leafGroup.filter(d => d.data.rank > 40);
  smallLeaf.append("text")
    .attr("x", 4)
    .attr("y", d => Math.min(14, (d.y1 - d.y0) - 4))
    .attr("font-size", "10px")
    .attr("font-weight", "bold")
    .attr("fill", "#fff")
    .style("text-shadow", textShadow)
    .text(d => `#${d.data.rank}`);

  // Add watermark overlay
  addWatermark(svg, width, height, titleLines, subtitleLines);

  return svg.node();
}
```

```js
// Text rankings rendering function
function renderTextRankings(weekData, weekIndex) {
  const prevRanks = getRankChanges(weekIndex);
  const prevDownloads = getDownloadChanges(weekIndex);
  const isOldestWeek = weekIndex === recentWeeks.length - 1;

  // Show all rankings, not just top 20
  const allRankings = weekData.rankings;

  // Create DOM elements for each ranking line
  const rankingElements = allRankings.map(show => {
    // Calculate options for formatting
    const rankChange = prevRanks.has(show.anilist_id)
      ? prevRanks.get(show.anilist_id) - show.rank
      : null;
    const prevDl = prevDownloads.get(show.anilist_id);
    const isNew = !prevRanks.has(show.anilist_id);

    const formattedHTML = formatRankingLineHTML(show, {
      rankChange,
      prevDownloads: prevDl,
      isNew,
      isOldest: isOldestWeek
    });

    // Create link wrapper
    const link = document.createElement('a');
    link.href = `https://anilist.co/anime/${show.anilist_id}`;
    link.target = '_blank';
    link.rel = 'noopener';
    link.className = 'ranking-line';
    link.innerHTML = formattedHTML;

    return link;
  });

  // Create the container
  const details = document.createElement('details');
  details.className = 'text-rankings';

  const summary = document.createElement('summary');
  summary.textContent = `View ${allRankings.length} rankings as text`;
  details.appendChild(summary);

  const content = document.createElement('div');
  content.className = 'rankings-content';
  rankingElements.forEach(el => content.appendChild(el));
  details.appendChild(content);

  return details;
}
```

```js
// Pre-create text rankings (independent of width, won't re-render on resize)
const textRankingElements = recentWeeks.map((week, i) => renderTextRankings(week, i));
```

```js
// Render treemaps and text rankings for each of the last 4 weeks
// Only treemaps depend on width and will re-render on resize
for (let i = 0; i < recentWeeks.length; i++) {
  const week = recentWeeks[i];
  const dateLines = formatDateStacked(week.week, week.start_date);
  const dateRange = formatDateRange(week.week, week.start_date);
  const subtitleLines = ["weekly downloads (all episodes)", "nyaastats.hiina.space"];

  // Add h2 header for the week
  display(html`<h2 id="week-${week.week}">${dateRange}</h2>`);

  display(html`<figure class="chart-figure">
    ${renderTreemap(week, i, dateLines, subtitleLines)}
  </figure>`);

  // Display pre-created text rankings (same DOM node, won't reset details state)
  display(textRankingElements[i]);
}
```

<style>
  .chart-figure {
    margin: 0 0 1.5rem;
  }

  .text-rankings {
    margin: 1rem 0 2rem;
    border: 1px solid var(--theme-foreground-faint);
    border-radius: 4px;
    padding: 0.5rem;
  }

  .text-rankings summary {
    cursor: pointer;
    font-weight: 600;
    padding: 0.5rem;
  }

  .text-rankings summary:hover {
    background: var(--theme-foreground-faintest);
  }

  .rankings-content {
    margin-top: 0.5rem;
    padding: 0.5rem;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
    font-size: 0.9rem;
    line-height: 1.6;
  }

  .ranking-line {
    white-space: pre;
  }

  .rank-up {
    color: #4ade80;
  }

  .rank-down {
    color: #f87171;
  }

  .rank-same {
    color: #888;
  }

  .rank-new {
    color: #aaa;
  }

  .dl-up {
    color: #4ade80;
  }

  .dl-down {
    color: #f87171;
  }

  .dl-same {
    color: #888;
  }

  .ranking-line {
    display: block;
    white-space: pre;
    text-decoration: none;
    color: var(--theme-foreground) !important;
    padding: 0.1rem 0;
  }

  .ranking-line:hover {
    background: var(--theme-foreground-faintest);
  }
</style>
