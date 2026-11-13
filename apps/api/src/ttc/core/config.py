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
    # 简历-岗位匹配小模型（通过子进程调用 resume-match/infer_cli.py）
    resume_match_model_dir: str | None = None
    resume_match_python: str = "python3"
    resume_match_timeout_seconds: int = 120
    resume_match_allow_keyword_fallback: bool = False
    resume_match_cli_path: str | None = None
    realtime_api_key: str | None = None
    realtime_model: str | None = None
    realtime_provider: str = "openai_realtime"
    dashscope_api_key: str | None = None
    dashscope_realtime_model: str = "qwen3-omni-flash-realtime"
    dashscope_realtime_voice: str = "Cherry"
    dashscope_realtime_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
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
