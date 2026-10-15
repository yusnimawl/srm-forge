import pytest

from srmbench.projections import project, recommended_workers, summary


def test_recommended_workers():
    b = [{"workers": 1, "per_min": 27}, {"workers": 8, "per_min": 165}, {"workers": 12, "per_min": 192},
         {"workers": 16, "per_min": 200}]
    assert recommended_workers(b) == 12


def test_recommended_workers_unsorted_and_single():
    assert recommended_workers([{"workers": 16, "per_min": 200}, {"workers": 4, "per_min": 195}]) == 4
    assert recommended_workers([{"workers": 3, "per_min": 10}]) == 3


def test_recommended_workers_empty_raises():
    with pytest.raises(ValueError):
        recommended_workers([])


def test_project_numbers():
    p = project({"screening": 5.0, "full": 15.0}, {"screening": 2.0, "full": 6.0}, 120.0,
                {"screening": 360, "full": 1008})
    assert p["screening_map_s"] == pytest.approx(5 + 360 * 0.5)
    assert p["full_map_s"] == pytest.approx(15 + 1008 * 3 * 0.5)
    assert p["search_h"] == pytest.approx(24 * p["full_map_s"] / 3600)


def _c(status, details=()):
    return {"status": status, "details": list(details)}


def _steps(screening_map_s: float | None = None, full_map_s: float | None = None) -> dict:
    steps = {
        "mesh": {"screening": {"seconds": 5.0, "nodes": 1000, "points": 360},
                 "full": {"seconds": 15.0, "nodes": 3000, "points": 1008}},
        "single_solve": {"screening": {"samples": [2.0], "median": 2.0}, "full": {"samples": [6.0], "median": 6.0}},
        "correctness_points": {"points": [], "correctness": _c("pass")},
        "batches": [
            {"workers": 4, "points": 32, "seconds": 16.0, "per_min": 120.0, "peak_ram_gb": 0.5},
            {"workers": 8, "points": 64, "seconds": 28.0, "per_min": 137.1, "peak_ram_gb": 0.7},
            {"workers": 16, "points": 128, "seconds": 38.4, "per_min": 200.0, "peak_ram_gb": 0.6},
        ],
    }
    if screening_map_s is not None:
        steps["screening_map"] = {"seconds": screening_map_s, "points": 320, "key_numbers": {}, "statuses": {},
                                  "correctness": _c("pass"), "workers": 16}
        steps["sustained"] = {"batches": [], "throttle_pct": -4.5, "workers": 16, "minutes": 5}
    if full_map_s is not None:
        steps["full_maps"] = {
            "8_6": {"map": {"seconds": full_map_s, "points": 960, "key_numbers": {}, "statuses": {},
                            "correctness": _c("not checked")},
                    "extras": {"seconds": 100.0}, "workers": 16},
            "12_8": {"map": {"seconds": 2 * full_map_s, "points": 960, "key_numbers": {}, "statuses": {},
                             "correctness": _c("not checked")},
                     "extras": {"seconds": 200.0}, "workers": 16},
        }
    return steps


def test_summary_marks_measured_maps_and_projection_error():
    s = summary(_steps(screening_map_s=228.0, full_map_s=1500.0), "long")
    assert s["screening_map_s"] == {"value": 228.0, "measured": True}
    assert s["full_map_s"] == {"value": 1500.0, "measured": True}
    assert s["throttle_pct"] == -4.5
    assert s["best_workers"] == 16 and s["recommended_workers"] == 16 and s["srmweb_workers"] == 16
    assert s["throughput_per_min"] == 200.0
    assert s["peak_ram_worker_gb"] == 0.7
    assert s["single_solve_s"] == 2.0 and s["single_solve_full_s"] == 6.0
    # projections at 200 solves/min: screening 5 + 360 * 0.3, full 15 + 1008 * 3 * 0.3
    proj_scr, proj_full = 5 + 360 * 0.3, 15 + 1008 * 3 * 0.3
    assert s["projection_error_pct"]["screening"] == pytest.approx((proj_scr / 228.0 - 1) * 100)
    assert s["projection_error_pct"]["full"] == pytest.approx((proj_full / 1500.0 - 1) * 100)
    assert s["search_h"] == pytest.approx(24 * proj_full / 3600)
    assert s["correctness"]["status"] == "pass"


def test_summary_search_hours_stay_projected_even_when_the_full_map_was_measured():
    s = summary(_steps(screening_map_s=228.0, full_map_s=1500.0), "long")
    assert s["search_h"] == pytest.approx(24 * (15 + 1008 * 3 * 0.3) / 3600)


def test_summary_standard_measures_screening_only():
    s = summary(_steps(screening_map_s=228.0), "standard")
    assert s["screening_map_s"]["measured"] is True
    assert s["full_map_s"]["measured"] is False
    assert s["full_map_s"]["value"] == pytest.approx(15 + 1008 * 3 * 0.3)
    assert s["projection_error_pct"] is None
    assert s["throttle_pct"] == -4.5
    assert s["recommended_workers"] == 16


def test_summary_quick_has_no_throttle_and_projected_maps():
    s = summary(_steps(), "quick")
    assert s["throttle_pct"] is None and s["projection_error_pct"] is None
    assert s["screening_map_s"] == {"value": pytest.approx(5 + 360 * 0.3), "measured": False}
    assert s["full_map_s"]["measured"] is False


def test_summary_quick_takes_the_better_worker_count_standard_the_smallest_within_95_percent():
    steps = _steps()
    steps["batches"] = [{"workers": 8, "points": 64, "seconds": 1, "per_min": 197.0, "peak_ram_gb": 0.5},
                        {"workers": 16, "points": 128, "seconds": 1, "per_min": 200.0, "peak_ram_gb": 0.5}]
    assert summary(steps, "quick")["recommended_workers"] == 16
    assert summary(steps, "standard")["recommended_workers"] == 8


def test_summary_peak_ram_none_when_no_batch_has_a_figure():
    steps = _steps()
    for b in steps["batches"]:
        b["peak_ram_gb"] = None
    assert summary(steps, "quick")["peak_ram_worker_gb"] is None


def test_correctness_rollup():
    steps = _steps(screening_map_s=228.0, full_map_s=1500.0)
    steps["screening_map"]["correctness"] = _c("fail", ["la: got 1, want 2"])
    s = summary(steps, "long")
    assert s["correctness"]["status"] == "fail"
    assert any("la: got 1, want 2" in d for d in s["correctness"]["details"])

    steps = _steps()
    steps["correctness_points"]["correctness"] = _c("not checked", ["reference is for srmcore 0.1"])
    s = summary(steps, "quick")
    assert s["correctness"]["status"] == "not checked"
    assert s["correctness"]["details"]

    steps = _steps(screening_map_s=228.0)
    steps["correctness_points"]["correctness"] = _c("not checked")
    assert summary(steps, "standard")["correctness"]["status"] == "pass"


def test_summary_uses_the_capped_recommendation_and_its_throughput():
    steps = _steps()
    steps["recommended"] = {"workers": 10, "uncapped": 16, "ram_cap": 10}
    s = summary(steps, "standard")
    assert s["recommended_workers"] == s["srmweb_workers"] == 10
    assert s["best_workers"] == 16
    assert s["throughput_per_min"] == 137.1  # the W = 8 batch
    assert s["screening_map_s"]["value"] == pytest.approx(5 + 360 * 60 / 137.1)


def test_throughput_below_every_measured_batch_scales_the_smallest():
    steps = _steps()
    steps["recommended"] = {"workers": 2, "uncapped": 16, "ram_cap": 2}
    assert summary(steps, "quick")["throughput_per_min"] == pytest.approx(60.0)


def test_summary_best_throughput_is_the_largest_batch_rate_not_the_recommended_one():
    steps = _steps()
    steps["recommended"] = {"workers": 4, "uncapped": 4, "ram_cap": None}
    s = summary(steps, "standard")
    assert s["throughput_per_min"] == 120.0 and s["best_throughput_per_min"] == 200.0
