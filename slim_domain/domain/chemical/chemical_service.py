from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from slim_domain.domain.chemical.chemical import Chemical
from slim_domain.domain.chemical.chemical_cache import ChemicalCache
from slim_domain.domain.chemical.chemical_repository import ChemicalRepository

METALS_PREP: tuple[str, ...] = (
    "N/A", "Evaporation", "Dilute and Shoot", "Organic Dilute and Shoot", "Standard Addition",
)
SILICON_PREP: tuple[str, ...] = ("N/A", "Evaporation", "Dilute and Shoot")
IONS_PREP: tuple[str, ...] = (
    "N/A", "Dilute and Shoot", "Evaporation", "Neutralizing", "Extraction", "Standard Addition",
)


class ChemicalService:
    """Public API for the chemical domain. Callers never touch repo or cache."""

    metals_prep_options: tuple[str, ...] = METALS_PREP
    silicon_prep_options: tuple[str, ...] = SILICON_PREP
    ions_prep_options: tuple[str, ...] = IONS_PREP

    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._repo = ChemicalRepository(session, engine=engine)
        self._cache = ChemicalCache(self._repo)

    # --- Reads ---

    def load_chemical(self, chemical_id: int) -> Chemical | None:
        """Return the Chemical for chemical_id, or None if not found."""
        return self._cache.get_by_id(chemical_id)

    def get_by_name(self, name: str) -> Chemical | None:
        """Return the Chemical matching name (case-insensitive), or None if not found."""
        return self._cache.get_by_name(name)

    def all_chemicals(self) -> list[Chemical]:
        """Return all chemicals loaded at startup."""
        return self._cache.all_chemicals()

    def get_id_by_form_name(self, form_name: str) -> int:
        """Return the chemical ID for a form name, or 0 if not mapped."""
        return self._cache.get_id_by_form_name(form_name)

    def get_by_form_name(self, form_name: str) -> Chemical | None:
        """Return the Chemical for a form name, or None if not mapped."""
        chemical_id = self._cache.get_id_by_form_name(form_name)
        if chemical_id > 0:
            return self._cache.get_by_id(chemical_id)
        return None

    def form_name_exists(self, form_name: str) -> bool:
        """Return True if the form name is already mapped to a chemical."""
        return self._cache.form_name_exists(form_name)

    # --- Writes ---

    def create_chemical(
        self,
        name: str,
        metals_prep: str,
        silicon_prep: str,
        ions_prep: str,
        ked_element_ids: frozenset[int] = frozenset(),
        metals_instrument: str = "ICPMS",
        created_by: str = "",
    ) -> Chemical:
        """Validate, persist, and cache a new chemical. Returns the persisted entity.

        created_by: the entering technician's initials, for the ISO 17025
        audit trail -- see CustomerService.create_customer's docstring for
        why initials rather than a login. Required."""
        self._require_valid_name(name)
        self._require_unique_name(name)
        self._require_valid_metals_prep(metals_prep)
        self._require_valid_silicon_prep(silicon_prep)
        self._require_valid_ions_prep(ions_prep)
        if not created_by.strip():
            raise ValueError("Initials cannot be blank")

        chemical = self._repo.insert(
            name, metals_prep, silicon_prep, ions_prep, ked_element_ids, metals_instrument,
            created_by=created_by,
        )
        self._cache.upsert(chemical)
        return chemical

    def add_form_name(self, form_name: str, chemical_id: int, created_by: str = "") -> None:
        """Persist a form-name → chemical_id mapping. Idempotent: no-op if already mapped.

        created_by: see CustomerService.add_form_key's docstring -- same
        reasoning, required even when mapping onto an existing chemical."""
        if self._cache.form_name_exists(form_name):
            return
        if not created_by.strip():
            raise ValueError("Initials cannot be blank")
        self._repo.insert_form_name(form_name, chemical_id, created_by=created_by)
        self._cache.add_form_name_index(form_name, chemical_id)

    # --- Validation (public for UI pre-validation) ---

    def is_valid_name(self, name: str) -> bool:
        return len(name.strip()) > 0

    def is_unique_name(self, name: str) -> bool:
        return not self._cache.exists_by_name(name)

    def is_valid_metals_prep(self, value: str) -> bool:
        return value in METALS_PREP

    def is_valid_silicon_prep(self, value: str) -> bool:
        return value in SILICON_PREP

    def is_valid_ions_prep(self, value: str) -> bool:
        return value in IONS_PREP

    # --- Private helpers ---

    def _require_valid_name(self, name: str) -> None:
        if not self.is_valid_name(name):
            raise ValueError("Chemical name cannot be blank")

    def _require_unique_name(self, name: str) -> None:
        if not self.is_unique_name(name):
            raise ValueError(f"Chemical name already exists: {name}")

    def _require_valid_metals_prep(self, value: str) -> None:
        if not self.is_valid_metals_prep(value):
            raise ValueError(f"Invalid metals prep: {value!r}")

    def _require_valid_silicon_prep(self, value: str) -> None:
        if not self.is_valid_silicon_prep(value):
            raise ValueError(f"Invalid silicon prep: {value!r}")

    def _require_valid_ions_prep(self, value: str) -> None:
        if not self.is_valid_ions_prep(value):
            raise ValueError(f"Invalid ions prep: {value!r}")
