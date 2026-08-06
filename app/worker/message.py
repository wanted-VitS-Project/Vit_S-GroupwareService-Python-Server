from datetime import datetime

from pydantic import BaseModel, Field


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
