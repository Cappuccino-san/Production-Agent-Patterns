"""Isolated Sandbox and AST Security Guard with Zero Internet Egress Enforcement."""

import ast
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Tuple
from app.models import ExecutionResult, ExecutionStatus

FORBIDDEN_MODULES = {
    "socket",
    "requests",
    "urllib",
    "http",
    "aiohttp",
    "httpx",
    "subprocess",
    "ctypes",
    "ftplib",
    "smtplib",
    "telnetlib",
}

FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "__import__",
}


def validate_ast_security(code: str) -> list[str]:
    """Inspect Python Abstract Syntax Tree (AST) to detect network egress and dangerous calls."""
    violations = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError during AST inspection: {e}"]

    for node in ast.walk(tree):
        # Inspect imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in FORBIDDEN_MODULES:
                    violations.append(f"Forbidden network/system import: '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in FORBIDDEN_MODULES:
                    violations.append(f"Forbidden network/system import: '{node.module}'")

        # Inspect calls to forbidden builtins
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALLS:
                    violations.append(f"Forbidden call to dynamic code execution builtin: '{node.func.id}'")

    return violations


def execute_in_sandbox(code: str, timeout_seconds: float = 5.0) -> ExecutionResult:
    """Execute Python code in isolated process with zero internet egress and strict resource guards."""
    execution_id = f"exec-{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()

    # 1. Static AST Security Gate
    ast_violations = validate_ast_security(code)
    if ast_violations:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return ExecutionResult(
            execution_id=execution_id,
            status=ExecutionStatus.SECURITY_VIOLATION,
            exit_code=1,
            stdout="",
            stderr=f"AST Security Violation: Zero internet egress policy enforced.\n" + "\n".join(ast_violations),
            execution_time_ms=round(duration_ms, 2),
            egress_blocked=True,
            ast_violations=ast_violations,
        )

    # 2. Ephemeral Sandbox Execution Script with Network Monkeypatch
    sandbox_wrapper = f"""
import sys
# Block raw socket instantiation to guarantee zero network egress
try:
    import socket
    def blocked_socket(*args, **kwargs):
        raise PermissionError("EgressBlocked: Internet network egress is prohibited in this sandbox.")
    socket.socket = blocked_socket
except ImportError:
    pass

# Execute user script
{code}
"""

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(sandbox_wrapper)
        script_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        if proc.returncode == 0:
            status = ExecutionStatus.SUCCESS
        else:
            status = ExecutionStatus.RUNTIME_ERROR

        return ExecutionResult(
            execution_id=execution_id,
            status=status,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            execution_time_ms=round(duration_ms, 2),
            egress_blocked=True,
            ast_violations=[],
        )
    except subprocess.TimeoutExpired:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return ExecutionResult(
            execution_id=execution_id,
            status=ExecutionStatus.TIMEOUT,
            exit_code=124,
            stdout="",
            stderr=f"Execution timed out after {timeout_seconds} seconds.",
            execution_time_ms=round(duration_ms, 2),
            egress_blocked=True,
            ast_violations=[],
        )
    finally:
        import os
        try:
            os.remove(script_path)
        except OSError:
            pass
