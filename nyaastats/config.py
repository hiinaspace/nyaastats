from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration settings for nyaastats."""

    # Database
    db_path: str = Field(
        default="nyaastats.db", description="Path to SQLite database file"
    )

    # RSS
    rss_url: str = Field(
        default="https://nyaa.si/?page=rss&c=1_2&f=0",
        description="URL for nyaa.si RSS feed",
    )
    rss_fetch_interval_hours: int = Field(
        default=1, description="Interval between RSS fetches in hours"
    )

    # Tracker
    tracker_url: str = Field(
        default="http://nyaa.tracker.wf:7777/scrape",
        description="BitTorrent tracker scrape URL",
    )
    scrape_batch_size: int = Field(
        default=40, description="Number of torrents to scrape in one batch"
    )
    scrape_interval_seconds: int = Field(
        default=60, description="Interval between scrape operations in seconds"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Optional observability
    enable_logfire: bool = Field(
        default=False, description="Enable Logfire observability integration"
    )
    logfire_token: str = Field(default="", description="Logfire authentication token")

    class Config:
        env_prefix = "NYAA_"
        case_sensitive = False


settings = Settings()
