import re
from datetime import date, datetime
from typing import Any

from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.chemical.chemical_service import ChemicalService
from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.tr.enums import RequestType
from slim_domain.domain.tr.tr_sample import TRSample
from slim_domain.domain.tr.tr_sample_form_parser import SampleRangeBounds, TRSampleFormParser
from slim_domain.domain.tr.tr_submission import SENTINEL_DATE, TRSubmission

_FOOTER_ROWS = 11


class TRSubmissionFormParser:
    def __init__(
        self,
        chemical_service: ChemicalService,
        analysis_service: AnalysisService,
        element_service: ElementService,
        input_resolver: Any,  # TRFormInputResolver or test stub
    ) -> None:
        self._resolver = input_resolver
        self._sample_parser = TRSampleFormParser(
            chemical_service=chemical_service,
            analysis_service=analysis_service,
            element_service=element_service,
            input_resolver=input_resolver,
        )

    def build_from_worksheet(
        self,
        ws: Any,  # openpyxl Worksheet
        download_date: datetime | None = None,
        filename: str = "",
    ) -> TRSubmission:
        if download_date is None:
            download_date = datetime.now()

        request_type = _read_request_type(ws)
        customer = self._resolver.resolve_customer(
            str(ws["C10"].value or "").strip(),
            str(ws["C11"].value or "").strip(),
            str(ws["C12"].value or "").strip(),
        )
        form_customer_name = str(ws["C10"].value or "").strip()
        form_customer_address = str(ws["C11"].value or "").strip()
        form_customer_address_2 = str(ws["C12"].value or "").strip()

        samples = self._build_samples(ws, request_type)
        results_main, results_cc, inv_main, inv_cc = self._build_emails(ws, request_type)

        return TRSubmission(
            id=0,
            customer_id=customer.id,
            date_submitted=_to_date(ws[_date_submitted_cell(request_type)].value, default=SENTINEL_DATE),
            date_received=_to_date(ws[_date_received_cell(request_type)].value),
            request_type=request_type,
            customer_contact=str(ws["C13"].value or ""),
            customer_phone=_read_phone(ws),
            po_information=_read_po_information(ws, request_type),
            credit_card_information=_read_credit_card_info(ws, request_type),
            file_name=filename,
            service_date=_extract_service_date(filename),
            download_date=download_date,
            form_customer_name=form_customer_name,
            form_customer_address=form_customer_address,
            form_customer_address_2=form_customer_address_2,
            technician_initials=_read_initials(ws, request_type),
            samples=tuple(samples),
            results_email_main=tuple(results_main),
            results_email_cc=tuple(results_cc),
            invoice_email_main=tuple(inv_main),
            invoice_email_cc=tuple(inv_cc),
        )

    def _build_samples(self, ws: Any, request_type: RequestType) -> list[TRSample]:
        bounds = _get_sample_range(ws)
        if bounds is None:
            return []
        samples: list[TRSample] = []
        for row in range(bounds.first_row, bounds.last_row + 1):
            val = ws.cell(row=row, column=2).value
            if val is not None and str(val).strip():
                samples.append(
                    self._sample_parser.build_from_row(ws, row, bounds, request_type)
                )
        return samples

    def _build_emails(
        self,
        ws: Any,
        request_type: RequestType,
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        results_main = _parse_emails(str(ws["C15"].value or ""))
        results_cc = _parse_emails(str(ws["C17"].value or ""))

        inv_main_cell, inv_cc_cell = _invoice_email_cells(request_type)
        inv_main = _parse_emails(str(ws[inv_main_cell].value or ""))
        inv_cc = _parse_emails(str(ws[inv_cc_cell].value or ""))

        return results_main, results_cc, inv_main, inv_cc


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _read_request_type(ws: Any) -> RequestType:
    val = str(ws["D3"].value or "")
    if val == "Chemical Testing Request Form":
        return RequestType.CHEMICAL
    if val == "Water Testing Request Form":
        return RequestType.WATER
    if val == "Wafer Testing Request Form":
        return RequestType.WAFER
    raise ValueError(f"Unrecognised form title in D3: {val!r}")


def _date_submitted_cell(request_type: RequestType) -> str:
    return "G4" if request_type == RequestType.WAFER else "I4"


def _date_received_cell(request_type: RequestType) -> str:
    return {RequestType.CHEMICAL: "P5", RequestType.WATER: "S5", RequestType.WAFER: "L5"}[
        request_type
    ]


def _invoice_email_cells(request_type: RequestType) -> tuple[str, str]:
    return {
        RequestType.CHEMICAL: ("N10", "N11"),
        RequestType.WATER: ("P10", "P11"),
        RequestType.WAFER: ("J10", "J11"),
    }[request_type]


def _read_initials(ws: Any, request_type: RequestType) -> str:
    """The "EXAMPLE LAB internal use only" box's "Initials:" cell -- one row
    below its own "Date:"/"Time:" cells, same column, confirmed real
    across every real TR form checked (Chemical: P5/P6/P7, Water:
    S5/S6/S7). Wafer follows the same one-row-below-date pattern as
    _date_received_cell (L5) -- not directly confirmed against a real
    Wafer form yet, but the same internal-use box shape is used across
    all three form types."""
    cell_map = {RequestType.CHEMICAL: "P7", RequestType.WATER: "S7", RequestType.WAFER: "L7"}
    return str(ws[cell_map[request_type]].value or "").strip()


def _read_phone(ws: Any) -> str:
    if str(ws["B14"].value or "") == "Phone :":
        return str(ws["C14"].value or "")
    if str(ws["B15"].value or "") == "Phone:":
        return str(ws["C15"].value or "")
    return ""


def _read_revision_letter(ws: Any, request_type: RequestType) -> str:
    cell_map = {
        RequestType.CHEMICAL: "P49",
        RequestType.WATER: "S51",
        RequestType.WAFER: "L45",
    }
    raw = str(ws[cell_map[request_type]].value or "")
    pos = raw.upper().find("REV ")
    return raw[pos + 4 : pos + 5].strip() if pos >= 0 else ""


def _read_po_information(ws: Any, request_type: RequestType) -> str:
    rev = _read_revision_letter(ws, request_type)
    if request_type == RequestType.CHEMICAL:
        addr = "H10" if rev.upper() >= "T" else "I10"
    elif request_type == RequestType.WATER:
        addr = "H10" if rev.upper() >= "I" else "J10"
    else:
        addr = "G10"
    po = str(ws[addr].value or "")
    return po.replace("\r", "").replace("\n", "").strip()


def _read_credit_card_info(ws: Any, request_type: RequestType) -> str:
    addr_map = {RequestType.CHEMICAL: "I11", RequestType.WATER: "J11", RequestType.WAFER: "G11"}
    cell = ws[addr_map[request_type]]
    main_val = str(cell.value or "")
    below_val = str(ws.cell(row=cell.row + 1, column=cell.column).value or "")
    return f"{main_val} {below_val}".strip() if below_val else main_val


def _get_sample_range(ws: Any) -> SampleRangeBounds | None:
    # A prefix match, not exact equality: confirmed real forms use varying
    # exact header text here -- Chemical/Water's B20 is literally
    # "Sample ID", but Wafer's is "Sample ID / Slot Number". An exact
    # match silently fell through to the row-21 fallback for every real
    # Wafer form, which lands the "header row" derivation two rows short
    # of the true header row and can truncate the analysis-column scan.
    first_row = 22 if str(ws["B20"].value or "").strip().startswith("Sample ID") else 21

    # Last row with data in column B, minus footer rows
    max_row = ws.max_row or first_row
    last_b_row = first_row
    for r in range(max_row, first_row - 1, -1):
        if ws.cell(row=r, column=2).value is not None:
            last_b_row = r
            break
    last_row = last_b_row - _FOOTER_ROWS

    # Last non-empty column in the header row two above the first sample row, minus 1
    header_row = first_row - 2
    max_col = ws.max_column or 2
    last_col = 2
    for c in range(max_col, 2, -1):
        if ws.cell(row=header_row, column=c).value is not None:
            last_col = c
            break
    last_col -= 1

    if last_row < first_row or last_col < 2:
        return None
    return SampleRangeBounds(first_row=first_row, last_row=last_row, first_col=2, last_col=last_col)


def _to_date(val: Any, *, default: date | None = None) -> date:
    """Raises ValueError (rather than silently substituting a placeholder
    date) when val is missing or unparseable, UNLESS default is given --
    used only for date_received (see call site below), confirmed real the
    hard way: a silent date(1, 1, 1) fallback here used to flow all the
    way through to a live report's date-of-analysis/sample-string
    formatting, where it crashed with a confusing Windows-only "format %y
    requires year >= 1900" error several steps downstream of the actual
    problem -- and even where it didn't crash, it would have rendered a
    nonsense date onto a real report instead of clearly refusing. This
    field is always filled in on the CURRENT Testing Request form
    template (confirmed: current policy is to assume every incoming
    submission is on the current template, not support older ones) -- a
    blank/unparseable value here means the form predates that template,
    which callers should surface as a clear, actionable message rather
    than silently guessing.

    default: for a field that's genuinely never read by anything
    downstream (date_submitted -- confirmed: assigned and tested, never
    consumed by any report-building code), silently falling back to a
    fixed, already-safe placeholder (SENTINEL_DATE, not date(1, 1, 1)) is
    the right call -- there's no real content at risk of being wrong,
    and no reason to refuse the whole submission over a field nothing
    uses.
    """
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if val is None:
        if default is not None:
            return default
        raise ValueError("date field is missing")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    if default is not None:
        return default
    raise ValueError(f"date field has an unrecognized value: {val!r}")


def _extract_service_date(filename: str) -> date:
    """Extract date from bracket notation in filename, e.g. '[2026-01-15]'. Returns sentinel on failure."""
    m = re.search(r"\[([^\]]+)\]", filename)
    if not m:
        return SENTINEL_DATE
    raw = m.group(1).replace("_", " ").replace("-", "/")
    for fmt in ("%Y/%m/%d", "%Y %m %d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return SENTINEL_DATE


def _parse_emails(email_string: str) -> list[str]:
    """Split a delimited address string and return valid email addresses."""
    s = email_string.replace(";", ",").replace(" ", ",").replace("\r", ",").replace("\n", ",")
    result: list[str] = []
    for token in s.split(","):
        token = token.strip()
        if token and _is_valid_email(token):
            result.append(token)
    return result


def _is_valid_email(addr: str) -> bool:
    return "@" in addr[1:] and "." in addr[2:]
