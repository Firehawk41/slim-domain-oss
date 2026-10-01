import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrastructure.database import Base
from slim_domain.domain.chemical.chemical_repository import _ChemicalRow, _FormChemicalRow
from slim_domain.domain.chemical.chemical_service import ChemicalService
from slim_domain.domain.customer.customer_repository import _CustomerRow, _FormCustomerRow
from slim_domain.domain.customer.customer_service import CustomerService
from slim_domain.domain.tr.tr_form_input_resolver import (
    TRFormInputResolver,
    UnresolvedChemicalError,
    UnresolvedCustomerError,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                _CustomerRow(
                    id=1,
                    customer_name="Customer ea6f9",
                    street_address="123 Main St",
                    city="Springfield",
                    state="IL",
                    postal_code="62701",
                    country="USA",
                ),
                _FormCustomerRow(
                    form_customer="Customer ea6f9",
                    form_address="123 main st",
                    form_address_2="",
                    customer_id=1,
                ),
                _ChemicalRow(
                    id=1,
                    chemical_name="Hydrochloric Acid",
                    metals_prep="Dilute and Shoot",
                    silicon_prep="N/A",
                    ions_prep="Dilute and Shoot",
                    database_entry_date=None,
                ),
            ]
        )
        s.commit()
        yield s


@pytest.fixture
def resolver(session: Session) -> TRFormInputResolver:
    customer_svc = CustomerService(session)
    chemical_svc = ChemicalService(session)
    return TRFormInputResolver(customer_svc, chemical_svc)


# --- ResolveCustomer ---


def test_resolve_customer_returns_customer_on_hit(resolver: TRFormInputResolver) -> None:
    c = resolver.resolve_customer("Customer ea6f9", "123 main st", "")
    assert c.id == 1
    assert c.name == "Customer ea6f9"


def test_resolve_customer_case_insensitive(resolver: TRFormInputResolver) -> None:
    c = resolver.resolve_customer("Customer ea6f9", "123 Main St", "")
    assert c.id == 1


def test_resolve_customer_raises_on_miss(resolver: TRFormInputResolver) -> None:
    with pytest.raises(UnresolvedCustomerError) as exc_info:
        resolver.resolve_customer("Unknown Co", "nowhere", "")
    assert exc_info.value.name == "Unknown Co"
    assert exc_info.value.address == "nowhere"


# --- ResolveChemical ---


def test_resolve_chemical_raises_on_miss(resolver: TRFormInputResolver) -> None:
    # "HCl" has no form_chemicals row → resolver raises UnresolvedChemicalError
    with pytest.raises(UnresolvedChemicalError) as exc_info:
        resolver.resolve_chemical("HCl")
    assert exc_info.value.form_name == "HCl"


def test_resolve_chemical_returns_chemical_on_hit(session: Session) -> None:
    # Seed a form_chemicals row so the resolver can find the chemical
    session.add(_FormChemicalRow(form_name="Hydrochloric Acid", chemical_id=1))
    session.commit()

    resolver = TRFormInputResolver(CustomerService(session), ChemicalService(session))
    c = resolver.resolve_chemical("Hydrochloric Acid")
    assert c.id == 1
    assert c.name == "Hydrochloric Acid"


def test_resolve_chemical_hit_is_case_insensitive(session: Session) -> None:
    session.add(_FormChemicalRow(form_name="Hydrochloric Acid", chemical_id=1))
    session.commit()

    resolver = TRFormInputResolver(CustomerService(session), ChemicalService(session))
    c = resolver.resolve_chemical("hydrochloric acid")
    assert c.id == 1


def test_unresolved_customer_error_carries_fields(resolver: TRFormInputResolver) -> None:
    try:
        resolver.resolve_customer("X", "Y", "Z")
    except UnresolvedCustomerError as e:
        assert e.name == "X"
        assert e.address == "Y"
        assert e.address2 == "Z"
