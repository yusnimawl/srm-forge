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
    """Mesh quality is below the configured thresholds.

    `report` carries one of two variants, depending on where the rejection happened:
    - `mesh.quality.MeshQualityReport`, from `check_quality`'s full-mesh sweep (min angle, aspect
      ratio and band min angle over the whole mesh).
    - `mesh.machine.BandRejection`, from `mesh_at_angle`'s own band checks (an inverted raw
      triangle, or a band min angle below threshold, at one specific rotor angle).
    """

    def __init__(self, reasons: list[str], report: object):
        self.reasons = list(reasons)
        self.report = report
        super().__init__("Mesh rejected: " + "; ".join(self.reasons))


class WorkerCrashed(RuntimeError):
    """A pool worker died twice on the same items (spec §8.1)."""

    def __init__(self, items: list[int]):
        self.items = list(items)
        super().__init__(f"worker process crashed twice on items {self.items}")


class MapFailed(RuntimeError):
    """A map violates the failed-point policy (spec §8.1)."""

    def __init__(self, reasons: list[str], n_failed: int):
        self.reasons = list(reasons)
        self.n_failed = n_failed
        super().__init__("Map failed: " + "; ".join(self.reasons))
