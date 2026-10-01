from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from infrastructure.database import Base, make_session


class _CustomerReportFolderRow(Base):
    __tablename__ = "customer_report_folders"

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.ID"), primary_key=True)
    # Part of the primary key so one customer can have more than one real
    # destination folder -- confirmed real need: SX5 is a single customer
    # record (shared for invoicing) whose real reports split across two
    # real folders (SX5_North/SX5_South) depending on the TR filename, not
    # anything in the customer record itself. "" (never NULL -- Postgres
    # composite PKs can't contain it) means "no location", i.e. every
    # other customer, unchanged from before this column existed.
    location: Mapped[str] = mapped_column(String, primary_key=True, default="")
    folder_path: Mapped[str] = mapped_column(String)
    # ISO 17025 audit trail -- who set the CURRENT mapping, and when.
    # Updated on every upsert (not just the first), since knowing who's
    # responsible for the mapping as it stands today is more useful for an
    # audit than freezing to whoever set it first. Nullable for pre-existing
    # rows. Not exposed via the cache/resolve_folder -- write-only.
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ReportFolderRepository:
    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._session = session
        self._engine = engine

    def _write_session(self) -> Session:
        """See CustomerRepository._write_session's docstring -- same
        confirmed-real reasoning, same fallback behavior."""
        return make_session(self._engine) if self._engine is not None else self._session

    def select_all(self) -> list[tuple[int, str, str]]:
        """Load all (customer_id, location) -> folder_path mappings. Called only by ReportFolderCache."""
        rows = self._session.query(_CustomerReportFolderRow).all()
        return [(r.customer_id, r.location, r.folder_path) for r in rows]

    def upsert(self, customer_id: int, folder_path: str, created_by: str | None = None, location: str = "") -> None:
        """Insert or overwrite the folder mapping for (customer_id, location)."""
        session = self._write_session()
        try:
            row = session.get(_CustomerReportFolderRow, (customer_id, location))
            if row is None:
                session.add(
                    _CustomerReportFolderRow(
                        customer_id=customer_id, location=location, folder_path=folder_path,
                        created_by=created_by, created_at=datetime.now(),
                    )
                )
            else:
                row.folder_path = folder_path
                row.created_by = created_by
                row.created_at = datetime.now()
            session.commit()
        finally:
            if session is not self._session:
                session.close()
