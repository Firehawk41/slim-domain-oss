from slim_domain.domain.customer.customer import Customer
from slim_domain.domain.customer.customer_repository import CustomerRepository


class CustomerCache:
    def __init__(self, repo: CustomerRepository) -> None:
        self._by_id: dict[int, Customer] = {}
        self._by_name: dict[str, Customer] = {}
        self._by_form_customer: dict[str, int] = {}
        self._build(repo)

    def _build(self, repo: CustomerRepository) -> None:
        self._by_id = {}
        self._by_name = {}
        self._by_form_customer = {}

        for c in repo.select_all():
            self._by_id[c.id] = c
            self._by_name[_norm(c.name)] = c

        for form_customer, form_address, form_address_2, customer_id in repo.select_all_form_customers():
            if not form_customer.strip() or not customer_id:
                continue
            key = _form_key(form_customer, form_address, form_address_2)
            if key not in self._by_form_customer:
                self._by_form_customer[key] = customer_id

    # --- Incremental updates ---

    def upsert(self, customer: Customer) -> None:
        """Add or replace a customer in all indexes, cleaning up stale name key on rename."""
        if customer.id in self._by_id:
            old_key = _norm(self._by_id[customer.id].name)
            if old_key != _norm(customer.name):
                self._by_name.pop(old_key, None)
        self._by_id[customer.id] = customer
        self._by_name[_norm(customer.name)] = customer

    def remove(self, customer_id: int) -> None:
        """Remove a customer from all indexes."""
        if customer_id in self._by_id:
            self._by_name.pop(_norm(self._by_id[customer_id].name), None)
            del self._by_id[customer_id]

    # --- Read API ---

    def get_by_id(self, customer_id: int) -> Customer | None:
        return self._by_id.get(customer_id)

    def get_by_name(self, name: str) -> Customer | None:
        return self._by_name.get(_norm(name))

    def get_id_by_name(self, name: str) -> int:
        """Return the ID for name. Raises KeyError if not found."""
        key = _norm(name)
        if key not in self._by_name:
            raise KeyError(f"Customer not found: {name!r}")
        return self._by_name[key].id

    def get_name_by_id(self, customer_id: int) -> str:
        """Return the name for customer_id. Raises KeyError if not found."""
        if customer_id not in self._by_id:
            raise KeyError(f"Customer ID not found: {customer_id}")
        return self._by_id[customer_id].name

    def exists_by_id(self, customer_id: int) -> bool:
        return customer_id in self._by_id

    def exists_by_name(self, name: str) -> bool:
        return _norm(name) in self._by_name

    def all_customers(self) -> list[Customer]:
        return list(self._by_id.values())

    def get_id_by_form_customer(self, name: str, address: str, address2: str) -> int:
        """Return customer_id for the composite form key, or 0 if not found."""
        return self._by_form_customer.get(_form_key(name, address, address2), 0)

    def form_key_exists(self, name: str, address: str, address2: str) -> bool:
        return _form_key(name, address, address2) in self._by_form_customer

    def add_form_customer_index(
        self, name: str, address: str, address2: str, customer_id: int
    ) -> None:
        key = _form_key(name, address, address2)
        if key not in self._by_form_customer:
            self._by_form_customer[key] = customer_id


def _norm(value: str) -> str:
    return value.lower().strip()


def _form_key(name: str, address: str, address2: str) -> str:
    return f"{_norm(name)}|{_norm(address)}|{_norm(address2)}"
