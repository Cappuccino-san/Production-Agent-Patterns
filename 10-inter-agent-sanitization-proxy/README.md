# Inter-Agent Sanitization Proxy

A security middleware and proxy architecture that intercepts communication between autonomous agents, strips adversarial instructions, removes data exfiltration vectors, and prevents cross-agent prompt injection attacks in multi-agent swarms.

---

## 1. Architectural Overview

In multi-agent architectures, an untrusted or compromised agent (e.g. an internet-scraping researcher or untrusted plugin) can inject hidden instructions into its output packet that hijack downstream privileged agents (e.g. a database executor or code interpreter). This proxy eliminates cross-agent contagion:
- **Protocol Interception**: All inter-agent message packets pass through the `SanitizationProxyNode` before reaching recipient mailboxes.
- **Pattern & Delimiter Scrubbing**: Automatically detects and replaces prompt injection payloads (e.g., `<system>` tags, `ignore previous instructions`, `curl/wget` exfiltration attempts).
- **Security Quarantine**: Messages with critical injection signatures or risk scores above 75.0 are quarantined; recipient delivery is immediately blocked.
- **Enterprise SQLite WAL & FTS5**: All raw payloads, scrubbed outputs, and detection audits are persisted under WAL mode and indexed for BM25 forensic search.

```mermaid
flowchart TD
    Sender[Sender Agent] --> Packet[MessagePacket]
    Packet --> Proxy[Sanitization Proxy Middleware]

    subgraph Security_Inspection ["Heuristic & Regex Inspection"]
        Proxy --> CheckOverride{"Check: System Prompt Override?"}
        Proxy --> CheckEscape{"Check: Delimiter / Tag Escape?"}
        Proxy --> CheckExfil{"Check: Data Exfiltration (curl/fetch)?"}
        Proxy --> CheckDestruct{"Check: Destructive Tool Hijack?"}
    end

    subgraph Decision_Gate ["Security Policy Enforcement"]
        CheckOverride --> ScoreCalc[Compute Composite Risk Score]
        CheckEscape --> ScoreCalc
        CheckExfil --> ScoreCalc
        CheckDestruct --> ScoreCalc

        ScoreCalc --> Decision{"Risk Score &ge; 75.0 or Critical?"}
        Decision -->|Yes| Quarantine[Security Quarantine: BLOCK Delivery]
        Decision -->|No (Scrubbed)| Scrub[Strip Injections & Deliver to Recipient]
        Decision -->|Clean| Deliver[Direct Safe Delivery to Recipient]
    end

    subgraph Storage_Layer ["SQLite WAL & FTS5"]
        Proxy -.-> InterceptTable[(intercepted_messages)]
        InterceptTable ===>|Automated Triggers| FTS5[(intercepted_messages_fts BM25)]
    end
```

---

## 2. Monitored Security Attack Vectors

| Rule ID | Attack Vector | Sanitization Action |
|---|---|---|
| `RULE_SYSTEM_OVERRIDE` | `ignore all previous instructions`, `system prompt reveal` | Stripped / Quarantined |
| `RULE_DELIMITER_ESCAPE` | `<system>`, `<\|im_start\|>`, `[ADMIN_OVERRIDE]`, `{{config}}` | Stripped / Quarantined |
| `RULE_JAILBREAK_PERSONA` | `you are now DAN / unrestricted` | Stripped / Quarantined |
| `RULE_DATA_EXFILTRATION` | `curl -X POST`, `fetch()`, `send passwords to` | Stripped |
| `RULE_DESTRUCTIVE_COMMAND` | `rm -rf /`, `drop table`, `__import__('os').system` | Blocked & Quarantined |

---

## 3. SQLite WAL Mode and FTS5 Sync

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TRIGGER intercepted_messages_ai AFTER INSERT ON intercepted_messages BEGIN
    INSERT INTO intercepted_messages_fts(rowid, message_id, sender_agent, receiver_agent, action_taken, raw_content, sanitized_content)
    VALUES (new.rowid, new.message_id, new.sender_agent, new.receiver_agent, new.action_taken, new.raw_content, new.sanitized_content);
END;
```

---

## 4. REST API Contract

| Method | Path | Description |
|---|---|---|
| `POST` | `/proxy/send` | Transmits message through proxy middleware with security evaluation |
| `GET` | `/proxy/messages/{message_id}` | Retrieves intercepted message audit and rule match details |
| `GET` | `/proxy/search?q={query}` | BM25 search across intercepted messages via SQLite FTS5 |
| `GET` | `/health/live` | Process liveness check |
| `GET` | `/health/ready` | SQLite readiness check |

---

## 5. Local Setup & Testing

### Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running Test Suite
```bash
python -m pytest tests/ -v
```

---

## 6. Docker & AWS EC2 Deployment

```bash
docker-compose up -d --build
```
