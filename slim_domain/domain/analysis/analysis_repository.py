from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from infrastructure.database import Base, make_session
from slim_domain.domain.analysis.analysis import Analysis


class _AnalysisRow(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column("ID", primary_key=True)
    analysis_name: Mapped[str] = mapped_column(String)
    analysis_description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Global tiebreaker for analyses that co-occur under a single combined
    # form_name (e.g. "Density, pH" -> [Density, pH] as two IDs from one
    # form-text key -- see analysis_cache.py). Sourced from the real legacy
    # template's own row layout (Python-VBA-Bridge "Report Creator
    # Template.xlsx", named ranges like Misc_Analysis_density_pH__select_
    # Density_pH), not guessed. Defaults to 0 (no defined order -- falls
    # back to insertion order, same as before this column existed) for
    # every analysis not yet assigned a real value.
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class _FormAnalysisRow(Base):
    __tablename__ = "form_analyses"

    form_name: Mapped[str] = mapped_column(String, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.ID"), primary_key=True)


class AnalysisRepository:
    def __init__(self, session: Session, engine: Engine | None = None) -> None:
        self._session = session
        self._engine = engine

    def _write_session(self) -> Session:
        """See CustomerRepository._write_session's docstring -- same
        confirmed-real reasoning, same fallback behavior."""
        return make_session(self._engine) if self._engine is not None else self._session

    def select_all(self) -> list[Analysis]:
        """Load every analysis row ordered by name. Called only by AnalysisCache.build."""
        rows = (
            self._session.query(_AnalysisRow)
            .order_by(_AnalysisRow.analysis_name)
            .all()
        )
        return [
            Analysis(
                id=r.id,
                name=r.analysis_name,
                description=r.analysis_description or "",
                sort_order=r.sort_order,
            )
            for r in rows
        ]

    def select_all_form_analyses(self) -> list[tuple[str, int]]:
        """Load all form-name → analysis_id mappings. Called only by AnalysisCache."""
        rows = self._session.query(_FormAnalysisRow).all()
        return [(r.form_name, r.analysis_id) for r in rows]

    def insert_form_analysis(self, form_name: str, analysis_id: int) -> None:
        """Persist a new form-name → analysis_id mapping."""
        session = self._write_session()
        try:
            session.add(_FormAnalysisRow(form_name=form_name, analysis_id=analysis_id))
            session.commit()
        finally:
            if session is not self._session:
                session.close()
