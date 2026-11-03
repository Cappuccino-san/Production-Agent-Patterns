import React from "react";

export interface BenchmarkRow {
  repository_id: string;
  architecture_pattern: string;
  avg_latency_ms: number;
  cost_per_1k_tasks_usd: number;
  resilience_score: number;
}

export const BenchmarkChart: React.FC<{ rows: BenchmarkRow[] }> = ({ rows }) => {
  return (
    <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "8px", padding: "20px" }}>
      <h3 style={{ margin: "0 0 16px 0", fontSize: "18px", color: "#ffffff" }}>
        Production Efficiency & Cost-per-Task Benchmarks (15 Repositories)
      </h3>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px", textAlign: "left" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #374151", color: "#9ca3af" }}>
              <th style={{ padding: "10px" }}>Repo #</th>
              <th style={{ padding: "10px" }}>Architecture Pattern</th>
              <th style={{ padding: "10px" }}>Latency (ms)</th>
              <th style={{ padding: "10px" }}>Cost / 1k Tasks ($)</th>
              <th style={{ padding: "10px" }}>Resilience Rating</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #1f2937", color: "#d1d5db" }}>
                <td style={{ padding: "10px", fontWeight: 600, color: "#60a5fa" }}>{r.repository_id}</td>
                <td style={{ padding: "10px" }}>{r.architecture_pattern}</td>
                <td style={{ padding: "10px" }}>{r.avg_latency_ms} ms</td>
                <td style={{ padding: "10px", color: "#34d399", fontWeight: 600 }}>${r.cost_per_1k_tasks_usd.toFixed(2)}</td>
                <td style={{ padding: "10px" }}>
                  <span style={{
                    display: "inline-block",
                    padding: "2px 8px",
                    borderRadius: "4px",
                    background: r.resilience_score >= 95 ? "#064e3b" : "#1e3a8a",
                    color: "#a7f3d0",
                    fontSize: "12px",
                  }}>
                    {r.resilience_score}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
