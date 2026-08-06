from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ?쒕쾭 ?ㅽ뻾 ?섍꼍 援щ텇
    app_env: str = "local"
    log_level: str = "INFO"

    # Gemini API ?ㅼ젙
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # Gemini ?ㅽ뙣 ??local 媛쒕컻???꾩떆 寃곌낵瑜??ъ슜?좎? ?щ?
    vitamate_ai_fallback_enabled: bool = False

    # Spring Boot ?대? API ?ㅼ젙
    spring_base_url: str = "http://localhost:8080"
    vitamate_worker_token: str = ""

    # Redis Stream worker ?ㅼ젙
    redis_url: str = "redis://localhost:6379/0"
    vitamate_stream_key: str = "vitamate:analysis:jobs"
    vitamate_consumer_group: str = "vitamate-python-workers"
    vitamate_consumer_name: str = "vitamate-worker-local"
    vitamate_file_index_stream_key: str = "vitamate:file-index:jobs"
    vitamate_file_index_consumer_group: str = "vitamate-file-index-workers"
    vitamate_file_index_consumer_name: str = "vitamate-file-index-worker-local"

    # ChromaDB 설정입니다.
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection_name: str = "vitamate_document_chunks"

    # 문서 chunk 임베딩 모델 설정입니다.
    gemini_embedding_model: str = "gemini-embedding-001"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    # ?ㅼ젙 媛앹껜瑜???踰덈쭔 留뚮뱾怨??ъ궗?⑺븳??
    return Settings()

