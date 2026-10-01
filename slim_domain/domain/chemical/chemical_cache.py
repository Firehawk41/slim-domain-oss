from slim_domain.domain.chemical.chemical import Chemical
from slim_domain.domain.chemical.chemical_repository import ChemicalRepository


class ChemicalCache:
    def __init__(self, repo: ChemicalRepository) -> None:
        self._by_id: dict[int, Chemical] = {}
        self._by_name: dict[str, Chemical] = {}
        self._by_form_name: dict[str, int] = {}
        self._build(repo)

    def _build(self, repo: ChemicalRepository) -> None:
        self._by_id = {}
        self._by_name = {}
        self._by_form_name = {}
        for c in repo.select_all():
            self._by_id[c.id] = c
            self._by_name[_norm(c.name)] = c
        for form_name, chemical_id in repo.select_all_form_names():
            if form_name.strip() and chemical_id:
                key = _norm(form_name)
                if key not in self._by_form_name:
                    self._by_form_name[key] = chemical_id

    def upsert(self, chemical: Chemical) -> None:
        if chemical.id in self._by_id:
            old_key = _norm(self._by_id[chemical.id].name)
            if old_key != _norm(chemical.name):
                self._by_name.pop(old_key, None)
        self._by_id[chemical.id] = chemical
        self._by_name[_norm(chemical.name)] = chemical

    def get_by_id(self, chemical_id: int) -> Chemical | None:
        return self._by_id.get(chemical_id)

    def get_by_name(self, name: str) -> Chemical | None:
        return self._by_name.get(_norm(name))

    def exists_by_id(self, chemical_id: int) -> bool:
        return chemical_id in self._by_id

    def exists_by_name(self, name: str) -> bool:
        return _norm(name) in self._by_name

    def all_chemicals(self) -> list[Chemical]:
        return list(self._by_id.values())

    def get_id_by_form_name(self, form_name: str) -> int:
        return self._by_form_name.get(_norm(form_name), 0)

    def form_name_exists(self, form_name: str) -> bool:
        return _norm(form_name) in self._by_form_name

    def add_form_name_index(self, form_name: str, chemical_id: int) -> None:
        """Add a single form-name → chemical_id mapping to the in-memory index."""
        key = _norm(form_name)
        if key not in self._by_form_name:
            self._by_form_name[key] = chemical_id


def _norm(value: str) -> str:
    return value.lower().strip()
