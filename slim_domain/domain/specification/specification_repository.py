from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from infrastructure.database import Base
from slim_domain.domain.specification.specification import ChemicalReportSetting, Specification


class _SpecificationRow(Base):
    __tablename__ = "specifications"

    id: Mapped[int] = mapped_column("ID", primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name_raw: Mapped[str] = mapped_column(String)
    chemical_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chemical_name_raw: Mapped[str] = mapped_column(String)
    element_symbol: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    category_label: Mapped[str] = mapped_column(String)
    parameter_text: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")


class _ChemicalReportSettingRow(Base):
    __tablename__ = "chemical_report_settings"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location: Mapped[str] = mapped_column(String, primary_key=True, default="")
    chemical_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assay_spec_text: Mapped[str | None] = mapped_column(String, nullable=True)
    report_note: Mapped[str | None] = mapped_column(String, nullable=True)
    display_label: Mapped[str | None] = mapped_column(String, nullable=True)


class SpecificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def select_all(self) -> list[Specification]:
        """Load every specification row. Called only by SpecificationCache --
        the real table (~3300 rows) is small enough to load whole, same
        pattern as every other domain here.
        """
        rows = self._session.query(_SpecificationRow).all()
        return [_to_specification(r) for r in rows]

    def select_all_report_settings(self) -> list[ChemicalReportSetting]:
        """Load every chemical_report_settings row (a handful) -- also
        called only by SpecificationCache."""
        rows = self._session.query(_ChemicalReportSettingRow).all()
        return [
            ChemicalReportSetting(
                customer_id=r.customer_id,
                location=r.location,
                chemical_id=r.chemical_id,
                assay_spec_text=r.assay_spec_text,
                report_note=r.report_note,
                display_label=r.display_label,
            )
            for r in rows
        ]


def _to_specification(row: _SpecificationRow) -> Specification:
    return Specification(
        id=row.id,
        kind=row.kind,
        customer_id=row.customer_id,
        customer_name_raw=row.customer_name_raw,
        chemical_id=row.chemical_id,
        chemical_name_raw=row.chemical_name_raw,
        element_symbol=row.element_symbol,
        value=row.value,
        unit=row.unit,
        category_label=row.category_label,
        parameter_text=row.parameter_text,
        location=row.location or "",
    )
