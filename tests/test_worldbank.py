import json
import urllib.error

import pandas as pd
import pytest
from conftest import worldbank_payload

from covid_pipeline import worldbank
from covid_pipeline.config import WORLDBANK_SNAPSHOT_PATH
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
        worldbank.fetch_worldbank(dest, snapshot_path=tmp_path / "no-snapshot.json")
    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))


def _api_down(url: str) -> list:
    raise urllib.error.HTTPError(url, 502, "Bad Gateway", None, None)


def test_snapshot_loads_to_the_same_profile(tmp_path):
    payload = worldbank_payload(["FRA", "XKX", "AAA"])
    raw, slim = tmp_path / "raw.json", tmp_path / "slim.json"
    raw.write_text(json.dumps(payload))
    worldbank.write_snapshot(raw, slim)

    pd.testing.assert_frame_equal(load_worldbank(slim), load_worldbank(raw))
    assert slim.stat().st_size < raw.stat().st_size
    with pytest.raises(ValueError, match="itself the snapshot"):  # a snapshot can't refresh itself
        worldbank.write_snapshot(slim, tmp_path / "again.json")


def test_fetch_falls_back_to_the_snapshot_when_the_api_is_down(monkeypatch, tmp_path):
    raw, slim, dest = tmp_path / "raw.json", tmp_path / "slim.json", tmp_path / "wb.json"
    raw.write_text(json.dumps(worldbank_payload(["FRA", "AAA"])))
    worldbank.write_snapshot(raw, slim)
    monkeypatch.setattr(worldbank, "_get_json", _api_down)

    assert worldbank.fetch_worldbank(dest, snapshot_path=slim) == "snapshot"
    pd.testing.assert_frame_equal(load_worldbank(dest), load_worldbank(raw))


def test_fetch_falls_back_when_the_api_is_too_slow(monkeypatch, tmp_path):
    raw, slim, dest = tmp_path / "raw.json", tmp_path / "slim.json", tmp_path / "wb.json"
    raw.write_text(json.dumps(worldbank_payload(["FRA", "AAA"])))
    worldbank.write_snapshot(raw, slim)
    monkeypatch.setattr(worldbank, "_get_json", lambda url: _page("x", 1, 1))  # answers, but the time is already up

    assert worldbank.fetch_worldbank(dest, snapshot_path=slim, budget=-1) == "snapshot"
    pd.testing.assert_frame_equal(load_worldbank(dest), load_worldbank(raw))


def test_fetch_fails_when_the_api_is_down_and_the_snapshot_is_incomplete(monkeypatch, tmp_path):
    raw, slim, dest = tmp_path / "raw.json", tmp_path / "slim.json", tmp_path / "wb.json"
    raw.write_text(json.dumps(worldbank_payload(["FRA"])))
    worldbank.write_snapshot(raw, slim)
    monkeypatch.setattr(worldbank, "_get_json", _api_down)
    monkeypatch.setattr(worldbank, "INDICATORS", worldbank.INDICATORS | {"new": "NEW.CODE"})

    with pytest.raises(ValueError, match="NEW.CODE"):
        worldbank.fetch_worldbank(dest, snapshot_path=slim)
    assert not dest.exists()


def test_versioned_snapshot_covers_every_indicator():
    """Adding an indicator without refreshing the snapshot would break the fallback."""
    payload = json.loads(WORLDBANK_SNAPSHOT_PATH.read_text())
    assert set(payload["indicators"]) == set(worldbank.INDICATORS.values())
    assert all(len(rows) > 150 for rows in payload["indicators"].values())
