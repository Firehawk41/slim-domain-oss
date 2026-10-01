from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from slim_domain.domain.customer.customer import Customer
from slim_domain.domain.customer.customer_cache import CustomerCache
from slim_domain.domain.customer.customer_repository import CustomerRepository


class CustomerService:
    """Public API for the customer domain. Callers never touch repo or cache."""

    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._repo = CustomerRepository(session, engine=engine)
        self._cache = CustomerCache(self._repo)

    # --- Reads ---

    def load_customer(self, customer_id: int) -> Customer | None:
        """Return the Customer for customer_id, or None if not found."""
        return self._cache.get_by_id(customer_id)

    def get_by_name(self, name: str) -> Customer | None:
        """Return the Customer matching name (case-insensitive), or None if not found."""
        return self._cache.get_by_name(name)

    def all_customers(self, include_groups: bool = False) -> list[Customer]:
        """Return all customers loaded at startup -- by default without
        group records (Customer.is_group), which hold shared limits but are
        never a Testing Request's customer, so they stay out of the
        resolution pages' pick list. load_customer() still returns them."""
        customers = self._cache.all_customers()
        return customers if include_groups else [c for c in customers if not c.is_group]

    def get_id_by_form_customer(
        self, form_name: str, form_address: str, form_address_2: str
    ) -> int:
        """Return the customer ID for the composite form key, or 0 if not mapped."""
        return self._cache.get_id_by_form_customer(form_name, form_address, form_address_2)

    def form_key_exists(self, name: str, address: str, address_2: str) -> bool:
        """Return True if the composite form key is already mapped."""
        return self._cache.form_key_exists(name, address, address_2)

    def get_name_by_id(self, customer_id: int) -> str:
        """Return the customer name for customer_id. Raises KeyError if not found."""
        return self._cache.get_name_by_id(customer_id)

    # --- Writes ---

    def create_customer(
        self,
        name: str,
        street_address: str,
        city: str,
        state: str,
        postal_code: str,
        country: str,
        created_by: str = "",
    ) -> Customer:
        """Validate, persist, and cache a new customer. Returns the persisted entity.

        created_by: the entering technician's initials, for the ISO 17025
        audit trail (there's no per-user login in this system -- everyone
        shares the same computers -- so initials, captured once at the
        point new reference data is entered, are the trail). Required."""
        self._require_valid_name(name)
        self._require_unique_name(name)
        self._require_non_blank(street_address, "Street address")
        self._require_non_blank(city, "City")
        self._require_non_blank(state, "State")
        self._require_non_blank(postal_code, "Postal code")
        self._require_non_blank(country, "Country")
        self._require_non_blank(created_by, "Initials")

        customer = self._repo.insert(
            name, street_address, city, state, postal_code, country, created_by=created_by
        )
        self._cache.upsert(customer)
        return customer

    def update_customer(self, customer: Customer) -> Customer:
        """Validate and persist changes to an existing customer. Returns the same entity."""
        if customer.id <= 0:
            raise ValueError("Cannot update a customer with no ID")
        self._require_valid_name(customer.name)
        self._require_unique_name_for_update(customer.name, customer.id)
        self._require_non_blank(customer.street_address, "Street address")
        self._require_non_blank(customer.city, "City")
        self._require_non_blank(customer.state, "State")
        self._require_non_blank(customer.postal_code, "Postal code")
        self._require_non_blank(customer.country, "Country")

        self._repo.update(customer)
        self._cache.upsert(customer)
        return customer

    def delete_customer(self, customer_id: int) -> None:
        """Delete the customer from DB and cache."""
        self._repo.delete(customer_id)
        self._cache.remove(customer_id)

    def add_form_key(
        self,
        form_customer: str,
        form_address: str,
        form_address_2: str,
        customer_id: int,
        created_by: str = "",
    ) -> None:
        """Persist a form-key -> customer_id mapping. Idempotent: no-op if already mapped.

        created_by: the technician's initials, for the ISO 17025 audit
        trail -- required even when mapping onto an EXISTING customer,
        not just when creating a new one. Confirmed real (2026-09-22): a
        form's ambiguous text mapped to the wrong existing customer is
        just as consequential as a bad new entry, and easier to miss
        later since nothing about the resulting report looks obviously
        wrong."""
        if self._cache.form_key_exists(form_customer, form_address, form_address_2):
            return
        if not created_by.strip():
            raise ValueError("Initials cannot be blank")
        self._repo.insert_form_customer(form_customer, form_address, form_address_2, customer_id, created_by=created_by)
        self._cache.add_form_customer_index(form_customer, form_address, form_address_2, customer_id)

    # --- Validation (public for UI pre-validation) ---

    def is_valid_name(self, name: str) -> bool:
        return len(name.strip()) > 0

    def is_unique_name(self, name: str) -> bool:
        return not self._cache.exists_by_name(name)

    def is_unique_name_for_update(self, name: str, customer_id: int) -> bool:
        """Return True if name is available, treating the customer's own name as non-conflicting."""
        existing = self._cache.get_by_name(name)
        return existing is None or existing.id == customer_id

    # --- Private helpers ---

    def _require_valid_name(self, name: str) -> None:
        if not self.is_valid_name(name):
            raise ValueError("Customer name cannot be blank")

    def _require_unique_name(self, name: str) -> None:
        if not self.is_unique_name(name):
            raise ValueError(f"Customer name already exists: {name}")

    def _require_unique_name_for_update(self, name: str, customer_id: int) -> None:
        if not self.is_unique_name_for_update(name, customer_id):
            raise ValueError(f"Customer name already exists: {name}")

    def _require_non_blank(self, value: str, field_name: str) -> None:
        if not value.strip():
            raise ValueError(f"{field_name} cannot be blank")
