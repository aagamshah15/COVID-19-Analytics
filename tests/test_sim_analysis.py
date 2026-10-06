import copy
import json
import math
from dataclasses import replace

import numpy as np
import pytest

from covid_pipeline.simulator import analysis
from covid_pipeline.simulator.analysis import ScenarioRun
from covid_pipeline.simulator.fixtures import GOLDEN_PATH

GOLDEN = json.loads(GOLDEN_PATH.read_text())["cases"]
SOURCES = {k: "calibrated" for k in ("transmission", "severity", "awareness", "reporting", "vaccine_acceptance", "vaccine_capacity")}
UNCERTAINTY = {
    "log_transmission_sd": {"calibrated": 0.12, "predicted": 0.25},
    "log_severity_sd": {"calibrated": 0.37, "predicted": 0.74},
    "log_awareness_country_sd": {"calibrated": 0.57, "predicted": 1.13},
    "logit_reporting_sd": {"observed": 0.2, "predicted": 2.1},
    "logit_vaccine_acceptance_sd": {"observed": 0.2, "predicted": 1.07},
    "log_vaccine_capacity_sd": {"observed": 0.2, "predicted": 0.69},
    "npi_coef_sd": 0.0006,
    "log_awareness_sd": 0.21,
    "seasonality_sd": 0.05,
    "log_r0_sd": 0.1,
    "log_ifr_sd": 0.2,
}


def scenario_json(name: str, days: int | None = None) -> dict:
    """A golden scenario as the browser would post it."""
    case = GOLDEN[name]
    body = {k: case[k] for k in ("place", "pathogen", "response", "variant", "constants")}
    body |= {"sources": SOURCES, "uncertainty": UNCERTAINTY, "days": days or case["days"]}
    return copy.deepcopy(body)  # tests edit what they get


def scenario(name: str, days: int | None = None) -> ScenarioRun:
    return ScenarioRun.from_dict(scenario_json(name, days))


def test_null_in_the_shared_json_means_never():
    s = scenario("adaptive_policy_variant_and_waning")
    assert s.constants.awareness_deaths_pm == math.inf  # null: people don't react to deaths
    assert s.pathogen.immunity_days == 120
    assert s.response.treatment_day == 60
    covid = scenario("covid_lockdown_and_vaccine")
    assert covid.variant.day == math.inf  # null: no variant
    assert covid.response.treatment_day == math.inf
    assert [g.level for g in covid.response.segments] == [75, 40]


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_central_run_reproduces_the_golden_scenarios(name):
    """The API's path from JSON to engine gives the outputs the browser engine is tested against."""
    out, summary = analysis.central(scenario(name))
    expected = GOLDEN[name]["outputs"]
    np.testing.assert_allclose(out.deaths[0], expected["deaths"], rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(out.hospital[0], expected["hospital"], rtol=1e-9, atol=1e-9)
    assert summary["deaths"] == pytest.approx(sum(expected["deaths"]), rel=1e-9)
    assert summary["peak_hospital_day"] == int(np.argmax(expected["hospital"]))


def test_no_response_counterfactual_keeps_the_place_and_the_seeding():
    s = scenario("covid_lockdown_and_vaccine")
    bare = analysis.without_response(s)
    assert bare.response.segments == [] and not bare.response.vaccine
    assert bare.response.start_month == s.response.start_month
    _, with_response = analysis.central(s)
    _, without = analysis.central(bare, capacity=s.capacity())
    assert without["deaths"] > with_response["deaths"]


def test_only_inputs_that_can_matter_are_uncertain():
    covid = scenario("covid_lockdown_and_vaccine")
    assert set(analysis.factors(covid)) == set(analysis.FACTOR_LABELS)

    no_vaccine = replace(covid, response=replace(covid.response, vaccine=False, segments=[]))
    dropped = set(analysis.FACTOR_LABELS) - set(analysis.factors(no_vaccine))
    assert dropped == {"vaccine_acceptance", "vaccine_capacity", "npi"}

    unaware = scenario("adaptive_policy_variant_and_waning")  # awareness threshold is "never"
    assert not {"awareness", "awareness_threshold"} & set(analysis.factors(unaware))
    # With nobody reacting to the news, reporting changes the reported count and nothing else.
    assert "death_reporting" in analysis.factors(unaware)
    assert "death_reporting" in analysis.factors(unaware, "reported_deaths")
    assert "death_reporting" not in analysis.factors(unaware, "deaths")

    fixed = replace(covid, sources=covid.sources | {"transmission": "user"})
    assert "transmission" not in analysis.factors(fixed)  # the visitor set it: no uncertainty
    predicted = replace(covid, sources=covid.sources | {"transmission": "predicted"})
    assert analysis.factors(predicted)["transmission"] == 0.25


def test_a_draw_moves_each_input_on_its_own_scale():
    s = scenario("covid_lockdown_and_vaccine")
    spreads = analysis.factors(s)
    same = analysis.perturbed(s, {k: 0.0 for k in spreads}, spreads)
    assert same.place == s.place and same.pathogen == s.pathogen and same.constants == s.constants

    up = analysis.perturbed(s, {k: 2.0 for k in spreads}, spreads)
    assert up.pathogen.r0 == pytest.approx(s.pathogen.r0 * math.exp(0.2))
    assert up.place.transmission == pytest.approx(s.place.transmission * math.exp(2 * 0.12))
    assert s.place.vaccine_acceptance < up.place.vaccine_acceptance < 1  # logit scale stays a share
    assert up.constants.npi_coef == pytest.approx(s.constants.npi_coef + 2 * 0.0006)


def test_reporting_uncertainty_widens_reported_deaths_even_when_nobody_reacts():
    s = scenario("adaptive_policy_variant_and_waning", days=140)
    only_reporting = replace(s, sources={k: "user" for k in s.sources} | {"reporting": "observed"}, uncertainty={"logit_reporting_sd": 0.5})
    ranges = analysis.monte_carlo(only_reporting, draws=100)["quantiles"]
    assert ranges["reported_deaths"][0] < ranges["reported_deaths"][4]
    assert ranges["deaths"][0] == ranges["deaths"][4]  # true deaths don't depend on who counts them


def test_draws_stay_inside_the_range_the_engine_is_defined_for():
    """However wide the spreads, a draw can't produce a negative transmission rate or an overflow."""
    s = scenario("covid_lockdown_and_vaccine", days=140)
    wild = {k: 3.0 for k in analysis.factors(s)}
    for z in (-40.0, 40.0):
        draw = analysis.perturbed(s, {k: z for k in wild}, wild)
        assert 0 < draw.pathogen.r0 <= 50 and 0 < draw.pathogen.ifr <= 1
        assert 0 <= draw.constants.covid_seasonality <= 1 and -1 <= draw.constants.npi_coef <= 1
        assert 0 < draw.place.transmission <= 1000 and 0 <= draw.place.vaccine_acceptance <= 1
        assert 0 < draw.constants.awareness_deaths_pm <= 1e9


def test_monte_carlo_is_reproducible_and_brackets_the_central_run():
    s = scenario("covid_lockdown_and_vaccine", days=140)
    first = analysis.monte_carlo(s, draws=300, seed=7)
    assert first == analysis.monte_carlo(s, draws=300, seed=7)
    assert first != analysis.monte_carlo(s, draws=300, seed=8)

    _, central = analysis.central(s)
    for key, q in first["quantiles"].items():
        assert q == sorted(q), key
    low, _, _, _, high = first["quantiles"]["deaths"]
    assert low < central["deaths"] < high
    weekly = np.array(first["weekly"]["deaths"])
    assert weekly.shape == (len(analysis.QUANTILES), 20)
    assert (np.diff(weekly, axis=0) >= 0).all()  # quantiles don't cross


def test_weekly_series_sum_flows_and_sample_stocks():
    values = np.arange(20, dtype=float).reshape(1, 20)
    assert analysis._weekly(values, flow=True).tolist() == [[21.0, 70.0, 99.0]]
    assert analysis._weekly(values, flow=False).tolist() == [[6.0, 13.0, 19.0]]


def test_sobol_indices_match_models_with_known_answers():
    """An additive model has no interactions: each input's share is its own variance."""
    weights = np.array([3.0, 2.0, 1.0])
    additive = analysis.sobol_indices(lambda x: x @ weights, d=3, n=2048)
    expected = weights**2 / (weights**2).sum()
    np.testing.assert_allclose(additive["first"], expected, atol=0.03)
    np.testing.assert_allclose(additive["total"], expected, atol=0.03)
    for i, share in enumerate(expected):
        low, high = additive["total_interval"][i]
        assert low - 0.02 <= share <= high + 0.02

    # A pure interaction: neither input explains anything alone, together they explain everything.
    product = analysis.sobol_indices(lambda x: x[:, 0] * x[:, 1], d=3, n=2048)
    np.testing.assert_allclose(product["first"], [0, 0, 0], atol=0.06)
    np.testing.assert_allclose(product["total"], [1, 1, 0], atol=0.08)


def test_sobol_indices_are_reproducible_and_work_for_one_input():
    def model(x):
        return np.exp(0.3 * x[:, 0])

    one = analysis.sobol_indices(model, d=1, n=256, seed=5)
    assert one["first"] == pytest.approx([1.0], abs=0.05) and one["total"] == pytest.approx([1.0], abs=0.05)
    again = analysis.sobol_indices(model, d=1, n=256, seed=5)
    assert all(np.array_equal(one[k], again[k]) for k in one)
    with pytest.raises(ValueError, match="power of two"):
        analysis.sobol_indices(model, d=1, n=100)


def test_sobol_gives_one_input_all_the_variance_when_it_is_the_only_one():
    s = scenario("covid_lockdown_and_vaccine", days=140)
    only_r0 = replace(s, sources={k: "user" for k in s.sources}, uncertainty={"log_r0_sd": 0.1})
    result = analysis.sobol(only_r0, n=64)
    assert [f["key"] for f in result["factors"]] == ["r0"]
    assert result["evaluations"] == 64 * 3
    assert result["factors"][0]["first"] == pytest.approx(1.0, abs=0.05)
    assert result["factors"][0]["total"] == pytest.approx(1.0, abs=0.05)


def test_sobol_ranks_every_uncertain_input():
    s = scenario("covid_lockdown_and_vaccine", days=140)
    result = analysis.sobol(s, n=64, seed=3)
    rows = result["factors"]
    assert {f["key"] for f in rows} == set(analysis.factors(s))
    assert result["evaluations"] == 64 * (len(rows) + 2)
    assert [f["total"] for f in rows] == sorted((f["total"] for f in rows), reverse=True)
    for f in rows:
        assert f["label"] == analysis.FACTOR_LABELS[f["key"]]
        for value in (f["first"], f["total"], *f["first_interval"], *f["total_interval"]):
            assert 0.0 <= value <= 1.0
        assert f["total_interval"][0] <= f["total_interval"][1]
    assert rows[0]["total"] > 0.2  # something drives the outcome
    assert result == analysis.sobol(s, n=64, seed=3)


def test_sobol_copes_with_an_outcome_that_never_varies():
    """A disease that kills nobody: deaths are zero in every run, so there is no variance to share out."""
    s = scenario("covid_lockdown_and_vaccine", days=60)
    harmless = replace(s, pathogen=replace(s.pathogen, ifr=0.0))
    result = analysis.sobol(harmless, n=16)
    assert result["factors"]
    assert all(f["first"] == 0.0 and f["total"] == 0.0 for f in result["factors"])
    assert all(f["total_interval"] == [0.0, 0.0] for f in result["factors"])


def test_sobol_without_uncertain_inputs_runs_nothing():
    s = scenario("covid_lockdown_and_vaccine", days=60)
    certain = replace(s, uncertainty={})
    assert analysis.sobol(certain, n=16) == {"output": "deaths", "n": 16, "evaluations": 0, "confidence": 0.9, "factors": []}
