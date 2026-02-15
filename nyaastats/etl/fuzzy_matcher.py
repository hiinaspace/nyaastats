"""Fuzzy title matching for torrent-to-AniList attribution."""

import logging
import re
from dataclasses import dataclass

from thefuzz import fuzz

from .anilist_client import AniListShow
from .config import EPISODE_SEASON_MAPPINGS, FUZZY_MATCH_THRESHOLD, TITLE_OVERRIDES

logger = logging.getLogger(__name__)


@dataclass
class TitleMatch:
    """Result of fuzzy title matching."""

    anilist_id: int
    score: float
    method: str  # "episode_range" | "manual_override" | "season_aware" | "fuzzy"
    matched_title: str  # Which AniList title variant matched
    season_matched: int | None = None  # Season number if season-aware match used


class FuzzyMatcher:
    """Fuzzy title matcher for torrents to AniList shows."""

    def __init__(
        self,
        shows: list[AniListShow],
        threshold: int = FUZZY_MATCH_THRESHOLD,
        overrides: dict[str, int] | None = None,
    ):
        """Initialize fuzzy matcher.

        Args:
            shows: List of AniList shows to match against
            threshold: Minimum fuzzy match score (0-100)
            overrides: Manual title overrides dict
        """
        self.shows = shows
        self.threshold = threshold
        self.overrides = overrides or TITLE_OVERRIDES

        # Build lookup index for shows
        self._show_by_id = {show.id: show for show in shows}

        # Build searchable title variants
        self._title_variants = self._build_title_index()

    def _is_informative_normalized_title(self, title: str) -> bool:
        """Check if normalized title has enough signal for fuzzy matching."""
        # Avoid empty/non-latin-normalized strings and low-information tokens
        # like "2" that can spuriously score 100 against similarly degenerate
        # AniList synonyms.
        return len(title) >= 3 and bool(re.search(r"[a-z]", title))

    def _build_title_index(self) -> dict[int, list[str]]:
        """Build index of normalized title variants per show.

        Returns:
            Dict mapping anilist_id to list of normalized title variants
        """
        index = {}

        for show in self.shows:
            variants = []

            variant_set = set()

            # Add romaji title
            if show.title_romaji:
                normalized = self._normalize_title(show.title_romaji)
                if self._is_informative_normalized_title(normalized):
                    variant_set.add(normalized)

            # Add english title
            if show.title_english:
                normalized = self._normalize_title(show.title_english)
                if self._is_informative_normalized_title(normalized):
                    variant_set.add(normalized)

            # Add synonyms
            for synonym in show.synonyms:
                if synonym:
                    normalized = self._normalize_title(synonym)
                    if self._is_informative_normalized_title(normalized):
                        variant_set.add(normalized)

            variants.extend(variant_set)
            index[show.id] = variants

        return index

    def _normalize_title(self, title: str) -> str:
        """Normalize title for fuzzy matching.

        Converts to lowercase, removes punctuation, collapses whitespace.

        Args:
            title: Raw title string

        Returns:
            Normalized title
        """
        # Lowercase
        title = title.lower()

        # Remove punctuation, keep only alphanumeric and spaces
        title = re.sub(r"[^a-z0-9\s]", "", title)

        # Collapse multiple spaces
        title = re.sub(r"\s+", " ", title).strip()

        return title

    def _episode_range_match(
        self, torrent_title: str, episode: int | None
    ) -> TitleMatch | None:
        """Match using episode number ranges for continuing series.

        Args:
            torrent_title: Title extracted from torrent
            episode: Episode number from guessit

        Returns:
            TitleMatch if episode falls within a configured range, None otherwise
        """
        if episode is None:
            return None

        normalized_title = self._normalize_title(torrent_title)

        # Check if this title has episode mappings configured
        if normalized_title not in EPISODE_SEASON_MAPPINGS:
            return None

        # Find matching range
        mappings = EPISODE_SEASON_MAPPINGS[normalized_title]
        for min_ep, max_ep, anilist_id in mappings:
            if min_ep <= episode <= max_ep:
                show = self._show_by_id.get(anilist_id)
                if show:
                    return TitleMatch(
                        anilist_id=anilist_id,
                        score=100.0,
                        method="episode_range",
                        matched_title=show.title_romaji,
                        season_matched=None,  # Episode ranges are explicit, not season-based
                    )

        return None

    def match(
        self,
        torrent_title: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> TitleMatch | None:
        """Match torrent title to AniList show.

        Args:
            torrent_title: Title extracted from torrent filename (via guessit)
            season: Season number from guessit (if available)
            episode: Episode number from guessit (if available)

        Returns:
            TitleMatch if a match is found, None otherwise
        """
        normalized_torrent = self._normalize_title(torrent_title)

        # Skip fuzzy matching for low-information parsed titles
        if not self._is_informative_normalized_title(normalized_torrent):
            return None

        # Priority 1: Episode-range mapping (for continuing series)
        episode_match = self._episode_range_match(torrent_title, episode)
        if episode_match:
            return episode_match

        # Priority 2: Check manual overrides
        if normalized_torrent in self.overrides:
            anilist_id = self.overrides[normalized_torrent]
            show = self._show_by_id.get(anilist_id)
            if show:
                return TitleMatch(
                    anilist_id=anilist_id,
                    score=100.0,
                    method="manual_override",
                    matched_title=show.title_romaji,
                    season_matched=season,
                )

        # Debug logging for specific titles
        if "oshi no ko" in normalized_torrent:
            logger.debug(
                f"Matching Oshi no Ko: normalized='{normalized_torrent}', season={season}, episode={episode}"
            )

        # Priority 3 & 4: Fuzzy matching (season-aware, then fallback)
        best_score = 0.0
        best_id = None
        best_season_match = None  # Track if season-aware match worked

        for anilist_id, variants in self._title_variants.items():
            show = self._show_by_id[anilist_id]

            for variant in variants:
                # Use token_sort_ratio for better handling of word order differences
                score = fuzz.token_sort_ratio(normalized_torrent, variant)

                # Bonus for season-aware matching
                # If guessit provides a season number and the show has matching format string
                season_bonus = 0
                if season is not None and show.format:
                    # Check if show format indicates this is the correct season
                    # AniList doesn't directly expose season numbers, so we use heuristics:
                    # - Check if show title contains season indicators like "2nd Season", "Season 3"
                    # This is a simplified heuristic; more sophisticated matching could be added
                    title_lower = show.title_romaji.lower()
                    if (
                        f"season {season}" in title_lower
                        or f"{season}nd season" in title_lower
                        or f"{season}rd season" in title_lower
                        or f"{season}th season" in title_lower
                    ):
                        season_bonus = 10  # Boost matches that have season indicators

                adjusted_score = score + season_bonus

                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_id = anilist_id
                    best_season_match = season if season_bonus > 0 else None

        # Return match if above threshold
        if best_score >= self.threshold and best_id:
            show = self._show_by_id[best_id]
            return TitleMatch(
                anilist_id=best_id,
                score=best_score,
                method="season_aware" if best_season_match else "fuzzy",
                matched_title=show.title_romaji,
                season_matched=best_season_match,
            )

        # Fallback: strip subtitle after " - " (common in SubsPlease titles with
        # Japanese subtitles that tank fuzzy scores, e.g.
        # "Kizoku Tensei - Megumareta Umare kara Saikyou no Chikara wo Eru")
        # Check the raw title since normalization removes the dash
        if best_score < self.threshold and " - " in torrent_title:
            prefix = self._normalize_title(torrent_title.split(" - ")[0].strip())
            if self._is_informative_normalized_title(prefix) and len(prefix) >= 4:
                return self._match_prefix_fallback(prefix, season)

        return None

    def _match_prefix_fallback(
        self, prefix: str, season: int | None
    ) -> TitleMatch | None:
        """Try matching with just the title prefix (before subtitle).

        Args:
            prefix: Normalized title prefix to match
            season: Season number from guessit (if available)

        Returns:
            TitleMatch if a match is found, None otherwise
        """
        # Check manual overrides first
        if prefix in self.overrides:
            anilist_id = self.overrides[prefix]
            show = self._show_by_id.get(anilist_id)
            if show:
                return TitleMatch(
                    anilist_id=anilist_id,
                    score=100.0,
                    method="manual_override",
                    matched_title=show.title_romaji,
                    season_matched=season,
                )

        best_score = 0.0
        best_id = None

        for anilist_id, variants in self._title_variants.items():
            for variant in variants:
                score = fuzz.token_sort_ratio(prefix, variant)
                if score > best_score:
                    best_score = score
                    best_id = anilist_id

        if best_score >= self.threshold and best_id:
            show = self._show_by_id[best_id]
            return TitleMatch(
                anilist_id=best_id,
                score=best_score,
                method="fuzzy",
                matched_title=show.title_romaji,
                season_matched=None,
            )

        return None

    def match_batch(
        self,
        torrent_titles: list[tuple[str, str, int | None, int | None]],
    ) -> tuple[list[tuple[any, TitleMatch]], list[tuple[any, str, float | None]]]:
        """Match a batch of torrent titles.

        Args:
            torrent_titles: List of (identifier, title, season, episode) tuples

        Returns:
            Tuple of:
            - List of (identifier, TitleMatch) for successful matches
            - List of (identifier, title, best_score) for failed matches
        """
        matched = []
        unmatched = []

        for identifier, title, season, episode in torrent_titles:
            match_result = self.match(title, season=season, episode=episode)

            if match_result:
                matched.append((identifier, match_result))
            else:
                # For unmatched, try to get best score for debugging
                normalized = self._normalize_title(title)
                if not self._is_informative_normalized_title(normalized):
                    unmatched.append((identifier, title, None))
                    continue
                best_score = 0.0
                for variants in self._title_variants.values():
                    for variant in variants:
                        score = fuzz.token_sort_ratio(normalized, variant)
                        best_score = max(best_score, score)

                unmatched.append(
                    (identifier, title, best_score if best_score > 0 else None)
                )

        # Log matching statistics by method
        method_counts = {}
        for _, match in matched:
            method_counts[match.method] = method_counts.get(match.method, 0) + 1

        logger.info(
            f"Matched {len(matched)}/{len(torrent_titles)} torrents "
            f"({len(matched) / len(torrent_titles) * 100:.1f}%)"
        )
        if method_counts:
            logger.info(f"Match methods: {method_counts}")

        if unmatched:
            logger.warning(f"{len(unmatched)} torrents could not be matched")

        return matched, unmatched
