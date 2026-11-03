"""Trajectory comparison and diffing engine."""

import uuid
from datetime import datetime, timezone
from app.models import (
    ComparisonRecommendation,
    ShadowComparisonReport,
    TrajectorySummary,
)


def calculate_tool_path_similarity(primary: TrajectorySummary, candidate: TrajectorySummary) -> float:
    """Computes Jaccard similarity between primary and candidate tool call sets."""
    primary_tools = set(tc.tool_name for tc in primary.tool_calls)
    candidate_tools = set(tc.tool_name for tc in candidate.tool_calls)

    if not primary_tools and not candidate_tools:
        return 1.0
    if not primary_tools or not candidate_tools:
        return 0.0

    intersection = primary_tools.intersection(candidate_tools)
    union = primary_tools.union(candidate_tools)
    return round(len(intersection) / len(union), 4)


def diff_trajectories(
    request_id: str,
    prompt: str,
    primary: TrajectorySummary,
    candidate: TrajectorySummary,
) -> ShadowComparisonReport:
    """Performs deep comparison between production primary trajectory and shadow candidate."""
    similarity = calculate_tool_path_similarity(primary, candidate)
    cost_delta = round(candidate.cost_usd - primary.cost_usd, 6)
    
    if primary.cost_usd > 0:
        cost_savings_pct = round(((primary.cost_usd - candidate.cost_usd) / primary.cost_usd) * 100.0, 2)
    else:
        cost_savings_pct = 0.0

    latency_delta = round(candidate.latency_ms - primary.latency_ms, 2)

    # Automated deployment recommendation rule
    if cost_savings_pct >= 10.0 and latency_delta <= 10.0:
        recommendation = ComparisonRecommendation.DEPLOY_CANDIDATE
    elif cost_delta > 0.005 or latency_delta > 100.0:
        recommendation = ComparisonRecommendation.REJECT_REGRESSION
    else:
        recommendation = ComparisonRecommendation.NEUTRAL

    p_tools_str = " -> ".join(tc.tool_name for tc in primary.tool_calls)
    c_tools_str = " -> ".join(tc.tool_name for tc in candidate.tool_calls)

    diff_summary = (
        f"Primary Topology [{primary.topology_name}]: Path=({p_tools_str}), Cost=${primary.cost_usd:.4f}, Latency={primary.latency_ms:.1f}ms. "
        f"Shadow Candidate [{candidate.topology_name}]: Path=({c_tools_str}), Cost=${candidate.cost_usd:.4f}, Latency={candidate.latency_ms:.1f}ms. "
        f"Delta: CostSavings={cost_savings_pct}%, LatencyDelta={latency_delta:+.1f}ms, ToolSimilarity={similarity:.2f}."
    )

    return ShadowComparisonReport(
        comparison_id=f"cmp-{uuid.uuid4().hex[:12]}",
        request_id=request_id,
        prompt=prompt,
        primary_trajectory=primary,
        candidate_trajectory=candidate,
        path_similarity_score=similarity,
        cost_delta_usd=cost_delta,
        cost_savings_pct=cost_savings_pct,
        latency_delta_ms=latency_delta,
        recommendation=recommendation,
        diff_summary=diff_summary,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
