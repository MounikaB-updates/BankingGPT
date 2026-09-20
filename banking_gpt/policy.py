from __future__ import annotations

import re
from urllib.parse import urlparse

from banking_gpt.models import ArtifactStep, AutomationPolicy, ProposedAction


class PolicyViolation(RuntimeError):
    pass


class PolicyApprovalRequired(RuntimeError):
    pass


class PolicyEngine:
    def __init__(self, policy: AutomationPolicy) -> None:
        self.policy = policy

    def check_url(self, url: str) -> None:
        hostname = urlparse(url).hostname
        if hostname not in self.policy.allowed_hosts:
            raise PolicyViolation(f"Host is not allowed: {hostname}")

    def check_action(self, action: ProposedAction) -> None:
        if action.action not in self.policy.allowed_actions:
            raise PolicyViolation(f"Action is not allowed: {action.action}")

        if action.action.value == "navigate" and action.value:
            self.check_url(action.value)

    def check_step(self, step: ArtifactStep) -> None:
        if step.action not in self.policy.allowed_actions:
            raise PolicyViolation(f"Action is not allowed: {step.action}")
        if step.risk in self.policy.require_approval_for:
            raise PolicyApprovalRequired(f"Step requires human approval: {step.id}")
        if step.action.value == "navigate" and step.value:
            self.check_url(step.value)


_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|token|secret|api[_ -]?key)\s*[:=]\s*\S+"),
    re.compile(r"\b\d{9}\b"),
]


def redact(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted

