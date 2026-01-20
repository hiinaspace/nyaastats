// Observable Framework configuration
// See https://observablehq.com/framework/config for documentation

import fs from "node:fs";

const seasonsPath = new URL("./src/data/seasons.json", import.meta.url);
let seasons = [];

try {
  seasons = JSON.parse(fs.readFileSync(seasonsPath, "utf-8"));
} catch {
  seasons = [];
}

const seasonPages = seasons.map((season) => ({
  name: `${season.name} Season`,
  path: `/season/${season.slug}`
}));

const dynamicPaths = seasons.map((season) => `/season/${season.slug}`);

export default {
  title: "Nyaastats",
  description: "Nyaa torrent download statistics and rankings by anime season",

  // Theme
  theme: "dark",

  // Root path for the site
  root: "src",

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
