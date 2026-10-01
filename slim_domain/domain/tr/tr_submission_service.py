from datetime import datetime
from pathlib import Path
from typing import Any

from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.chemical.chemical_service import ChemicalService
from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.tr.tr_submission import TRSubmission
from slim_domain.domain.tr.tr_submission_form_parser import TRSubmissionFormParser


class TRSubmissionService:
    """Public API for the TR submission domain. Callers never touch the parser directly."""

    def __init__(
        self,
        chemical_service: ChemicalService,
        analysis_service: AnalysisService,
        element_service: ElementService,
        input_resolver: Any,  # TRFormInputResolver or protocol-compatible
    ) -> None:
        self._parser = TRSubmissionFormParser(
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
        """Build a TRSubmission from an already-open openpyxl worksheet."""
        return self._parser.build_from_worksheet(ws, download_date=download_date, filename=filename)

    def build_from_file(self, path: Path | str) -> TRSubmission:
        """Load an .xlsx file and build a TRSubmission. Scans sheets for Testing Request Form."""
        import openpyxl

        path = Path(path)
        download_date = datetime.fromtimestamp(path.stat().st_mtime)
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = _find_form_sheet(wb)
            if ws is None:
                raise ValueError(f"No Testing Request Form sheet found in {path.name}")
            return self._parser.build_from_worksheet(ws, download_date=download_date, filename=path.name)
        finally:
            wb.close()


def _find_form_sheet(wb: Any) -> Any:
    """Return the first worksheet whose D3 cell contains 'Testing Request Form', or None."""
    for ws in wb.worksheets:
        val = str(ws["D3"].value or "")
        if "Testing Request Form" in val:
            return ws
    return None
