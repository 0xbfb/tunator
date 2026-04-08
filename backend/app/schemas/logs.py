from pydantic import BaseModel


class LogResponse(BaseModel):
    entries: list[str]
