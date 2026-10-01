from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrastructure.database import Base
from slim_domain.domain.report_log.report_log_repository import _ReportGenerationLogRow
from slim_domain.domain.report_log.report_log_service import ReportGenerationLogService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_record_generation_inserts_a_row(session: Session):
    svc = ReportGenerationLogService(session)
    svc.record_generation(
        input_path=r"S:\Testing_Requests\Acme\010126-Acme Water STD.xlsx",
        output_path=r"S:\Testing_Requests\Acme\010126-Acme Water STD_report.xlsx",
        customer_name="Customer ea6f9",
        request_type="WATER",
        technician_initials="JT",
    )
    rows = session.query(_ReportGenerationLogRow).all()
    assert len(rows) == 1
    assert rows[0].customer_name == "Customer ea6f9"
    assert rows[0].technician_initials == "JT"
    assert isinstance(rows[0].generated_at, datetime)


def test_regenerating_the_same_submission_appends_a_second_row(session: Session):
    """The whole point: this is an append-only event log, not a one-row-
    per-submission record -- a technician catching a mistake and
    regenerating shows up as two rows for the same input_path."""
    svc = ReportGenerationLogService(session)
    for _ in range(2):
        svc.record_generation(
            input_path=r"S:\Testing_Requests\Acme\010126-Acme Water STD.xlsx",
            output_path=r"S:\Testing_Requests\Acme\010126-Acme Water STD_report.xlsx",
            customer_name="Customer ea6f9",
            request_type="WATER",
            technician_initials="JT",
        )
    rows = session.query(_ReportGenerationLogRow).all()
    assert len(rows) == 2


def test_blank_initials_stored_as_none_not_empty_string(session: Session):
    svc = ReportGenerationLogService(session)
    svc.record_generation(
        input_path="x.xlsx", output_path="y.xlsx", customer_name="Customer ea6f9",
        request_type="CHEMICAL", technician_initials="",
    )
    row = session.query(_ReportGenerationLogRow).one()
    assert row.technician_initials is None
