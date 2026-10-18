"""R3 iron-loss check against Materu's measured 6/4 losses (docs/r3-loss-results.md). The result is a report: the
test asserts that every row and the region shares are computed and finite, not a limit on the error."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples"))
import materu_losses_check as check  # noqa: E402

pytestmark = pytest.mark.slow


def test_materu_rows_and_yan_shares_are_finite(tmp_path):
    rows = check.materu_rows(cache_dir=tmp_path)
    assert len(rows) == 10
    for r in rows:
        for key in ("computed_iron_w", "error_pct", "iron_uncertainty_pct", "computed_peak", "computed_rms",
                    "computed_copper_w"):
            assert math.isfinite(r[key]), (r["table"], r["index"], key)
        assert r["computed_iron_w"] > 0
    shares = check.yan_shares(cache_dir=tmp_path)["shares_pct"]
    assert all(math.isfinite(v) for v in shares.values())
    assert sum(shares.values()) == pytest.approx(100.0)
