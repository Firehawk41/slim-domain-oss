from slim_domain.domain.element.element import Element
from slim_domain.domain.element.element_repository import ElementRepository


class ElementCache:
    def __init__(self, repo: ElementRepository) -> None:
        self._by_id: dict[int, Element] = {}
        self._by_name: dict[str, Element] = {}
        self._by_symbol: dict[str, Element] = {}
        self._build(repo)

    def _build(self, repo: ElementRepository) -> None:
        self._by_id = {}
        self._by_name = {}
        self._by_symbol = {}
        for e in repo.select_all():
            self._by_id[e.id] = e
            self._by_name[_norm(e.name)] = e
            self._by_symbol[_norm(e.symbol)] = e

    def get_by_id(self, element_id: int) -> Element | None:
        return self._by_id.get(element_id)

    def get_by_name(self, name: str) -> Element | None:
        return self._by_name.get(_norm(name))

    def get_by_symbol(self, symbol: str) -> Element | None:
        return self._by_symbol.get(_norm(symbol))

    def exists_by_id(self, element_id: int) -> bool:
        return element_id in self._by_id

    def exists_by_name(self, name: str) -> bool:
        return _norm(name) in self._by_name

    def exists_by_symbol(self, symbol: str) -> bool:
        return _norm(symbol) in self._by_symbol

    def all_elements(self) -> list[Element]:
        return list(self._by_id.values())


def _norm(value: str) -> str:
    return value.lower().strip()
