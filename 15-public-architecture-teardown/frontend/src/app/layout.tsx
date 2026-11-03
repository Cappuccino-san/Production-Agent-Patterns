import React from "react";

export const metadata = {
  title: "Agentic AI Engineering: 15-Repository Architecture Teardown",
  description: "Enterprise Operations Cockpit & Architectural Deep-Dives for 15 Production-Grade Agent Systems",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0, fontFamily: "system-ui, -apple-system, sans-serif", background: "#0a0d14", color: "#f3f4f6" }}>
        {children}
      </body>
    </html>
  );
}
