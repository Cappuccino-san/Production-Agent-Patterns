"""Deterministic Mock LLM for Async HITL Slack Gate."""

from typing import Any
from app.models import ActionType


class DeterministicMockLLM:
    """Evaluates risk and drafts Slack Block Kit interactive message."""

    def evaluate_risk(self, action_type: ActionType, payload: dict[str, Any]) -> float:
        if action_type == ActionType.MASS_REFUND:
            amount = payload.get("total_usd", 0)
            return 95.0 if amount > 5000 else 60.0
        elif action_type == ActionType.DATABASE_MIGRATION:
            return 85.0
        elif action_type == ActionType.DEPLOY_PRODUCTION:
            return 75.0
        return 50.0

    def generate_slack_blocks(self, action_id: str, action_type: ActionType, risk_score: float, description: str) -> dict[str, Any]:
        return {
            "channel": "#prod-gatekeepers",
            "text": f"🚨 High-Stakes Action Approval Required: {action_type.value}",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "High-Stakes Gate: Human Approval Required"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Action ID:*\n`{action_id}`"},
                        {"type": "mrkdwn", "text": f"*Risk Score:*\n`{risk_score}/100`"},
                        {"type": "mrkdwn", "text": f"*Type:*\n`{action_type.value}`"},
                        {"type": "mrkdwn", "text": "*Timeout Window:*\n72 Hours (3 Days)"},
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Description:*\n{description}"},
                },
                {
                    "type": "actions",
                    "block_id": f"hitl_actions_{action_id}",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve Action"},
                            "style": "primary",
                            "value": f"approve:{action_id}",
                            "action_id": "btn_approve",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Reject Action"},
                            "style": "danger",
                            "value": f"reject:{action_id}",
                            "action_id": "btn_reject",
                        },
                    ],
                },
            ],
        }
