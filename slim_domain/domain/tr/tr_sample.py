from pydantic import BaseModel, ConfigDict

from slim_domain.domain.tr.enums import ProcessingTime


class TRSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int = 0
    sample_name: str
    form_chemical_name: str
    processing_time: ProcessingTime
    additional_notes: str
    requested_time: str  # empty string for Wafer (column not present)
    chemical_id: int
    analysis_ids: tuple[int, ...] = ()
    additional_element_ids: tuple[int, ...] = ()
    # Only meaningful for Wafer samples ("Reporting Unit" column, e.g.
    # "atoms/cm^2") -- part of a wafer's grouping identity alongside
    # form_chemical_name (which holds Wafer Size for this request type),
    # the resolved element/anion-count analysis, and processing_time.
    # Empty string for Chemical/Water, where it doesn't apply.
    reporting_units: str = ""
    # Only meaningful for Water samples ("Water testing package" column,
    # e.g. "Premium package"/"Standard package") -- confirmed real
    # (2026-09-28, a real Water dummy TR run through the legacy macro):
    # a bundled preset that expands into a FIXED set of panels server-
    # side, entirely independent of (and, in every real example checked,
    # used INSTEAD of) the normal individual-checkbox analysis_ids. Not a
    # real catalog analysis -- there is no analysis_id for it -- so it
    # gets its own field rather than being forced into analysis_ids.
    # Empty string for every non-package sample (the overwhelming
    # majority) and for Chemical/Wafer, where the column doesn't exist.
    water_package: str = ""

    @property
    def processing_time_str(self) -> str:
        return self.processing_time.label
