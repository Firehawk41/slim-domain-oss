from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from infrastructure.database import Base, make_session
from slim_domain.domain.customer.customer import Customer


class _CustomerRow(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column("ID", primary_key=True)
    # unique=True: CustomerService.create_customer()'s own uniqueness check
    # reads the in-memory cache, which can't be atomic across two concurrent
    # requests -- confirmed real, not theoretical: two exact real-data
    # duplicate customer rows (and 15 duplicate "DGA Agent" chemical rows)
    # were found already sitting in the live DB, from an earlier bug where
    # the app read from one DB and wrote to another. This DB-level
    # constraint is what actually closes the race; insert() below catches
    # the resulting IntegrityError so a losing request still gets the same
    # friendly "already exists" message as the ordinary (non-race) case.
    #
    # CITEXT on Postgres (2026-09-23): confirmed real via a direct test that
    # the plain-String UNIQUE constraint let "Customer 138" and "Customer 138" coexist
    # as two separate rows -- a human reads those as the same customer, and
    # the in-memory cache's own lookup already treats them the same (see
    # CustomerCache._norm), so the DB-level race-condition safety net should
    # too. with_variant keeps this a no-op (plain case-sensitive String) on
    # any non-Postgres dialect -- several tests build this schema against
    # SQLite, which has no CITEXT type at all.
    customer_name: Mapped[str] = mapped_column(String().with_variant(CITEXT, "postgresql"), unique=True)
    street_address: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    postal_code: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
    additional_elements_prep: Mapped[str] = mapped_column(String, default="")
    parent_customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.ID"), nullable=True)
    is_group: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Audit trail for ISO 17025: who entered this customer and when. Nullable
    # for pre-existing rows (genuinely no recorded operator). Deliberately
    # not exposed on the Customer domain model or cache -- this is a
    # write-once record for a direct DB audit if ever needed, not something
    # the running app reads back.
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)


class _FormCustomerRow(Base):
    __tablename__ = "form_customers"

    form_customer: Mapped[str] = mapped_column(String, primary_key=True)
    form_address: Mapped[str] = mapped_column(String, primary_key=True)
    form_address_2: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.ID"))
    # ISO 17025 audit trail -- who mapped this form text to this customer,
    # and when. Confirmed necessary the hard way (2026-09-22): a form's
    # ambiguous/generic text mapped to the WRONG customer or chemical is
    # just as consequential as a bad brand-new catalog entry, and easier
    # to miss later -- initials are now required on this decision too, not
    # just on creating a new customer outright. Nullable for pre-existing
    # rows (genuinely no recorded operator).
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CustomerRepository:
    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._session = session
        self._engine = engine

    def _write_session(self) -> Session:
        """A short-lived session for this one write, when self._engine is
        set (Slim-LIMS's real concurrent-write path) -- confirmed real need
        (2026-09-24 stress test against the live service): concurrent
        requests sharing self._session directly can hit SQLAlchemy's own
        "Session is already flushing" reentrancy guard, or silently lose an
        unrelated in-flight write when another thread's failure rolls the
        shared session back. Falls back to self._session when no engine was
        supplied (every pre-existing call site/test) -- behavior is then
        byte-for-byte unchanged from before this existed."""
        return make_session(self._engine) if self._engine is not None else self._session

    def select_all(self) -> list[Customer]:
        """Load all customers ordered by name. Called only by CustomerCache."""
        rows = (
            self._session.query(_CustomerRow)
            .order_by(_CustomerRow.customer_name)
            .all()
        )
        return [_to_customer(r) for r in rows]

    def select_all_form_customers(self) -> list[tuple[str, str, str, int]]:
        """Load all form-customer mappings. Called only by CustomerCache."""
        rows = (
            self._session.query(_FormCustomerRow)
            .order_by(_FormCustomerRow.form_customer)
            .all()
        )
        return [(r.form_customer, r.form_address, r.form_address_2, r.customer_id) for r in rows]

    def insert(
        self,
        name: str,
        street_address: str,
        city: str,
        state: str,
        postal_code: str,
        country: str,
        additional_elements_prep: str = "",
        created_by: str | None = None,
    ) -> Customer:
        """Insert a new customer. Returns the persisted Customer with its new ID."""
        session = self._write_session()
        try:
            row = _CustomerRow(
                customer_name=name,
                street_address=street_address,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country,
                additional_elements_prep=additional_elements_prep,
                created_by=created_by,
                created_at=datetime.now(),
            )
            session.add(row)
            session.flush()  # materialise the auto-assigned ID
            new_id = row.id  # read while the row is still attached to a live session
            session.commit()
        except IntegrityError:
            # The rare race: another request's create_customer() for the
            # same name committed between this call's own (in-memory,
            # non-atomic) uniqueness check and this insert. Roll back so
            # a shared session (when self._engine is None -- see
            # _write_session) stays usable for the next caller -- an
            # uncleared failed transaction would otherwise poison every
            # later operation on it.
            session.rollback()
            raise ValueError(f"Customer name already exists: {name}") from None
        finally:
            if session is not self._session:
                # A fresh per-write session (self._engine is set) has
                # expire_on_commit=True by default -- row's attributes would
                # otherwise lazily re-fetch against this now-closed session
                # the moment anything below touches them. new_id was already
                # captured above specifically to avoid that.
                session.close()
        return Customer(
            id=new_id,
            name=name,
            street_address=street_address,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            additional_elements_prep=additional_elements_prep,
        )

    def update(self, customer: Customer) -> None:
        """Overwrite all mutable fields for an existing customer."""
        session = self._write_session()
        try:
            row = session.get(_CustomerRow, customer.id)
            if row is None:
                raise ValueError(f"Customer ID not found: {customer.id}")
            row.customer_name = customer.name
            row.street_address = customer.street_address
            row.city = customer.city
            row.state = customer.state
            row.postal_code = customer.postal_code
            row.country = customer.country
            row.additional_elements_prep = customer.additional_elements_prep
            row.parent_customer_id = customer.parent_customer_id
            row.is_group = customer.is_group
            session.commit()
        finally:
            if session is not self._session:
                session.close()

    def delete(self, customer_id: int) -> None:
        """Delete the customer row. No-op if the ID does not exist."""
        session = self._write_session()
        try:
            row = session.get(_CustomerRow, customer_id)
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            if session is not self._session:
                session.close()

    def insert_form_customer(
        self,
        form_customer: str,
        form_address: str,
        form_address_2: str,
        customer_id: int,
        created_by: str | None = None,
    ) -> None:
        """Persist a new form-customer -> customer_id mapping."""
        session = self._write_session()
        try:
            session.add(
                _FormCustomerRow(
                    form_customer=form_customer,
                    form_address=form_address,
                    form_address_2=form_address_2,
                    customer_id=customer_id,
                    created_by=created_by,
                    created_at=datetime.now(),
                )
            )
            session.commit()
        finally:
            if session is not self._session:
                session.close()


def _to_customer(row: _CustomerRow) -> Customer:
    return Customer(
        id=row.id,
        name=row.customer_name,
        street_address=row.street_address,
        city=row.city,
        state=row.state,
        postal_code=row.postal_code,
        country=row.country,
        additional_elements_prep=row.additional_elements_prep or "",
        parent_customer_id=row.parent_customer_id,
        is_group=bool(row.is_group),
    )
