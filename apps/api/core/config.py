from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/ — keep .env resolution independent of the process working directory.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DeepSeek (OpenAI-compatible)
    # https://api-docs.deepseek.com/zh-cn/
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-flash"

    # Pipeline concurrency / LLM request behavior
    MAX_CONCURRENCY: int = 5
    MAX_LLM_RETRIES: int = 3
    LLM_RETRY_MIN_WAIT: float = 1.0
    LLM_RETRY_MAX_WAIT: float = 10.0
    LLM_TIMEOUT_SECONDS: float = 120.0

    # Storage
    CACHE_DIR: str = "./cache"
    UPLOAD_DIR: str = "./uploads"
    SAVED_JOBS_FILE: str = "./cache/saved_jobs.json"

    # App
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def deepseek_configured(self) -> bool:
        """True when a non-empty DeepSeek API key is available."""
        return bool(self.DEEPSEEK_API_KEY.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
