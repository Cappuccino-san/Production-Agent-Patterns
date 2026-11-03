"""REST API endpoints for Sandboxed Code Execution and Agent Tasks."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import create_interpreter_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import Settings, get_settings
from app.database import (
    get_execution_result_sync,
    save_execution_result_sync,
    search_executions_fts_sync,
)
from app.models import (
    CodeInterpreterTask,
    ExecutionRequest,
    ExecutionResult,
    ExecutionSearchHit,
)
from app.sandbox import execute_in_sandbox

router = APIRouter(prefix="/sandbox", tags=["Sandbox"])

_agent_graph = None


def get_agent_graph(settings: Settings = Depends(get_settings)):
    global _agent_graph
    if _agent_graph is None:
        mock_llm = DeterministicMockLLM()
        _agent_graph = create_interpreter_graph(settings.database_path, mock_llm)
    return _agent_graph


def set_agent_graph(graph):
    global _agent_graph
    _agent_graph = graph


@router.post(
    "/execute",
    response_model=ExecutionResult,
    status_code=status.HTTP_200_OK,
    summary="Execute raw Python code in isolated microVM sandbox with zero internet egress",
)
def execute_code(
    request: ExecutionRequest,
    settings: Settings = Depends(get_settings),
) -> ExecutionResult:
    timeout = request.timeout_seconds or settings.sandbox_timeout_seconds
    result = execute_in_sandbox(request.code, timeout_seconds=timeout)
    save_execution_result_sync(settings.database_path, request.code, result)
    return result


@router.post(
    "/agent-task",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Run Code-Interpreter agent that writes and executes Python in isolated sandbox",
)
def run_agent_task(
    task: CodeInterpreterTask,
    graph=Depends(get_agent_graph),
) -> dict:
    initial_state = {
        "task_prompt": task.prompt,
        "generated_code": "",
        "timeout_seconds": task.timeout_seconds,
        "ast_violations": [],
        "execution_result": None,
        "final_answer": "",
        "audit_trail": [],
    }

    final_state = graph.invoke(initial_state)

    res = final_state.get("execution_result")
    return {
        "task_prompt": task.prompt,
        "generated_code": final_state["generated_code"],
        "status": res.status.value if res else "UNKNOWN",
        "stdout": res.stdout if res else "",
        "stderr": res.stderr if res else "",
        "final_answer": final_state["final_answer"],
        "audit_trail": final_state["audit_trail"],
    }


@router.get(
    "/search",
    response_model=list[ExecutionSearchHit],
    summary="Full-text BM25 search across execution code, stdout, and error traces via SQLite FTS5",
)
def search_executions(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[ExecutionSearchHit]:
    return search_executions_fts_sync(settings.database_path, q, limit)


@router.get(
    "/executions/{execution_id}",
    response_model=dict,
    summary="Retrieve sandboxed execution report by execution ID",
)
def get_execution(
    execution_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    record = get_execution_result_sync(settings.database_path, execution_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution '{execution_id}' not found.",
        )
    return record
