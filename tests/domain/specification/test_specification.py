import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrastructure.database import Base
from slim_domain.domain.specification.specification_repository import _SpecificationRow
from slim_domain.domain.specification.specification_service import SpecificationService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                _SpecificationRow(
                    id=1, kind="specification", customer_id=30, customer_name_raw="Customer 3fbc3",
                    chemical_id=129, chemical_name_raw="49%HF", element_symbol="Fe",
                    value=0.5, unit="ppb", category_label="Trace Metals", parameter_text="Fe",
                ),
                _SpecificationRow(
                    id=2, kind="specification", customer_id=30, customer_name_raw="Customer 3fbc3",
                    chemical_id=129, chemical_name_raw="49%HF", element_symbol="Ca",
                    value=1.0, unit="ppb", category_label="Trace Metals", parameter_text="Ca",
                ),
                _SpecificationRow(
                    id=3, kind="warning_limit", customer_id=30, customer_name_raw="Customer 3fbc3",
                    chemical_id=129, chemical_name_raw="49%HF", element_symbol="Fe",
                    value=0.4, unit="ppb", category_label="Trace Metals", parameter_text="Fe",
                ),
                _SpecificationRow(
                    id=4, kind="specification", customer_id=None, customer_name_raw="Customer a2519",
                    chemical_id=None, chemical_name_raw="SurfClean", element_symbol="Na",
                    value=2.0, unit="ppb", category_label="Trace Metals", parameter_text="Na",
                ),
                _SpecificationRow(
                    id=5, kind="specification", customer_id=88, customer_name_raw="Customer a359c",
                    chemical_id=201, chemical_name_raw="PG", element_symbol="Al",
                    value=1.0, unit="ppm", category_label="Trace Metals", parameter_text="Al",
                ),
                _SpecificationRow(
                    id=6, kind="specification", customer_id=91, customer_name_raw="Customer 98168",
                    chemical_id=202, chemical_name_raw="1% NH4OH", element_symbol="Fe",
                    value=0.5, unit="(ppb)", category_label="Trace Metals", parameter_text="Fe",
                ),
            ]
        )
        s.commit()
        yield s


@pytest.fixture
def service(session: Session) -> SpecificationService:
    return SpecificationService(session)


def test_get_specs_returns_specification_kind_only(service: SpecificationService) -> None:
    specs = service.get_specs(30, 129)
    assert specs == {"Fe": 0.5, "Ca": 1.0}


def test_get_specs_returns_empty_for_unknown_pair(service: SpecificationService) -> None:
    assert service.get_specs(999, 999) == {}


def test_get_warning_limits_returns_warning_limit_kind_only(service: SpecificationService) -> None:
    assert service.get_warning_limits(30, 129) == {"Fe": 0.4}


def test_get_specs_by_raw_names_reaches_unresolved_rows(service: SpecificationService) -> None:
    assert service.get_specs_by_raw_names("Customer a2519", "SurfClean") == {"Na": 2.0}


def test_get_specs_by_raw_names_is_case_and_whitespace_insensitive(service: SpecificationService) -> None:
    assert service.get_specs_by_raw_names("  Customer a2519  ", "surfclean") == {"Na": 2.0}


def test_get_unit_override_returns_none_for_plain_ppb(service: SpecificationService) -> None:
    assert service.get_unit_override(30, 129) is None


def test_get_unit_override_returns_none_when_no_spec_on_file(service: SpecificationService) -> None:
    assert service.get_unit_override(999, 999) is None


def test_get_unit_override_returns_the_real_unit_when_not_ppb(service: SpecificationService) -> None:
    """Confirmed real (direct DB check, 2026-09-28): Customer a359c's
    PG spec is on file in ppm, and a real completed report shows "All
    data in units of ppm unless otherwise noted" in place of the default
    ppb wording."""
    assert service.get_unit_override(88, 201) == "ppm"


def test_get_unit_override_treats_parenthesized_ppb_as_ppb_equivalent(service: SpecificationService) -> None:
    """Confirmed real (direct evidence check, 2026-09-28): several real
    spec rows have "(ppb)" verbatim on file (a data-entry inconsistency,
    not a genuinely different unit) -- a real completed Customer 98168 report for
    one of them shows the plain, unsubstituted "ppb" wording, not "(ppb)"."""
    assert service.get_unit_override(91, 202) is None


# --- site-split customers (location) and chemical_report_settings ---------

@pytest.fixture
def site_split_service() -> SpecificationService:
    from slim_domain.domain.specification.specification_repository import _ChemicalReportSettingRow

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                _SpecificationRow(
                    id=1, kind="specification", customer_id=21, customer_name_raw="SiteN",
                    chemical_id=61, chemical_name_raw="HCL", element_symbol="Fe",
                    value=0.1, unit="ppb", category_label="N-QC-HCL", parameter_text="Fe", location="N",
                ),
                _SpecificationRow(
                    id=2, kind="specification", customer_id=21, customer_name_raw="SiteS",
                    chemical_id=61, chemical_name_raw="HCL", element_symbol="Fe",
                    value=0.2, unit="ppm", category_label="S-QC-HCL", parameter_text="Fe", location="S",
                ),
                _ChemicalReportSettingRow(
                    customer_id=21, location="N", chemical_id=214,
                    assay_spec_text="1 - 2", report_note="A note", display_label="Label",
                ),
            ]
        )
        s.commit()
        yield SpecificationService(s)


def test_specs_are_separated_by_location(site_split_service: SpecificationService) -> None:
    assert site_split_service.get_specs(21, 61, location="N") == {"Fe": 0.1}
    assert site_split_service.get_specs(21, 61, location="S") == {"Fe": 0.2}
    assert site_split_service.get_specs(21, 61) == {}


def test_category_label_is_per_location(site_split_service: SpecificationService) -> None:
    assert site_split_service.get_category_label(21, 61, location="N") == "N-QC-HCL"
    assert site_split_service.get_category_label(21, 61, location="S") == "S-QC-HCL"
    assert site_split_service.get_category_label(21, 61) is None


def test_site_split_rows_never_feed_the_generic_unit_override(site_split_service: SpecificationService) -> None:
    assert site_split_service.get_unit_override(21, 61) is None


def test_report_setting_lookup(site_split_service: SpecificationService) -> None:
    setting = site_split_service.get_report_setting(21, 214, location="N")
    assert setting is not None
    assert (setting.assay_spec_text, setting.report_note, setting.display_label) == ("1 - 2", "A note", "Label")
    assert site_split_service.get_report_setting(21, 214, location="S") is None


def test_category_label_is_per_kind(service: SpecificationService) -> None:
    assert service.get_category_label(30, 129) == "Trace Metals"
    assert service.get_category_label(30, 129, kind="warning_limit") == "Trace Metals"
    assert service.get_category_label(30, 129, kind="no_such_kind") is None


def test_limits_owner_is_own_customer_when_it_has_limits(service: SpecificationService) -> None:
    assert service.limits_owner(30, 129, parent_customer_id=999) == 30


def test_limits_owner_falls_back_to_the_group_per_chemical(service: SpecificationService) -> None:
    # customer 77 has no limits for chemical 129 -> its group's apply
    assert service.limits_owner(77, 129, parent_customer_id=30) == 30
    assert service.limits_owner(77, 129, parent_customer_id=None) == 77
