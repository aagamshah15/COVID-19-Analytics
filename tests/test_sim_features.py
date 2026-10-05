import pandas as pd
import pytest

from covid_pipeline.quality import run_checks
from covid_pipeline.simulator.features import AGE_SHARE_COLUMNS, OUTCOME_END


def test_profile_joins_sources_and_imputes_missing_age_structure(sim_tables):
    profile = sim_tables[0].set_index("iso_code")
    assert "OWID_WRL" not in profile.index  # aggregates never become profiles
    assert profile.at["AAA", "age_source"] == "worldbank"
    assert profile.at["AAA", "physicians_per_thousand"] == 10.0
    # Namibia has no World Bank data: its age structure comes from the closest median ages.
    assert profile.at["NAM", "age_source"] == "imputed_from_median_age"
    assert profile.loc["NAM", AGE_SHARE_COLUMNS].sum() == pytest.approx(1.0)
    # OWID beds are kept where present (the fixture has 3.0; the World Bank says 2.0).
    assert profile.at["AAA", "hospital_beds_per_thousand"] == 3.0
    assert profile.at["AAA", "beds_source"] == "owid"


def test_profile_outcomes_cover_the_pre_omicron_window(sim_tables, curated):
    profile = sim_tables[0].set_index("iso_code")
    _, weekly = curated
    window = weekly[(weekly["iso_code"] == "BBB") & (weekly["week_end"] <= OUTCOME_END)]
    expected = window["new_deaths"].sum() / window["population"].iloc[-1] * 1e6
    assert profile.at["BBB", "reported_deaths_pm_2021"] == pytest.approx(expected)
    # Excess deaths run 50% above reported deaths in the fixture; Cland reports none.
    assert profile.at["BBB", "excess_deaths_pm_2021"] > profile.at["BBB", "reported_deaths_pm_2021"]
    assert pd.isna(profile.at["CCC", "excess_deaths_pm_2021"])
    assert 0 < profile.at["AAA", "stringency_mean_2021"] < 75


def test_sim_weekly_adds_weekly_signals_and_clips_negative_rt(sim_tables, curated):
    _, sim_weekly = sim_tables
    assert len(sim_weekly) == len(curated[1])  # one row per curated country-week
    lockdown = sim_weekly[(sim_weekly["iso_code"] == "AAA") & sim_weekly["week_end"].between("2020-04-01", "2020-05-15")]
    assert (lockdown["stringency_index"] == 75).all()
    assert sim_weekly.loc[sim_weekly["week_end"] > "2023-01-08", "stringency_index"].isna().all()
    cland = sim_weekly[sim_weekly["iso_code"] == "CCC"]
    assert cland["rt_clipped"].any()
    assert (sim_weekly["reproduction_rate"].dropna() >= 0).all()


def test_dq_reports_simulator_inputs(sim_tables, curated):
    profile, sim_weekly = sim_tables
    result = run_checks(*curated, profile=profile, sim_weekly=sim_weekly)
    checks = {c.name: c for c in result.checks}
    assert checks["sim_age_shares_sum_to_one"].passed
    assert not checks["sim_negative_rt_clipped"].passed  # Cland's dip is reported, not hidden
    # Six synthetic countries are far below the coverage thresholds: warnings, never errors.
    assert not checks["sim_stringency_coverage"].passed
    assert all(c.severity == "warn" for name, c in checks.items() if name.startswith("sim_"))
    assert "sim_age_structure_coverage" not in {c.name for c in run_checks(*curated).checks}
