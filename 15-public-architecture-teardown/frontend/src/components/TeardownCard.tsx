import React from "react";

export interface TeardownArticle {
  slug: string;
  title: string;
  category: string;
  summary: string;
  published_at: string;
  read_time_minutes: number;
  key_findings: string[];
}

export const TeardownCard: React.FC<{ article: TeardownArticle; onSelect: (slug: string) => void }> = ({
  article,
  onSelect,
}) => {
  return (
    <div
      onClick={() => onSelect(article.slug)}
      style={{
        background: "#111827",
        border: "1px solid #1f2937",
        borderRadius: "8px",
        padding: "20px",
        cursor: "pointer",
        transition: "transform 0.15s ease, border-color 0.15s ease",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <span style={{ fontSize: "12px", color: "#60a5fa", textTransform: "uppercase", fontWeight: 600 }}>
          {article.category}
        </span>
        <span style={{ fontSize: "12px", color: "#9ca3af" }}>{article.read_time_minutes} min read</span>
      </div>
      <h3 style={{ fontSize: "18px", fontWeight: 700, margin: "0 0 10px 0", color: "#ffffff" }}>
        {article.title}
      </h3>
      <p style={{ fontSize: "14px", color: "#9ca3af", lineHeight: "1.5", marginBottom: "14px" }}>
        {article.summary}
      </p>
      <div>
        <h4 style={{ fontSize: "12px", color: "#d1d5db", margin: "0 0 6px 0" }}>Key Findings:</h4>
        <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "13px", color: "#9ca3af" }}>
          {article.key_findings.map((item, idx) => (
            <li key={idx} style={{ marginBottom: "4px" }}>{item}</li>
          ))}
        </ul>
      </div>
    </div>
  );
};
