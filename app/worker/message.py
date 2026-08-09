from datetime import datetime
import json
from pydantic import BaseModel, Field, field_validator

class VitamateAnalysisJobMessage(BaseModel):
    # Redis Stream에서 받은 비타메이트 분석 작업 메시지
    analysis_id: int = Field(alias="analysisId")
    attempt_id: str = Field(alias="attemptId")
    retry_count: int = Field(default=0, alias="retryCount")
    created_at: datetime | None = Field(default=None, alias="createdAt")

    model_config = {
        "populate_by_name": True,
    }
class VitamateFileIndexJobMessage(BaseModel):
    # Redis Stream에서 받은 파일 인덱싱 작업 메시지입니다.
    file_version_id: int = Field(alias="fileVersionId")
    retry_count: int = Field(default=0, alias="retryCount")
    created_at: datetime | None = Field(default=None, alias="createdAt")

    model_config = {
        "populate_by_name": True,
    }

class VitamateChromaCleanupJobMessage(BaseModel):
    # Redis Stream에서 받은 ChromaDB 벡터 삭제 작업 메시지입니다.
    cleanup_job_id: int = Field(gt=0, alias="cleanupJobId")
    cleanup_key: str = Field(min_length=1, alias="cleanupKey")
    attempt_id: str = Field(min_length=1, alias="attemptId")
    file_version_ids: list[int] = Field(
        min_length=1,
        alias="fileVersionIds",
    )
    retry_count: int = Field(default=0, ge=0, alias="retryCount")

    model_config = {
        "populate_by_name": True,
    }

    @field_validator("file_version_ids", mode="before")
    @classmethod
    def parse_file_version_ids(cls, value):
        # Redis에 JSON 문자열로 저장된 파일 버전 ID 목록을 변환합니다.
        if isinstance(value, str):
            return json.loads(value)
        return value

    @field_validator("file_version_ids")
    @classmethod
    def validate_file_version_ids(cls, value: list[int]) -> list[int]:
        # 잘못된 ID로 다른 ChromaDB 데이터를 삭제하지 못하게 차단합니다.
        if any(file_version_id <= 0 for file_version_id in value):
            raise ValueError("fileVersionIds must contain positive values")
        return value
