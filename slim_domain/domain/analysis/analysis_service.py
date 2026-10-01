from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from slim_domain.domain.analysis.analysis import Analysis
from slim_domain.domain.analysis.analysis_cache import AnalysisCache
from slim_domain.domain.analysis.analysis_repository import AnalysisRepository


class AnalysisService:
    """Public API for the analysis domain. Callers never touch repo or cache."""

    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._repo = AnalysisRepository(session, engine=engine)
        self._cache = AnalysisCache(self._repo)

    # --- Reads ---

    def load_analysis(self, analysis_id: int) -> Analysis | None:
        """Return the Analysis for analysis_id, or None if not found."""
        return self._cache.get_by_id(analysis_id)

    def get_by_name(self, name: str) -> Analysis | None:
        """Return the Analysis matching name (case-insensitive), or None if not found."""
        return self._cache.get_by_name(name)

    def all_analyses(self) -> list[Analysis]:
        """Return all analyses loaded at startup."""
        return self._cache.all_analyses()

    def get_ids_by_form_name(self, form_name: str) -> list[int]:
        """Return analysis IDs associated with a form name, or [] if not mapped."""
        return self._cache.get_ids_by_form_name(form_name)

    def form_name_exists(self, form_name: str) -> bool:
        """Return True if the form name has at least one analysis mapped."""
        return self._cache.form_name_exists(form_name)

    # --- Writes ---

    def add_form_analysis(self, form_name: str, analysis_id: int) -> None:
        """Persist a form-name → analysis_id mapping. Idempotent: no-op if already mapped."""
        if self._cache.form_analysis_exists(form_name, analysis_id):
            return
        self._repo.insert_form_analysis(form_name, analysis_id)
        self._cache.add_form_analysis_index(form_name, analysis_id)
