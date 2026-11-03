"""Inter-Agent message sanitization engine stripping injection vectors and computing risk scores."""

import re
from typing import Tuple
from app.models import ActionTaken, SanitizationResult


INJECTION_RULES = [
    {
        "id": "RULE_SYSTEM_OVERRIDE",
        "name": "System Prompt Override Attempt",
        "pattern": re.compile(r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+system\s+prompt|forget\s+all\s+rules)"),
        "weight": 85.0,
        "critical": True,
    },
    {
        "id": "RULE_DELIMITER_ESCAPE",
        "name": "Delimiter Escape / Tag Injection",
        "pattern": re.compile(r"(<system>|</system>|<\|im_start\|>|<\|im_end\|>|\[ADMIN_OVERRIDE\]|\[SYSTEM_DIRECTIVE\]|\{\{config\.\w+\}\})"),
        "weight": 80.0,
        "critical": True,
    },
    {
        "id": "RULE_JAILBREAK_PERSONA",
        "name": "Jailbreak / Persona Hijack",
        "pattern": re.compile(r"(?i)(you\s+are\s+now\s+(DAN|unrestricted|jailbroken|evil\s+agent)|act\s+without\s+any\s+ethics)"),
        "weight": 75.0,
        "critical": True,
    },
    {
        "id": "RULE_DATA_EXFILTRATION",
        "name": "Data Exfiltration / Egress Pattern",
        "pattern": re.compile(r"(?i)(curl\s+-[XF]|fetch\(|wget\s+https?://|send\s+(credentials|tokens|secrets|passwords)\s+to)"),
        "weight": 70.0,
        "critical": False,
    },
    {
        "id": "RULE_DESTRUCTIVE_COMMAND",
        "name": "Destructive Command / Tool Hijack",
        "pattern": re.compile(r"(?i)(rm\s+-rf\s+/|drop\s+table|drop\s+database|__import__\(['\"]os['\"]\)\.system)"),
        "weight": 90.0,
        "critical": True,
    },
]


class MessageSanitizer:
    def __init__(self, quarantine_threshold: float = 75.0, block_critical: bool = True) -> None:
        self.quarantine_threshold = quarantine_threshold
        self.block_critical = block_critical

    def sanitize(
        self,
        message_id: str,
        sender_agent: str,
        receiver_agent: str,
        content: str,
    ) -> SanitizationResult:
        matched_rules = []
        highest_weight = 0.0
        has_critical = False
        scrubbed_content = content

        for rule in INJECTION_RULES:
            pattern = rule["pattern"]
            if pattern.search(scrubbed_content):
                matched_rules.append(rule["name"])
                if rule["weight"] > highest_weight:
                    highest_weight = rule["weight"]
                if rule["critical"]:
                    has_critical = True
                # Strip the malicious instruction
                scrubbed_content = pattern.sub("[STRIPPED_SECURITY_INJECTION]", scrubbed_content)

        risk_score = min(100.0, highest_weight)

        if not matched_rules:
            action = ActionTaken.PASSED
            is_clean = True
            final_content = content
        else:
            is_clean = False
            # If critical or exceeds threshold, quarantine message completely
            if (self.block_critical and has_critical) or risk_score >= self.quarantine_threshold:
                action = ActionTaken.BLOCKED_QUARANTINE
                final_content = "[MESSAGE_BLOCKED_BY_SANITIZATION_PROXY: CRITICAL_INJECTION_DETECTED]"
            else:
                action = ActionTaken.SANITIZED
                final_content = scrubbed_content.strip()

        return SanitizationResult(
            message_id=message_id,
            sender_agent=sender_agent,
            receiver_agent=receiver_agent,
            is_clean=is_clean,
            sanitized_content=final_content,
            risk_score=risk_score,
            action_taken=action,
            matched_rules=matched_rules,
        )
