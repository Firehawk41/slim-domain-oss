from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from infrastructure.database import Base, make_session
from slim_domain.domain.chemical.chemical import Chemical


class _ChemicalRow(Base):
    __tablename__ = "chemicals"

    id: Mapped[int] = mapped_column("ID", primary_key=True)
    # unique=True: see the matching comment on _CustomerRow.customer_name --
    # same race, same fix. Confirmed real: 15 duplicate "DGA Agent" rows
    # were found already sitting in the live DB before this was added.
    #
    # CITEXT on Postgres (2026-09-23): same reasoning as
    # _CustomerRow.customer_name -- confirmed real via a live production
    # failure where the DB had "HCL" against SX5's dispatch tables' "HCl".
    # with_variant is a no-op on non-Postgres dialects (SQLite in several
    # tests here), which have no CITEXT type.
    chemical_name: Mapped[str] = mapped_column(String().with_variant(CITEXT, "postgresql"), unique=True)
    metals_prep: Mapped[str] = mapped_column(String)
    silicon_prep: Mapped[str] = mapped_column(String)
    ions_prep: Mapped[str] = mapped_column(String)
    metals_instrument: Mapped[str] = mapped_column(String, default="ICPMS")
    database_entry_date: Mapped[datetime | None] = mapped_column(nullable=True)
    # ISO 17025 audit trail -- who entered this chemical. database_entry_date
    # above already serves as "when" (populated on every insert since before
    # this); this just adds "who." Nullable for pre-existing rows. Not
    # exposed on the Chemical domain model -- write-once for a direct DB
    # audit, not read back by the running app.
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)


class _KEDElementRow(Base):
    __tablename__ = "ked_elements"

    chemical_id: Mapped[int] = mapped_column(ForeignKey("chemicals.ID"), primary_key=True)
    element_id: Mapped[int] = mapped_column(primary_key=True)


class _FormChemicalRow(Base):
    __tablename__ = "form_chemicals"

    form_name: Mapped[str] = mapped_column(String, primary_key=True)
    chemical_id: Mapped[int] = mapped_column(ForeignKey("chemicals.ID"))
    # ISO 17025 audit trail -- see the matching comment on
    # _FormCustomerRow in customer_repository.py. Confirmed real, not
    # hypothetical: a customer's generic form text ("RAW MATERIALS")
    # mapped to one specific chemical globally, with no record of who
    # made that call -- this closes that gap. Nullable for pre-existing
    # rows.
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ChemicalRepository:
    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._session = session
        self._engine = engine

    def _write_session(self) -> Session:
        """See CustomerRepository._write_session's docstring -- same
        confirmed-real reasoning, same fallback behavior."""
        return make_session(self._engine) if self._engine is not None else self._session

    def select_all(self) -> list[Chemical]:
        """Load all chemicals and KED element IDs in two queries. Called only by ChemicalCache."""
        chem_rows = (
            self._session.query(_ChemicalRow)
            .order_by(_ChemicalRow.chemical_name)
            .all()
        )
        ked_rows = self._session.query(_KEDElementRow).all()

        ked_map: dict[int, set[int]] = {}
        for r in ked_rows:
            ked_map.setdefault(r.chemical_id, set()).add(r.element_id)

        return [
            Chemical(
                id=r.id,
                name=r.chemical_name,
                metals_prep=r.metals_prep,
                silicon_prep=r.silicon_prep,
                ions_prep=r.ions_prep,
                metals_instrument=r.metals_instrument or "ICPMS",
                entry_date=r.database_entry_date,
                ked_element_ids=frozenset(ked_map.get(r.id, set())),
            )
            for r in chem_rows
        ]

    def insert(
        self,
        name: str,
        metals_prep: str,
        silicon_prep: str,
        ions_prep: str,
        ked_element_ids: frozenset[int],
        metals_instrument: str = "ICPMS",
        created_by: str | None = None,
    ) -> Chemical:
        """Insert a new chemical + its KED elements in one transaction. Returns the persisted Chemical."""
        session = self._write_session()
        try:
            row = _ChemicalRow(
                chemical_name=name,
                metals_prep=metals_prep,
                silicon_prep=silicon_prep,
                ions_prep=ions_prep,
                metals_instrument=metals_instrument,
                database_entry_date=datetime.now(),
                created_by=created_by,
            )
            session.add(row)
            try:
                session.flush()  # materialise the auto-assigned ID before adding FK children
            except IntegrityError:
                # Same race as CustomerRepository.insert() -- see its comment.
                session.rollback()
                raise ValueError(f"Chemical name already exists: {name}") from None

            for element_id in ked_element_ids:
                session.add(_KEDElementRow(chemical_id=row.id, element_id=element_id))

            session.commit()
            return Chemical(
                id=row.id,
                name=name,
                metals_prep=metals_prep,
                silicon_prep=silicon_prep,
                ions_prep=ions_prep,
                metals_instrument=metals_instrument,
                entry_date=row.database_entry_date,
                ked_element_ids=ked_element_ids,
            )
        finally:
            if session is not self._session:
                session.close()

    def select_all_form_names(self) -> list[tuple[str, int]]:
        """Load all form-name → chemical_id mappings. Called only by ChemicalCache."""
        rows = self._session.query(_FormChemicalRow).all()
        return [(r.form_name, r.chemical_id) for r in rows]

    def insert_form_name(self, form_name: str, chemical_id: int, created_by: str | None = None) -> None:
        """Persist a new form-name → chemical_id mapping."""
        session = self._write_session()
        try:
            session.add(
                _FormChemicalRow(
                    form_name=form_name, chemical_id=chemical_id, created_by=created_by, created_at=datetime.now()
                )
            )
            session.commit()
        finally:
            if session is not self._session:
                session.close()
