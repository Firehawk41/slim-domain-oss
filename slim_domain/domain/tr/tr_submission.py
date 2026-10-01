from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from slim_domain.domain.tr.enums import ProcessingTime, RequestType
from slim_domain.domain.tr.tr_sample import TRSample

SENTINEL_DATE = date(1901, 1, 1)


class TRSubmission(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int = 0
    customer_id: int
    date_submitted: date
    date_received: date
    request_type: RequestType
    customer_contact: str
    customer_phone: str
    po_information: str
    credit_card_information: str
    file_name: str
    service_date: date
    download_date: datetime
    form_customer_name: str
    form_customer_address: str
    form_customer_address_2: str
    # The internal "EXAMPLE LAB internal use only" box's own "Initials:" cell
    # -- whoever logged the sample in, NOT the same as a resolve-page
    # created_by (which is who resolved an unmapped customer/chemical, a
    # separate and rarer action). Added 2026-09-25 for report-generation
    # traceability (slim_report_engine.reporting.generation_log). Default
    # "" keeps every existing TRSubmission(...) call site (tests, older
    # callers) unaffected.
    technician_initials: str = ""
    samples: tuple[TRSample, ...] = ()
    results_email_main: tuple[str, ...] = ()
    results_email_cc: tuple[str, ...] = ()
    invoice_email_main: tuple[str, ...] = ()
    invoice_email_cc: tuple[str, ...] = ()

    @property
    def effective_service_date(self) -> date:
        """If service_date is the sentinel, compute from received date + max processing time."""
        if self.service_date == SENTINEL_DATE:
            max_pt = (
                max(self.samples, key=lambda s: s.processing_time.days).processing_time
                if self.samples
                else ProcessingTime.NEXT_DAY
            )
            days = max_pt.days
            if days == 0:
                return self.date_received
            return _add_working_days(self.date_received, days)
        return self.service_date

    @property
    def results_email_main_first(self) -> str:
        return self.results_email_main[0] if self.results_email_main else ""

    @property
    def invoice_email_main_first(self) -> str:
        return self.invoice_email_main[0] if self.invoice_email_main else ""


def _add_working_days(start: date, days: int) -> date:
    """Add working days to start, skipping weekends (Mon=0 … Sun=6)."""
    result = start
    for _ in range(days):
        result += timedelta(days=1)
        while result.weekday() >= 5:  # Saturday=5, Sunday=6
            result += timedelta(days=1)
    return result
