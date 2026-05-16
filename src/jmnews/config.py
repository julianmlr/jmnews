"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    filter_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="JMNEWS_FILTER_MODEL"
    )
    briefing_model: str = Field(
        default="claude-sonnet-4-6", alias="JMNEWS_BRIEFING_MODEL"
    )

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # Paths
    db_path: Path = Field(default=Path("data/jmnews.db"), alias="JMNEWS_DB_PATH")
    profile_path: Path = Field(default=Path("jm_profile.md"), alias="JMNEWS_PROFILE_PATH")
    briefings_dir: Path = Field(default=Path("data/briefings"), alias="JMNEWS_BRIEFINGS_DIR")
    log_dir: Path = Field(default=Path("data/logs"), alias="JMNEWS_LOG_DIR")

    # Behaviour
    lookback_hours: int = Field(default=24, alias="JMNEWS_LOOKBACK_HOURS")
    filter_batch_size: int = Field(default=15, alias="JMNEWS_FILTER_BATCH_SIZE")
    purge_days: int = Field(default=30, alias="JMNEWS_PURGE_DAYS")
    timezone: str = Field(default="Europe/Berlin", alias="JMNEWS_TIMEZONE")
    collect_hour: int = Field(default=6, alias="JMNEWS_COLLECT_HOUR")
    collect_minute: int = Field(default=45, alias="JMNEWS_COLLECT_MINUTE")
    deliver_hour: int = Field(default=7, alias="JMNEWS_DELIVER_HOUR")
    deliver_minute: int = Field(default=0, alias="JMNEWS_DELIVER_MINUTE")

    log_level: str = Field(default="INFO", alias="JMNEWS_LOG_LEVEL")


def get_settings() -> Settings:
    return Settings()
