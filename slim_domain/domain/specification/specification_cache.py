from slim_domain.domain.specification.specification import ChemicalReportSetting
from slim_domain.domain.specification.specification_repository import SpecificationRepository


class SpecificationCache:
    def __init__(self, repo: SpecificationRepository) -> None:
        # Keyed (customer_id, chemical_id, location, kind) -- location is ""
        # for every customer except a site-split one (SX5), so a SX5N row
        # can never answer a lookup for SX5S or for the plain "" location.
        self._by_customer_chemical: dict[tuple[int, int, str, str], dict[str, float]] = {}
        self._category_label: dict[tuple[int, int, str, str], str] = {}
        self._report_settings: dict[tuple[int, int, str], ChemicalReportSetting] = {}
        self._by_raw_names: dict[tuple[str, str, str], dict[str, float]] = {}
        # "specification"-kind rows only (matches the real VBA source,
        # modReportCreator.bas's Get_Specs -- the "if not ppb, substitute
        # the real unit into the preamble" behavior reads from
        # Specifications_Database specifically, never Warning_Limits_Database).
        # Confirmed real, direct DB check (2026-09-28): exactly one real
        # (customer, chemical) combo currently has a genuinely different
        # unit on file -- Customer a359c / PG, "ppm" -- confirmed
        # against real completed reports showing "All data in units of
        # ppm unless otherwise noted" in place of the default ppb wording.
        self._unit_by_customer_chemical: dict[tuple[int, int], str] = {}
        self._build(repo)

    def _build(self, repo: SpecificationRepository) -> None:
        self._by_customer_chemical = {}
        self._by_raw_names = {}
        self._unit_by_customer_chemical = {}
        self._category_label = {}
        self._report_settings = {}
        for s in repo.select_all():
            if s.customer_id is not None and s.chemical_id is not None:
                key = (s.customer_id, s.chemical_id, s.location, s.kind)
                self._by_customer_chemical.setdefault(key, {})[s.element_symbol] = s.value
                self._category_label.setdefault((s.customer_id, s.chemical_id, s.location, s.kind), s.category_label)
                if s.kind == "specification":
                    # The unit override is a generic-path (location "")
                    # feature only -- site-split rows never feed it.
                    if s.location == "":
                        self._unit_by_customer_chemical.setdefault((s.customer_id, s.chemical_id), s.unit)
            raw_key = (_norm(s.customer_name_raw), _norm(s.chemical_name_raw), s.kind)
            self._by_raw_names.setdefault(raw_key, {})[s.element_symbol] = s.value
        for r in repo.select_all_report_settings():
            self._report_settings[(r.customer_id, r.chemical_id, r.location)] = r

    def get_by_customer_chemical(
        self, customer_id: int, chemical_id: int, kind: str, location: str = ""
    ) -> dict[str, float]:
        return dict(self._by_customer_chemical.get((customer_id, chemical_id, location, kind), {}))

    def get_category_label(
        self, customer_id: int, chemical_id: int, location: str = "", kind: str = "specification"
    ) -> str | None:
        return self._category_label.get((customer_id, chemical_id, location, kind))

    def get_report_setting(self, customer_id: int, chemical_id: int, location: str = "") -> ChemicalReportSetting | None:
        return self._report_settings.get((customer_id, chemical_id, location))

    def get_by_raw_names(self, customer_name_raw: str, chemical_name_raw: str, kind: str) -> dict[str, float]:
        key = (_norm(customer_name_raw), _norm(chemical_name_raw), kind)
        return dict(self._by_raw_names.get(key, {}))

    def get_unit_by_customer_chemical(self, customer_id: int, chemical_id: int) -> str | None:
        return self._unit_by_customer_chemical.get((customer_id, chemical_id))


def _norm(value: str) -> str:
    return value.lower().strip()
