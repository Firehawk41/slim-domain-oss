from pydantic import BaseModel, ConfigDict


class Customer(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    street_address: str
    city: str
    state: str
    postal_code: str
    country: str
    # Per-customer override for the additional-elements block's prep-method
    # footer text (e.g. "Analysis by ICPMS (<this>)") -- confirmed real:
    # at least one customer's agreement calls for their additional
    # elements to be run by a different method than their main metals
    # panel. Empty string (the default) means "no override, use whatever
    # the main panel uses" -- deliberately generic/customer-agnostic here;
    # any customer-specific value belongs only in a real database record,
    # never hardcoded in this public repo. Same pattern as
    # Chemical.metals_prep.
    additional_elements_prep: str = ""
    # Customer groups (2026-10-01): a site's parent group, whose limits it
    # uses for any chemical it has no limits of its own for -- e.g. every
    # Chemco site under one "Chemco" group, which holds one set of limits per
    # chemical (as the legacy Access "Chemco" customer did). None for an
    # ordinary customer. See SpecificationService.limits_owner.
    parent_customer_id: int | None = None
    # True on a group record itself: it holds shared limits but is never a
    # customer a Testing Request maps to, so it's left out of
    # CustomerService.all_customers() (the resolution pages' pick list).
    is_group: bool = False

    @property
    def formatted_address(self) -> str:
        """street_address, city [postal_code][, country] — state omitted (matches VBA)."""
        addr = f"{self.street_address}, {self.city}"
        if self.postal_code:
            addr += f" {self.postal_code}"
        if self.country:
            addr += f", {self.country}"
        return addr
