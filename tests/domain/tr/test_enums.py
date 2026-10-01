import pytest

from slim_domain.domain.tr.enums import ProcessingTime, RequestType


def test_request_type_values() -> None:
    assert RequestType.CHEMICAL == 1
    assert RequestType.WATER == 2
    assert RequestType.WAFER == 3


# --- ProcessingTime.from_form_string ---


@pytest.mark.parametrize(
    "form_string, expected",
    [
        ("Extended Time", ProcessingTime.EXTENDED_TIME),
        ("Next Day", ProcessingTime.NEXT_DAY),
        ("Next Day RUSH", ProcessingTime.NEXT_DAY_RUSH),
        ("NextDayRush", ProcessingTime.NEXT_DAY_RUSH),
        ("Time Limited", ProcessingTime.TIME_LIMITED),
        ("TimeLimited", ProcessingTime.TIME_LIMITED),
        ("Next Day Time Limited", ProcessingTime.TIME_LIMITED),
        ("Same Day Rush", ProcessingTime.SAME_DAY_RUSH),
        ("SameDayRush", ProcessingTime.SAME_DAY_RUSH),
        ("Call In Rush", ProcessingTime.CALL_IN_RUSH),
        ("Call-in RUSH", ProcessingTime.CALL_IN_RUSH),
        ("CallInRush", ProcessingTime.CALL_IN_RUSH),
        ("Two Days", ProcessingTime.TWO_DAYS),
        ("2 Days", ProcessingTime.TWO_DAYS),
        ("2days", ProcessingTime.TWO_DAYS),
        ("Three Days", ProcessingTime.THREE_DAYS),
        ("3 Days", ProcessingTime.THREE_DAYS),
        ("3days", ProcessingTime.THREE_DAYS),
        ("Up To 3 Working Days", ProcessingTime.THREE_DAYS),
        ("Five Days", ProcessingTime.FIVE_DAYS),
        ("5 Days", ProcessingTime.FIVE_DAYS),
        ("5days", ProcessingTime.FIVE_DAYS),
        # case-insensitive
        ("next day", ProcessingTime.NEXT_DAY),
        ("SAME DAY RUSH", ProcessingTime.SAME_DAY_RUSH),
        # leading/trailing whitespace
        ("  Next Day  ", ProcessingTime.NEXT_DAY),
    ],
)
def test_from_form_string(form_string: str, expected: ProcessingTime) -> None:
    assert ProcessingTime.from_form_string(form_string) == expected


def test_from_form_string_raises_on_unknown() -> None:
    with pytest.raises(ValueError, match="Unrecognised"):
        ProcessingTime.from_form_string("Overnight Express")


# --- ProcessingTime.days ---


@pytest.mark.parametrize(
    "pt, expected_days",
    [
        (ProcessingTime.SAME_DAY_RUSH, 0),
        (ProcessingTime.CALL_IN_RUSH, 0),
        (ProcessingTime.NEXT_DAY, 1),
        (ProcessingTime.NEXT_DAY_RUSH, 1),
        (ProcessingTime.TIME_LIMITED, 1),
        (ProcessingTime.TWO_DAYS, 2),
        (ProcessingTime.EXTENDED_TIME, 3),
        (ProcessingTime.THREE_DAYS, 3),
        (ProcessingTime.FIVE_DAYS, 5),
    ],
)
def test_days(pt: ProcessingTime, expected_days: int) -> None:
    assert pt.days == expected_days


# --- ProcessingTime.label ---


@pytest.mark.parametrize(
    "pt, expected_label",
    [
        (ProcessingTime.EXTENDED_TIME, "Extended Time"),
        (ProcessingTime.NEXT_DAY, "Next Day"),
        (ProcessingTime.NEXT_DAY_RUSH, "Next Day RUSH"),
        (ProcessingTime.TIME_LIMITED, "Next Day Time Limited"),
        (ProcessingTime.SAME_DAY_RUSH, "Same Day RUSH"),
        (ProcessingTime.CALL_IN_RUSH, "Call-in RUSH"),
        (ProcessingTime.TWO_DAYS, "Two Days"),
        (ProcessingTime.THREE_DAYS, "Three Days"),
        (ProcessingTime.FIVE_DAYS, "Five Days"),
    ],
)
def test_label(pt: ProcessingTime, expected_label: str) -> None:
    assert pt.label == expected_label
