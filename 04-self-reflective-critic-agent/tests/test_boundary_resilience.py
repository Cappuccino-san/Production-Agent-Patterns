"""Tier 5: Boundary conditions, resilience, early stopping, and concurrency tests."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.agent.graph import create_reflection_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import AgentState
from app.database import create_session_sync, get_session_sync
from app.models import RubricCriterion


class TestBoundaryAndEarlyStopping:
    """Verifies edge cases, early stopping, and iteration boundary enforcement."""

    def test_early_stopping_on_low_threshold(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        """When threshold is low (e.g., 50.0), initial draft passes immediately without revising."""
        sid = "sess_early_stop"
        create_session_sync("Simple counter function", 50.0, None, sid, temp_db)

        initial_state: AgentState = {
            "session_id": sid,
            "task": "Simple counter function",
            "threshold": 50.0,
            "max_iterations": 4,
            "iteration": 0,
            "current_draft": "",
            "critique": "",
            "defects": [],
            "suggestions": [],
            "rubric_scores": {},
            "composite_score": 0.0,
            "passed": False,
            "status": "in_progress",
            "history": [],
            "db_path": temp_db,
        }

        graph = create_reflection_graph(mock_llm)
        final_state = graph.invoke(initial_state)

        # Passes on first iteration
        assert final_state["status"] == "completed"
        assert len(final_state["history"]) == 1
        assert final_state["composite_score"] >= 50.0

    def test_strict_max_iteration_cutoff(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        """When threshold is unattainable within max_iterations, terminates cleanly."""
        sid = "sess_unattainable"
        create_session_sync("Hard task", 99.5, None, sid, temp_db)

        initial_state: AgentState = {
            "session_id": sid,
            "task": "Hard task",
            "threshold": 99.5,
            "max_iterations": 2,
            "iteration": 0,
            "current_draft": "",
            "critique": "",
            "defects": [],
            "suggestions": [],
            "rubric_scores": {},
            "composite_score": 0.0,
            "passed": False,
            "status": "in_progress",
            "history": [],
            "db_path": temp_db,
        }

        graph = create_reflection_graph(mock_llm)
        final_state = graph.invoke(initial_state)

        assert final_state["status"] == "max_iterations_reached"
        assert len(final_state["history"]) == 2
        assert final_state["composite_score"] < 99.5


class TestCustomRubricAndSeedDeterminism:
    """Verifies custom weighted rubrics and deterministic execution reproducibility."""

    def test_custom_weighted_rubric_evaluation(self, mock_llm: DeterministicMockLLM) -> None:
        """Custom weighted criteria correctly alter composite score."""
        custom_criteria = [
            RubricCriterion(name="correctness", weight=3.0, description="Heavily weighted"),
            RubricCriterion(name="clarity", weight=1.0, description="Lightly weighted"),
        ]

        draft = 'def solve():\n    """Docstring only."""\n    return 42\n'
        result = mock_llm.evaluate_draft(
            task="Solve math problem",
            draft=draft,
            criteria=custom_criteria,
            threshold=80.0,
        )

        assert "correctness" in result.criteria_scores
        assert "clarity" in result.criteria_scores
        # Composite should match weighted formula
        expected = round(
            (result.criteria_scores["correctness"] * 3.0 + result.criteria_scores["clarity"] * 1.0) / 4.0,
            1,
        )
        assert abs(result.composite_score - expected) < 0.2

    def test_deterministic_seed_consistency(self) -> None:
        """Identical seeds produce identical outputs and progressive score milestones."""
        llm1 = DeterministicMockLLM(seed=42)
        llm2 = DeterministicMockLLM(seed=42)

        draft1 = llm1.generate_initial_draft("Binary search")
        draft2 = llm2.generate_initial_draft("Binary search")
        assert draft1 == draft2

        eval1 = llm1.evaluate_draft("Binary search", draft1)
        eval2 = llm2.evaluate_draft("Binary search", draft2)
        assert eval1.composite_score == eval2.composite_score
        assert eval1.criteria_scores == eval2.criteria_scores

    def test_unicode_and_complex_task_prompts(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        """Handles unicode, emojis, and multiline inputs without error."""
        task = "Process UTF-8 strings 🚀 with accents: café, naïve, and résumés\n\nEnsure strict O(1) checks."
        sid = "sess_unicode_01"
        create_session_sync(task, 85.0, None, sid, temp_db)

        initial_state: AgentState = {
            "session_id": sid,
            "task": task,
            "threshold": 85.0,
            "max_iterations": 3,
            "iteration": 0,
            "current_draft": "",
            "critique": "",
            "defects": [],
            "suggestions": [],
            "rubric_scores": {},
            "composite_score": 0.0,
            "passed": False,
            "status": "in_progress",
            "history": [],
            "db_path": temp_db,
        }

        graph = create_reflection_graph(mock_llm)
        final_state = graph.invoke(initial_state)

        assert final_state["status"] in ("completed", "max_iterations_reached")
        assert len(final_state["history"]) >= 1


class TestConcurrentSessionExecution:
    """Verifies SQLite WAL concurrency and multi-threaded agent execution."""

    def test_concurrent_sessions_under_wal(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        """Executes 5 concurrent agent reflection loops against SQLite WAL database."""
        def run_session(idx: int) -> dict[str, Any]:
            sid = f"sess_concurrent_{idx}"
            create_session_sync(f"Concurrent task {idx}", 85.0, None, sid, temp_db)

            state: AgentState = {
                "session_id": sid,
                "task": f"Concurrent task {idx} implementation",
                "threshold": 85.0,
                "max_iterations": 3,
                "iteration": 0,
                "current_draft": "",
                "critique": "",
                "defects": [],
                "suggestions": [],
                "rubric_scores": {},
                "composite_score": 0.0,
                "passed": False,
                "status": "in_progress",
                "history": [],
                "db_path": temp_db,
            }

            graph = create_reflection_graph(mock_llm)
            return graph.invoke(state)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_session, i) for i in range(5)]
            results = [f.result() for f in futures]

        assert len(results) == 5
        for idx, res in enumerate(results):
            assert res["status"] in ("completed", "max_iterations_reached")
            sess = get_session_sync(f"sess_concurrent_{idx}", temp_db)
            assert sess is not None
            assert len(sess["iterations"]) >= 1
