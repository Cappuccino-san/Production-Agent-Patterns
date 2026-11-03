"""State definition for Shadow Trajectory Comparator LangGraph agent."""

from typing import Optional
from pydantic import BaseModel, Field
from app.models import ShadowComparisonReport, TrajectorySummary


class ShadowComparatorState(BaseModel):
    request_id: str
    prompt: str
    is_shadow_sampled: bool = False
    primary_trajectory: Optional[TrajectorySummary] = None
    candidate_trajectory: Optional[TrajectorySummary] = None
    comparison_report: Optional[ShadowComparisonReport] = None
