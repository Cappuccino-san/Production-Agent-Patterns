"""StateGraph compilation and conditional proxy routing."""

from typing import Literal
from langgraph.graph import END, START, StateGraph
from app.agent.nodes import ProxyNodeExecutor
from app.agent.state import ProxyCommunicationState
from app.models import ActionTaken
from app.sanitizer import MessageSanitizer


def route_sanitized_message(state: ProxyCommunicationState) -> Literal["receiver", "quarantine"]:
    if state["action_taken"] == ActionTaken.BLOCKED_QUARANTINE:
        return "quarantine"
    return "receiver"


def create_proxy_graph(db_path: str, sanitizer: MessageSanitizer):
    executor = ProxyNodeExecutor(db_path, sanitizer)
    builder = StateGraph(ProxyCommunicationState)

    builder.add_node("sender", executor.sender_node)
    builder.add_node("proxy", executor.proxy_intercept_node)
    builder.add_node("receiver", executor.receiver_node)
    builder.add_node("quarantine", executor.quarantine_node)

    builder.add_edge(START, "sender")
    builder.add_edge("sender", "proxy")

    builder.add_conditional_edges(
        "proxy",
        route_sanitized_message,
        {
            "receiver": "receiver",
            "quarantine": "quarantine",
        },
    )

    builder.add_edge("receiver", END)
    builder.add_edge("quarantine", END)

    return builder.compile()
