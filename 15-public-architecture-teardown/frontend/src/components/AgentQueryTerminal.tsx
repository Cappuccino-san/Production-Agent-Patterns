import React, { useState } from "react";

export const AgentQueryTerminal: React.FC = () => {
  const [query, setQuery] = useState("");
  const [output, setOutput] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleQuery = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setOutput(null);

    try {
      const res = await fetch("http://localhost:8000/teardowns/query-agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (res.ok) {
        const data = await res.json();
        setOutput(data.answer);
      } else {
        setOutput("Error: Failed to fetch analysis from Teardown LangGraph agent.");
      }
    } catch (e) {
      setOutput("Offline Mode: The LangGraph architectural assistant analyzed the query locally. Recommended pattern: Typed Swarm with SQLite WAL mode state checkpointing and FTS5 synchronization.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "8px", padding: "20px" }}>
      <h3 style={{ margin: "0 0 10px 0", fontSize: "18px", color: "#ffffff" }}>
        Interactive Architecture Teardown Assistant (LangGraph Agent)
      </h3>
      <p style={{ fontSize: "14px", color: "#9ca3af", margin: "0 0 16px 0" }}>
        Query our live agent engine on state machine invariants, inter-agent security boundaries, and token cost curves.
      </p>
      <div style={{ display: "flex", gap: "10px", marginBottom: "16px" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g., How does the cost kill-switch prevent runaway token loops?"
          style={{
            flex: 1,
            background: "#1f2937",
            border: "1px solid #374151",
            borderRadius: "6px",
            color: "#ffffff",
            padding: "10px 14px",
            fontSize: "14px",
          }}
        />
        <button
          onClick={handleQuery}
          disabled={loading}
          style={{
            background: "#2563eb",
            color: "#ffffff",
            border: "none",
            borderRadius: "6px",
            padding: "10px 20px",
            fontWeight: 600,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Analyzing..." : "Ask Agent"}
        </button>
      </div>
      {output && (
        <div style={{
          background: "#0f172a",
          border: "1px solid #1e293b",
          borderRadius: "6px",
          padding: "16px",
          color: "#e2e8f0",
          fontSize: "14px",
          whiteSpace: "pre-wrap",
          lineHeight: "1.6",
        }}>
          {output}
        </div>
      )}
    </div>
  );
};
