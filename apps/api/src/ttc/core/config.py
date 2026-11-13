from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TTC AI 人才挖掘平台 API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str | None = None
    jwt_secret: str | None = None
    column_encryption_key: str | None = None
    demo_mode: bool = False
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket_resumes: str = "resumes"
    s3_bucket_audio: str = "audio"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int = 60
    realtime_api_key: str | None = None
    realtime_model: str | None = None
    openats_base_url: str | None = None
    openats_api_key: str | None = None
    vekt_base_url: str | None = None
    vekt_api_key: str | None = None
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
