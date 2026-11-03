"""Tier 2: LangGraph node execution, state transitions, and Reflexion loop tests."""


from app.agent.graph import create_reflection_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import (
    actor_node,
    critic_node,
    finalize_node,
    reflection_node,
    reviser_node,
    should_continue,
)
from app.agent.state import AgentState
from app.database import get_session_sync


class TestAgentNodes:
    """Unit tests for individual LangGraph node handlers."""

    def test_actor_node_generates_initial_draft(self, mock_llm: DeterministicMockLLM) -> None:
        state: AgentState = {
            "task": "Filter positive numbers from a list",
            "iteration": 0,
            "history": [],
        }
        res = actor_node(state, mock_llm)
        assert res["iteration"] == 1
        assert res["status"] == "in_progress"
        assert "def " in res["current_draft"]
        assert len(res["current_draft"]) > 10

    def test_critic_node_evaluates_flawed_draft(self, mock_llm: DeterministicMockLLM) -> None:
        state: AgentState = {
            "task": "Filter positive numbers",
            "current_draft": "def filter_pos(items):\n    return [x for x in items if x > 0]\n",
            "threshold": 85.0,
        }
        res = critic_node(state, mock_llm)
        assert "rubric_scores" in res
        assert "composite_score" in res
        assert res["composite_score"] < 85.0
        assert res["passed"] is False
        assert len(res["defects"]) > 0
        assert "critique" in res

    def test_reflection_node_persists_to_db(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        from app.database import create_session_sync

        create_session_sync("Sample task", 85.0, None, "sess_refl_test", temp_db)

        state: AgentState = {
            "session_id": "sess_refl_test",
            "task": "Sample task",
            "iteration": 1,
            "max_iterations": 4,
            "current_draft": "def sample(): pass",
            "critique": "Draft critique",
            "rubric_scores": {"correctness": 60.0},
            "composite_score": 60.0,
            "passed": False,
            "history": [],
            "db_path": temp_db,
        }
        res = reflection_node(state, mock_llm)
        assert res["status"] == "in_progress"
        assert len(res["history"]) == 1

        # Verify persisted in SQLite
        sess = get_session_sync("sess_refl_test", temp_db)
        assert sess is not None
        assert len(sess["iterations"]) == 1
        assert sess["iterations"][0]["composite_score"] == 60.0

    def test_reviser_node_increments_iteration(
        self, mock_llm: DeterministicMockLLM
    ) -> None:
        state: AgentState = {
            "task": "Process items",
            "current_draft": "def process(items): return items",
            "critique": "Needs type hints and docstrings.",
            "defects": ["Missing comprehensive docstring", "Missing static type annotations"],
            "iteration": 1,
        }
        res = reviser_node(state, mock_llm)
        assert res["iteration"] == 2
        assert res["status"] == "in_progress"
        assert "typing" in res["current_draft"] or "def " in res["current_draft"]

    def test_should_continue_router_logic(self) -> None:
        # If passed, should finalize
        assert should_continue({"passed": True, "iteration": 1, "max_iterations": 4}) == "finalize"

        # If max iterations reached, should finalize
        assert should_continue({"passed": False, "iteration": 4, "max_iterations": 4}) == "finalize"

        # If not passed and iteration < max_iterations, route to reviser
        assert should_continue({"passed": False, "iteration": 1, "max_iterations": 4}) == "reviser"

    def test_finalize_node_updates_database(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        from app.database import create_session_sync

        create_session_sync("Sample task", 85.0, None, "sess_fin_test", temp_db)

        state: AgentState = {
            "session_id": "sess_fin_test",
            "status": "completed",
            "composite_score": 92.0,
            "db_path": temp_db,
        }
        res = finalize_node(state, mock_llm)
        assert res["status"] == "completed"

        sess = get_session_sync("sess_fin_test", temp_db)
        assert sess is not None
        assert sess["status"] == "completed"
        assert sess["final_score"] == 92.0


class TestReflexionGraphExecution:
    """End-to-end tests for compiled LangGraph Reflexion StateGraph."""

    def test_graph_progressive_score_improvement(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        from app.database import create_session_sync

        sid = "sess_graph_01"
        create_session_sync(
            task="Write an efficient unique element extractor with error checks",
            threshold=85.0,
            rubric=None,
            session_id=sid,
            db_path=temp_db,
        )

        initial_state: AgentState = {
            "session_id": sid,
            "task": "Write an efficient unique element extractor with error checks",
            "threshold": 85.0,
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

        # Confirm successful completion
        assert final_state["status"] == "completed"
        assert final_state["composite_score"] >= 85.0
        assert len(final_state["history"]) >= 2

        # Verify progressive improvement: score strictly increases across revisions!
        scores = [step["composite_score"] for step in final_state["history"]]
        assert len(scores) >= 2
        assert scores[1] > scores[0], f"Revision score {scores[1]} should exceed initial {scores[0]}"

        # Check final draft quality
        assert "def " in final_state["current_draft"]
        assert '"""' in final_state["current_draft"]

    def test_graph_max_iterations_cutoff(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        from app.database import create_session_sync

        sid = "sess_cutoff_01"
        create_session_sync(
            task="Impossible threshold test",
            threshold=99.9,
            rubric=None,
            session_id=sid,
            db_path=temp_db,
        )

        # Set max_iterations to 1 so it cannot revise even if below threshold
        initial_state: AgentState = {
            "session_id": sid,
            "task": "Impossible threshold test",
            "threshold": 99.9,
            "max_iterations": 1,
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
        assert len(final_state["history"]) == 1
        assert final_state["composite_score"] < 99.9
