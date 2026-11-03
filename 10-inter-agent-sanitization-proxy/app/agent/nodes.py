"""LangGraph node handlers for proxy message interception and routing."""

from typing import Any
from app.agent.state import ProxyCommunicationState
from app.database import save_intercepted_message_sync
from app.models import ActionTaken
from app.sanitizer import MessageSanitizer


class ProxyNodeExecutor:
    def __init__(self, db_path: str, sanitizer: MessageSanitizer) -> None:
        self.db_path = db_path
        self.sanitizer = sanitizer

    def sender_node(self, state: ProxyCommunicationState) -> dict[str, Any]:
        """Sender agent: constructs message packet."""
        return {
            "delivered": False,
            "audit_trail": [{"event": "MESSAGE_TRANSMITTED_BY_SENDER", "agent": state["sender_agent"]}],
        }

    def proxy_intercept_node(self, state: ProxyCommunicationState) -> dict[str, Any]:
        """Proxy middleware: intercepts message, scans for prompt injection, scrubs or quarantines."""
        message_id = state["message_id"]
        sender = state["sender_agent"]
        receiver = state["receiver_agent"]
        raw = state["raw_content"]

        result = self.sanitizer.sanitize(
            message_id=message_id,
            sender_agent=sender,
            receiver_agent=receiver,
            content=raw,
        )

        # Persist to SQLite WAL
        save_intercepted_message_sync(self.db_path, raw, result)

        return {
            "sanitized_content": result.sanitized_content,
            "action_taken": result.action_taken,
            "risk_score": result.risk_score,
            "matched_rules": result.matched_rules,
            "audit_trail": [{
                "event": "PROXY_INTERCEPTED",
                "action": result.action_taken.value,
                "risk_score": result.risk_score,
                "rules": result.matched_rules,
            }],
        }

    def receiver_node(self, state: ProxyCommunicationState) -> dict[str, Any]:
        """Receiver agent: consumes sanitized, safe message."""
        return {
            "delivered": True,
            "audit_trail": [{"event": "MESSAGE_SAFELY_DELIVERED", "agent": state["receiver_agent"]}],
        }

    def quarantine_node(self, state: ProxyCommunicationState) -> dict[str, Any]:
        """Security quarantine: isolates dangerous injection attempt, blocking delivery."""
        return {
            "delivered": False,
            "audit_trail": [{
                "event": "MESSAGE_QUARANTINED_ALERT_EMITTED",
                "reason": "Critical prompt injection detected",
            }],
        }
