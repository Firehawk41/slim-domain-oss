from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from infrastructure.database import Base, make_session


class _ReportGenerationLogRow(Base):
    __tablename__ = "report_generation_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # The real TR input file path -- NOT unique: a technician regenerating
    # the same submission (caught a mistake, redid it) produces a second
    # row for the same input_path, which is the point -- this table is an
    # append-only event log, not a one-row-per-submission record.
    input_path: Mapped[str] = mapped_column(String)
    output_path: Mapped[str] = mapped_column(String)
    customer_name: Mapped[str] = mapped_column(String)
    request_type: Mapped[str] = mapped_column(String)
    # From the TR form's own "Initials:" cell (TRSubmission.technician_initials)
    # -- who logged the sample in, not who ran the generation. Nullable:
    # the Wafer cell mapping isn't yet confirmed real, and older/malformed
    # TR forms may have it blank.
    technician_initials: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime)


class ReportGenerationLogRepository:
    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._session = session
        self._engine = engine

    def insert(
        self,
        input_path: str,
        output_path: str,
        customer_name: str,
        request_type: str,
        technician_initials: str | None,
        generated_at: datetime,
    ) -> None:
        session = make_session(self._engine) if self._engine is not None else self._session
        row = _ReportGenerationLogRow(
            input_path=input_path,
            output_path=output_path,
            customer_name=customer_name,
            request_type=request_type,
            technician_initials=technician_initials,
            generated_at=generated_at,
        )
        session.add(row)
        try:
            session.commit()
        finally:
            if self._engine is not None:
                session.close()
