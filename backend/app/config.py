"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "EasySpeak API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./easyspeak.db"

    # Admin API Key (for content import from Hermes)
    ADMIN_API_KEY: str = "change-me-in-production"

    # WeChat Mini Program
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    # Obsidian data path (for importing historical data)
    OBSIDIAN_DATA_PATH: str = os.path.expanduser(
        "~/Documents/obsidianFiles/koenigsegg/英语口语"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
