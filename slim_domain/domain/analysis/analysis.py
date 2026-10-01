from pydantic import BaseModel, ConfigDict


class Analysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    description: str = ""
    sort_order: int = 0
