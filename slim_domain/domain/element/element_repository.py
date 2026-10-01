from sqlalchemy import String
from sqlalchemy.orm import Mapped, Session, mapped_column

from infrastructure.database import Base
from slim_domain.domain.element.element import Element


class _ElementRow(Base):
    __tablename__ = "elements"

    id: Mapped[int] = mapped_column("ID", primary_key=True)
    element_symbol: Mapped[str] = mapped_column(String)
    element_name: Mapped[str] = mapped_column(String)


class ElementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def select_all(self) -> list[Element]:
        """Load every element row ordered by symbol. Called only by ElementCache."""
        rows = (
            self._session.query(_ElementRow)
            .order_by(_ElementRow.element_symbol)
            .all()
        )
        return [
            Element(id=r.id, symbol=r.element_symbol, name=r.element_name)
            for r in rows
        ]
