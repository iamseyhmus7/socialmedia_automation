from __future__ import annotations

from src.domain.state import WorkflowState


class WorkflowRouter:
    def route_after_feedback(self, state: WorkflowState) -> str:
        status = state.get("status")
        if status == "needs_changes":
            return "apply_feedback_actions"
        if status == "clarify":
            return "ask_for_approval"
        return "end"


def route_after_feedback(state: WorkflowState) -> str:
    return WorkflowRouter().route_after_feedback(state)
