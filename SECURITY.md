# Security Policy

## Supported Versions

Production Agent Patterns (PAP-15) maintains security patches across active architecture patterns.

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We prioritize agentic safety, sandboxing isolation, and prompt injection defense.

If you discover an architectural vulnerability—such as:
- **Sandbox Boundary Escapes** (bypassing AST checks or socket neutralization in `11-sandboxed-code-executor`)
- **Prompt Injection Bypasses** (circumventing regex or scoring thresholds in `10-inter-agent-sanitization-proxy`)
- **Budget Runaway Flaws** (bypassing step cost limits in `12-cost-kill-switch-middleware`)
- **State Poisoning** (corrupting SQLite WAL journals or FTS5 sync triggers)

Please do **NOT** open a public issue. Instead, submit a security advisory via [GitHub Security Advisories](https://github.com/Cappuccino-san/Production-Agent-Patterns/security/advisories) or contact the maintainers directly.

All verified vulnerabilities will be acknowledged and remediated with patched regression tests.
