import fs from "node:fs";
import {parseArgs} from "node:util";

const {values} = parseArgs({
  options: {
    season: {type: "string"}
  }
});

const seasonsPath = new URL("../data/seasons.json", import.meta.url);
let seasons = [];

try {
  seasons = JSON.parse(fs.readFileSync(seasonsPath, "utf-8"));
} catch {
  seasons = [];
}

const requestedSlug = values.season || seasons?.[0]?.slug || "season";
const seasonMeta = seasons.find((item) => item.slug === requestedSlug) || seasons[0] || {};
const seasonLabel = seasonMeta.name || requestedSlug.replace(/-/g, " ");
const seasonStatus = seasonMeta.status || "unknown";
let seasonTitle = seasonLabel;
if (seasonStatus === "in-progress") {
  const today = new Date();
  const formatted = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC"
  }).format(today);
  seasonTitle = `${seasonLabel} (up to ${formatted})`;
}

const templatePath = new URL("../../season-template.md", import.meta.url);
let template = fs.readFileSync(templatePath, "utf-8");

template = template.replaceAll("__SEASON_SLUG__", requestedSlug);
template = template.replaceAll("__SEASON_LABEL__", seasonLabel);
template = template.replaceAll("__SEASON_TITLE__", seasonTitle);

process.stdout.write(template);
