"""State definition for Teardown Assistant LangGraph agent."""

from typing import List
from pydantic import BaseModel, Field
from app.models import TeardownSearchHit


class TeardownAssistantState(BaseModel):
    query_id: str
    query: str
    db_path: str = "./data/teardown.db"
    search_hits: List[TeardownSearchHit] = Field(default_factory=list)
    retrieved_context: str = ""
    answer: str = ""
    sources: List[str] = Field(default_factory=list)
