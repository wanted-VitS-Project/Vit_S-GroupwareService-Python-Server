from app.core.config import Settings
from app.service.chroma.vitamate_chroma_store import VitamateChromaStore


class VitamateChromaCleanupService:
    def __init__(
        self,
        settings: Settings,
        chroma_store: VitamateChromaStore | None = None,
    ):
        self._chroma_store = chroma_store or VitamateChromaStore(settings)

    def cleanup(self, file_version_ids: list[int]) -> int:
        normalized_ids = sorted(set(file_version_ids))

        if not normalized_ids:
            raise ValueError("fileVersionIds must not be empty")

        if any(file_version_id <= 0 for file_version_id in normalized_ids):
            raise ValueError("fileVersionIds must contain positive values")

        return self._chroma_store.delete_by_file_version_ids(normalized_ids)
