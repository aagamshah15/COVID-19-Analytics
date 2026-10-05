from dataclasses import replace

import numpy as np
import pytest
from scipy.optimize import brentq

from covid_pipeline.simulator.engine import EngineInputs, overload_multiplier, run
from covid_pipeline.simulator.scenario import (
    PRESETS,
    ModelConstants,
    Place,
    Response,
    Segment,
    band_severity,
    build_inputs,
    levin_ifr,
    seasonal_terms,
)

DAYS = 400
PLACE = Place(
    population=10_000_000,
    age_shares=[0.22, 0.26, 0.27, 0.20, 0.05],
    age_means=[10.0, 30.0, 50.0, 68.0, 85.0],
    beds_per_thousand=3.0,
)
COVID = PRESETS["covid_ancestral"]
CONSTANTS = ModelConstants(npi_coef=-0.0115)


def simulate(place=PLACE, pathogen=COVID, response=None, days=DAYS, constants=CONSTANTS, **kw):
    return run(build_inputs(place, pathogen, response or Response(vaccine=False, awareness=False), days, constants, **kw), days)


def sir(r0: float):
    """A plain SIR epidemic: no deaths, no waning, no policy, no awareness."""
    pathogen = replace(COVID, r0=r0, ifr=0.0, hosp=0.0, immunity_days=float("inf"), seasonality=0.0)
    return simulate(pathogen=pathogen, response=Response(vaccine=False, awareness=False, seed_per_million=1), days=1500)


@pytest.mark.parametrize("r0", [1.3, 2.0, 2.8, 5.0])
def test_final_size_matches_the_analytic_sir_result(r0):
    out = sir(r0)
    attack = 1 - out.susceptible[0, -1] / PLACE.population
    expected = brentq(lambda z: z - 1 + np.exp(-r0 * z), 1e-9, 1)
    assert attack == pytest.approx(expected, abs=2e-3)


def test_initial_rt_equals_r0_without_interventions():
    assert sir(2.8).rt[0, 0] == pytest.approx(2.8)


def test_no_epidemic_below_threshold():
    out = sir(0.8)
    assert out.infections.sum() < 50 * PLACE.population / 1e6  # a few generations of the seed, then nothing


def test_population_is_conserved_and_nothing_goes_negative():
    out = simulate(response=Response(segments=[Segment(40, 200, 60)], vaccine_day=100))
    total = out.susceptible + out.infected + out.immune + out.hospital + out.dead
    np.testing.assert_allclose(total, PLACE.population, rtol=1e-9)
    for series in (out.susceptible, out.infected, out.immune, out.hospital, out.dead, out.infections):
        assert (series >= -1e-6).all()


def test_lockdowns_vaccines_and_beds_each_reduce_deaths():
    base = simulate().deaths.sum()
    assert simulate(response=Response(segments=[Segment(30, 300, 70)], vaccine=False, awareness=False)).deaths.sum() < base
    assert simulate(response=Response(vaccine=True, vaccine_day=40, awareness=False)).deaths.sum() < base
    assert simulate(place=replace(PLACE, beds_per_thousand=0.5)).deaths.sum() > base  # an overwhelmed system kills more


def test_vaccinating_oldest_first_saves_more_lives_for_an_age_steep_disease():
    oldest = simulate(response=Response(vaccine_day=20, vaccine_oldest_first=True, awareness=False))
    uniform = simulate(response=Response(vaccine_day=20, vaccine_oldest_first=False, awareness=False))
    assert oldest.deaths.sum() < uniform.deaths.sum()
    assert oldest.vaccinated[0, -1] == pytest.approx(uniform.vaccinated[0, -1], rel=1e-6)


def test_awareness_flattens_the_peak():
    plain = simulate(response=Response(vaccine=False, awareness=False))
    aware = simulate(response=Response(vaccine=False, awareness=True), constants=replace(CONSTANTS, awareness_deaths_pm=1.0))
    assert aware.deaths.max() < 0.5 * plain.deaths.max()


def test_adaptive_policy_switches_on_at_the_trigger():
    out = simulate(response=Response(vaccine=False, awareness=False, adaptive=True, adaptive_on=0.3, adaptive_level=75))
    on = out.stringency[0] == 75
    assert on.any()
    first = int(np.argmax(on))
    occupancy = out.hospital[0, first - 1] / (PLACE.beds_per_thousand * PLACE.population / 1000 * PLACE.bed_availability)
    assert occupancy >= 0.3


def test_reported_deaths_scale_with_reporting():
    out = simulate(place=replace(PLACE, death_reporting=0.4))
    np.testing.assert_allclose(out.reported_deaths, out.deaths * 0.4)


def test_border_delay_shifts_the_epidemic():
    early = simulate()
    late = simulate(response=Response(vaccine=False, awareness=False, border_delay_days=30))
    assert int(late.infections[0].argmax()) == pytest.approx(int(early.infections[0].argmax()) + 30, abs=1)


def test_lanes_are_independent():
    inputs = [build_inputs(PLACE, replace(COVID, r0=r0), Response(vaccine=False), 200, CONSTANTS) for r0 in (1.5, 3.0)]
    stacked = EngineInputs(**{f: np.concatenate([getattr(x, f) for x in inputs]) for f in inputs[0].__dataclass_fields__})
    together = run(stacked, 200)
    for lane, single in enumerate(inputs):
        np.testing.assert_allclose(together.deaths[lane], run(single, 200).deaths[0], rtol=1e-12)


def test_overload_multiplier_follows_bravata_and_rises_past_capacity():
    unmet = np.array([3.0])
    assert overload_multiplier(np.array([0.3]), unmet)[0] == pytest.approx(1.0)
    assert overload_multiplier(np.array([0.875]), unmet)[0] == pytest.approx(1.94)
    assert overload_multiplier(np.array([2.0]), unmet)[0] == pytest.approx((1.94 + 3.0) / 2)


def test_band_severity_uses_levin_and_applies_country_severity_to_older_bands_only():
    ifr, hosp = band_severity(COVID, PLACE, CONSTANTS)
    np.testing.assert_allclose(ifr, levin_ifr(PLACE.age_means), rtol=1e-6)
    severe = band_severity(COVID, replace(PLACE, severity=2.0), CONSTANTS)[0]
    np.testing.assert_allclose(severe[:3], ifr[:3])
    np.testing.assert_allclose(severe[3:], 2 * ifr[3:])
    assert (hosp >= ifr / 0.95 - 1e-12).all()


def test_every_preset_runs_and_respects_its_threshold():
    for preset in PRESETS.values():
        out = simulate(pathogen=preset, response=Response(vaccine=False, awareness=False), days=365)
        attack = out.infections.sum() / PLACE.population
        assert np.isfinite(attack)
        if preset.r0 < 1:
            assert attack < 1e-4


def test_seasonal_phase_follows_hemisphere_and_start_month():
    c = replace(CONSTANTS, covid_seasonality=0.3, season_peak_day_north=10.0)
    north, south, tropics = (replace(PLACE, latitude=lat) for lat in (50.0, -50.0, 0.0))
    assert seasonal_terms(COVID, north, Response(start_month=1), c) == pytest.approx((0.3, 10.0))
    assert seasonal_terms(COVID, south, Response(start_month=1), c) == pytest.approx((0.3, 192.5))
    # Starting on 1 July (day 181), the next northern peak is 194 days away.
    assert seasonal_terms(COVID, north, Response(start_month=7), c)[1] == pytest.approx((10 - 181) % 365)
    assert seasonal_terms(COVID, tropics, Response(), c)[0] == 0.0
    # A pathogen's own amplitude overrides the learned SARS-CoV-2 one, scaled by latitude.
    halfway = (23.5 + 40.0) / 2
    assert seasonal_terms(PRESETS["seasonal_flu"], replace(PLACE, latitude=halfway), Response(), c)[0] == pytest.approx(0.1)
    assert seasonal_terms(COVID, replace(PLACE, latitude=20.0), Response(), c)[0] == 0.0  # inside the tropics


def test_a_winter_start_spreads_faster_than_a_summer_start():
    c = replace(CONSTANTS, covid_seasonality=0.3)
    place = replace(PLACE, latitude=50.0)
    winter = simulate(place=place, response=Response(vaccine=False, awareness=False, start_month=1), constants=c)
    summer = simulate(place=place, response=Response(vaccine=False, awareness=False, start_month=7), constants=c)
    assert winter.rt[0, 0] > summer.rt[0, 0]
    assert winter.infections[0].argmax() < summer.infections[0].argmax()


def test_a_more_tolerant_population_reaches_a_higher_peak():
    c = replace(CONSTANTS, awareness_deaths_pm=1.0)
    cautious = simulate(response=Response(vaccine=False, awareness=True), constants=c)
    tolerant = simulate(place=replace(PLACE, awareness=4.0), response=Response(vaccine=False, awareness=True), constants=c)
    assert tolerant.deaths.max() > cautious.deaths.max()
