import json

from covid_pipeline.simulator.fixtures import GOLDEN_PATH, golden_cases


def test_golden_scenarios_are_up_to_date():
    """The browser engine is tested against this file: regenerate it with `covid-pipeline sim-fixtures`."""
    committed = json.loads(GOLDEN_PATH.read_text())
    assert committed == json.loads(json.dumps(golden_cases(), allow_nan=False))


def test_golden_scenarios_exercise_every_mechanism():
    cases = golden_cases()["cases"]
    adaptive = cases["adaptive_policy_variant_and_waning"]["outputs"]
    assert max(adaptive["stringency"]) == 80  # the adaptive trigger fired
    assert max(cases["covid_lockdown_and_vaccine"]["outputs"]["vaccinated"]) > 0
    assert sum(cases["subcritical_mers"]["outputs"]["infections"]) < 10_000
    overwhelmed = cases["overwhelmed_hospitals"]
    beds = overwhelmed["inputs"]["beds"]
    assert max(overwhelmed["outputs"]["hospital"]) > beds  # demand exceeded capacity
