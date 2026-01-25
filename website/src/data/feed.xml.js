import { Feed } from "feed";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { formatRankingLine, escapeHtml } from "../components/rankings.js";

// Get directory path for ES modules
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Base URL - can be configured via environment variable
const BASE_URL = process.env.NYAASTATS_BASE_URL || "https://nyaastats.hiina.space";

// Read rankings data
const rankingsData = JSON.parse(
  fs.readFileSync(path.join(__dirname, "rankings.json"), "utf-8")
);

// Helper: Convert ISO week to Monday date
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

// Helper: Format date range for display
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

// Create feed
const feed = new Feed({
  title: "Nyaastats Weekly Rankings",
  description: "Weekly anime torrent download rankings",
  id: BASE_URL + "/",
  link: BASE_URL + "/",
  language: "en",
  updated: new Date(),
  feedLinks: {
    rss2: BASE_URL + "/_file/data/feed.xml",
  },
  author: {
    name: "Nyaastats",
    link: BASE_URL
  }
});

// Get last 4 weeks (most recent first for feed)
const weeks = rankingsData.weeks.slice(-4).reverse();

// Add items for each week
for (let i = 0; i < weeks.length; i++) {
  const weekData = weeks[i];
  const prevWeekData = weeks[i + 1]; // May be undefined for oldest week

  // Calculate deltas
  const prevRanks = prevWeekData
    ? new Map(prevWeekData.rankings.map(r => [r.anilist_id, r.rank]))
    : new Map();
  const prevDownloads = prevWeekData
    ? new Map(prevWeekData.rankings.map(r => [r.anilist_id, r.downloads]))
    : new Map();

  // Show all rankings
  const allRankings = weekData.rankings;
  const isOldestWeek = i === weeks.length - 1;

  const rankingLines = allRankings.map(show => {
    const rankChange = prevRanks.has(show.anilist_id)
      ? prevRanks.get(show.anilist_id) - show.rank
      : null;
    const prevDl = prevDownloads.get(show.anilist_id);
    const isNew = !prevRanks.has(show.anilist_id);

    const formattedLine = formatRankingLine(show, {
      rankChange,
      prevDownloads: prevDl,
      isNew,
      isOldest: isOldestWeek
    });

    return escapeHtml(formattedLine);
  }).join("\n");

  const dateRange = formatDateRange(weekData.week, weekData.start_date);
  const description = `<h3>All Anime by Downloads (${dateRange})</h3>\n<pre>${rankingLines}</pre>`;

  feed.addItem({
    title: `Weekly Rankings: ${dateRange}`,
    link: `${BASE_URL}/#week-${weekData.week}`,
    description: description,
    date: weekData.start_date ? new Date(weekData.start_date) : isoWeekToMonday(weekData.week),
    guid: `nyaastats-weekly-${weekData.week}`,
  });
}

// Output RSS 2.0 XML
process.stdout.write(feed.rss2());
