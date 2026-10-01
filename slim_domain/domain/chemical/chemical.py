from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Chemical(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    metals_prep: str
    silicon_prep: str
    ions_prep: str
    entry_date: datetime | None = None
    ked_element_ids: frozenset[int] = frozenset()
    # Which instrument the metals panel's footer names ("Analysis by
    # <this> (<metals_prep>)") -- confirmed real: normally "ICPMS", but a
    # very dirty/nasty matrix, or one that itself contains a metal (e.g.
    # NaOH), gets manually switched to "ICPOES" during the quote process --
    # rules are real but non-trivial (a human judgment call upstream of
    # the TR form, not derivable from parsed submission data), so this is
    # a plain manually-set catalog field, same as metals_prep, not
    # computed. Default "ICPMS" matches current practice for a chemical
    # with no override on file.
    metals_instrument: str = "ICPMS"
