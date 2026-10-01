from pydantic import BaseModel, ConfigDict


class Specification(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    # "specification" (a hard customer spec limit) or "warning_limit" (an
    # internal QC threshold) -- migrated from two separate real Access
    # tables (Specifications_Database / Warning_Limits_Database) that
    # share the same (customer, chemical, element) shape, normalized into
    # one table here rather than two near-identical ones.
    kind: str
    # Nullable: resolved by exact case-insensitive name match against the
    # customers/chemicals catalog at migration time -- real match rates are
    # well under 100% (dirty legacy customer/chemical name text), so an
    # unresolved row still migrates rather than being dropped, keeping the
    # raw name as the only way to reach it (see get_specs_by_raw_names).
    customer_id: int | None
    customer_name_raw: str
    chemical_id: int | None
    chemical_name_raw: str
    element_symbol: str
    value: float
    unit: str
    # For most rows a plain category ("Trace Metals", "Specification"...);
    # for a site-split customer (SX5) it carries the sheet's QC reference
    # code, e.g. "SX5N-QC-REF-HCL" -- see SpecificationService.get_category_label.
    category_label: str
    parameter_text: str
    # "" for every customer except one whose specs differ per site (SX5:
    # "SX5N"/"SX5S") -- same convention as customer_report_folders.location.
    location: str = ""


class ChemicalReportSetting(BaseModel):
    """Per-(customer, location, chemical) report text that isn't a
    per-element limit: an assay spec range, a note printed on the report,
    or a display name the customer requires in place of the chemical's
    own name. Every text field is optional -- None means "nothing on file"."""

    model_config = ConfigDict(frozen=True)

    customer_id: int
    location: str
    chemical_id: int
    assay_spec_text: str | None = None
    report_note: str | None = None
    display_label: str | None = None
