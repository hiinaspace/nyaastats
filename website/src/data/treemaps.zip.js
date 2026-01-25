import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { hierarchy, treemap, treemapSquarify } from "d3-hierarchy";
import JSZip from "jszip";
import sharp from "sharp";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rankingsPath = path.join(__dirname, "rankings.json");

const baseWidth = Number(process.env.NYAASTATS_TREEMAP_WIDTH || 1200);
const scale = Number(process.env.NYAASTATS_TREEMAP_SCALE || 1.5);
const width = Math.round(baseWidth * scale);
const height = Math.round(width * 0.66);
const weekCount = Number(process.env.NYAASTATS_TREEMAP_WEEKS || 4);

const rankingsData = JSON.parse(fs.readFileSync(rankingsPath, "utf-8"));
const weeks = rankingsData.weeks.slice(-weekCount).reverse();

const cacheDir = path.join(os.tmpdir(), "nyaastats-treemap-cache");
fs.mkdirSync(cacheDir, { recursive: true });

const imageCache = new Map();

function hashKey(input) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&apos;");
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

function formatDateStacked(weekStr, startDate) {
  const start = startDate ? new Date(startDate) : isoWeekToMonday(weekStr);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const startFmt = start.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const endFmt = end.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const yearFmt = end.toLocaleDateString("en-US", { year: "numeric" });
  return [startFmt, `–${endFmt}`, yearFmt];
}

function formatCompact(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
  return String(n);
}

async function fetchImageDataUri(url) {
  if (!url) return null;
  if (imageCache.has(url)) return imageCache.get(url);

  const cacheKey = hashKey(url);
  const cachePath = path.join(cacheDir, cacheKey);
  const metaPath = `${cachePath}.json`;

  if (fs.existsSync(cachePath) && fs.existsSync(metaPath)) {
    const buffer = fs.readFileSync(cachePath);
    const meta = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
    const dataUri = `data:${meta.contentType};base64,${buffer.toString("base64")}`;
    imageCache.set(url, dataUri);
    return dataUri;
  }

  try {
    const response = await fetch(url, {
      headers: { "User-Agent": "nyaastats/1.0 treemap renderer" }
    });
    if (!response.ok) {
      console.warn(`treemap: failed to fetch image ${url} (${response.status})`);
      return null;
    }
    const arrayBuffer = await response.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    const contentType = (response.headers.get("content-type") || "image/jpeg").split(";")[0];
    fs.writeFileSync(cachePath, buffer);
    fs.writeFileSync(metaPath, JSON.stringify({ contentType }));
    const dataUri = `data:${contentType};base64,${buffer.toString("base64")}`;
    imageCache.set(url, dataUri);
    return dataUri;
  } catch (error) {
    console.warn(`treemap: error fetching image ${url}: ${error}`);
    return null;
  }
}

async function renderTreemapSvg(weekData, weekIndex) {
  const prevWeekData = weeks[weekIndex + 1];
  const prevRanks = prevWeekData
    ? new Map(prevWeekData.rankings.map(r => [r.anilist_id, r.rank]))
    : new Map();
  const prevDownloads = prevWeekData
    ? new Map(prevWeekData.rankings.map(r => [r.anilist_id, r.downloads]))
    : new Map();
  const isOldestWeek = weekIndex === weeks.length - 1;

  const hierarchyData = {
    name: "root",
    children: weekData.rankings.map(r => ({
      ...r,
      value: r.downloads
    }))
  };

  const root = hierarchy(hierarchyData)
    .sum(d => d.value)
    .sort((a, b) => b.value - a.value);

  treemap()
    .tile(treemapSquarify.ratio(0.7))
    .size([width, height])
    .padding(2)
    .round(true)(root);

  const svgParts = [];
  const leaves = root.leaves();
  const gradientId = `treemap-text-gradient-${weekIndex}`;
  const textBgHeight = 80 * scale;
  const textStroke = "rgba(0,0,0,0.85)";
  const textShadowWidth = 3 * scale;

  svgParts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`
  );
  svgParts.push(`<rect width="100%" height="100%" fill="#0b0b0b"/>`);
  svgParts.push(
    `<defs><linearGradient id="${gradientId}" x1="0%" y1="0%" x2="0%" y2="100%">` +
    `<stop offset="0%" stop-color="rgba(0,0,0,0)"/>` +
    `<stop offset="100%" stop-color="rgba(0,0,0,0.85)"/>` +
    `</linearGradient></defs>`
  );

  for (let i = 0; i < leaves.length; i++) {
    const leaf = leaves[i];
    const { x0, y0, x1, y1 } = leaf;
    const cellWidth = Math.max(0, x1 - x0);
    const cellHeight = Math.max(0, y1 - y0);
    const clipId = `cell-clip-${weekIndex}-${i}`;

    svgParts.push(`<defs><clipPath id="${clipId}"><rect x="${x0}" y="${y0}" width="${cellWidth}" height="${cellHeight}"/></clipPath></defs>`);

    const fillColor = leaf.data.cover_image_color || "#1a1a2e";
    svgParts.push(
      `<rect x="${x0}" y="${y0}" width="${cellWidth}" height="${cellHeight}" fill="${fillColor}" stroke="#222" stroke-width="1"/>`
    );

    const dataUri = await fetchImageDataUri(leaf.data.cover_image_url);
    if (dataUri) {
      svgParts.push(
        `<image href="${dataUri}" x="${x0}" y="${y0}" width="${cellWidth}" height="${cellHeight}" preserveAspectRatio="xMidYMid slice" clip-path="url(#${clipId})"/>`
      );
    }

    const isTop = leaf.data.rank <= 40;
    if (isTop) {
      const overlayHeight = Math.min(cellHeight, textBgHeight);
      const overlayY = y0 + cellHeight - overlayHeight;
      svgParts.push(
        `<rect x="${x0}" y="${overlayY}" width="${cellWidth}" height="${overlayHeight}" fill="url(#${gradientId})"/>`
      );

      const title = escapeXml(leaf.data.title_romaji || leaf.data.title || "");
      const downloads = formatCompact(leaf.data.downloads);
      const rankChange = prevRanks.has(leaf.data.anilist_id)
        ? prevRanks.get(leaf.data.anilist_id) - leaf.data.rank
        : null;
      const prevDl = prevDownloads.get(leaf.data.anilist_id);
      const downloadChangePct = (!isOldestWeek && prevDl && prevDl > 0)
        ? Math.round(((leaf.data.downloads - prevDl) / prevDl) * 100)
        : null;
      const isNew = !prevRanks.has(leaf.data.anilist_id);
      const textX = x0 + 6 * scale;
      const bottomY = y0 + cellHeight - 8 * scale;
      const titleY = bottomY - 16 * scale;
      const rankY = bottomY - 34 * scale;

      let rankDeltaText = "";
      let rankDeltaColor = "#888";
      if (!isOldestWeek) {
        if (isNew) {
          rankDeltaText = " NEW";
          rankDeltaColor = "#aaa";
        } else if (rankChange !== null && rankChange !== undefined) {
          if (rankChange > 0) {
            rankDeltaText = ` ▲${rankChange}`;
            rankDeltaColor = "#4ade80";
          } else if (rankChange < 0) {
            rankDeltaText = ` ▼${Math.abs(rankChange)}`;
            rankDeltaColor = "#f87171";
          } else {
            rankDeltaText = " —";
            rankDeltaColor = "#888";
          }
        }
      }
      svgParts.push(
        `<text x="${textX}" y="${rankY}" font-size="${13 * scale}" font-weight="700" fill="#fff" stroke="${textStroke}" stroke-width="${textShadowWidth}" paint-order="stroke" font-family="Arial, sans-serif" clip-path="url(#${clipId})">` +
        `#${leaf.data.rank}` +
        (rankDeltaText ? `<tspan fill="${rankDeltaColor}">${rankDeltaText}</tspan>` : "") +
        `</text>`
      );
      svgParts.push(
        `<text x="${textX}" y="${titleY}" font-size="${11 * scale}" font-weight="600" fill="#fff" stroke="${textStroke}" stroke-width="${textShadowWidth}" paint-order="stroke" font-family="Arial, sans-serif" clip-path="url(#${clipId})">${title}</text>`
      );
      const dlDeltaColor = downloadChangePct == null
        ? "#aaa"
        : downloadChangePct > 0
          ? "#4ade80"
          : downloadChangePct < 0
            ? "#f87171"
            : "#aaa";
      svgParts.push(
        `<text x="${textX}" y="${bottomY}" font-size="${10 * scale}" fill="#ddd" stroke="${textStroke}" stroke-width="${textShadowWidth}" paint-order="stroke" font-family="Arial, sans-serif" clip-path="url(#${clipId})">` +
        `${downloads}` +
        (downloadChangePct == null || downloadChangePct === 0
          ? ""
          : `<tspan fill="${dlDeltaColor}"> ${downloadChangePct > 0 ? "+" : ""}${downloadChangePct}%</tspan>`) +
        `</text>`
      );
    } else {
      svgParts.push(
        `<text x="${x0 + 6 * scale}" y="${y0 + 14 * scale}" font-size="${10 * scale}" font-weight="700" fill="#fff" stroke="${textStroke}" stroke-width="${textShadowWidth}" paint-order="stroke" font-family="Arial, sans-serif" clip-path="url(#${clipId})">#${leaf.data.rank}</text>`
      );
    }
  }

  const titleLines = formatDateStacked(weekData.week, weekData.start_date);
  const subtitleLines = ["weekly downloads (all episodes)", "nyaastats"];
  const titleFontSize = 48 * scale;
  const subtitleFontSize = 14 * scale;
  const titleLineHeight = 58 * scale;
  const subtitleLineHeight = 18 * scale;
  const subtitleGap = 8 * scale;
  const margin = 15 * scale;
  const watermarkStroke = "rgba(0, 0, 0, 0.7)";
  const watermarkFill = "rgba(255, 255, 100, 0.85)";

  const subtitleHeight = subtitleLines.length > 0
    ? (subtitleLines.length * subtitleLineHeight) + subtitleGap
    : 0;

  for (let i = 0; i < subtitleLines.length; i++) {
    const line = escapeXml(subtitleLines[subtitleLines.length - 1 - i]);
    const y = height - margin - (i * subtitleLineHeight);
    svgParts.push(
      `<text x="${width - margin}" y="${y}" font-size="${subtitleFontSize}" font-weight="600" fill="${watermarkFill}" stroke="${watermarkStroke}" stroke-width="${6 * scale}" paint-order="stroke" text-anchor="end" font-family="Arial, sans-serif">${line}</text>`
    );
  }

  for (let i = 0; i < titleLines.length; i++) {
    const line = escapeXml(titleLines[titleLines.length - 1 - i]);
    const y = height - margin - subtitleHeight - (i * titleLineHeight);
    svgParts.push(
      `<text x="${width - margin}" y="${y}" font-size="${titleFontSize}" font-weight="700" fill="${watermarkFill}" stroke="${watermarkStroke}" stroke-width="${10 * scale}" paint-order="stroke" text-anchor="end" font-family="Arial, sans-serif">${line}</text>`
    );
  }

  svgParts.push("</svg>");
  return svgParts.join("");
}

async function main() {
  const zip = new JSZip();

  for (let i = 0; i < weeks.length; i++) {
    const week = weeks[i];
    const svg = await renderTreemapSvg(week, i);
    const jpgBuffer = await sharp(Buffer.from(svg))
      .jpeg({ quality: 82 })
      .toBuffer();
    zip.file(`treemap-${week.week}.jpg`, jpgBuffer);
  }

  const zipBuffer = await zip.generateAsync({ type: "nodebuffer" });
  process.stdout.write(zipBuffer);
}

main().catch((error) => {
  console.error(`treemap: failed to render zip: ${error}`);
  process.exit(1);
});
