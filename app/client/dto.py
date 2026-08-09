from pydantic import BaseModel, Field


class VitamateChunk(BaseModel):
    # AI 분석에 사용할 문서 청크 정보
    document_chunk_id: int = Field(alias="documentChunkId")
    chroma_id: str | None = Field(default=None, alias="chromaId")
    page_number: int | None = Field(default=None, alias="pageNumber")
    excerpt: str | None = None


class VitamateDocument(BaseModel):
    # 분석 대상 파일 버전과 그 안의 청크 목록
    file_version_id: int = Field(alias="fileVersionId")
    file_name: str = Field(alias="fileName")
    document_role: str = Field(alias="documentRole")
    chunks: list[VitamateChunk] = Field(default_factory=list)


class VitamateSearchScope(BaseModel):
    # Spring이 검증해 내려준 분석 검색 범위
    project_id: int = Field(alias="projectId")
    block_id: int = Field(alias="blockId")
    file_version_ids: list[int] = Field(alias="fileVersionIds")


class VitamateReviewTemplate(BaseModel):
    # Spring이 분석 요청 시점에 고정해서 전달하는 검토 템플릿 항목입니다.
    review_type: str = Field(alias="reviewType")
    category_code: str = Field(alias="categoryCode")
    category_name: str = Field(alias="categoryName")
    prompt_template: str = Field(alias="promptTemplate")
    template_version: str = Field(alias="templateVersion")


class VitamateAnalysisJob(BaseModel):
    # Python worker가 Spring에서 조회하는 분석 작업 상세
    analysis_id: int = Field(alias="analysisId")
    attempt_id: str = Field(alias="attemptId")
    review_type: str = Field(alias="reviewType")
    review_category_codes: list[str] = Field(
        default_factory=list,
        alias="reviewCategoryCodes",
    )
    prompt: str
    review_templates: list[VitamateReviewTemplate] = Field(
        default_factory=list,
        alias="reviewTemplates",
    )
    search_scope: VitamateSearchScope = Field(alias="searchScope")
    documents: list[VitamateDocument] = Field(default_factory=list)


class VitamateCitationCallback(BaseModel):
    # 분석 결과의 근거 청크 정보
    document_chunk_id: int = Field(alias="documentChunkId")
    file_version_id: int = Field(alias="fileVersionId")
    rank_order: int = Field(alias="rankOrder")
    distance_score: float = Field(alias="distanceScore")
    excerpt: str | None = None


class VitamateCallbackRequest(BaseModel):
    # Spring callback API에 보낼 분석 결과
    attempt_id: str = Field(alias="attemptId")
    analysis_status: str = Field(alias="analysisStatus")
    result: str | None = None
    citations: list[VitamateCitationCallback] = Field(default_factory=list)
    error_message: str | None = Field(default=None, alias="errorMessage")

    model_config = {
        "populate_by_name": True,
    }


class VitamateCallbackResponse(BaseModel):
    # Spring callback API 응답
    accepted: bool
    analysis_id: int = Field(alias="analysisId")
    analysis_status: str = Field(alias="analysisStatus")
    reason: str | None = None

class VitamateFileIndexCallbackRequest(BaseModel):
    # Spring file_index callback API로 보낼 인덱싱 상태 변경 요청입니다.
    index_status: str = Field(alias="indexStatus")
    index_attempt_id: str | None = Field(default=None, alias="indexAttemptId")
    error_message: str | None = Field(default=None, alias="errorMessage")

    model_config = {
        "populate_by_name": True,
    }


class VitamateFileIndexCallbackResponse(BaseModel):
    # Spring file_index callback API 응답입니다.
    accepted: bool
    file_version_id: int = Field(alias="fileVersionId")
    index_attempt_id: str | None = Field(default=None, alias="indexAttemptId")
    index_status: str = Field(alias="indexStatus")
    reason: str | None = None

    
    
class VitamateSavedDocumentChunk(BaseModel):
    # Spring에 저장된 document_chunk 식별 정보입니다.
    document_chunk_id: int = Field(alias="documentChunkId")
    chunk_index: int = Field(alias="chunkIndex")
    embedding_status: str = Field(alias="embeddingStatus")
    
class VitamateFileIndexSourceResponse(BaseModel):
    # Spring에서 받은 파일 인덱싱 대상 파일 정보입니다.
    file_version_id: int = Field(alias="fileVersionId")
    file_id: int = Field(alias="fileId")
    project_id: int = Field(alias="projectId")
    original_file_name: str = Field(alias="originalFileName")
    extension: str
    mime_type: str | None = Field(default=None, alias="mimeType")
    size_bytes: int | None = Field(default=None, alias="sizeBytes")
    storage_key: str = Field(alias="storageKey")
    download_url: str = Field(alias="downloadUrl")


class VitamateDocumentChunkRequest(BaseModel):
    # Spring document_chunk 테이블에 저장할 chunk 한 건입니다.
    chunk_index: int = Field(alias="chunkIndex")
    page_number: int | None = Field(default=None, alias="pageNumber")
    section_title: str | None = Field(default=None, alias="sectionTitle")
    start_offset: int | None = Field(default=None, alias="startOffset")
    end_offset: int | None = Field(default=None, alias="endOffset")
    token_count: int | None = Field(default=None, alias="tokenCount")
    excerpt: str

    model_config = {
        "populate_by_name": True,
    }


class VitamateDocumentChunkSaveRequest(BaseModel):
    # Spring chunk 저장 API로 보낼 요청입니다.
    chunks: list[VitamateDocumentChunkRequest]

    model_config = {
        "populate_by_name": True,
    }


class VitamateDocumentChunkSaveResponse(BaseModel):
    # Spring chunk 저장 API 응답입니다.
    file_version_id: int = Field(alias="fileVersionId")
    index_attempt_id: str = Field(alias="indexAttemptId")
    saved_chunk_count: int = Field(alias="savedChunkCount")
    saved_chunks: list[VitamateSavedDocumentChunk] = Field(default_factory=list, alias="savedChunks")

class VitamateChunkEmbeddingRequest(BaseModel):
    # document_chunk와 ChromaDB vector를 연결하는 요청입니다.
    document_chunk_id: int = Field(alias="documentChunkId")
    chroma_id: str = Field(alias="chromaId")

    model_config = {
        "populate_by_name": True,
    }
    
class VitamateChunkEmbeddingSaveRequest(BaseModel):
    # ChromaDB 저장 결과를 Spring에 반영하는 요청입니다.
    embedding_model: str = Field(alias="embeddingModel")
    index_attempt_id: str = Field(alias="indexAttemptId")
    chunks: list[VitamateChunkEmbeddingRequest]

    model_config = {
        "populate_by_name": True,
    }
    
class VitamateChromaCleanupCallbackRequest(BaseModel):
    # ChromaDB 벡터 삭제 처리 결과를 Spring에 전달합니다.
    attempt_id: str = Field(min_length=1, alias="attemptId")
    status: str
    retryable: bool = False
    deleted_vector_count: int | None = Field(
        default=None,
        ge=0,
        alias="deletedVectorCount",
    )
    error_code: str | None = Field(default=None, alias="errorCode")
    error_message: str | None = Field(default=None, alias="errorMessage")

    model_config = {
        "populate_by_name": True,
    }


class VitamateChromaCleanupCallbackResponse(BaseModel):
    # Spring이 cleanup callback을 수락했는지 나타내는 응답입니다.
    accepted: bool
    cleanup_job_id: int = Field(alias="cleanupJobId")
    cleanup_status: str = Field(alias="cleanupStatus")
    reason: str | None = None

    model_config = {
        "populate_by_name": True,
    }
    
