"""Fuzzy title matching for torrent-to-AniList attribution."""

import logging
import re
from dataclasses import dataclass

from thefuzz import fuzz

from .anilist_client import AniListShow
from .config import FUZZY_MATCH_THRESHOLD, TITLE_OVERRIDES

logger = logging.getLogger(__name__)


@dataclass
class TitleMatch:
    """Result of fuzzy title matching."""

    anilist_id: int
    score: float
    method: str  # "exact" | "fuzzy" | "manual_override"
    matched_title: str  # Which AniList title variant matched


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

    def _build_title_index(self) -> dict[int, list[str]]:
        """Build index of normalized title variants per show.

        Returns:
            Dict mapping anilist_id to list of normalized title variants
        """
        index = {}

        for show in self.shows:
            variants = []

            # Add romaji title
            if show.title_romaji:
                variants.append(self._normalize_title(show.title_romaji))

            # Add english title
            if show.title_english:
                variants.append(self._normalize_title(show.title_english))

            # Add synonyms
            for synonym in show.synonyms:
                if synonym:
                    variants.append(self._normalize_title(synonym))

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

    def match(self, torrent_title: str) -> TitleMatch | None:
        """Match torrent title to AniList show.

        Args:
            torrent_title: Title extracted from torrent filename (via guessit)

        Returns:
            TitleMatch if a match is found, None otherwise
        """
        normalized_torrent = self._normalize_title(torrent_title)

        # Check manual overrides first
        if normalized_torrent in self.overrides:
            anilist_id = self.overrides[normalized_torrent]
            show = self._show_by_id.get(anilist_id)
            if show:
                return TitleMatch(
                    anilist_id=anilist_id,
                    score=100.0,
                    method="manual_override",
                    matched_title=show.title_romaji,
                )

        # Try fuzzy matching against all variants
        best_match = None
        best_score = 0.0
        best_variant = None
        best_id = None

        for anilist_id, variants in self._title_variants.items():
            for variant in variants:
                # Use token_sort_ratio for better handling of word order differences
                score = fuzz.token_sort_ratio(normalized_torrent, variant)

                if score > best_score:
                    best_score = score
                    best_match = variant
                    best_id = anilist_id
                    best_variant = variant

        # Return match if above threshold
        if best_score >= self.threshold and best_id:
            show = self._show_by_id[best_id]
            return TitleMatch(
                anilist_id=best_id,
                score=best_score,
                method="fuzzy",
                matched_title=show.title_romaji,
            )

        return None

    def match_batch(
        self, torrent_titles: list[tuple[str, any]]
    ) -> tuple[list[tuple[any, TitleMatch]], list[tuple[any, str, float | None]]]:
        """Match a batch of torrent titles.

        Args:
            torrent_titles: List of (identifier, title) tuples

        Returns:
            Tuple of:
            - List of (identifier, TitleMatch) for successful matches
            - List of (identifier, title, best_score) for failed matches
        """
        matched = []
        unmatched = []

        for identifier, title in torrent_titles:
            match_result = self.match(title)

            if match_result:
                matched.append((identifier, match_result))
            else:
                # For unmatched, try to get best score for debugging
                normalized = self._normalize_title(title)
                best_score = 0.0
                for variants in self._title_variants.values():
                    for variant in variants:
                        score = fuzz.token_sort_ratio(normalized, variant)
                        best_score = max(best_score, score)

                unmatched.append(
                    (identifier, title, best_score if best_score > 0 else None)
                )

        logger.info(
            f"Matched {len(matched)}/{len(torrent_titles)} torrents "
            f"({len(matched) / len(torrent_titles) * 100:.1f}%)"
        )

        if unmatched:
            logger.warning(f"{len(unmatched)} torrents could not be matched")

        return matched, unmatched
