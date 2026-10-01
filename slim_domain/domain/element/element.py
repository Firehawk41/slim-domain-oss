from pydantic import BaseModel, ConfigDict


class Element(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    symbol: str
    name: str
