from slim_domain.domain.chemical.chemical import Chemical
from slim_domain.domain.chemical.chemical_service import ChemicalService
from slim_domain.domain.customer.customer import Customer
from slim_domain.domain.customer.customer_service import CustomerService


class UnresolvedCustomerError(Exception):
    def __init__(self, name: str, address: str, address2: str) -> None:
        self.name = name
        self.address = address
        self.address2 = address2
        super().__init__(f"Unresolved customer: {name!r} / {address!r} / {address2!r}")


class UnresolvedChemicalError(Exception):
    def __init__(self, form_name: str) -> None:
        self.form_name = form_name
        super().__init__(f"Unresolved chemical: {form_name!r}")


class TRFormInputResolver:
    """
    Fast-path-only resolver: looks up form strings in the domain caches and
    raises a typed exception on a miss. The VBA slow path (UI selector) is
    not ported — callers catch UnresolvedCustomerError / UnresolvedChemicalError
    and handle them (e.g. surface to the user or skip the record).
    """

    def __init__(
        self,
        customer_service: CustomerService,
        chemical_service: ChemicalService,
    ) -> None:
        self._customer_svc = customer_service
        self._chemical_svc = chemical_service

    def resolve_customer(self, name: str, address: str, address2: str) -> Customer:
        """Return the Customer for the form composite key, or raise UnresolvedCustomerError."""
        customer_id = self._customer_svc.get_id_by_form_customer(name, address, address2)
        if customer_id > 0:
            customer = self._customer_svc.load_customer(customer_id)
            if customer is not None:
                return customer
        raise UnresolvedCustomerError(name, address, address2)

    def resolve_chemical(self, form_name: str) -> Chemical:
        """Return the Chemical for the form name, or raise UnresolvedChemicalError."""
        chemical_id = self._chemical_svc.get_id_by_form_name(form_name)
        if chemical_id > 0:
            chemical = self._chemical_svc.load_chemical(chemical_id)
            if chemical is not None:
                return chemical
        raise UnresolvedChemicalError(form_name)
