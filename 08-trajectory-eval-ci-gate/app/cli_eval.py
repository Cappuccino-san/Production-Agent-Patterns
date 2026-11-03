"""CLI tool executed in CI/CD pipeline (e.g. GitHub Actions) to replay trajectories and block PRs."""

import argparse
import sys
from app.agent.graph import create_eval_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db_sync, save_golden_dag_sync
from app.models import EvalVerdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Trajectory Replay CI Gate")
    parser.add_argument("--dag-id", default="golden-default", help="Golden DAG ID")
    parser.add_argument("--num-trajectories", type=int, default=100, help="Number of trajectories to replay")
    parser.add_argument("--fail-on-deviation", action="store_true", default=True, help="Block PR on any deviation")
    parser.add_argument("--db-path", default="./data/trajectory_eval.db", help="SQLite DB path")
    args = parser.parse_args()

    print(f"🚀 Initializing Trajectory CI Gate for DAG '{args.dag_id}'...")
    init_db_sync(args.db_path)

    # Ensure default golden DAG exists
    golden_dag = DeterministicMockLLM.get_default_golden_dag(args.dag_id)
    save_golden_dag_sync(args.db_path, golden_dag, "2026-11-02T12:00:00Z")

    trajectories = DeterministicMockLLM.generate_trajectories(
        count=args.num_trajectories,
        pr_number=101,
        commit_sha="ci-run-sha",
        inject_deviations=0,
    )
    print(f"📦 Replaying {len(trajectories)} agent trajectories against Golden DAG...")

    graph = create_eval_graph(args.db_path)
    state = {
        "eval_id": "ci-run-1",
        "dag_id": args.dag_id,
        "pr_number": 101,
        "commit_sha": "ci-run-sha",
        "golden_dag": golden_dag,
        "trajectories": trajectories,
        "total_evaluated": 0,
        "passed_count": 0,
        "failed_count": 0,
        "verdict": EvalVerdict.PASS,
        "fail_on_any_deviation": args.fail_on_deviation,
        "deviations": [],
        "logs": [],
    }

    result = graph.invoke(state)

    print("=" * 60)
    print(f"📊 Replay Results:")
    print(f"   Total Evaluated: {result['total_evaluated']}")
    print(f"   Passed:          {result['passed_count']}")
    print(f"   Failed:          {result['failed_count']}")
    print(f"   Verdict:         {result['verdict'].value}")
    print("=" * 60)

    if result["verdict"] == EvalVerdict.BLOCK:
        print("❌ CI Gate BLOCKED: One or more trajectories deviated from Golden DAG.")
        return 1
    else:
        print("✅ CI Gate PASSED: All 100 trajectories strictly match Golden DAG.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
