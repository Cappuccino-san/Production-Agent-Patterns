"""Tier 2: LangGraph node execution, state transitions, and conditional routing tests."""

import pytest
from app.agent.graph import build_plan_execute_graph, should_replan_or_continue
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import (
    executor_node,
    planner_node,
    replanner_node,
    synthesizer_node,
)
from app.agent.state import PlanExecuteState


@pytest.mark.graph
class TestLangGraphNodes:
    """Isolated unit tests for individual LangGraph node functions."""

    def test_planner_node_generates_steps(self, mock_llm: DeterministicMockLLM) -> None:
        state: PlanExecuteState = {
            "goal": "Build an automated CI/CD pipeline for Python microservice",
            "iterations": 0,
        }
        res = planner_node(state, mock_llm)
        assert len(res["plan"]) >= 3
        assert res["current_step_index"] == 0
        assert res["completed"] is False
        assert res["needs_replan"] is False
        assert res["iterations"] == 1

    def test_planner_node_preserves_existing_plan(self, mock_llm: DeterministicMockLLM) -> None:
        pre_existing = [{"title": "Custom Step", "description": "Custom desc", "tool": "custom"}]
        state: PlanExecuteState = {
            "goal": "Custom goal",
            "plan": pre_existing,
            "iterations": 0,
        }
        res = planner_node(state, mock_llm)
        assert len(res["plan"]) == 1
        assert res["plan"][0]["title"] == "Custom Step"

    def test_executor_node_success(self, mock_llm: DeterministicMockLLM) -> None:
        state: PlanExecuteState = {
            "goal": "Deploy Docker container",
            "plan": [
                {"title": "Step 1", "description": "Build image", "tool": "code"},
                {"title": "Step 2", "description": "Start container", "tool": "devops"},
            ],
            "current_step_index": 0,
            "past_steps": [],
            "iterations": 1,
        }
        res = executor_node(state, mock_llm)
        assert res["current_step_index"] == 1
        assert res["needs_replan"] is False
        assert len(res["past_steps"]) == 1
        assert res["past_steps"][0]["status"] == "completed"
        assert res["past_steps"][0]["result"] is not None

    def test_executor_node_failure_triggers_replan_flag(self) -> None:
        failing_mock = DeterministicMockLLM(fail_at_step=0)
        state: PlanExecuteState = {
            "goal": "Deploy Docker container",
            "plan": [
                {"title": "Step 1", "description": "Failing step", "tool": "code"},
                {"title": "Step 2", "description": "Subsequent step", "tool": "devops"},
            ],
            "current_step_index": 0,
            "past_steps": [],
            "iterations": 1,
        }
        res = executor_node(state, failing_mock)
        assert res["current_step_index"] == 0
        assert res["needs_replan"] is True
        assert res["completed"] is False
        assert res["past_steps"][0]["status"] == "failed"
        assert res["error"] is not None

    def test_executor_node_completes_when_past_all_steps(self, mock_llm: DeterministicMockLLM) -> None:
        state: PlanExecuteState = {
            "goal": "Finished goal",
            "plan": [{"title": "Step 1", "description": "Done", "tool": "code"}],
            "current_step_index": 1,
            "past_steps": [],
            "iterations": 2,
        }
        res = executor_node(state, mock_llm)
        assert res["completed"] is True
        assert res["needs_replan"] is False

    def test_replanner_node_reconstructs_plan(self, mock_llm: DeterministicMockLLM) -> None:
        state: PlanExecuteState = {
            "goal": "Setup database",
            "plan": [
                {"title": "Step 1", "description": "Init table", "tool": "database"},
                {"title": "Step 2", "description": "Query index", "tool": "database"},
            ],
            "current_step_index": 0,
            "past_steps": [
                {"title": "Step 1", "status": "failed", "error": "Table locked"}
            ],
            "needs_replan": True,
            "replan_count": 0,
            "iterations": 2,
        }
        res = replanner_node(state, mock_llm)
        assert res["needs_replan"] is False
        assert res["replan_count"] == 1
        assert len(res["plan"]) >= 2
        # Check that a recovery step was inserted
        assert "Diagnose and Recover" in res["plan"][0]["title"]

    def test_synthesizer_node_formulates_response(self, mock_llm: DeterministicMockLLM) -> None:
        state: PlanExecuteState = {
            "goal": "Create benchmark report",
            "past_steps": [
                {"title": "Run Benchmark", "status": "completed", "result": "1000 ops/sec"}
            ],
            "plan": [{"title": "Run Benchmark"}],
            "current_step_index": 1,
            "completed": True,
            "iterations": 3,
        }
        res = synthesizer_node(state, mock_llm)
        assert res["response"] is not None
        assert "Plan-and-Execute Workflow Summary" in res["response"]
        assert res["completed"] is True


@pytest.mark.graph
class TestConditionalRouting:
    """Validation of should_replan_or_continue edge routing logic."""

    def test_routing_to_replanner_when_needed(self) -> None:
        state: PlanExecuteState = {
            "needs_replan": True,
            "replan_count": 0,
            "iterations": 2,
            "max_iterations": 10,
        }
        assert should_replan_or_continue(state) == "replanner"

    def test_routing_to_synthesizer_when_replan_bound_exceeded(self) -> None:
        state: PlanExecuteState = {
            "needs_replan": True,
            "replan_count": 3,
            "iterations": 5,
            "max_iterations": 10,
        }
        assert should_replan_or_continue(state) == "synthesizer"

    def test_routing_to_synthesizer_when_max_iterations_reached(self) -> None:
        state: PlanExecuteState = {
            "needs_replan": False,
            "iterations": 15,
            "max_iterations": 15,
        }
        assert should_replan_or_continue(state) == "synthesizer"

    def test_routing_to_synthesizer_when_all_steps_completed(self) -> None:
        state: PlanExecuteState = {
            "plan": [{"title": "Step 1"}],
            "current_step_index": 1,
            "needs_replan": False,
            "iterations": 3,
            "max_iterations": 10,
        }
        assert should_replan_or_continue(state) == "synthesizer"

    def test_routing_to_executor_when_more_steps_remain(self) -> None:
        state: PlanExecuteState = {
            "plan": [{"title": "Step 1"}, {"title": "Step 2"}],
            "current_step_index": 0,
            "needs_replan": False,
            "iterations": 1,
            "max_iterations": 10,
        }
        assert should_replan_or_continue(state) == "executor"


@pytest.mark.graph
class TestLangGraphEndToEndExecution:
    """Full execution tests for the compiled StateGraph."""

    def test_successful_plan_execution_e2e(self, mock_llm: DeterministicMockLLM) -> None:
        graph = build_plan_execute_graph(mock_llm)
        initial_state: PlanExecuteState = {
            "goal": "Design SQLite WAL and FTS5 BM25 search architecture",
            "max_iterations": 15,
        }
        final_state = graph.invoke(initial_state)

        assert final_state["completed"] is True
        assert len(final_state["past_steps"]) >= 3
        assert final_state["response"] is not None
        assert "Plan-and-Execute Workflow Summary" in final_state["response"]
        assert all(s["status"] == "completed" for s in final_state["past_steps"])

    def test_execution_with_failure_and_adaptive_replan(self) -> None:
        # Step 0 succeeds, step 1 fails, replanner triggers and adapts, subsequent steps succeed
        failing_mock = DeterministicMockLLM(fail_at_step=1)
        graph = build_plan_execute_graph(failing_mock)

        # After step 1 fails and replans, clear fail_at_step so recovery succeeds
        initial_state: PlanExecuteState = {
            "goal": "Build resilient data pipeline",
            "plan": [
                {"title": "Step 0: Init", "description": "Init pipeline", "tool": "code"},
                {"title": "Step 1: Ingest", "description": "trigger_error in data", "tool": "analysis"},
                {"title": "Step 2: Process", "description": "Process data", "tool": "code"},
            ],
            "max_iterations": 15,
        }

        final_state = graph.invoke(initial_state)
        assert final_state["replan_count"] >= 1
        assert final_state["response"] is not None
        assert len(final_state["past_steps"]) >= 2
