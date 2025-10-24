from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BIKE_RECORDER_", env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///" + str(Path(__file__).resolve().parents[1] / "bike_recorder.db")
    storage_dir: Path = Path(__file__).resolve().parents[1] / "storage"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    allow_registration: bool = True
    caddy_proxy_origin: Optional[str] = None


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
