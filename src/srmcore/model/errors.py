"""Error types shared by all layers."""
from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    parameter: str
    rule: str
    message: str
    severity: Severity = "error"


class InputError(ValueError):
    """A design violates a rule. Raised before any meshing."""

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = list(issues)
        lines = [f"{i.parameter}: [{i.rule}] {i.message}" for i in self.issues if i.severity == "error"]
        super().__init__("Invalid design:\n" + "\n".join(lines))


class MeshRejected(RuntimeError):
    """Mesh quality is below the configured thresholds."""

    def __init__(self, reasons: list[str], report: object):
        self.reasons = list(reasons)
        self.report = report
        super().__init__("Mesh rejected: " + "; ".join(self.reasons))
