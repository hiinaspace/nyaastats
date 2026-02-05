#!/usr/bin/env python3
"""Look up anime on AniList by title. Useful for finding IDs for ETL overrides.

Usage:
    uv run python scripts/anilist_lookup.py "Gachiakuta"
    uv run python scripts/anilist_lookup.py "Gachiakuta" "Jigokuraku" "One Piece"
"""

import argparse
import sys

import httpx

ANILIST_API_URL = "https://graphql.anilist.co"

SEARCH_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 5) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      id
      title {
        romaji
        english
      }
      format
      status
      episodes
      seasonYear
      season
      startDate { year month }
    }
  }
}
"""


def search_anime(title: str) -> list[dict]:
    with httpx.Client() as client:
        resp = client.post(
            ANILIST_API_URL,
            json={"query": SEARCH_QUERY, "variables": {"search": title}},
        )
        resp.raise_for_status()
        return resp.json()["data"]["Page"]["media"]


def main():
    parser = argparse.ArgumentParser(description="Look up anime on AniList by title")
    parser.add_argument("titles", nargs="+", help="Anime titles to search for")
    args = parser.parse_args()

    for title in args.titles:
        print(f"\n{'=' * 60}")
        print(f"Search: {title}")
        print("=" * 60)
        results = search_anime(title)
        if not results:
            print("  No results found")
            continue
        for r in results:
            romaji = r["title"]["romaji"]
            english = r["title"].get("english") or ""
            fmt = r.get("format") or "?"
            status = r.get("status") or "?"
            eps = r.get("episodes") or "?"
            year = r.get("seasonYear") or r.get("startDate", {}).get("year") or "?"
            season = r.get("season") or ""
            eng_str = f" / {english}" if english and english != romaji else ""
            print(f"  ID: {r['id']:>8}  {romaji}{eng_str}")
            print(f"           {fmt} | {status} | {eps} eps | {season} {year}")


if __name__ == "__main__":
    sys.exit(main() or 0)
