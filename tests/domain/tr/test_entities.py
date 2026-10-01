from datetime import date, datetime

import pytest

from slim_domain.domain.tr.enums import ProcessingTime, RequestType
from slim_domain.domain.tr.tr_sample import TRSample
from slim_domain.domain.tr.tr_submission import SENTINEL_DATE, TRSubmission, _add_working_days


# --- TRSample ---


def _make_sample(**kwargs) -> TRSample:
    defaults = dict(
        sample_name="S001",
        form_chemical_name="HCl",
        processing_time=ProcessingTime.NEXT_DAY,
        additional_notes="",
        requested_time="2:00 PM",
        chemical_id=1,
    )
    return TRSample(**(defaults | kwargs))


def test_tr_sample_fields() -> None:
    s = _make_sample(analysis_ids=(10, 20), additional_element_ids=(5,))
    assert s.sample_name == "S001"
    assert s.form_chemical_name == "HCl"
    assert s.processing_time == ProcessingTime.NEXT_DAY
    assert s.analysis_ids == (10, 20)
    assert s.additional_element_ids == (5,)
    assert s.chemical_id == 1


def test_tr_sample_processing_time_str() -> None:
    assert _make_sample(processing_time=ProcessingTime.SAME_DAY_RUSH).processing_time_str == "Same Day RUSH"


def test_tr_sample_is_frozen() -> None:
    s = _make_sample()
    with pytest.raises(Exception):
        s.sample_name = "changed"  # type: ignore[misc]


def test_tr_sample_reporting_units_defaults_empty() -> None:
    """Not applicable to Chemical/Water samples -- defaults to "" so every
    existing construction site (including SLIM-Invoicing-Program's own,
    unmigrated copy of this entity) stays valid without changes."""
    assert _make_sample().reporting_units == ""


def test_tr_sample_reporting_units_settable_for_wafer() -> None:
    s = _make_sample(reporting_units="atoms/cm^2")
    assert s.reporting_units == "atoms/cm^2"


# --- TRSubmission ---


def _make_submission(**kwargs) -> TRSubmission:
    defaults = dict(
        customer_id=1,
        date_submitted=date(2026, 1, 15),
        date_received=date(2026, 1, 16),
        request_type=RequestType.CHEMICAL,
        customer_contact="John Smith",
        customer_phone="555-1234",
        po_information="PO-123",
        credit_card_information="",
        file_name="Lab Results [2026-01-20].xlsx",
        service_date=date(2026, 1, 20),
        download_date=datetime(2026, 1, 16, 9, 0),
        form_customer_name="Customer ea6f9",
        form_customer_address="123 Main St",
        form_customer_address_2="",
    )
    return TRSubmission(**(defaults | kwargs))


def test_tr_submission_fields() -> None:
    sub = _make_submission()
    assert sub.customer_id == 1
    assert sub.request_type == RequestType.CHEMICAL
    assert sub.date_submitted == date(2026, 1, 15)


def test_tr_submission_is_frozen() -> None:
    sub = _make_submission()
    with pytest.raises(Exception):
        sub.customer_id = 99  # type: ignore[misc]


def test_effective_service_date_uses_stored_date() -> None:
    sub = _make_submission(service_date=date(2026, 1, 20))
    assert sub.effective_service_date == date(2026, 1, 20)


def test_effective_service_date_sentinel_no_samples() -> None:
    # No samples → default to NEXT_DAY (1 working day from received)
    sub = _make_submission(service_date=SENTINEL_DATE, date_received=date(2026, 1, 16))
    # 2026-01-16 is Friday; +1 working day = Monday 2026-01-19
    assert sub.effective_service_date == date(2026, 1, 19)


def test_effective_service_date_sentinel_uses_max_processing_time() -> None:
    s1 = _make_sample(processing_time=ProcessingTime.NEXT_DAY)        # 1 day
    s2 = _make_sample(processing_time=ProcessingTime.THREE_DAYS)      # 3 days
    sub = _make_submission(
        service_date=SENTINEL_DATE,
        date_received=date(2026, 1, 12),  # Monday
        samples=(s1, s2),
    )
    # +3 working days from Mon 2026-01-12 = Thursday 2026-01-15
    assert sub.effective_service_date == date(2026, 1, 15)


def test_effective_service_date_zero_days_same_as_received() -> None:
    s = _make_sample(processing_time=ProcessingTime.SAME_DAY_RUSH)
    sub = _make_submission(
        service_date=SENTINEL_DATE,
        date_received=date(2026, 1, 16),
        samples=(s,),
    )
    assert sub.effective_service_date == date(2026, 1, 16)


def test_results_email_main_first() -> None:
    sub = _make_submission(results_email_main=("a@b.com", "c@d.com"))
    assert sub.results_email_main_first == "a@b.com"


def test_results_email_main_first_empty() -> None:
    assert _make_submission().results_email_main_first == ""


# --- _add_working_days ---


def test_add_working_days_no_weekend() -> None:
    # Mon + 2 = Wed
    assert _add_working_days(date(2026, 1, 12), 2) == date(2026, 1, 14)


def test_add_working_days_crosses_weekend() -> None:
    # Fri + 1 = Mon
    assert _add_working_days(date(2026, 1, 16), 1) == date(2026, 1, 19)


def test_add_working_days_crosses_two_weekends() -> None:
    # Mon + 7 = Wed (skipping two weekends = +4 extra days)
    assert _add_working_days(date(2026, 1, 12), 7) == date(2026, 1, 21)


def test_add_working_days_zero() -> None:
    assert _add_working_days(date(2026, 1, 16), 0) == date(2026, 1, 16)
