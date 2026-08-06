from google import genai

from app.core.config import Settings
from app.core.exceptions import VitamateAiGenerateError


class GeminiEmbeddingClient:
    # Gemini embedding API로 문서 chunk를 벡터로 변환합니다.

    def __init__(self, settings: Settings):
        self._model_name = settings.gemini_embedding_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def embed_text(self, text: str) -> list[float]:
        # 하나의 chunk 텍스트를 ChromaDB에 저장할 embedding vector로 변환합니다.
        if not text or not text.strip():
            raise VitamateAiGenerateError("Embedding text is empty")

        try:
            response = self._client.models.embed_content(
                model=self._model_name,
                contents=text.strip(),
            )
        except Exception as exc:
            raise VitamateAiGenerateError("Gemini embedding request failed") from exc

        embeddings = response.embeddings or []
        if not embeddings or not embeddings[0].values:
            raise VitamateAiGenerateError("Gemini returned empty embedding")

        return list(embeddings[0].values)
