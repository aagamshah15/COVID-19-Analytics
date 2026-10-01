import pandas as pd

from covid_pipeline.ingest import iso2_to_iso3, load_who, merge_sources


def test_iso2_to_iso3_handles_special_codes():
    assert iso2_to_iso3("FR") == "FRA"
    assert iso2_to_iso3("NA") == "NAM"  # Namibia, not a missing value
    assert iso2_to_iso3("XK") == "OWID_KOS"  # Kosovo uses OWID's code
    assert iso2_to_iso3("XJ") is None  # international conveyance


def test_load_who_parses_bom_namibia_and_drops_conveyances(who_csv):
    who = load_who(who_csv)
    assert "date" in who.columns  # BOM stripped from the first header
    assert set(who["iso_code"]) == {"NAM", "OWID_KOS", "FRA"}
    assert who["new_deaths"].isna().sum() == 1  # empty field stays missing, not zero


def test_merge_fills_gaps_from_who_without_overriding_owid():
    owid = pd.DataFrame(
        {
            "iso_code": ["FRA", "FRA"],
            "date": pd.to_datetime(["2020-03-01", "2020-03-02"]),
            "new_cases": [None, 50.0],
            "new_deaths": [3.0, 1.0],
        }
    )
    who = pd.DataFrame(
        {
            "iso_code": ["FRA", "FRA"],
            "date": pd.to_datetime(["2020-03-01", "2020-03-02"]),
            "who_region": ["EUR", "EUR"],
            "new_cases": [100.0, 999.0],
            "new_deaths": [2.0, 9.0],
        }
    )
    merged = merge_sources(owid, who)
    assert merged["new_cases"].tolist() == [100.0, 50.0]  # gap filled, OWID value kept
    assert merged["new_deaths"].tolist() == [3.0, 1.0]
    assert merged["new_cases_filled_from_who"].tolist() == [True, False]
    assert merged["who_region"].eq("EUR").all()
    assert merged["who_matched"].all()
