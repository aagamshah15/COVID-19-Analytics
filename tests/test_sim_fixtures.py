import json
import math

from covid_pipeline.simulator.fixtures import GOLDEN_PATH, golden_cases

# Platforms disagree in the last digits of exp() and friends, so values can differ by a unit in the
# 13th significant digit between macOS and Linux. Stale fixtures (a changed engine) differ by far more.
REL_TOL = 1e-9


def _mismatches(committed, fresh, path="") -> list[str]:
    if isinstance(fresh, dict):
        if not isinstance(committed, dict) or committed.keys() != fresh.keys():
            return [f"{path}: keys differ"]
        return [m for k in fresh for m in _mismatches(committed[k], fresh[k], f"{path}.{k}")]
    if isinstance(fresh, list):
        if not isinstance(committed, list) or len(committed) != len(fresh):
            return [f"{path}: lengths differ"]
        return [m for i, (a, b) in enumerate(zip(committed, fresh, strict=True)) for m in _mismatches(a, b, f"{path}[{i}]")]
    if isinstance(fresh, float) and isinstance(committed, (int, float)) and not isinstance(committed, bool):
        return [] if math.isclose(committed, fresh, rel_tol=REL_TOL, abs_tol=1e-12) else [f"{path}: {committed} != {fresh}"]
    return [] if committed == fresh else [f"{path}: {committed!r} != {fresh!r}"]


def test_golden_scenarios_are_up_to_date():
    """The browser engine is tested against this file: regenerate it with `covid-pipeline sim-fixtures`."""
    committed = json.loads(GOLDEN_PATH.read_text())
    mismatches = _mismatches(committed, json.loads(json.dumps(golden_cases(), allow_nan=False)))
    assert not mismatches, f"{len(mismatches)} stale values, first: {mismatches[:3]}"


def test_golden_scenarios_exercise_every_mechanism():
    cases = golden_cases()["cases"]
    adaptive = cases["adaptive_policy_variant_and_waning"]["outputs"]
    assert max(adaptive["stringency"]) == 80  # the adaptive trigger fired
    assert max(cases["covid_lockdown_and_vaccine"]["outputs"]["vaccinated"]) > 0
    assert sum(cases["subcritical_mers"]["outputs"]["infections"]) < 10_000
    overwhelmed = cases["overwhelmed_hospitals"]
    beds = overwhelmed["inputs"]["beds"]
    assert max(overwhelmed["outputs"]["hospital"]) > beds  # demand exceeded capacity
