from covid_pipeline.config import DQThresholds
from covid_pipeline.quality import run_checks

LOOSE = DQThresholds(min_countries=5)


def test_clean_data_passes_gate(curated):
    daily, weekly = curated
    result = run_checks(daily, weekly, thresholds=LOOSE)
    assert result.passed, [c.name for c in result.errors]
    # The fixture's planted problems surface as warnings rather than silently passing.
    warned = {c.name for c in result.warnings}
    assert {"negative_revisions_clipped", "death_reporting_active_at_end"} <= warned


def test_stale_extract_fails_coverage(curated):
    """The original failure mode: data that silently stopped in 2020 must not pass."""
    daily, weekly = curated
    stale = daily[daily["date"] <= "2020-09-19"]
    result = run_checks(stale, weekly[weekly["week_end"] <= "2020-09-20"], thresholds=LOOSE)
    assert not result.passed
    assert "coverage_reaches_end_date" in {c.name for c in result.errors}


def test_duplicates_and_too_few_countries_fail(curated):
    daily, weekly = curated
    result = run_checks(daily.iloc[list(range(len(daily))) + [0]], weekly)  # default min_countries=150
    errors = {c.name for c in result.errors}
    assert {"daily_unique_iso_date", "country_count"} <= errors
