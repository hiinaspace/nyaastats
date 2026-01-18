// Observable Framework configuration
// See https://observablehq.com/framework/config for documentation

import {readFileSync} from "fs";

// Load shows metadata for dynamic sidebar
let showsData = {};
try {
  showsData = JSON.parse(readFileSync("src/data/shows.json", "utf-8"));
} catch (e) {
  console.warn("shows.json not found, sidebar will be empty. Run ETL to generate.");
}

// Generate dynamic paths for all shows
const dynamicPaths = Object.values(showsData)
  .flat()
  .map(show => `/show/${show.id}`);

// Generate sidebar pages grouped by season
const seasonPages = Object.entries(showsData).map(([seasonName, shows]) => ({
  name: seasonName,
  open: false,
  pages: shows.map(show => ({
    name: `#${show.rank} ${show.title_romaji}`,
    path: `/show/${show.id}`
  }))
}));

export default {
  title: "Nyaastats",
  description: "Nyaa torrent download statistics and rankings for Fall 2025 & Winter 2026 anime",

  // Theme
  theme: "dark",

  // Root path for the site
  root: "src",

  // Output directory
  output: "dist",

  // Dynamic paths for parameterized routes
  dynamicPaths,

  // Pages and navigation
  pages: [
    {name: "Rankings", path: "/"},
    ...seasonPages,
    {name: "About", path: "/about"}
  ],

  // Footer
  footer: "Built with Observable Framework",

  search: true,

  // Head additions
  head: `
    <style>
      body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }
    </style>
  `
};
