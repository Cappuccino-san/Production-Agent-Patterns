"""Deterministic mock LLM engine and risk assessment rules for offline execution."""

from typing import Any, Optional


class DeterministicMockLLM:
    """Deterministic evaluation and execution engine for agent actions."""

    CRITICAL_PATTERNS = [
        "drop_database",
        "drop_table",
        "delete_all_records",
        "terminate_ec2",
        "destroy_cluster",
        "format_disk",
        "grant_admin",
        "assume_root",
        "sudo_exec",
        "execute_shell",
        "eval_code",
    ]

    HIGH_PATTERNS = [
        "delete_user",
        "purge_cache",
        "truncate_table",
        "revoke_access",
        "update_all",
        "batch_transfer",
    ]

    MEDIUM_PATTERNS = [
        "update_user",
        "toggle_feature",
        "modify_record",
        "patch_config",
        "resize_disk",
        "update_email",
        "change_role",
    ]

    LOW_PATTERNS = [
        "query_database",
        "get_user",
        "read_logs",
        "list_resources",
        "describe_instance",
        "fetch_metrics",
        "status_check",
        "info_lookup",
        "view_config",
    ]

    def classify_risk(
        self,
        action_type: str,
        description: str,
        payload: dict[str, Any],
        risk_override: Optional[str] = None,
    ) -> str:
        """Classify risk level based on action patterns, payload attributes, or explicit override."""
        if risk_override in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            return risk_override

        action_norm = action_type.lower().replace("-", "_").strip()
        desc_norm = description.lower()

        # Check financial thresholds if applicable
        if "transfer" in action_norm or "amount" in payload:
            amount = payload.get("amount", 0)
            try:
                amt_val = float(amount)
                if amt_val > 5000:
                    return "CRITICAL"
                if amt_val > 1000:
                    return "HIGH"
                if amt_val > 0:
                    return "MEDIUM"
            except (ValueError, TypeError):
                pass

        # Check for critical keywords in action or description
        for pat in self.CRITICAL_PATTERNS:
            if pat in action_norm or pat in desc_norm:
                return "CRITICAL"
        if "destructive" in desc_norm or "drop database" in desc_norm or "rm -rf" in desc_norm:
            return "CRITICAL"

        # Check for high keywords
        for pat in self.HIGH_PATTERNS:
            if pat in action_norm or pat in desc_norm:
                return "HIGH"
        if "delete" in action_norm or "purge" in action_norm or "truncate" in action_norm:
            return "HIGH"

        # Check for medium keywords
        for pat in self.MEDIUM_PATTERNS:
            if pat in action_norm or pat in desc_norm:
                return "MEDIUM"
        if "update" in action_norm or "modify" in action_norm or "patch" in action_norm:
            return "MEDIUM"

        # Check for low keywords
        for pat in self.LOW_PATTERNS:
            if pat in action_norm or pat in desc_norm:
                return "LOW"
        if "read" in action_norm or "get" in action_norm or "query" in action_norm:
            return "LOW"

        # Default fallback for unknown actions is MEDIUM to enforce safety
        return "MEDIUM"

    def formulate_safety_plan(
        self,
        action_type: str,
        risk_level: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate human-readable execution plan with risk mitigations."""
        if risk_level == "LOW":
            return {
                "requires_review": False,
                "summary": f"Read-only execution of {action_type}",
                "impact": "Minimal. No persistent data modification.",
                "mitigation": "Read operations are safe for automated execution.",
            }
        elif risk_level == "MEDIUM":
            return {
                "requires_review": True,
                "summary": f"Modification action: {action_type}",
                "impact": f"Alters target record or config using parameters {list(payload.keys())}",
                "mitigation": "Requires standard operator review before committing changes.",
            }
        elif risk_level == "HIGH":
            return {
                "requires_review": True,
                "summary": f"High-risk action: {action_type}",
                "impact": f"Potential data deletion or broad mutation affecting target {payload.get('target', 'all')}",
                "mitigation": "Mandatory operator authorization with confirmed backup verification.",
            }
        else:  # CRITICAL
            return {
                "requires_review": True,
                "summary": f"CRITICAL destructive action: {action_type}",
                "impact": "Irreversible system or schema alteration. Potential service interruption.",
                "mitigation": "Strict human review gate. Requires senior operator approval.",
            }

    def execute_action(
        self,
        action_type: str,
        payload: dict[str, Any],
        decision_by: Optional[str] = None,
        is_modified: bool = False,
    ) -> dict[str, Any]:
        """Safely execute the requested action and return execution outcome."""
        action_norm = action_type.lower().replace("-", "_").strip()
        auth_note = f" (Authorized by {decision_by})" if decision_by else " (Auto-approved)"
        mod_note = " with reviewer modified parameters" if is_modified else ""

        if any(pat in action_norm for pat in self.LOW_PATTERNS) or "read" in action_norm:
            target = payload.get("table", payload.get("resource", "records"))
            filter_query = payload.get("query", payload.get("id", "all"))
            return {
                "success": True,
                "output": f"Successfully retrieved data from {target} matching '{filter_query}'. Returned 3 simulated records.{auth_note}",
                "records_affected": 0,
                "payload_executed": payload,
            }

        if any(pat in action_norm for pat in self.MEDIUM_PATTERNS) or "update" in action_norm:
            target = payload.get("id", payload.get("target", "record_123"))
            changes = {k: v for k, v in payload.items() if k not in ("id", "target")}
            return {
                "success": True,
                "output": f"Successfully updated {target} with changes: {changes}.{auth_note}{mod_note}",
                "records_affected": 1,
                "payload_executed": payload,
            }

        if any(pat in action_norm for pat in self.CRITICAL_PATTERNS + self.HIGH_PATTERNS):
            target = payload.get("target", payload.get("database", payload.get("table", "specified_resource")))
            return {
                "success": True,
                "output": f"Executed high-consequence action '{action_type}' on target '{target}'. Audit receipt generated.{auth_note}{mod_note}",
                "records_affected": payload.get("limit", 1),
                "payload_executed": payload,
            }

        # Fallback generic execution
        return {
            "success": True,
            "output": f"Action '{action_type}' completed successfully.{auth_note}{mod_note}",
            "records_affected": 1,
            "payload_executed": payload,
        }
