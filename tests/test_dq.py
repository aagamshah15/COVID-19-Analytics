import pandas as pd

from src.dq import run_dq_checks


def test_dq_score_output_shape():
    daily = pd.DataFrame(
        {
            "iso_code": ["AAA", "AAA"],
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "location": ["A", "A"],
            "new_deaths": [0, 1],
            "new_cases": [1, 2],
            "vaccination_rate": [0.0, 0.1],
        }
    )
    weekly = pd.DataFrame(
        {
            "iso_code": ["AAA"],
            "location": ["A"],
            "date": pd.to_datetime(["2020-01-05"]),
        }
    )

    report, score = run_dq_checks(daily, weekly, save=False)

    assert len(report) >= 5
    assert 0 <= score <= 100
    assert set(["check_name", "passed", "pass_rate"]).issubset(report.columns)
