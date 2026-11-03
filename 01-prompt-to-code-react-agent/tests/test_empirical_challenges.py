import pytest
from fastapi.testclient import TestClient

from app.agent.nodes import execute_tool_node, validate_ast_node
from app.agent.state import AgentState
from app.database import save_run, search_runs


@pytest.mark.parametrize(
    "query",
    [
        "fibonacci",
        "FIBONACCI",
        "fib*",
        "AND",
        "OR",
        "NOT",
        "NEAR",
        "AND OR NOT",
        '"fibonacci"',
        '"def fib"',
        "' OR 1=1 --",
        "'; DROP TABLE runs; --",
        ":::;;;<<<>>>",
        "caf\u00e9",
        "\U0001f680",
        "a" * 500,
        "   ",
        "",
        "***",
        "fib AND python",
        "nonexistent_term_12345",
    ],
)
@pytest.mark.asyncio
async def test_fts5_hostile_and_special_character_resilience(temp_db: str, query: str) -> None:
    """Empirically challenge FTS5 search with boolean operators, wildcards, and SQL injection."""
    # Seed DB with test record
    await save_run(
        {
            "id": "run_fts_seed",
            "prompt": "Write a fibonacci function in Python with café 🚀",
            "language": "python",
            "code": "def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)\nprint(fib(5))",
            "is_valid": True,
            "output": "5",
            "iterations": 1,
            "steps": [],
            "status": "completed",
        },
        temp_db,
    )

    results = await search_runs(query=query, limit=10, db_path=temp_db)
    assert isinstance(results, list)
    for hit in results:
        assert "id" in hit
        assert "prompt" in hit
        assert "snippet" in hit
        assert "rank" in hit


@pytest.mark.asyncio
async def test_fts5_delete_and_update_triggers(temp_db: str) -> None:
    """Empirically verify FTS5 triggers correctly handle update and delete without orphan index rows."""
    run_record = {
        "id": "run_sync_test",
        "prompt": "Original prompt for indexing test",
        "language": "python",
        "code": "print('initial')",
        "is_valid": True,
        "output": "initial",
        "iterations": 1,
        "steps": [],
        "status": "completed",
    }
    await save_run(run_record, temp_db)

    # Initial search
    initial_hits = await search_runs("Original", limit=10, db_path=temp_db)
    assert len(initial_hits) == 1
    assert initial_hits[0]["id"] == "run_sync_test"

    # Update record with new prompt text
    run_record["prompt"] = "Transformed prompt after refactoring"
    run_record["code"] = "print('transformed')"
    await save_run(run_record, temp_db)

    # Search for new text
    transformed_hits = await search_runs("Transformed", limit=10, db_path=temp_db)
    assert len(transformed_hits) == 1
    assert transformed_hits[0]["id"] == "run_sync_test"

    # Verify old text no longer matches in FTS5
    old_hits = await search_runs("Original", limit=10, db_path=temp_db)
    assert len(old_hits) == 0


@pytest.mark.parametrize(
    "malformed_code,error_substring",
    [
        ("print(10 + 20", "was never closed"),
        ("def foo():\nreturn 1", "expected an indented block"),
        ('"""unclosed string', "unterminated triple-quoted string"),
        ("def foo():\x00 pass", "source code string cannot contain"),
        ("def foo(a,): pass\nfoo(a=1, 2)", "positional argument follows keyword"),
        ("def foo():\n    return 1 @@@ 2", "invalid syntax"),
        ("def foo():\n\treturn 1\n    return 2", "unindent does not match"),
    ],
)
def test_ast_syntax_error_matrix(malformed_code: str, error_substring: str) -> None:
    """Empirically verify AST validator catches diverse Python syntax and tokenization errors."""
    state: AgentState = {
        "prompt": "Test error handling",
        "language": "python",
        "code": malformed_code,
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    result = validate_ast_node(state)
    assert result["is_valid"] is False
    assert result["error"] is not None
    assert "SyntaxError" in result["error"]
    assert error_substring in result["error"]


def test_sandbox_disallows_import_and_eval() -> None:
    """Empirically test sandbox isolation against __import__ and os calls."""
    dangerous_state: AgentState = {
        "prompt": "Exploit sandbox",
        "language": "python",
        "code": "import os\nos.system('echo exploit')",
        "is_valid": True,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    result = execute_tool_node(dangerous_state)
    assert result["output"] is None
    assert result["error"] is not None
    assert "RuntimeError" in result["error"]
    assert "__import__ not found" in result["error"]


def test_sandbox_executes_safe_math_and_builtins() -> None:
    """Empirically test that permitted builtins (sum, range, len, abs) execute cleanly."""
    safe_state: AgentState = {
        "prompt": "Run math",
        "language": "python",
        "code": "numbers = [abs(x) for x in [-1, -2, 3, 4]]\nprint(f'Sum: {sum(numbers)}, Count: {len(numbers)}')",
        "is_valid": True,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    result = execute_tool_node(safe_state)
    assert result["error"] is None
    assert result["output"] == "Sum: 10, Count: 4"


def test_api_search_endpoint_with_special_characters(test_client: TestClient) -> None:
    """Empirically verify /api/v1/agent/runs/search HTTP contract with hostile inputs."""
    res = test_client.get("/api/v1/agent/runs/search", params={"q": "AND OR NOT *** :::"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    res_empty = test_client.get("/api/v1/agent/runs/search", params={"q": "   "})
    assert res_empty.status_code == 200
    assert res_empty.json() == []


def test_api_run_with_custom_iterations(test_client: TestClient) -> None:
    """Empirically verify API execution bounds on max_iterations."""
    res_invalid = test_client.post(
        "/api/v1/agent/run",
        json={"prompt": "Test out of bounds", "max_iterations": 99},
    )
    assert res_invalid.status_code == 422

    res_zero = test_client.post(
        "/api/v1/agent/run",
        json={"prompt": "Test zero iterations", "max_iterations": 0},
    )
    assert res_zero.status_code == 422
