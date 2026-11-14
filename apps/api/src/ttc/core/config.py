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
    # 人才库向量化：未配置时回落到本地字符 n-gram 哈希向量（lexical）
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_dim: int = 512
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
    # 本账号实测可连的实时模型；qwen3-omni-flash-realtime 会直接回 Model not exist。
    dashscope_realtime_model: str = "qwen3.8-omni-flash-realtime"
    dashscope_realtime_voice: str = "Tina"
    dashscope_realtime_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    # 扫描件 OCR：配置模型链后优先走视觉模型；质量不足时按顺序换更强模型。
    # 链上模型全部失败时报错，不回落 tesseract（tesseract 只在未配置视觉模型时使用）。
    ocr_vlm_models: str | None = None
    ocr_vlm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ocr_vlm_api_key: str | None = None
    ocr_vlm_timeout_seconds: int = 90
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
