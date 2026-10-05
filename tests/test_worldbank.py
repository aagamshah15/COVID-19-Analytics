import json

import pytest
from conftest import worldbank_payload

from covid_pipeline import worldbank
from covid_pipeline.worldbank import load_worldbank


def test_load_takes_latest_pre_pandemic_value_and_maps_kosovo(tmp_path):
    payload = worldbank_payload(["FRA", "XKX"])
    path = tmp_path / "wb.json"
    path.write_text(json.dumps(payload))
    wb = load_worldbank(path)

    assert {"FRA", "OWID_KOS"} <= set(wb.index)  # Kosovo's WDI code maps to OWID's
    assert wb.at["FRA", "physicians_per_thousand"] == 10.0  # 2019 value wins over 2012's 99
    assert "female_share" not in wb.columns  # only used to weight the age groups


def test_age_structure_weights_sexes_and_sums_to_one(worldbank):
    row = worldbank.loc["AAA"]
    assert row["age_0_19"] == pytest.approx(0.25)  # (22% female + 28% male) / 2
    assert row["age_80_plus"] == pytest.approx(0.09)  # (12% + 6%) / 2
    shares = row[["age_0_19", "age_20_39", "age_40_59", "age_60_79", "age_80_plus"]]
    assert shares.sum() == pytest.approx(1.0)
    assert row["age_mean_0_19"] == pytest.approx(10.0)  # midpoints 2.5, 7.5, 12.5, 17.5
    assert row["age_mean_80_plus"] == 85.0


def _page(code: str, page: int, pages: int) -> list:
    return [{"page": page, "pages": pages}, [{"countryiso3code": "FRA", "date": "2019", "value": float(page)}]]


def test_fetch_follows_pagination(monkeypatch, tmp_path):
    monkeypatch.setattr(worldbank, "INDICATORS", {"urban_share": "SP.URB.TOTL.IN.ZS"})
    monkeypatch.setattr(worldbank, "_get_json", lambda url: _page("x", int(url.rsplit("page=", 1)[1]), 2))
    dest = tmp_path / "wb.json"
    worldbank.fetch_worldbank(dest)
    rows = json.loads(dest.read_text())["indicators"]["SP.URB.TOTL.IN.ZS"]
    assert [r["value"] for r in rows] == [1.0, 2.0]


def test_fetch_is_all_or_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(worldbank, "INDICATORS", {"a": "GOOD", "b": "BAD"})

    def fake(url: str) -> list:
        return [{"message": "indicator not found"}] if "BAD" in url else _page("GOOD", 1, 1)

    monkeypatch.setattr(worldbank, "_get_json", fake)
    dest = tmp_path / "wb.json"
    with pytest.raises(ValueError, match="BAD"):
        worldbank.fetch_worldbank(dest)
    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))
