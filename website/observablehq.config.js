// Observable Framework configuration
// See https://observablehq.com/framework/config for documentation

import fs from "node:fs";

const seasonsPath = new URL("./src/data/seasons.json", import.meta.url);
const rankingsPath = new URL("./src/data/rankings.json", import.meta.url);
const treemapsLoaderPath = new URL("./src/data/treemaps.zip.js", import.meta.url);
let seasons = [];
let rankings = null;

try {
  seasons = JSON.parse(fs.readFileSync(seasonsPath, "utf-8"));
} catch {
  seasons = [];
}

try {
  rankings = JSON.parse(fs.readFileSync(rankingsPath, "utf-8"));
} catch {
  rankings = null;
}

try {
  const rankingsStat = fs.statSync(rankingsPath);
  const loaderStat = fs.statSync(treemapsLoaderPath);
  if (rankingsStat.mtimeMs > loaderStat.mtimeMs) {
    fs.utimesSync(treemapsLoaderPath, rankingsStat.atime, rankingsStat.mtime);
  }
} catch {
  // Ignore missing files during initial setup
}

const seasonPages = seasons.map((season) => ({
  name: `${season.name} Season`,
  path: `/season/${season.slug}`
}));

const treemapWeekCount = Number(process.env.NYAASTATS_TREEMAP_WEEKS || 4);
const treemapWeeks = rankings?.weeks
  ? rankings.weeks.slice(-treemapWeekCount).reverse()
  : [];
const treemapPaths = treemapWeeks.map((week) => `/data/treemaps/treemap-${week.week}.jpg`);

const dynamicPaths = [
  ...seasons.map((season) => `/season/${season.slug}`),
  "/data/feed.xml",
  ...treemapPaths
];

export default {
  title: "Nyaastats",
  description: "Nyaa torrent download statistics and rankings by anime season",

  // Root path for the site
  root: "src",

  // seems to be required for simple hosting
  preserveExtension: true,

  // Output directory
  output: "dist",

  // Pages and navigation
  pages: [
    {name: "Weekly Rankings", path: "/"},
    ...seasonPages,
    {name: "About", path: "/about"}
  ],

  dynamicPaths,

  // Footer
  footer: "Built with Observable Framework",

  // Head additions
  head: `
    <style>
      body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }
    </style>
  `
};
