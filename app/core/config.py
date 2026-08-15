from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 서버 실행 환경 구분
    app_env: str = "local"
    log_level: str = "INFO"

    # Gemini API 설정
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # Gemini 실패 시 local 개발용 임시 결과를 사용할지 여부
    vitamate_ai_fallback_enabled: bool = False

    # Spring Boot 내부 API 설정
    spring_base_url: str = "http://localhost:8080"
    vitamate_worker_token: str = ""

    # Redis Stream worker 설정
    redis_url: str = "redis://localhost:6379/0"
    vitamate_stream_key: str = "vitamate:analysis:jobs"
    vitamate_consumer_group: str = "vitamate-python-workers"
    vitamate_consumer_name: str = "vitamate-worker-local"

    # 입찰 공고 AI 요약 worker 설정
    bidding_worker_token: str = ""
    bidding_summary_stream_key: str = "bidding:summary:jobs"
    bidding_summary_consumer_group: str = "bidding-summary-workers"
    bidding_summary_consumer_name: str = "bidding-summary-worker-local"
    bidding_summary_claim_min_idle_ms: int = 60_000
    bidding_summary_claim_count: int = 10

    # 입찰 문서 비교 검토 worker 설정 (bidding_worker_token 재사용 - 같은 /internal/v1/bidding 경로)
    bidding_review_stream_key: str = "bidding:review:jobs"
    bidding_review_consumer_group: str = "bidding-review-workers"
    bidding_review_consumer_name: str = "bidding-review-worker-local"
    bidding_review_claim_min_idle_ms: int = 60_000
    bidding_review_claim_count: int = 10

    vitamate_file_index_stream_key: str = "vitamate:file-index:jobs"
    vitamate_file_index_consumer_group: str = "vitamate-file-index-workers"
    vitamate_file_index_consumer_name: str = "vitamate-file-index-worker-local"
        # ChromaDB 설정입니다.
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection_name: str = "vitamate_document_chunks"
    
    #Chroma cleanup Redis Stream과 DLQ 설정을 관리
    vitamate_chroma_cleanup_stream_key: str = "vitamate:chroma-cleanup:jobs"
    vitamate_chroma_cleanup_consumer_group: str = "vitamate-chroma-cleanup-workers"
    vitamate_chroma_cleanup_consumer_name: str = "vitamate-chroma-cleanup-worker-local"
    vitamate_chroma_cleanup_dlq_stream_key: str = "vitamate:chroma-cleanup:dlq"
    
    # ACK되지 않은 cleanup 메시지의 자동 회수 설정입니다.
    vitamate_chroma_cleanup_claim_min_idle_ms: int = 300_000
    vitamate_chroma_cleanup_claim_count: int = 10
    
    
    
    # 문서 chunk 임베딩 모델 설정입니다.
    gemini_embedding_model: str = "gemini-embedding-001"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    # 설정 객체를 한 번만 만들고 재사용한다.
    return Settings()
