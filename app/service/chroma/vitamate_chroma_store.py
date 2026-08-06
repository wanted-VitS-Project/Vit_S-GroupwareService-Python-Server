import chromadb

from app.core.config import Settings


class VitamateChromaStore:
    # 비타메이트 document_chunk embedding을 ChromaDB collection에 저장합니다.

    def __init__(self, settings: Settings):
        self._collection_name = settings.chroma_collection_name
        self._client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )

    def upsert_chunk(
        self,
        chroma_id: str,
        embedding: list[float],
        document: str,
        metadata: dict,
    ) -> None:
        # 같은 chroma_id가 다시 들어오면 기존 vector를 갱신합니다.
        collection = self._client.get_or_create_collection(name=self._collection_name)

        clean_metadata = {
            key: value
            for key, value in metadata.items()
            if value is not None
        }

        collection.upsert(
            ids=[chroma_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[clean_metadata],
        )
