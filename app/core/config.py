from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 서버 실행 환경 구분
    app_env: str = "local"
    log_level: str = "INFO"

    # Gemini API 설정
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    # Spring Boot 내부 API 설정
    spring_base_url: str = "http://localhost:8080"
    vitamate_worker_token: str = ""

    # Redis Stream worker 설정
    redis_url: str = "redis://localhost:6379/0"
    vitamate_stream_key: str = "vitamate:analysis:jobs"
    vitamate_consumer_group: str = "vitamate-python-workers"
    vitamate_consumer_name: str = "vitamate-worker-local"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    # 설정 객체를 한 번만 만들고 재사용한다.
    return Settings()