from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeEntry(BaseModel):
    topic: str = ""
    triggers: list[str] = Field(default_factory=list)
    answer: str = ""
