from sqlalchemy.orm import Session

from slim_domain.domain.specification.specification import ChemicalReportSetting
from slim_domain.domain.specification.specification_cache import SpecificationCache
from slim_domain.domain.specification.specification_repository import SpecificationRepository


class SpecificationService:
    """Public API for the specification domain. Callers never touch repo or
    cache. An absent (customer, chemical) key -- or an absent element symbol
    within its result -- means "no spec/limit on file", never a guess; every
    caller treats {} the same as a dict missing that one symbol.
    """

    def __init__(self, session: Session) -> None:
        repo = SpecificationRepository(session)
        self._cache = SpecificationCache(repo)

    def get_specs(self, customer_id: int, chemical_id: int, location: str = "") -> dict[str, float]:
        """element_symbol -> real customer spec limit for (customer_id,
        chemical_id), or {} if this customer+chemical has none on file.
        location: "" for every customer except a site-split one (SX5's
        "SX5N"/"SX5S"), whose limits differ per site.
        """
        return self._cache.get_by_customer_chemical(customer_id, chemical_id, "specification", location)

    def get_warning_limits(self, customer_id: int, chemical_id: int, location: str = "") -> dict[str, float]:
        """element_symbol -> internal QC warning limit for (customer_id,
        chemical_id), or {} if none on file.
        """
        return self._cache.get_by_customer_chemical(customer_id, chemical_id, "warning_limit", location)

    def limits_owner(self, customer_id: int, chemical_id: int, parent_customer_id: int | None) -> int:
        """Whose limits apply to this customer + chemical: the customer's
        own if it has any (specification or warning limit) for this
        chemical, otherwise its group's (Customer.parent_customer_id) -- e.g.
        a Chemco site with no limits of its own for PGMEA uses the Chemco group's
        PGMEA limits, as the legacy macro did. Per chemical, so a site can
        later hold its own limits for one chemical and still inherit the
        rest. Returns customer_id when there's no group."""
        own = self.get_specs(customer_id, chemical_id) or self.get_warning_limits(customer_id, chemical_id)
        if own or parent_customer_id is None:
            return customer_id
        return parent_customer_id

    def get_category_label(
        self, customer_id: int, chemical_id: int, location: str = "", kind: str = "specification"
    ) -> str | None:
        """The category_label on file for this (customer, chemical,
        location)'s rows of one kind ("specification" or "warning_limit"),
        or None if it has none. It is the customer-requested header for
        that limit column (e.g. "Action Limit", "Warning Limit"); for SX5
        it is the sheet's QC reference code (e.g. "SX5N-QC-REF-HCL")."""
        return self._cache.get_category_label(customer_id, chemical_id, location, kind)

    def get_report_setting(
        self, customer_id: int, chemical_id: int, location: str = ""
    ) -> ChemicalReportSetting | None:
        """Assay spec range / report note / display label on file for this
        (customer, chemical, location), or None if nothing is on file."""
        return self._cache.get_report_setting(customer_id, chemical_id, location)

    def get_specs_by_raw_names(self, customer_name_raw: str, chemical_name_raw: str) -> dict[str, float]:
        """Same as get_specs, but keyed by the raw (case-insensitive,
        whitespace-trimmed) customer/chemical name text instead of resolved
        IDs -- the only way to reach a migrated row whose customer_id or
        chemical_id didn't resolve against the catalog at migration time.
        """
        return self._cache.get_by_raw_names(customer_name_raw, chemical_name_raw, "specification")

    def get_unit_override(self, customer_id: int, chemical_id: int) -> str | None:
        """The real reporting unit for this (customer, chemical)'s specs,
        ONLY when it's genuinely something other than ppb -- None means
        "use the default ppb wording" (either no spec on file, or its
        unit is a ppb-equivalent). Confirmed real (modReportCreator.bas's
        Get_Specs, direct VBA source check 2026-09-28): the real template
        preamble reads "All data in units of ppb unless otherwise noted"
        by default, and the legacy macro replaces "ppb" with this real
        unit when the spec on file isn't ppb -- confirmed against a real
        completed report (Customer 047 / PG, unit "ppm" on file,
        real report reads "...units of ppm unless otherwise noted").

        "(ppb)" is treated as equivalent to "ppb" (case/whitespace/paren
        insensitive), not a genuinely different unit -- confirmed real:
        several (customer, chemical) rows have "(ppb)" verbatim on file
        (a data-entry inconsistency in the source spec database, not a
        real different unit), but a real completed report for one of
        them (Customer 168 / 1% NH4OH) shows the plain, unsubstituted "ppb"
        wording -- so treating "(ppb)" as ppb-equivalent matches real
        evidence, not just a guess at cleaning up messy source data.
        """
        unit = self._cache.get_unit_by_customer_chemical(customer_id, chemical_id)
        if unit is None:
            return None
        normalized = unit.strip().lower().strip("()")
        if normalized == "ppb" or not normalized:
            return None
        return unit
