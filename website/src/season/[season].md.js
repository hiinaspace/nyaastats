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
const seasonDataPath = new URL(`../data/season-${requestedSlug}.json`, import.meta.url);
let seasonData = {};

try {
  seasonData = JSON.parse(fs.readFileSync(seasonDataPath, "utf-8"));
} catch {
  seasonData = {};
}

function formatUtcDate(value) {
  if (!value) return null;
  const date = new Date(value.includes("T") ? value : `${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC"
  }).format(date);
}

const formattedDataThrough = formatUtcDate(seasonData.data_through_date);
const seasonTitle = formattedDataThrough
  ? `${seasonLabel} (up to ${formattedDataThrough})`
  : seasonLabel;

const templatePath = new URL("../../season-template.md", import.meta.url);
let template = fs.readFileSync(templatePath, "utf-8");

template = template.replaceAll("__SEASON_SLUG__", requestedSlug);
template = template.replaceAll("__SEASON_LABEL__", seasonLabel);
template = template.replaceAll("__SEASON_TITLE__", seasonTitle);

process.stdout.write(template);
