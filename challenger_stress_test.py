"""Adversarial Empirical Stress Test Harness for Milestone 1 (01-prompt-to-code-react-agent).

Executes empirical challenges against:
1. SQLite WAL concurrency and busy timeouts
2. FTS5 edge cases (unclosed quotes, boolean operators, unicode, triggers on UPDATE/DELETE)
3. AST validation and sandbox escape/resilience
4. FastAPI endpoints under stress, concurrency, and invalid inputs
"""

import asyncio
import gc
import os
import sqlite3
import sys
import tempfile
import time
from typing import Any

# Ensure 01-prompt-to-code-react-agent is in Python path
REPO_PATH = os.path.abspath("01-prompt-to-code-react-agent")
if REPO_PATH not in sys.path:
    sys.path.insert(0, REPO_PATH)

import aiosqlite
from fastapi.testclient import TestClient
from app.database import (
    check_database_health,
    get_db_connection,
    get_run,
    init_db,
    init_db_sync,
    list_runs,
    save_run,
    search_runs,
)
from app.agent.nodes import execute_tool_node, validate_ast_node, reason_node, finalize_node
from app.agent.graph import create_agent_graph
from app.config import get_settings
from app.main import app

results = []

def record(test_name: str, passed: bool, details: str):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {test_name}: {details}")
    results.append({"name": test_name, "passed": passed, "details": details})


# ==============================================================================
# SUITE 1: SQLite WAL Mode Concurrency & Busy Timeouts
# ==============================================================================
async def test_suite_wal_concurrency():
    print("\n--- Running Suite 1: SQLite WAL Concurrency & Busy Timeouts ---")
    
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "stress_wal.db")
        await init_db(db_path)

        # 1.1 Verify WAL pragmas on get_db_connection
        async with get_db_connection(db_path) as conn:
            cursor = await conn.execute("PRAGMA journal_mode;")
            mode = (await cursor.fetchone())[0]
            cursor = await conn.execute("PRAGMA synchronous;")
            sync = (await cursor.fetchone())[0]
            cursor = await conn.execute("PRAGMA busy_timeout;")
            busy = (await cursor.fetchone())[0]
            cursor = await conn.execute("PRAGMA foreign_keys;")
            fk = (await cursor.fetchone())[0]
        
        pragmas_ok = (mode.lower() == "wal" and sync in (1, "1") and busy == 5000 and fk == 1)
        record("WAL Pragmas via get_db_connection", pragmas_ok, f"mode={mode}, sync={sync}, busy_timeout={busy}, fk={fk}")

        # Persistent database header verification (raw connection without setting pragmas)
        with sqlite3.connect(db_path) as raw_conn:
            raw_mode = raw_conn.execute("PRAGMA journal_mode;").fetchone()[0]
        record("Persistent WAL Journal Mode", raw_mode.lower() == "wal", f"raw_conn mode={raw_mode}")

        # 1.2 High-concurrency simultaneous writes (30 workers x 10 writes = 300 writes)
        async def writer_task(worker_id: int):
            for i in range(10):
                rec = {
                    "id": f"worker_{worker_id}_{i}",
                    "prompt": f"Prompt from worker {worker_id} iteration {i}",
                    "language": "python",
                    "code": f"x = {worker_id} + {i}",
                    "is_valid": True,
                    "output": f"{worker_id + i}",
                    "iterations": 1,
                    "steps": ["step1", "step2"],
                    "status": "completed",
                }
                await save_run(rec, db_path)

        start_time = time.time()
        tasks = [writer_task(w) for w in range(30)]
        try:
            await asyncio.gather(*tasks)
            elapsed = time.time() - start_time
            # Verify count in database
            with sqlite3.connect(db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM runs;").fetchone()[0]
                fts_count = conn.execute("SELECT COUNT(*) FROM runs_fts;").fetchone()[0]
            
            writes_ok = (count == 300 and fts_count == 300)
            record("High-Concurrency 300 Writes", writes_ok, f"Saved {count} runs (fts={fts_count}) across 30 concurrent workers in {elapsed:.2f}s")
        except Exception as e:
            record("High-Concurrency 300 Writes", False, f"Exception: {e}")

        # 1.3 Interleaved simultaneous readers and writers
        read_counts = 0
        read_errors = 0

        async def reader_task():
            nonlocal read_counts, read_errors
            for _ in range(15):
                try:
                    runs = await list_runs(limit=10, db_path=db_path)
                    hits = await search_runs("worker", limit=10, db_path=db_path)
                    read_counts += 1
                except Exception as e:
                    read_errors += 1
                await asyncio.sleep(0.01)

        async def writer_task_interleaved(wid: int):
            for i in range(10):
                rec = {
                    "id": f"interleaved_{wid}_{i}",
                    "prompt": f"Interleaved prompt {wid}-{i}",
                    "language": "python",
                    "code": "print('ok')",
                    "is_valid": True,
                    "output": "ok",
                    "iterations": 1,
                    "steps": [],
                    "status": "completed",
                }
                await save_run(rec, db_path)
                await asyncio.sleep(0.005)

        readers = [reader_task() for _ in range(10)]
        writers = [writer_task_interleaved(w) for w in range(10)]
        start_time = time.time()
        try:
            await asyncio.gather(*readers, *writers)
            interleaved_ok = (read_errors == 0 and read_counts == 150)
            record("Interleaved Readers & Writers", interleaved_ok, f"Reads={read_counts}, ReadErrors={read_errors} in {time.time()-start_time:.2f}s")
        except Exception as e:
            record("Interleaved Readers & Writers", False, f"Exception: {e}")

        # 1.4 Busy Timeout Behavior: Short Lock (holds exclusive lock for 500ms, less than 5000ms timeout)
        def hold_exclusive_lock_sync(duration_sec: float):
            conn = sqlite3.connect(db_path, timeout=10)
            try:
                conn.execute("BEGIN EXCLUSIVE;")
                time.sleep(duration_sec)
                conn.commit()
            finally:
                conn.close()

        loop = asyncio.get_running_loop()
        lock_fut = loop.run_in_executor(None, hold_exclusive_lock_sync, 0.5)
        await asyncio.sleep(0.1) # ensure lock is acquired
        
        test_rec = {
            "id": "busy_timeout_test_1",
            "prompt": "Testing busy timeout wait",
            "language": "python",
            "code": "y = 99",
            "is_valid": True,
            "output": "99",
            "iterations": 1,
            "steps": [],
            "status": "completed",
        }
        start_wait = time.time()
        try:
            await save_run(test_rec, db_path)
            wait_elapsed = time.time() - start_wait
            await lock_fut
            saved = await get_run("busy_timeout_test_1", db_path)
            record("Busy Timeout Wait & Recovery (<5s)", (saved is not None and wait_elapsed >= 0.3), f"Waited {wait_elapsed:.2f}s and succeeded without error")
        except Exception as e:
            record("Busy Timeout Wait & Recovery (<5s)", False, f"Failed with {e}")

        # 1.5 Exceeded Busy Timeout: Verify OperationalError is raised properly when lock duration exceeds busy_timeout
        lock_fut_long = loop.run_in_executor(None, hold_exclusive_lock_sync, 1.0)
        await asyncio.sleep(0.1) # ensure lock is acquired
        
        timed_out_gracefully = False
        start_wait = time.time()
        details = ""
        try:
            async with get_db_connection(db_path) as conn:
                await conn.execute("PRAGMA busy_timeout = 200;")
                await conn.execute("INSERT INTO runs (id, prompt, language, code, is_valid, iterations, steps, status) VALUES ('fail', 'f', 'p', 'c', 1, 1, '[]', 'c');")
                await conn.commit()
        except (sqlite3.OperationalError, aiosqlite.OperationalError) as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                timed_out_gracefully = True
            details = f"OperationalError raised as expected: {e}"
        except Exception as e:
            details = f"Unexpected exception: {type(e)}: {e}"
        finally:
            await lock_fut_long
        record("Busy Timeout Exceeded Lock Detection", timed_out_gracefully, details)

        await asyncio.sleep(0.2)
        gc.collect()


# ==============================================================================
# SUITE 2: FTS5 Edge Cases & Trigger Synchronization
# ==============================================================================
async def test_suite_fts5_edge_cases():
    print("\n--- Running Suite 2: FTS5 Edge Cases & Trigger Synchronization ---")
    
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "fts5_edge.db")
        await init_db(db_path)

        run1 = {
            "id": "run_prime",
            "prompt": "Calculate prime numbers up to 100",
            "language": "python",
            "code": "def is_prime(n):\n    return n > 1\nprint([x for x in range(100) if is_prime(x)])",
            "is_valid": True,
            "output": "[2, 3, 5, 7, ...]",
            "iterations": 1,
            "steps": [],
            "status": "completed",
        }
        run2 = {
            "id": "run_fib",
            "prompt": "Generate Fibonacci sequence",
            "language": "python",
            "code": "def fib(n): return [0, 1]\nprint(fib(10))",
            "is_valid": True,
            "output": "[0, 1, 1, 2, 3, 5, 8]",
            "iterations": 1,
            "steps": [],
            "status": "completed",
        }
        await save_run(run1, db_path)
        await save_run(run2, db_path)

        adversarial_queries = [
            ("Unclosed double quote", '"prime numbers'),
            ("Unclosed single quote", "'Fibonacci"),
            ("Multiple unclosed quotes", '"""""'),
            ("Boolean keyword AND alone", "AND"),
            ("Boolean keyword OR alone", "OR"),
            ("Boolean keyword NOT alone", "NOT"),
            ("Boolean combined syntax", "prime AND NOT fibonacci"),
            ("FTS5 column filter syntax", "prompt:prime"),
            ("Asterisk wildcard spam", "***???***"),
            ("SQL injection attempt", "'; DROP TABLE runs; --"),
            ("Regex characters", "([a-zA-Z0-9]+.*)"),
            ("HTML and script tags", "<script>alert('xss')</script>"),
            ("Unicode emojis", "🚀 💻 🔥"),
            ("Non-Latin scripts", "вычислить простые числа"),
            ("Chinese characters", "计算素数"),
            ("Punctuation only", "!@#$%^&*()_+-=[]{}|;':,./<>?"),
            ("Massive whitespace", "      \t\n   \r\n     "),
            ("Super long string (5000 chars)", "word " * 1000),
        ]

        fts_robust = True
        failed_cases = []
        for label, q in adversarial_queries:
            try:
                res = await search_runs(query=q, limit=10, db_path=db_path)
                if not isinstance(res, list):
                    fts_robust = False
                    failed_cases.append(f"{label} (not a list)")
            except Exception as exc:
                fts_robust = False
                failed_cases.append(f"{label} raised {type(exc).__name__}: {exc}")

        record("FTS5 Adversarial Query Robustness", fts_robust, 
               "All 18 adversarial queries handled safely without unhandled exceptions" if fts_robust else f"Failures: {failed_cases}")

        # 2.2 Trigger Synchronization on UPDATE
        run1_updated = dict(run1)
        run1_updated["prompt"] = "Implement quicksort algorithm in Python"
        run1_updated["code"] = "def quicksort(arr): return arr"
        run1_updated["output"] = "sorted list"
        await save_run(run1_updated, db_path)

        hits_new = await search_runs("quicksort", limit=10, db_path=db_path)
        hits_old = await search_runs("prime", limit=10, db_path=db_path)
        
        update_sync_ok = (len(hits_new) == 1 and hits_new[0]["id"] == "run_prime" and len(hits_old) == 0)
        record("FTS5 AFTER UPDATE Trigger Sync", update_sync_ok, 
               f"New query hits={len(hits_new)}, Old query hits={len(hits_old)}")

        # 2.3 Trigger Synchronization on DELETE
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM runs WHERE id = 'run_fib';")
            conn.commit()

        hits_deleted = await search_runs("Fibonacci", limit=10, db_path=db_path)
        delete_sync_ok = (len(hits_deleted) == 0)
        record("FTS5 AFTER DELETE Trigger Sync", delete_sync_ok, f"Hits for deleted record={len(hits_deleted)}")

        # 2.4 External content table row count consistency
        with sqlite3.connect(db_path) as conn:
            runs_count = conn.execute("SELECT count(*) FROM runs;").fetchone()[0]
            fts_count = conn.execute("SELECT count(*) FROM runs_fts;").fetchone()[0]
        record("FTS5 External Content Table Consistency", runs_count == fts_count, f"runs={runs_count}, runs_fts={fts_count}")

        await asyncio.sleep(0.2)
        gc.collect()


# ==============================================================================
# SUITE 3: AST Validation, Sandbox Security, & Graph State Machine
# ==============================================================================
def test_suite_agent_sandbox_and_graph():
    print("\n--- Running Suite 3: AST Validation, Sandbox Security & Graph ---")

    # 3.1 AST validation edge cases
    malformed_state = {
        "prompt": "broken code",
        "language": "python",
        "code": "def func(a, b:\n    return a + b",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    ast_res = validate_ast_node(malformed_state)
    record("AST Syntax Error Detection", ast_res["is_valid"] is False and "SyntaxError" in ast_res["error"], f"error={ast_res.get('error')}")

    empty_state = dict(malformed_state, code="")
    ast_empty = validate_ast_node(empty_state)
    record("AST Empty Code Handling", ast_empty["is_valid"] is True, "Valid AST module with 0 statements")

    js_state = dict(malformed_state, language="javascript", code="console.log('hello');")
    ast_js = validate_ast_node(js_state)
    record("AST Non-Python Language Passthrough", ast_js["is_valid"] is True, f"steps={ast_js.get('steps')}")

    # 3.2 Sandbox Standard Isolation: dangerous imports and filesystem writes blocked
    standard_attacks = [
        ("Import os.system", "import os; os.system('echo hacked')"),
        ("Import subprocess", "import subprocess; subprocess.run(['echo', 'hacked'])"),
        ("File open() write", "with open('sandbox_escape.txt', 'w') as f: f.write('escape')"),
        ("Builtin __import__", "__import__('sys').exit(1)"),
    ]

    sandbox_secure = True
    escape_reasons = []
    for name, attack_code in standard_attacks:
        state = {
            "prompt": name,
            "language": "python",
            "code": attack_code,
            "is_valid": True,
            "output": None,
            "steps": [],
            "iterations": 1,
            "max_iterations": 5,
            "completed": False,
            "error": None,
        }
        res = execute_tool_node(state)
        if res["error"] is None:
            sandbox_secure = False
            escape_reasons.append(f"{name} executed without error: output={res.get('output')}")
    
    file_created = os.path.exists("sandbox_escape.txt")
    if file_created:
        sandbox_secure = False
        escape_reasons.append("File 'sandbox_escape.txt' was created on filesystem!")
        try:
            os.remove("sandbox_escape.txt")
        except Exception:
            pass

    record("Sandbox Standard Attack Isolation", sandbox_secure, 
           "Standard attacks (import, open, exec) blocked by restricted builtins" if sandbox_secure else f"Breaches: {escape_reasons}")

    # 3.3 Graph Max Iteration Exhaustion with persistent syntax error
    class AlwaysBrokenLLM:
        def reason_and_generate(self, prompt, iteration, error=None):
            return "Thought: broken", "def broken(\n"
    
    broken_graph = create_agent_graph(llm=AlwaysBrokenLLM())
    init_state = {
        "prompt": "Persistent error test",
        "language": "python",
        "code": "",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 0,
        "max_iterations": 3,
        "completed": False,
        "error": None,
    }
    final_broken = broken_graph.invoke(init_state)
    exhaustion_ok = (final_broken["iterations"] == 3 and final_broken["completed"] is True and final_broken["is_valid"] is False)
    record("Graph Max Iterations Termination", exhaustion_ok, 
           f"iterations={final_broken.get('iterations')}, completed={final_broken.get('completed')}, is_valid={final_broken.get('is_valid')}")


# ==============================================================================
# SUITE 4: FastAPI TestClient Endpoint Stress & Contract Verification
# ==============================================================================
def test_suite_api_endpoints():
    print("\n--- Running Suite 4: FastAPI Endpoint Stress & Contracts ---")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    os.environ["DATABASE_PATH"] = db_path
    get_settings.cache_clear()

    try:
        with TestClient(app) as client:
            # 4.1 Health Probes
            live_resp = client.get("/health/live")
            ready_resp = client.get("/health/ready")
            health_resp = client.get("/health")
            probes_ok = (live_resp.status_code == 200 and ready_resp.status_code == 200 and health_resp.status_code == 200)
            record("Health Probes (live, ready, root)", probes_ok, 
                   f"live={live_resp.status_code}, ready={ready_resp.status_code}, health={health_resp.status_code}")

            # 4.2 Malformed payloads to POST /api/v1/agent/run
            # Extra fields forbidden
            res_extra = client.post("/api/v1/agent/run", json={"prompt": "test", "extra_bad_field": 123})
            record("RFC 7807 Extra Fields Forbidden", res_extra.status_code == 422, f"status={res_extra.status_code}")

            # Empty prompt forbidden
            res_empty = client.post("/api/v1/agent/run", json={"prompt": ""})
            record("Empty Prompt 422 Rejection", res_empty.status_code == 422, f"status={res_empty.status_code}")

            # Whitespace prompt rejected due to strip + min_length
            res_ws = client.post("/api/v1/agent/run", json={"prompt": "    "})
            record("Whitespace-Only Prompt Rejection", res_ws.status_code == 422, f"status={res_ws.status_code}")

            # Negative max_iterations rejected
            res_neg_iter = client.post("/api/v1/agent/run", json={"prompt": "valid prompt", "max_iterations": -1})
            record("Negative max_iterations Rejection", res_neg_iter.status_code == 422, f"status={res_neg_iter.status_code}")

            # Max iterations exceeded (>20) rejected
            res_over_iter = client.post("/api/v1/agent/run", json={"prompt": "valid prompt", "max_iterations": 50})
            record("Excessive max_iterations (>20) Rejection", res_over_iter.status_code == 422, f"status={res_over_iter.status_code}")

            # 4.3 Successful run execution and query
            res_run = client.post("/api/v1/agent/run", json={"prompt": "Compute factorial of 5"})
            assert res_run.status_code == 200
            run_data = res_run.json()
            run_id = run_data["run_id"]
            record("Successful Agent Run Execution", run_data["is_valid"] is True and run_data["status"] == "completed", 
                   f"run_id={run_id}, output={run_data.get('output')}")

            # 4.4 Retrieve run by ID
            res_get = client.get(f"/api/v1/agent/runs/{run_id}")
            record("Retrieve Run by ID", res_get.status_code == 200 and res_get.json()["run_id"] == run_id, f"status={res_get.status_code}")

            # 4.5 404 on nonexistent run ID (RFC 7807 Problem Details)
            res_404 = client.get("/api/v1/agent/runs/nonexistent_run_99999")
            is_rfc7807 = (
                res_404.status_code == 404 
                and "type" in res_404.json() 
                and "title" in res_404.json() 
                and "status" in res_404.json()
            )
            record("RFC 7807 404 Problem Details", is_rfc7807, f"body={res_404.json()}")

            # 4.6 Search endpoint with multiple queries
            res_search = client.get("/api/v1/agent/runs/search?q=factorial")
            record("Search API Endpoint (q=factorial)", res_search.status_code == 200 and len(res_search.json()) >= 1, 
                   f"hits={len(res_search.json())}")

            res_search_empty = client.get("/api/v1/agent/runs/search?q=xyznonexistentterm999")
            record("Search API Endpoint Zero Hits Graceful", res_search_empty.status_code == 200 and len(res_search_empty.json()) == 0, 
                   f"hits={len(res_search_empty.json())}")

            # 4.7 Rapid sequential execution
            seq_ok = True
            for i in range(5):
                r = client.post("/api/v1/agent/run", json={"prompt": f"Prompt number {i} for fibonacci"})
                if r.status_code != 200:
                    seq_ok = False
                    break
            record("Sequential Agent Execution (5 runs)", seq_ok, "5 runs executed and saved successfully")

            # Check total runs in database
            res_all = client.get("/api/v1/agent/runs?limit=50")
            record("List Runs API Count", len(res_all.json()) == 6, f"Returned {len(res_all.json())} runs")

    finally:
        get_settings.cache_clear()
        for ext in ["", "-wal", "-shm"]:
            p = db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
async def main():
    print("=" * 80)
    print("EMPIRICAL CHALLENGER STRESS HARNESS: 01-prompt-to-code-react-agent")
    print("=" * 80)

    await test_suite_wal_concurrency()
    await test_suite_fts5_edge_cases()
    test_suite_agent_sandbox_and_graph()
    test_suite_api_endpoints()

    print("\n" + "=" * 80)
    print("CHALLENGE SUMMARY")
    print("=" * 80)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = sum(1 for r in results if not r["passed"])
    print(f"Total Tests Run: {len(results)}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    
    if failed_count > 0:
        print("\nFAILED CHALLENGES:")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['name']}: {r['details']}")
        sys.exit(1)
    else:
        print("\nALL ADVERSARIAL CHALLENGES PASSED EMPIRICALLY WITH ZERO FAILURES.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
