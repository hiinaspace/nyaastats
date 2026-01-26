// Shared rankings formatting utilities

/**
 * Format a single ranking line as text
 * @param {Object} show - Show data with rank, title, downloads, anilist_id
 * @param {Object} options - Formatting options
 * @param {number|null} options.rankChange - Change in rank from previous week (positive = improved)
 * @param {number|null} options.downloadChange - Change in downloads from previous week
 * @param {number|null} options.prevDownloads - Previous week's downloads for calculating percentage
 * @param {boolean} options.isNew - Whether this show is new this week
 * @param {boolean} options.isOldest - Whether this is the oldest week (no deltas)
 * @returns {string} Formatted ranking line
 */
export function formatRankingLine(show, options = {}) {
  const { rankChange, downloadChange, prevDownloads, isNew, isOldest } = options;

  const rank = show.rank.toString().padStart(2, ' ');

  // Rank delta (padded to 3 chars)
  let rankDelta = '   ';
  if (!isOldest) {
    if (isNew) {
      rankDelta = 'NEW';
    } else if (rankChange !== null && rankChange !== undefined) {
      if (rankChange > 0) {
        rankDelta = `↑${rankChange.toString().padStart(2, ' ')}`;
      } else if (rankChange < 0) {
        rankDelta = `↓${Math.abs(rankChange).toString().padStart(2, ' ')}`;
      } else {
        rankDelta = ' — ';
      }
    }
  }

  // Download count with comma separator (padded to 6 chars)
  const downloads = show.downloads.toLocaleString('en-US').padStart(6, ' ');

  // Download delta (padded with sign and no decimal)
  let downloadDelta = '      ';
  if (!isOldest && prevDownloads && prevDownloads > 0) {
    const dlPct = Math.round(((show.downloads - prevDownloads) / prevDownloads) * 100);
    const sign = dlPct >= 0 ? '+' : '-';
    downloadDelta = `${sign}${dlPct.toString().replaceAll('-','').padStart(3, ' ')}%`;
  }

  const title = show.title_romaji || show.title;

  return `#${rank} (${rankDelta}) ${downloads} test (${downloadDelta}) ${title}`;
}

/**
 * Format ranking line as HTML with color coding
 * @param {Object} show - Show data
 * @param {Object} options - Same as formatRankingLine
 * @returns {string} HTML string with span elements for color coding
 */
export function formatRankingLineHTML(show, options = {}) {
  const { rankChange, downloadChange, prevDownloads, isNew, isOldest } = options;

  const rank = show.rank.toString().padStart(2, ' ');

  // Rank delta (padded to 3 chars)
  let rankDelta = '   ';
  let rankClass = '';
  if (!isOldest) {
    if (isNew) {
      rankDelta = 'NEW';
      rankClass = 'rank-new';
    } else if (rankChange !== null && rankChange !== undefined) {
      if (rankChange > 0) {
        rankDelta = `↑${rankChange.toString().padStart(2, ' ')}`;
        rankClass = 'rank-up';
      } else if (rankChange < 0) {
        rankDelta = `↓${Math.abs(rankChange).toString().padStart(2, ' ')}`;
        rankClass = 'rank-down';
      } else {
        rankDelta = ' — ';
        rankClass = 'rank-same';
      }
    }
  }

  // Download count with comma separator (padded to 6 chars)
  const downloads = show.downloads.toLocaleString('en-US').padStart(6, ' ');

  // Download delta (padded to 5 chars with sign and no decimal)
  let downloadDelta = '     ';
  let dlClass = '';
  if (!isOldest && prevDownloads && prevDownloads > 0) {
    const dlPct = Math.round(((show.downloads - prevDownloads) / prevDownloads) * 100);
    const sign = dlPct >= 0 ? '+' : '-';
    downloadDelta = `${sign}${dlPct.toString().replaceAll('-','').padStart(3, ' ')}%`;
    dlClass = dlPct > 0 ? 'dl-up' : dlPct < 0 ? 'dl-down' : 'dl-same';
  }

  const title = show.title_romaji || show.title;

  const rankDeltaHTML = rankClass ? `<span class="${rankClass}">${rankDelta}</span>` : rankDelta;
  const downloadDeltaHTML = dlClass ? `<span class="${dlClass}">${downloadDelta}</span>` : downloadDelta;

  return `#${rank} (${rankDeltaHTML}) ${downloads} (${downloadDeltaHTML}) ${title}`;
}

/**
 * Escape HTML entities
 */
export function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}
