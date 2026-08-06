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
    chunks: list[VitamateChunk] = Field(default_factory=list)


class VitamateSearchScope(BaseModel):
    # Spring이 검증해 내려준 분석 검색 범위
    project_id: int = Field(alias="projectId")
    block_id: int = Field(alias="blockId")
    file_version_ids: list[int] = Field(alias="fileVersionIds")


class VitamateAnalysisJob(BaseModel):
    # Python worker가 Spring에서 조회하는 분석 작업 상세
    analysis_id: int = Field(alias="analysisId")
    attempt_id: str = Field(alias="attemptId")
    prompt: str
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
    error_message: str | None = Field(default=None, alias="errorMessage")

    model_config = {
        "populate_by_name": True,
    }


class VitamateFileIndexCallbackResponse(BaseModel):
    # Spring file_index callback API 응답입니다.
    accepted: bool
    file_version_id: int = Field(alias="fileVersionId")
    index_status: str = Field(alias="indexStatus")
    reason: str | None = None
    
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
    saved_chunk_count: int = Field(alias="savedChunkCount")