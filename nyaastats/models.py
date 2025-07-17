"""Pydantic models for nyaastats data structures."""

from pydantic import BaseModel, ConfigDict
from whenever import Instant


class StatsData(BaseModel):
    """Statistics data for a torrent."""

    model_config = ConfigDict(extra="forbid")

    seeders: int
    leechers: int
    downloads: int


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
    guessit_data: dict | None = None
