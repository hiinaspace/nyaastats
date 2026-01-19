---
toc: false
---
# Nyaa Download Rankings

<div class="note">
  Tracking download statistics for Fall 2025 and Winter 2026 anime seasons.
  Data updates weekly. <a href="/season/fall-2025">View the interactive Fall 2025 Season Overview →</a>
</div>

```js
// Load rankings data
const rankings = FileAttachment("data/rankings.json").json();
```

```js
// Get latest 4 weeks (most recent first for display)
const recentWeeks = rankings.weeks.slice(-4).reverse();

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
function renderTreemap(weekData, weekIndex) {
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
      isNew: !prevRanks.has(r.anilist_id)
    }))
  };

  // Create treemap layout (~20% larger)
  const width = 1080;
  const height = 720;

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
  const leaf = svg.selectAll("g")
    .data(root.leaves())
    .join("g")
    .attr("transform", d => `translate(${d.x0},${d.y0})`);

  // Define clip paths for cells
  leaf.append("clipPath")
    .attr("id", (d, i) => `cell-clip-${weekIndex}-${i}`)
    .append("rect")
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0);

  // Rectangle background (fallback color or default)
  leaf.append("rect")
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0)
    .attr("fill", d => d.data.cover_image_color || "#1a1a2e")
    .attr("stroke", "#222")
    .attr("stroke-width", 1);

  // Cover image background
  leaf.filter(d => d.data.cover_image_url)
    .append("image")
    .attr("href", d => d.data.cover_image_url)
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0)
    .attr("preserveAspectRatio", "xMidYMid slice")
    .attr("clip-path", (d, i) => `url(#cell-clip-${weekIndex}-${i})`);

  // Only add text elements for top 40 shows
  const textLeaf = leaf.filter(d => d.data.rank <= 40);

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
    .text(d => {
      const dl = d.data.downloads.toLocaleString();
      if (d.data.downloadChange !== null && d.data.downloadChange !== 0) {
        const sign = d.data.downloadChange > 0 ? "+" : "";
        return `${dl} (${sign}${d.data.downloadChange.toLocaleString()})`;
      }
      return dl;
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

  // Change indicator in color
  rankText.append("tspan")
    .attr("fill", d => {
      if (d.data.isNew) return "#aaa";
      if (d.data.rankChange > 0) return "#4ade80";
      if (d.data.rankChange < 0) return "#f87171";
      return "#888";
    })
    .text(d => {
      if (d.data.isNew) return " NEW";
      if (d.data.rankChange > 0) return ` ▲${d.data.rankChange}`;
      if (d.data.rankChange < 0) return ` ▼${Math.abs(d.data.rankChange)}`;
      return " —";
    });

  // For ranks >40, just show the rank number (no title/details)
  const smallLeaf = leaf.filter(d => d.data.rank > 40);
  smallLeaf.append("text")
    .attr("x", 4)
    .attr("y", d => Math.min(14, (d.y1 - d.y0) - 4))
    .attr("font-size", "10px")
    .attr("font-weight", "bold")
    .attr("fill", "#fff")
    .style("text-shadow", textShadow)
    .text(d => `#${d.data.rank}`);

  return svg.node();
}
```

## Weekly Rankings

```js
// Render treemaps for each of the last 4 weeks
for (let i = 0; i < recentWeeks.length; i++) {
  const week = recentWeeks[i];
  display(html`<h3>Week ${week.week}</h3>`);
  display(renderTreemap(week, i));
}
```

---

<div class="note">
  Data source: Nyaa.si torrent tracker. Statistics aggregated from tracker scrapes.
</div>
