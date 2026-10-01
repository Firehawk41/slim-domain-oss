from unittest.mock import MagicMock

from slim_domain.domain.tr.tr_submission_service import _find_form_sheet


def _make_ws(d3_value: str | None) -> MagicMock:
    ws = MagicMock()
    cell = MagicMock()
    cell.value = d3_value
    ws.__getitem__ = MagicMock(return_value=cell)
    return ws


def _make_wb(*d3_values: str | None) -> MagicMock:
    wb = MagicMock()
    wb.worksheets = [_make_ws(v) for v in d3_values]
    return wb


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def test_finds_chemical_form():
    wb = _make_wb("Chemical Testing Request Form")
    ws = _find_form_sheet(wb)
    assert ws is wb.worksheets[0]


def test_finds_water_form():
    wb = _make_wb("Water Testing Request Form")
    assert _find_form_sheet(wb) is wb.worksheets[0]


def test_finds_wafer_form():
    wb = _make_wb("Wafer Testing Request Form")
    assert _find_form_sheet(wb) is wb.worksheets[0]


def test_skips_non_matching_sheet_and_finds_later_one():
    wb = _make_wb("Summary", "Chemical Testing Request Form")
    assert _find_form_sheet(wb) is wb.worksheets[1]


def test_returns_first_match_when_multiple_sheets_match():
    wb = _make_wb("Chemical Testing Request Form", "Water Testing Request Form")
    assert _find_form_sheet(wb) is wb.worksheets[0]


# ---------------------------------------------------------------------------
# No match
# ---------------------------------------------------------------------------


def test_returns_none_when_no_matching_sheet():
    wb = _make_wb("Summary", "Data", "Charts")
    assert _find_form_sheet(wb) is None


def test_returns_none_for_empty_workbook():
    wb = _make_wb()
    assert _find_form_sheet(wb) is None


def test_returns_none_for_none_d3_value():
    wb = _make_wb(None, None)
    assert _find_form_sheet(wb) is None


def test_returns_none_for_partial_match():
    # "Testing Request" without "Form" at the end
    wb = _make_wb("Chemical Testing Request")
    assert _find_form_sheet(wb) is None
