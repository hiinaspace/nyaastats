// Observable Framework configuration
// See https://observablehq.com/framework/config for documentation

export default {
  title: "Nyaastats",
  description: "Nyaa torrent download statistics and rankings for Fall 2025 & Winter 2026 anime",

  // Theme
  theme: "dark",

  // Root path for the site
  root: "src",

  // Output directory
  output: "dist",

  // Pages and navigation
  pages: [
    {name: "Rankings", path: "/"},
    {name: "About", path: "/about"}
  ],

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
