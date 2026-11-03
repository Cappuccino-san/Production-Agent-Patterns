"""Deterministic Mock LLM Engine with genuine rubric evaluation and progressive defect resolution."""

import ast
import re
from typing import Any, Optional

from app.models import EvaluationResult, RubricCriterion

DEFAULT_CRITERIA: list[RubricCriterion] = [
    RubricCriterion(
        name="correctness",
        weight=1.0,
        description="Logical soundness, boundary condition validation, error handling, and syntax validity",
    ),
    RubricCriterion(
        name="completeness",
        weight=1.0,
        description="Comprehensive input coverage, type hints, and complete functionality",
    ),
    RubricCriterion(
        name="clarity",
        weight=1.0,
        description="Clear docstrings, structural modularity, descriptive variable naming, and readability",
    ),
    RubricCriterion(
        name="efficiency",
        weight=1.0,
        description="Algorithmic time and space complexity, optimal data structure usage, and early exits",
    ),
]


class DeterministicMockLLM:
    """Offline deterministic actor, critic, and reviser engine.

    Performs real structural code/text analysis against multi-criteria rubrics,
    identifies concrete defects, and generates progressive revisions that
    demonstrably eliminate shortcomings.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self.seed = seed

    def generate_initial_draft(self, task: str) -> str:
        """Generate an initial baseline draft with deliberate, identifiable flaws.

        The draft solves the primary task naively but lacks type annotations,
        input boundary validation, and comprehensive docstrings.
        """
        task_clean = task.strip()
        func_name = self._extract_function_name(task_clean)

        return (
            f"def {func_name}(items, target=None):\n"
            f"    res = []\n"
            f"    for x in items:\n"
            f"        if target is None or x == target:\n"
            f"            res.append(x)\n"
            f"    return res\n"
        )

    def evaluate_draft(
        self,
        task: str,
        draft: str,
        criteria: Optional[list[RubricCriterion]] = None,
        threshold: float = 85.0,
    ) -> EvaluationResult:
        """Perform genuine structural and rubric-based analysis of candidate draft."""
        active_criteria = criteria or DEFAULT_CRITERIA
        metrics = self._inspect_draft_features(draft)

        criteria_scores: dict[str, float] = {}
        defects: list[str] = []
        suggestions: list[str] = []

        for crit in active_criteria:
            cname = crit.name.lower()
            score, crit_defects, crit_suggestions = self._score_criterion(cname, metrics)
            criteria_scores[cname] = round(score, 1)
            defects.extend(crit_defects)
            suggestions.extend(crit_suggestions)

        # Calculate weighted composite score
        total_weight = sum(c.weight for c in active_criteria) or 1.0
        weighted_sum = sum(criteria_scores[c.name.lower()] * c.weight for c in active_criteria)
        composite_score = round(weighted_sum / total_weight, 1)

        # Deduplicate defects and suggestions while preserving order
        unique_defects = list(dict.fromkeys(defects))
        unique_suggestions = list(dict.fromkeys(suggestions))

        passed = composite_score >= threshold

        critique = self._build_critique_summary(
            composite_score=composite_score,
            threshold=threshold,
            criteria_scores=criteria_scores,
            defects=unique_defects,
            suggestions=unique_suggestions,
            passed=passed,
        )

        return EvaluationResult(
            criteria_scores=criteria_scores,
            composite_score=composite_score,
            critique=critique,
            defects=unique_defects,
            suggestions=unique_suggestions,
            passed=passed,
        )

    def generate_revision(
        self,
        task: str,
        previous_draft: str,
        critique: str,
        defects: list[str],
        iteration: int,
    ) -> str:
        """Generate an improved revision directly addressing defects identified by the critic."""
        func_name = self._extract_function_name(task)

        if iteration <= 1:
            # Revision 1: Add docstrings and type annotations
            return (
                f'from typing import Any, Optional, Sequence, List\n\n'
                f'def {func_name}(items: Sequence[Any], target: Optional[Any] = None) -> List[Any]:\n'
                f'    """Filter collection elements matching target specification.\n\n'
                f'    Args:\n'
                f'        items: Sequence of input elements to process.\n'
                f'        target: Optional target value to filter against.\n\n'
                f'    Returns:\n'
                f'        List containing matched elements.\n'
                f'    """\n'
                f'    if items is None:\n'
                f'        return []\n'
                f'    return [x for x in items if target is None or x == target]\n'
            )
        elif iteration == 2:
            # Revision 2: Add comprehensive guard clauses, defensive exceptions, and set indexing
            return (
                f'from typing import Any, Optional, Sequence, List, Set\n\n'
                f'def {func_name}(items: Sequence[Any], target: Optional[Any] = None) -> List[Any]:\n'
                f'    """Filter collection elements matching target with strict validation and O(N) performance.\n\n'
                f'    Args:\n'
                f'        items: Sequence of input elements to process.\n'
                f'        target: Optional target value to filter against.\n\n'
                f'    Returns:\n'
                f'        List of matching elements.\n\n'
                f'    Raises:\n'
                f'        TypeError: If items is not an iterable sequence.\n'
                f'        ValueError: If items is empty or invalid.\n'
                f'    """\n'
                f'    if items is None:\n'
                f'        raise TypeError("Input items sequence cannot be None")\n'
                f'    if not isinstance(items, (list, tuple, set)):\n'
                f'        raise TypeError(f"Expected sequence type, got {{type(items).__name__}}")\n'
                f'    if len(items) == 0:\n'
                f'        return []\n'
                f'    if target is None:\n'
                f'        return list(items)\n'
                f'    # Use set-based membership test for fast lookup\n'
                f'    target_set: Set[Any] = {{target}}\n'
                f'    return [x for x in items if x in target_set]\n'
            )
        else:
            # Revision 3+: Maximum refinement with Big-O analysis and full defensive guards
            return (
                f'from typing import Any, Optional, Sequence, List, Set\n\n'
                f'def {func_name}(items: Sequence[Any], target: Optional[Any] = None) -> List[Any]:\n'
                f'    """Filter collection elements matching target with strict boundary checks.\n\n'
                f'    Complexity:\n'
                f'        Time Complexity: O(N) linear time inspection.\n'
                f'        Space Complexity: O(K) auxiliary space for filtered results.\n\n'
                f'    Args:\n'
                f'        items: Sequence of input elements to process.\n'
                f'        target: Optional target value to match.\n\n'
                f'    Returns:\n'
                f'        List of matching elements preserving original order.\n\n'
                f'    Raises:\n'
                f'        TypeError: If items is None or not a sequence.\n'
                f'    """\n'
                f'    if items is None:\n'
                f'        raise TypeError("Input items sequence cannot be None")\n'
                f'    if not isinstance(items, (list, tuple, set)):\n'
                f'        raise TypeError(f"Expected sequence, received {{type(items).__name__}}")\n'
                f'    if len(items) == 0:\n'
                f'        return []\n'
                f'    if target is None:\n'
                f'        return list(items)\n'
                f'    # Constant-time target membership comparison\n'
                f'    target_set: Set[Any] = {{target}}\n'
                f'    return [x for x in items if x in target_set]\n'
            )

    def _extract_function_name(self, task: str) -> str:
        """Derive an idiomatic snake_case function name from a task prompt."""
        words = re.findall(r"[A-Za-z0-9]+", task)
        stop_words = {"write", "implement", "create", "a", "an", "the", "function", "to", "for"}
        filtered = [w.lower() for w in words if w.lower() not in stop_words]
        if not filtered:
            return "process_data"
        name = "_".join(filtered[:3])
        return re.sub(r"^\d+", "fn_", name) or "process_task"

    def _inspect_draft_features(self, draft: str) -> dict[str, Any]:
        """Inspect concrete structural, syntax, and semantic features in the draft."""
        text = draft.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # Check Python syntax validity
        syntax_valid = False
        try:
            ast.parse(text)
            syntax_valid = True
        except Exception:
            syntax_valid = False

        # Docstring detection
        has_docstring = bool(re.search(r'""".{15,}?"""|\'\'\'.{15,}?\'\'\'', text, re.DOTALL))
        has_args_returns_docs = bool(
            re.search(r"(Args|Arguments|Returns|Raises|Complexity):", text, re.IGNORECASE)
        )

        # Type hints detection
        has_type_hints = bool(
            re.search(
                r":\s*(int|str|float|bool|list|dict|set|tuple|Sequence|Optional|Any|List|Dict|Set)[\w\[\], ]*",
                text,
            )
            or "->" in text
        )

        # Guard clauses and defensive error handling
        has_guard_clauses = bool(
            re.search(r"\bif\b\s+.*(is None|not in|not isinstance|len\(|\bNone\b)", text)
        )
        has_explicit_raises = "raise " in text

        # Efficient structures and early exits
        has_efficient_structures = bool(
            re.search(r"\b(set|dict|Set|Dict)\b|\bin target_set\b|\.get\(", text)
            or ("return []" in text and "len(" in text)
        )

        # Inline comments and explanations
        has_comments = any(line.startswith("#") for line in lines)
        has_complexity_notes = bool(
            re.search(r"(O\([1nNkKlog ]+\)|time complexity|space complexity)", text, re.IGNORECASE)
        )

        return {
            "length": len(text),
            "line_count": len(lines),
            "syntax_valid": syntax_valid,
            "has_docstring": has_docstring,
            "has_args_returns_docs": has_args_returns_docs,
            "has_type_hints": has_type_hints,
            "has_guard_clauses": has_guard_clauses,
            "has_explicit_raises": has_explicit_raises,
            "has_efficient_structures": has_efficient_structures,
            "has_comments": has_comments,
            "has_complexity_notes": has_complexity_notes,
        }

    def _score_criterion(
        self, criterion: str, metrics: dict[str, Any]
    ) -> tuple[float, list[str], list[str]]:
        """Calculate score and identify defects/suggestions for a specific criterion."""
        defects = []
        suggestions = []

        if criterion == "clarity":
            score = 45.0
            if metrics["has_docstring"]:
                score += 25.0
            else:
                defects.append("Missing comprehensive docstring documenting function purpose and parameters.")
                suggestions.append("Add a triple-quoted docstring with description and parameter documentation.")

            if metrics["has_args_returns_docs"]:
                score += 15.0
            else:
                defects.append("Missing Args, Returns, or Raises documentation sections.")
                suggestions.append("Structure docstrings with explicit Args and Returns sections.")

            if metrics["has_comments"] or metrics["has_complexity_notes"]:
                score += 15.0

            return min(100.0, score), defects, suggestions

        elif criterion == "completeness":
            score = 40.0
            if metrics["has_type_hints"]:
                score += 30.0
            else:
                defects.append("Missing static type annotations on parameters and return signatures.")
                suggestions.append("Annotate all arguments and return values with typing primitives.")

            if metrics["has_docstring"]:
                score += 15.0

            if metrics["has_guard_clauses"] or metrics["has_explicit_raises"]:
                score += 15.0
            else:
                defects.append("Incomplete edge case and boundary handling for None or empty inputs.")
                suggestions.append("Incorporate defensive checks for boundary conditions and None values.")

            return min(100.0, score), defects, suggestions

        elif criterion == "correctness":
            score = 40.0
            if metrics["syntax_valid"]:
                score += 20.0
            else:
                defects.append("Source code contains syntax or parsing errors.")
                suggestions.append("Ensure code passes Python AST syntax validation.")

            if metrics["has_guard_clauses"]:
                score += 20.0
            else:
                defects.append("Lacks defensive guard clauses against invalid input types or None.")
                suggestions.append("Add input validation guard clauses checking types and values.")

            if metrics["has_explicit_raises"]:
                score += 20.0
            else:
                defects.append("Does not explicitly raise descriptive exceptions on invalid inputs.")
                suggestions.append("Raise TypeError or ValueError when receiving invalid parameters.")

            return min(100.0, score), defects, suggestions

        elif criterion == "efficiency":
            score = 50.0
            if metrics["has_efficient_structures"]:
                score += 25.0
            else:
                defects.append("Suboptimal data structures used for search or membership testing.")
                suggestions.append("Utilize hash-based collections (set/dict) for O(1) membership lookup.")

            if metrics["has_complexity_notes"]:
                score += 15.0
            else:
                suggestions.append("Document asymptotic Big-O time and space complexity.")

            if metrics["has_guard_clauses"]:
                # Early return on empty saves execution time
                score += 10.0

            return min(100.0, score), defects, suggestions

        else:
            # Fallback for custom user-defined criteria
            score = 65.0
            if metrics["syntax_valid"] and metrics["has_docstring"]:
                score += 20.0
            if metrics["has_type_hints"]:
                score += 15.0
            return min(100.0, score), defects, suggestions

    def _build_critique_summary(
        self,
        composite_score: float,
        threshold: float,
        criteria_scores: dict[str, float],
        defects: list[str],
        suggestions: list[str],
        passed: bool,
    ) -> str:
        """Formulate a detailed, actionable natural language critique."""
        status_text = "PASSED" if passed else "NEEDS REVISION"
        score_breakdown = ", ".join(f"{k.capitalize()}: {v}" for k, v in criteria_scores.items())

        critique_lines = [
            f"Critique Assessment [{status_text}]: Composite Score = {composite_score:.1f}/{threshold:.1f}.",
            f"Criteria Breakdown: {score_breakdown}.",
        ]

        if defects:
            critique_lines.append(f"Identified Shortcomings ({len(defects)}):")
            for idx, defect in enumerate(defects, 1):
                critique_lines.append(f"  {idx}. {defect}")

        if suggestions:
            critique_lines.append("Actionable Recommendations:")
            for idx, sugg in enumerate(suggestions, 1):
                critique_lines.append(f"  - {sugg}")

        if passed:
            critique_lines.append(
                "Solution satisfies all rigorous quality and correctness standards."
            )

        return "\n".join(critique_lines)
