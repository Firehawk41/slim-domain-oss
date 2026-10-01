from slim_domain.domain.analysis.analysis import Analysis
from slim_domain.domain.analysis.analysis_repository import AnalysisRepository


class AnalysisCache:
    def __init__(self, repo: AnalysisRepository) -> None:
        self._by_id: dict[int, Analysis] = {}
        self._by_name: dict[str, Analysis] = {}
        self._by_form_name: dict[str, list[int]] = {}
        self._build(repo)

    def _build(self, repo: AnalysisRepository) -> None:
        self._by_id = {}
        self._by_name = {}
        self._by_form_name = {}
        for a in repo.select_all():
            self._by_id[a.id] = a
            self._by_name[_norm(a.name)] = a
        for form_name, analysis_id in repo.select_all_form_analyses():
            if form_name.strip() and analysis_id:
                key = _norm(form_name)
                self._by_form_name.setdefault(key, [])
                if analysis_id not in self._by_form_name[key]:
                    self._by_form_name[key].append(analysis_id)
        for ids in self._by_form_name.values():
            ids.sort(key=self._sort_order_of)

    def _sort_order_of(self, analysis_id: int) -> int:
        analysis = self._by_id.get(analysis_id)
        return analysis.sort_order if analysis is not None else 0

    def get_by_id(self, analysis_id: int) -> Analysis | None:
        return self._by_id.get(analysis_id)

    def get_by_name(self, name: str) -> Analysis | None:
        return self._by_name.get(_norm(name))

    def exists_by_id(self, analysis_id: int) -> bool:
        return analysis_id in self._by_id

    def exists_by_name(self, name: str) -> bool:
        return _norm(name) in self._by_name

    def all_analyses(self) -> list[Analysis]:
        return list(self._by_id.values())

    def get_ids_by_form_name(self, form_name: str) -> list[int]:
        return list(self._by_form_name.get(_norm(form_name), []))

    def form_name_exists(self, form_name: str) -> bool:
        return _norm(form_name) in self._by_form_name

    def form_analysis_exists(self, form_name: str, analysis_id: int) -> bool:
        return analysis_id in self._by_form_name.get(_norm(form_name), [])

    def add_form_analysis_index(self, form_name: str, analysis_id: int) -> None:
        """Add a single form-name → analysis_id mapping to the in-memory index."""
        key = _norm(form_name)
        self._by_form_name.setdefault(key, [])
        if analysis_id not in self._by_form_name[key]:
            self._by_form_name[key].append(analysis_id)
            self._by_form_name[key].sort(key=self._sort_order_of)


def _norm(name: str) -> str:
    return name.lower().strip()
