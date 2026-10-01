from sqlalchemy.orm import Session

from slim_domain.domain.element.element import Element
from slim_domain.domain.element.element_cache import ElementCache
from slim_domain.domain.element.element_repository import ElementRepository


class ElementService:
    """Public API for the element domain. Callers never touch repo or cache."""

    def __init__(self, session: Session) -> None:
        repo = ElementRepository(session)
        self._cache = ElementCache(repo)

    def load_element(self, element_id: int) -> Element | None:
        """Return the Element for element_id, or None if not found."""
        return self._cache.get_by_id(element_id)

    def get_by_name(self, name: str) -> Element | None:
        """Return the Element matching name (case-insensitive), or None if not found."""
        return self._cache.get_by_name(name)

    def get_by_symbol(self, symbol: str) -> Element | None:
        """Return the Element matching symbol (case-insensitive), or None if not found."""
        return self._cache.get_by_symbol(symbol)

    def all_elements(self) -> list[Element]:
        """Return all elements loaded at startup."""
        return self._cache.all_elements()
