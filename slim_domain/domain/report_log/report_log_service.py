from datetime import datetime

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from slim_domain.domain.report_log.report_log_repository import ReportGenerationLogRepository


class ReportGenerationLogService:
    """Append-only traceability log: who/what/when a report was generated.

    Deliberately create-only, no read/query API here -- Quality reads this
    table directly (SQL) when they need it, same as any other audit trail;
    this service exists only so slim_report_engine.cli.run() has one call
    to make on every successful generation. Cannot observe a report being
    deleted or a customer cancelling afterward (that happens outside this
    app, on the file share) -- multiple rows for the same input_path is
    the only signal available for "this got regenerated," not why.
    """

    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._repo = ReportGenerationLogRepository(session, engine=engine)

    def record_generation(
        self,
        input_path: str,
        output_path: str,
        customer_name: str,
        request_type: str,
        technician_initials: str | None,
    ) -> None:
        self._repo.insert(
            input_path=input_path,
            output_path=output_path,
            customer_name=customer_name,
            request_type=request_type,
            technician_initials=technician_initials or None,
            generated_at=datetime.now(),
        )
