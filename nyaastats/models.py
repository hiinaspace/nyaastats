"""Pydantic models for nyaastats data structures."""

from pydantic import BaseModel, ConfigDict
from whenever import Instant


class StatsData(BaseModel):
    """Statistics data for a torrent."""

    model_config = ConfigDict(extra="forbid")

    seeders: int
    leechers: int
    downloads: int


class GuessitData(BaseModel):
    """Guessit metadata for a torrent."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    alternative_title: str | None = None
    episode: int | None = None
    season: int | None = None
    year: int | None = None
    release_group: str | None = None
    screen_size: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    source: str | None = None
    container: str | None = None
    language: str | None = None
    subtitles: list[str] | None = None
    # Additional fields are allowed due to extra="allow"


class TorrentData(BaseModel):
    """Torrent data structure."""

    model_config = ConfigDict(extra="forbid")

    infohash: str
    filename: str
    pubdate: Instant
    size_bytes: int
    nyaa_id: int | None = None
    trusted: bool = False
    remake: bool = False
    seeders: int
    leechers: int
    downloads: int
