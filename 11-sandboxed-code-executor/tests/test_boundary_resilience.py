"""Tier 5: Boundary Conditions, Timeout Enforcement, and Sandbox Egress Block Tests."""

from fastapi.testclient import TestClient
from app.database import search_executions_fts_sync
from app.sandbox import execute_in_sandbox, validate_ast_security
from app.models import ExecutionStatus


class TestBoundaryResilience:
    def test_infinite_loop_timeout_enforced(self):
        """Infinite loops must be killed strictly within the timeout window."""
        code = "while True:\n    pass"
        res = execute_in_sandbox(code, timeout_seconds=1.0)
        assert res.status == ExecutionStatus.TIMEOUT
        assert res.exit_code == 124
        assert "timed out" in res.stderr

    def test_ast_blocks_socket_and_dynamic_exec(self):
        code_socket = "import socket\ns = socket.socket()"
        violations_socket = validate_ast_security(code_socket)
        assert any("socket" in v for v in violations_socket)

        code_exec = "eval('__import__(\"os\")')"
        violations_exec = validate_ast_security(code_exec)
        assert any("eval" in v for v in violations_exec)

    def test_search_empty_and_special_characters(self, temp_db: str):
        hits_empty = search_executions_fts_sync(temp_db, "   ")
        assert hits_empty == []

        hits_special = search_executions_fts_sync(temp_db, "'; DROP TABLE sandbox_executions; -- !@#$")
        assert isinstance(hits_special, list)
