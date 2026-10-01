from typing import Any, NamedTuple

from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.chemical.chemical_service import ChemicalService
from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.tr.enums import ProcessingTime, RequestType
from slim_domain.domain.tr.tr_sample import TRSample


class SampleRangeBounds(NamedTuple):
    first_row: int
    last_row: int
    first_col: int  # always col 2 (sample-ID column)
    last_col: int


class TRSampleFormParser:
    def __init__(
        self,
        chemical_service: ChemicalService,
        analysis_service: AnalysisService,
        element_service: ElementService,
        input_resolver: Any,  # TRFormInputResolver or test stub
    ) -> None:
        self._chemical_svc = chemical_service
        self._analysis_svc = analysis_service
        self._element_svc = element_service
        self._resolver = input_resolver

    def build_from_row(
        self,
        ws: Any,  # openpyxl Worksheet
        row: int,
        sample_range: SampleRangeBounds,
        request_type: RequestType,
    ) -> TRSample:
        form_chem_name = _get_form_chemical_name(ws, row, request_type)
        chemical = self._resolver.resolve_chemical(form_chem_name)

        processing_time = _get_processing_time(ws, row, request_type)
        additional_notes = _cell_str(ws, row, _notes_col(request_type))
        requested_time = _cell_str(ws, row, _requested_time_col(request_type))
        reporting_units = _cell_str(ws, row, _reporting_units_col(request_type))
        water_package = _cell_str(ws, row, _water_package_col(request_type)).strip()
        sample_name = _cell_str(ws, row, 2)

        analysis_ids = self._collect_analysis_ids(ws, row, sample_range, request_type)
        additional_element_ids = self._collect_additional_element_ids(ws, row, request_type)

        return TRSample(
            id=0,
            sample_name=sample_name,
            form_chemical_name=form_chem_name,
            processing_time=processing_time,
            additional_notes=additional_notes,
            requested_time=requested_time,
            chemical_id=chemical.id,
            analysis_ids=tuple(analysis_ids),
            additional_element_ids=tuple(additional_element_ids),
            reporting_units=reporting_units,
            water_package=water_package,
        )

    def _collect_analysis_ids(
        self,
        ws: Any,
        row: int,
        sample_range: SampleRangeBounds,
        request_type: RequestType,
    ) -> list[int]:
        start_col = _analysis_start_col(request_type)
        seen: set[int] = set()
        result: list[int] = []

        # Confirmed real (2026-09-23, direct user correction): the legacy
        # VBA macro scanned "Additional Requests or Notes" for a form-name
        # match exactly like any other column -- not a special case, no
        # fuzzy text search, just the same exact lookup. This is how new
        # analyses got requested without a Testing Request template
        # revision (real example: "Acetate & Formate" typed in that column
        # on a Folder b65a8 Water form, with no structured dropdown
        # selection for it anywhere).
        scan_cols = list(range(start_col, sample_range.last_col + 1))
        notes_col = _notes_col(request_type)
        if notes_col:
            scan_cols.append(notes_col)

        for col in scan_cols:
            val = ws.cell(row=row, column=col).value
            if val is None or not str(val).strip():
                continue
            # AnalysisService.get_ids_by_form_name is a plain dict lookup
            # (AnalysisCache._by_form_name, built from form_analyses at
            # startup) that returns [] for an unmatched name -- it never
            # raises. A prior version of this loop guarded against a
            # NotImplementedError from an earlier, not-yet-ported form of
            # this lookup; removed 2026-09-29 (failure-path audit) as dead
            # code once that was confirmed -- silently swallowing any
            # exception here would risk dropping a real, requested
            # analysis with no signal to anyone.
            ids = self._analysis_svc.get_ids_by_form_name(str(val).strip())
            for aid in ids:
                if aid not in seen:
                    seen.add(aid)
                    result.append(aid)

        # Check if the additional-elements column header itself maps to an analysis.
        add_el_col = _additional_element_col(request_type)
        if add_el_col > 0:
            header_val = ws.cell(row=sample_range.first_row - 1, column=add_el_col).value
            if header_val and str(header_val).strip():
                analysis = self._analysis_svc.get_by_name(str(header_val).strip())
                if analysis is not None and analysis.id not in seen:
                    seen.add(analysis.id)
                    result.append(analysis.id)

        return result

    def _collect_additional_element_ids(
        self,
        ws: Any,
        row: int,
        request_type: RequestType,
    ) -> list[int]:
        add_el_col = _additional_element_col(request_type)
        if add_el_col == 0:
            return []
        cell_val = str(ws.cell(row=row, column=add_el_col).value or "").strip()
        if not cell_val:
            return []
        seen: set[int] = set()
        result: list[int] = []
        for symbol in _parse_element_symbols(cell_val):
            element = self._element_svc.get_by_symbol(symbol)
            if element is not None and element.id not in seen:
                seen.add(element.id)
                result.append(element.id)
        return result


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _cell_str(ws: Any, row: int, col: int) -> str:
    if col == 0:
        return ""
    return str(ws.cell(row=row, column=col).value or "")


def _get_form_chemical_name(ws: Any, row: int, request_type: RequestType) -> str:
    if request_type == RequestType.CHEMICAL:
        return _cell_str(ws, row, 3)
    if request_type == RequestType.WATER:
        return "Water"
    return _cell_str(ws, row, 4)  # Wafer


def _get_processing_time(ws: Any, row: int, request_type: RequestType) -> ProcessingTime:
    col_map = {RequestType.CHEMICAL: 11, RequestType.WATER: 14, RequestType.WAFER: 9}
    raw = _cell_str(ws, row, col_map[request_type])
    return ProcessingTime.from_form_string(raw)


def _notes_col(request_type: RequestType) -> int:
    return {RequestType.CHEMICAL: 14, RequestType.WATER: 17, RequestType.WAFER: 10}[request_type]


def _requested_time_col(request_type: RequestType) -> int:
    return {RequestType.CHEMICAL: 13, RequestType.WATER: 16, RequestType.WAFER: 0}[request_type]


def _reporting_units_col(request_type: RequestType) -> int:
    """"Reporting Unit" (e.g. "atoms/cm^2") -- only present on the Wafer
    form, column 3. Confirmed against the real Wafer intake form's own
    header row; not present at all on Chemical/Water."""
    return 3 if request_type == RequestType.WAFER else 0


def _water_package_col(request_type: RequestType) -> int:
    """"Water testing package" (e.g. "Premium package"/"Standard
    package") -- only present on the Water form, column 3 (confirmed
    against the real Water intake form's own header row). Not present at
    all on Chemical/Wafer -- Wafer's own column 3 is reporting_units,
    a different real field that happens to share the column index."""
    return 3 if request_type == RequestType.WATER else 0


def _analysis_start_col(request_type: RequestType) -> int:
    return {RequestType.CHEMICAL: 4, RequestType.WATER: 4, RequestType.WAFER: 5}[request_type]


def _additional_element_col(request_type: RequestType) -> int:
    if request_type in (RequestType.CHEMICAL, RequestType.WATER):
        return 5
    if request_type == RequestType.WAFER:
        return 6
    return 0


def _parse_element_symbols(element_string: str) -> list[str]:
    """Split a delimited element symbol string (;  .  space  newline) into tokens."""
    s = element_string
    for sep in (";", ".", " ", "\r\n", "\r", "\n"):
        s = s.replace(sep, ",")
    return [t.strip() for t in s.split(",") if t.strip()]
