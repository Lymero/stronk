"""Typed settings from the environment and `.env`. Secrets are SecretStr and never printed."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="STRONK_", extra="ignore")

    runs_dir: Path = Path("runs")
    dist_dir: Path = Path("dist/data")
    riot_api_key: SecretStr | None = Field(default=None, validation_alias="RIOT_API_KEY")
