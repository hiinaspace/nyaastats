import json
import logging
import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import guessit
import httpx
from bs4 import BeautifulSoup
from guessit.jsonutils import GuessitEncoder
from whenever import Instant

from .database import Database
from .models import TorrentData

logger = logging.getLogger(__name__)


class HtmlScraper:
    """HTML scraper for Nyaa's browse page to support backfill functionality."""

    def __init__(
        self,
        db: Database,
        client: httpx.Client,
        base_url: str = "https://nyaa.si",
        now_func: Callable[[], Instant] = Instant.now,
    ):
        self.db = db
        self.client = client
        self.base_url = base_url
        self.now_func = now_func

    def fetch_page(
        self, page: int = 1, category: str = "1_2", filter_type: str = "0"
    ) -> str:
        """Fetch HTML page from Nyaa browse endpoint."""
        params = {
            "c": category,
            "f": filter_type,
            "p": str(page),
        }

        try:
            response = self.client.get(self.base_url, params=params)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to fetch page {page}: {e}")
            raise

    def parse_html_page(self, html: str) -> list[TorrentData]:
        """Parse HTML page and extract torrent data."""
        soup = BeautifulSoup(html, "lxml")

        # Find the torrent table
        table = soup.find("table", class_="torrent-list")
        if not table:
            logger.warning("No torrent table found in HTML")
            return []

        tbody = table.find("tbody")
        if not tbody:
            logger.warning("No tbody found in torrent table")
            return []

        results = []

        for row in tbody.find_all("tr"):
            try:
                torrent_data = self._parse_table_row(row)
                if torrent_data:
                    results.append(torrent_data)
            except Exception as e:
                logger.warning(f"Failed to parse table row: {e}")
                continue

        return results

    def _parse_table_row(self, row) -> TorrentData | None:
        """Parse a single table row to extract torrent data."""
        cells = row.find_all("td")
        if len(cells) < 8:
            logger.warning(f"Row has {len(cells)} cells, expected 8")
            return None

        # Extract data from cells
        # Column 0: Category (skip)
        # Column 1: Name (colspan=2, so cells[1] contains the name)
        # Column 2: Link (download/magnet)
        # Column 3: Size
        # Column 4: Date
        # Column 5: Seeders
        # Column 6: Leechers
        # Column 7: Downloads

        try:
            # Extract name and nyaa_id from the view link
            # Skip comment links and find the main torrent link
            name_cell = cells[1]
            view_link = None

            # Find all links with /view/\d+ pattern
            all_view_links = name_cell.find_all("a", href=re.compile(r"/view/\d+"))

            # Filter out comment links (those with #comments or class="comments")
            for link in all_view_links:
                href = link.get("href", "")
                classes = link.get("class", [])

                # Skip if it's a comment link
                if "#comments" in href or "comments" in classes:
                    continue

                # This is the main torrent link
                view_link = link
                break

            if not view_link:
                logger.warning("No view link found in name cell")
                return None

            filename = view_link.get("title") or view_link.get_text().strip()
            nyaa_id = self._extract_nyaa_id(view_link["href"])

            # Extract infohash from magnet link
            link_cell = cells[2]
            magnet_link = link_cell.find("a", href=re.compile(r"magnet:"))
            if not magnet_link:
                logger.warning("No magnet link found in link cell")
                return None

            infohash = self._extract_infohash(magnet_link["href"])

            # Extract size
            size_text = cells[3].get_text().strip()
            size_bytes = self._parse_size(size_text)

            # Extract date from data-timestamp attribute
            date_cell = cells[4]
            timestamp_str = date_cell.get("data-timestamp")
            if not timestamp_str:
                logger.warning("No data-timestamp found in date cell")
                return None

            pubdate = Instant.from_timestamp(int(timestamp_str))

            # Extract seeders, leechers, downloads
            seeders = int(cells[5].get_text().strip())
            leechers = int(cells[6].get_text().strip())
            downloads = int(cells[7].get_text().strip())

            # Determine if torrent is trusted (check for success class)
            trusted = "success" in row.get("class", [])
            remake = "danger" in row.get("class", [])

            # Extract metadata with guessit
            guessit_data = None
            if filename:
                try:
                    guessit_result = guessit.guessit(filename)
                    guessit_data = json.loads(
                        json.dumps(
                            guessit_result, cls=GuessitEncoder, ensure_ascii=False
                        )
                    )
                except Exception as e:
                    logger.warning(f"Guessit parsing failed for '{filename}': {e}")
                    guessit_data = None

            # Create TorrentData
            torrent_data = TorrentData(
                infohash=infohash,
                filename=filename,
                pubdate=pubdate,
                size_bytes=size_bytes,
                nyaa_id=nyaa_id,
                trusted=trusted,
                remake=remake,
                seeders=seeders,
                leechers=leechers,
                downloads=downloads,
                guessit_data=guessit_data,
            )

            return torrent_data

        except Exception as e:
            logger.warning(f"Failed to parse row data: {e}")
            return None

    def _extract_nyaa_id(self, view_href: str) -> int:
        """Extract nyaa_id from view link href like '/view/1994237'."""
        match = re.search(r"/view/(\d+)", view_href)
        if not match:
            raise ValueError(f"Could not extract nyaa_id from: {view_href}")
        return int(match.group(1))

    def _extract_infohash(self, magnet_url: str) -> str:
        """Extract infohash from magnet link."""
        parsed = urlparse(magnet_url)
        query_params = parse_qs(parsed.query)

        # Look for xt parameter with btih
        xt_values = query_params.get("xt", [])
        for xt in xt_values:
            if xt.startswith("urn:btih:"):
                return xt[9:]  # Remove "urn:btih:" prefix

        raise ValueError(f"Could not extract infohash from magnet URL: {magnet_url}")

    def _parse_size(self, size_text: str) -> int:
        """Parse size string like '1.2 GiB' or '309.2 MiB' to bytes."""
        size_text = size_text.strip()

        # Mapping of units to bytes
        units = {
            "TiB": 1024**4,
            "GiB": 1024**3,
            "MiB": 1024**2,
            "KiB": 1024,
            "TB": 1000**4,
            "GB": 1000**3,
            "MB": 1000**2,
            "KB": 1000,
            "B": 1,
        }

        # Find the unit in the string (check longest units first)
        for unit, multiplier in units.items():
            if size_text.endswith(unit):
                size_value = float(size_text[: -len(unit)].strip())
                return int(size_value * multiplier)

        raise ValueError(f"Could not parse size: {size_text}")

    def process_page(self, page: int = 1) -> int:
        """Process a single page and insert torrents into database."""
        logger.info(f"Processing page {page}")

        # Fetch the HTML page
        html = self.fetch_page(page)

        # Parse torrents from HTML
        torrents = self.parse_html_page(html)

        processed_count = 0

        for torrent_data in torrents:
            try:
                # Check if torrent already exists
                if self.db.get_torrent_exists(torrent_data.infohash):
                    logger.debug(
                        f"Torrent {torrent_data.infohash} already exists, skipping"
                    )
                    continue

                # Insert torrent
                self.db.insert_torrent(torrent_data)
                processed_count += 1

                logger.debug(f"Processed torrent: {torrent_data.filename}")

            except Exception as e:
                logger.error(f"Failed to process torrent {torrent_data.infohash}: {e}")
                continue

        logger.info(f"Processed {processed_count} new torrents from page {page}")
        return processed_count
