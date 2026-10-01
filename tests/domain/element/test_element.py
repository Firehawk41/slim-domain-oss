import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrastructure.database import Base
from slim_domain.domain.element.element_repository import _ElementRow
from slim_domain.domain.element.element_service import ElementService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                _ElementRow(id=1, element_symbol="Fe", element_name="Iron"),
                _ElementRow(id=2, element_symbol="Ca", element_name="Calcium"),
                _ElementRow(id=3, element_symbol="Na", element_name="Sodium"),
            ]
        )
        s.commit()
        yield s


@pytest.fixture
def service(session: Session) -> ElementService:
    return ElementService(session)


def test_load_by_id_returns_correct_element(service: ElementService) -> None:
    e = service.load_element(1)
    assert e is not None
    assert e.id == 1
    assert e.symbol == "Fe"
    assert e.name == "Iron"


def test_load_by_id_returns_none_for_missing(service: ElementService) -> None:
    assert service.load_element(999) is None


def test_get_by_name_exact_match(service: ElementService) -> None:
    e = service.get_by_name("Calcium")
    assert e is not None
    assert e.id == 2


def test_get_by_name_case_insensitive(service: ElementService) -> None:
    e = service.get_by_name("calcium")
    assert e is not None
    assert e.id == 2


def test_get_by_name_strips_whitespace(service: ElementService) -> None:
    e = service.get_by_name("  Iron  ")
    assert e is not None
    assert e.id == 1


def test_get_by_name_returns_none_for_missing(service: ElementService) -> None:
    assert service.get_by_name("Unobtanium") is None


def test_get_by_symbol_exact_match(service: ElementService) -> None:
    e = service.get_by_symbol("Na")
    assert e is not None
    assert e.id == 3


def test_get_by_symbol_case_insensitive(service: ElementService) -> None:
    e = service.get_by_symbol("na")
    assert e is not None
    assert e.id == 3


def test_get_by_symbol_strips_whitespace(service: ElementService) -> None:
    e = service.get_by_symbol("  Ca  ")
    assert e is not None
    assert e.id == 2


def test_get_by_symbol_returns_none_for_missing(service: ElementService) -> None:
    assert service.get_by_symbol("Xx") is None


def test_all_elements_returns_all_rows(service: ElementService) -> None:
    assert len(service.all_elements()) == 3


def test_element_is_frozen(service: ElementService) -> None:
    e = service.load_element(1)
    assert e is not None
    with pytest.raises(Exception):
        e.symbol = "Au"  # type: ignore[misc]
