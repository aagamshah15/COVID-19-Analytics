import copy
import json
import math
import subprocess
import sys
import threading
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_sim_analysis import GOLDEN, scenario_json

from api import schemas
from api.limits import Budget, Limit
from api.main import MAX_BODY_BYTES, SERIES, Settings, create_app, significant
from covid_pipeline.simulator import analysis

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://aagamshah15.github.io"


def make_client(tmp_path, **overrides) -> TestClient:
    """A client for a small, fast service with no model card unless a test writes one."""
    settings = Settings(**{"deep_draws": 200, "sobol_n": 16, "model_card_path": tmp_path / "simulator.json"} | overrides)
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path) -> TestClient:
    return make_client(tmp_path)


@pytest.fixture
def body() -> dict:
    return {"scenario": scenario_json("covid_lockdown_and_vaccine")}


# --------------------------------------------------------------------------- endpoints


def test_health_and_index(client):
    assert client.get("/health").json() == {"status": "ok", "version": "1.0.0", "model_version": None}
    assert "/analyze/deep" in client.get("/").json()["endpoints"]


def test_model_card_is_served_when_bundled(tmp_path, client):
    assert client.get("/model").status_code == 404
    card = {
        "version": "1.0.0",
        "trained_at": "2026-10-05T21:51:03+00:00",
        "constants": {"npi_coef": -0.0075, "awareness_deaths_pm": float("inf")},
        "uncertainty": {"log_r0_sd": 0.1},
        "validation": {"holdout": {"wape": 0.6}},
        "countries": [{"iso": "ITA"}, {"iso": "USA"}],
        "presets": [{"id": "measles", "name": "Measles", "r0": 15, "ifr": 0.002, "hosp": 0.2}],
        "models": {"too": "big to serve"},
    }
    (tmp_path / "simulator.json").write_text(json.dumps(card))
    with_card = make_client(tmp_path)
    assert with_card.get("/health").json()["model_version"] == "1.0.0"
    served = with_card.get("/model").json()
    assert served["countries"] == 2
    assert served["presets"] == [{"id": "measles", "name": "Measles", "r0": 15, "ifr": 0.002}]
    assert served["constants"]["awareness_deaths_pm"] is None  # infinity travels as null
    assert "models" not in served


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_simulate_returns_what_the_browser_engine_is_tested_against(client, name):
    result = client.post("/simulate", json={"scenario": scenario_json(name)}).json()
    expected = GOLDEN[name]["outputs"]
    assert set(result["series"]) == set(SERIES)
    for series in ("deaths", "hospital", "infections", "rt", "vaccinated"):
        assert result["series"][series] == pytest.approx(expected[series], rel=1e-5, abs=1e-9), series
    assert result["deaths_by_age"] == pytest.approx(expected["deaths_by_age"], rel=1e-5, abs=1e-9)
    assert result["summary"]["deaths"] == pytest.approx(sum(expected["deaths"]), rel=1e-9)
    assert result["days"] == GOLDEN[name]["days"]
    assert "ensemble" not in result


def test_simulate_compares_with_doing_nothing_and_can_add_ranges(client, body):
    result = client.post("/simulate", json=body | {"draws": 50, "seed": 3, "series": False}).json()
    assert "series" not in result
    assert result["no_response"]["deaths"] > result["summary"]["deaths"]
    place = body["scenario"]["place"]
    assert result["hospital_capacity"] == pytest.approx(place["beds_per_thousand"] * place["population"] / 1000 * place["bed_availability"])
    low, _, median, _, high = result["ensemble"]["quantiles"]["deaths"]
    assert result["ensemble"]["draws"] == 50
    assert low < median < high
    assert result == client.post("/simulate", json=body | {"draws": 50, "seed": 3, "series": False}).json() | {"ms": result["ms"]}


def test_deep_analysis_returns_ranges_and_sensitivity(client, body):
    result = client.post("/analyze/deep", json=body).json()
    assert result["monte_carlo"]["draws"] == 200
    assert len(result["monte_carlo"]["weekly"]["deaths"]) == len(analysis.QUANTILES)
    factors = result["sobol"]["factors"]
    assert result["sobol"]["evaluations"] == 16 * (len(factors) + 2)
    assert {f["key"] for f in factors} == set(analysis.FACTOR_LABELS)
    assert all(0 <= f["first"] <= 1 and 0 <= f["total"] <= 1 for f in factors)
    assert result["summary"]["deaths"] == pytest.approx(sum(GOLDEN["covid_lockdown_and_vaccine"]["outputs"]["deaths"]), rel=1e-9)


def test_responses_never_carry_nan_or_infinity(client, body):
    """A disease that kills nobody leaves nothing to rank; the answer is still valid JSON."""
    body["scenario"]["pathogen"]["ifr"] = 0
    response = client.post("/analyze/deep", json=body)
    assert response.status_code == 200
    json.loads(response.text, parse_constant=lambda name: pytest.fail(f"{name} in the response"))
    assert all(f["total"] == 0 for f in response.json()["sobol"]["factors"])


def test_significant_rounds_to_six_figures():
    assert significant([123456789.0, 0.000123456789, 0.0, -98765.4321]) == [123457000.0, 0.000123457, 0.0, -98765.4]


def test_limits_can_be_set_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEP_PER_DAY", "7")
    monkeypatch.setenv("COMPUTE_SECONDS_PER_DAY", "90")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.setenv("MODEL_CARD_PATH", str(tmp_path / "card.json"))
    settings = Settings.from_env()
    assert (settings.deep_per_day, settings.compute_seconds_per_day, settings.simulate_per_day) == (7, 90, Settings().simulate_per_day)
    assert settings.allowed_origins == ["https://a.example", "https://b.example"]
    assert settings.model_card_path == tmp_path / "card.json"


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("days",), 5000),  # longer than three years
        (("days",), 3),
        (("place", "population"), -1),
        (("place", "age_shares"), [0.5, 0.5, 0.5, 0.5, 0.5]),  # doesn't sum to one
        (("place", "age_shares"), [0.5, 0.5]),
        (("pathogen", "r0"), 500),
        (("pathogen", "latent_days"), 0),  # shorter than an engine step
        (("pathogen", "age_profile"), "made_up"),
        (("response", "segments"), [{"start_day": 0, "end_day": 10, "level": 500}]),
        (("response", "start_month"), 13),
        (("sources", "severity"), "guessed"),
        (("uncertainty", "log_r0_sd"), 50),
        (("constants", "reference_shares"), [0, 0, 0, 0, 0]),  # no reference population to scale severity by
        (("place", "surprise"), 1),  # unknown fields are refused, not ignored
    ],
)
def test_scenarios_outside_the_bounds_are_refused(client, body, path, value):
    target = body["scenario"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    for endpoint in ("/simulate", "/analyze/deep"):
        assert client.post(endpoint, json=body).status_code == 422, endpoint


EXTREMES = {
    "one person": lambda s: s["place"].update(population=1),
    "no beds": lambda s: s["place"].update(beds_per_thousand=0, bed_availability=0),
    "one age band": lambda s: s["place"].update(age_shares=[0, 0, 1, 0, 0]),
    "no care, nothing reported": lambda s: s["place"].update(access=0, death_reporting=0),
    "everyone vaccinated at once": lambda s: s["place"].update(vaccine_acceptance=1, vaccine_capacity=1),
    "most contagious": lambda s: s["pathogen"].update(r0=50),
    "barely contagious": lambda s: s["pathogen"].update(r0=1e-6),
    "always fatal": lambda s: s["pathogen"].update(ifr=1, hosp=1, icu_share=1),
    "harmless": lambda s: s["pathogen"].update(ifr=0, hosp=0),
    "fastest stages": lambda s: s["pathogen"].update(latent_days=0.25, infectious_days=0.25, hosp_days=0.25, immunity_days=0.25),
    "slowest stages": lambda s: s["pathogen"].update(latent_days=36500, infectious_days=36500, hosp_days=36500),
    "everyone seeded": lambda s: s["response"].update(seed_per_million=1e5),
    "largest multipliers": lambda s: s["place"].update(transmission=1000, severity=1000, awareness=1000, adherence=10),
    "smallest multipliers": lambda s: s["place"].update(transmission=1e-9, severity=1e-9, awareness=1e-9, adherence=0),
    "strongest variant": lambda s: s["variant"].update(day=0, transmission=1000, severity=1000, escape=1),
    "extreme constants": lambda s: s["constants"].update(npi_coef=-1, fatigue_ratio=10, awareness_power=10, unmet_multiplier=100),
    "restrictions that spread it": lambda s: s["constants"].update(npi_coef=1),
    "hair-trigger awareness": lambda s: s["constants"].update(awareness_deaths_pm=1e-9),
    "locked down throughout": lambda s: s["response"].update(segments=[{"start_day": 0, "end_day": 1095, "level": 100}]),
    "a segment that ends before it starts": lambda s: s["response"].update(segments=[{"start_day": 200, "end_day": 10, "level": 50}]),
    "adaptive at zero": lambda s: s["response"].update(adaptive=True, adaptive_on=0, adaptive_off=0, adaptive_min_days=0),
    "widest spreads": lambda s: s["uncertainty"].update(log_r0_sd=3, log_ifr_sd=3, npi_coef_sd=3, seasonality_sd=3, log_awareness_sd=3),
    "at the pole": lambda s: s["place"].update(latitude=90),
    "one week": lambda s: s.update(days=7),
    "newborns only": lambda s: s["place"].update(age_means=[0, 0, 0, 0, 0]),
}


@pytest.mark.parametrize("name", sorted(EXTREMES))
def test_every_scenario_the_schema_allows_gives_finite_numbers(name):
    """The bounds in the schema are the engine's limits: inside them nothing overflows or divides by zero."""
    raw = scenario_json("covid_lockdown_and_vaccine", days=200)
    EXTREMES[name](raw)
    s = analysis.ScenarioRun.from_dict(schemas.Scenario(**raw).model_dump())
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a numerical warning is a bug here
        _, summary = analysis.central(s)
        ranges = analysis.monte_carlo(s, draws=40)
        indices = analysis.sobol(s, n=16)
    assert all(math.isfinite(v) and v >= 0 for v in summary.values()), summary
    assert all(math.isfinite(v) for q in ranges["quantiles"].values() for v in q)
    assert all(0 <= f["total"] <= 1 for f in indices["factors"])


def test_requests_are_capped(client, body):
    assert client.post("/simulate", json=body | {"draws": 501}).status_code == 422
    assert client.post("/simulate", json=body | {"extra": True}).status_code == 422
    assert client.post("/simulate", content=b"not json", headers={"content-type": "application/json"}).status_code == 422
    assert client.get("/simulate").status_code == 405


def test_refusals_explain_the_problem_without_echoing_the_request(client, body):
    body["scenario"]["pathogen"]["r0"] = 500
    body["scenario"]["place"]["population"] = "x" * 5000
    problems = client.post("/simulate", json=body).json()["detail"]
    assert {tuple(p["loc"]) for p in problems} == {("body", "scenario", "pathogen", "r0"), ("body", "scenario", "place", "population")}
    assert all(set(p) == {"loc", "msg", "type"} for p in problems)

    as_text = client.post("/simulate", content=json.dumps(body), headers={"content-type": "text/plain"})
    assert as_text.status_code == 422 and len(as_text.content) < 500  # the body is not sent back


def test_oversized_bodies_are_refused_even_without_a_declared_length(client, body):
    padded = copy.deepcopy(body)
    padded["scenario"]["pathogen"]["sources"] = ["x" * 190] * 40
    padded["scenario"]["pathogen"]["assumptions"] = ["x" * 70] * 40
    assert client.post("/simulate", json=padded).status_code == 200  # the largest valid scenario fits

    huge = b'{"scenario": "' + b"x" * (MAX_BODY_BYTES + 1) + b'"}'
    assert client.post("/simulate", content=huge, headers={"content-type": "application/json"}).status_code == 413

    def chunks():  # sent with chunked transfer encoding: no Content-Length to check
        yield from (huge[i : i + 8192] for i in range(0, len(huge), 8192))

    assert client.post("/analyze/deep", content=chunks(), headers={"content-type": "application/json"}).status_code == 413


# --------------------------------------------------------------------------- limits


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limit_allows_a_fixed_number_of_calls_a_minute_per_address():
    clock = Clock()
    limit = Limit(per_minute=2, per_day=100, clock=clock)
    assert limit.check("a") is None and limit.check("a") is None
    assert limit.check("a") == pytest.approx(60)
    assert limit.check("b") is None  # another address has its own allowance
    clock.now += 45
    assert limit.check("a") == pytest.approx(15)
    clock.now += 15
    assert limit.check("a") is None


def test_a_limit_of_zero_closes_the_endpoint():
    assert Limit(per_minute=0, per_day=100).check("a") == 60
    assert Limit(per_minute=10, per_day=0).check("a") == pytest.approx(86400)


def test_limit_caps_everyone_together_per_day():
    clock = Clock()
    limit = Limit(per_minute=10, per_day=3, clock=clock)
    assert [limit.check(address) for address in "abc"] == [None, None, None]
    clock.now += 3600
    assert limit.check("d") == pytest.approx(86400 - 3600)  # a new address doesn't help
    clock.now += 86400 - 3600
    assert limit.check("d") is None


def test_budget_stops_when_the_day_is_spent_and_resets_the_next_day():
    clock = Clock()
    budget = Budget(seconds_per_day=10, clock=clock)
    with budget.spend():
        clock.now += 6
    assert budget.wait() is None
    with pytest.raises(RuntimeError), budget.spend():  # failed work is still paid for
        clock.now += 5
        raise RuntimeError
    assert budget.wait() == pytest.approx(86400 - 11)
    clock.now += 86400
    assert budget.wait() is None


def test_each_address_is_limited_and_refusals_say_when_to_retry(tmp_path, body):
    client = make_client(tmp_path, simulate_per_minute=3, deep_per_minute=1)
    light = body | {"series": False}
    assert [client.post("/simulate", json=light).status_code for _ in range(4)] == [200, 200, 200, 429]
    refused = client.post("/simulate", json=light)
    assert 0 < int(refused.headers["retry-after"]) <= 60
    assert "browser" in refused.json()["detail"]
    assert client.get("/health").status_code == 200  # cheap endpoints stay open
    assert [client.post("/analyze/deep", json=body).status_code for _ in range(2)] == [200, 429]  # its own allowance


def test_invalid_requests_count_towards_the_limit(tmp_path, body):
    client = make_client(tmp_path, simulate_per_minute=2)
    bad = {"scenario": body["scenario"] | {"days": 99999}}
    assert [client.post("/simulate", json=bad).status_code for _ in range(3)] == [422, 422, 429]


def test_the_caller_is_the_address_the_platform_appended(tmp_path, body):
    """Cloud Run appends the real address to X-Forwarded-For; anything before it is the caller's claim."""
    client = make_client(tmp_path, simulate_per_minute=1)
    light = body | {"series": False}

    def call(forwarded: str) -> int:
        return client.post("/simulate", json=light, headers={"x-forwarded-for": forwarded}).status_code

    assert call("203.0.113.7") == 200
    assert call("1.2.3.4, 203.0.113.7") == 429  # a spoofed first entry doesn't buy a new allowance
    assert call("203.0.113.7, 198.51.100.9") == 200  # a different caller


@pytest.mark.parametrize("spent", [{"compute_seconds_per_day": 0}, {"simulate_per_day": 0, "deep_per_day": 0}])
def test_the_daily_limits_close_the_expensive_endpoints(tmp_path, body, spent):
    client = make_client(tmp_path, **spent)
    for endpoint in ("/simulate", "/analyze/deep"):
        refused = client.post(endpoint, json=body)
        assert refused.status_code == 429
        assert "today" in refused.json()["detail"]
        assert int(refused.headers["retry-after"]) > 3600
    assert client.get("/health").status_code == 200


def test_large_answers_are_compressed(client, body):
    plain = client.post("/simulate", json=body, headers={"accept-encoding": "identity"})
    packed = client.post("/simulate", json=body, headers={"accept-encoding": "gzip"})
    assert "content-encoding" not in plain.headers and packed.headers["content-encoding"] == "gzip"
    assert packed.json()["series"] == plain.json()["series"]
    assert int(packed.headers["content-length"]) < int(plain.headers["content-length"]) / 2


def test_only_one_deep_analysis_runs_at_a_time(tmp_path, body, monkeypatch):
    started, release = threading.Event(), threading.Event()
    real = analysis.sobol

    def slow(*args, **kwargs):
        started.set()
        release.wait(timeout=10)
        return real(*args, **kwargs)

    monkeypatch.setattr(analysis, "sobol", slow)
    app = create_app(Settings(deep_draws=50, sobol_n=16, deep_wait_seconds=0.05, model_card_path=tmp_path / "none.json"))
    statuses = []
    first = threading.Thread(target=lambda: statuses.append(TestClient(app).post("/analyze/deep", json=body).status_code))
    first.start()
    try:
        assert started.wait(timeout=10)
        busy = TestClient(app).post("/analyze/deep", json=body)
        assert busy.status_code == 503 and busy.headers["retry-after"] == "15"
    finally:
        release.set()
        first.join(timeout=20)
    assert statuses == [200]
    assert TestClient(app).post("/analyze/deep", json=body).status_code == 200  # the slot was released


# --------------------------------------------------------------------------- browsers


def test_only_the_dashboard_may_call_from_a_browser(tmp_path, body):
    client = make_client(tmp_path, simulate_per_minute=1)
    preflight = {"origin": ORIGIN, "access-control-request-method": "POST", "access-control-request-headers": "content-type"}
    allowed = client.options("/analyze/deep", headers=preflight)
    assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == ORIGIN
    elsewhere = client.options("/analyze/deep", headers=preflight | {"origin": "https://example.com"})
    assert elsewhere.status_code == 400 and "access-control-allow-origin" not in elsewhere.headers

    assert client.post("/simulate", json=body, headers={"origin": ORIGIN}).headers["access-control-allow-origin"] == ORIGIN
    refused = client.post("/simulate", json=body, headers={"origin": ORIGIN})
    assert refused.status_code == 429  # the browser can read a refusal and when to retry
    assert refused.headers["access-control-allow-origin"] == ORIGIN
    assert "retry-after" in refused.headers["access-control-expose-headers"].lower()


# --------------------------------------------------------------------------- packaging


def test_the_published_schema_is_up_to_date():
    """The dashboard validates its scenarios against this file: regenerate it with `python -m api.schemas`."""
    assert json.loads(schemas.SCHEMA_PATH.read_text()) == schemas.scenario_schema()


def test_the_service_needs_only_its_own_requirements():
    """The image installs api/requirements.txt, not the pipeline's dependencies: importing the app must not need them."""
    code = (
        "import sys\n"
        "for heavy in ('pandas', 'sklearn', 'statsmodels', 'duckdb', 'pyarrow', 'pycountry'):\n"
        "    sys.modules[heavy] = None\n"  # makes `import pandas` raise ImportError
        "import api.main\n"
        "print(sorted(r.path for r in api.main.app.routes if r.path.startswith(('/s', '/a'))))\n"
    )
    env = {"PYTHONPATH": f"{ROOT}:{ROOT / 'src'}"}
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['/analyze/deep', '/simulate']"
    listed = {line.split("==")[0] for line in (ROOT / "api" / "requirements.txt").read_text().split() if "==" in line}
    assert {"numpy", "scipy", "fastapi", "uvicorn"} <= listed
