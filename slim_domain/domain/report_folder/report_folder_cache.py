from slim_domain.domain.report_folder.report_folder_repository import ReportFolderRepository


class ReportFolderCache:
    def __init__(self, repo: ReportFolderRepository) -> None:
        self._by_key: dict[tuple[int, str], str] = {}
        self._build(repo)

    def _build(self, repo: ReportFolderRepository) -> None:
        self._by_key = {(customer_id, location): folder_path for customer_id, location, folder_path in repo.select_all()}

    # --- Incremental updates ---

    def set(self, customer_id: int, folder_path: str, location: str = "") -> None:
        self._by_key[(customer_id, location)] = folder_path

    # --- Read API ---

    def get(self, customer_id: int, location: str = "") -> str | None:
        return self._by_key.get((customer_id, location))
