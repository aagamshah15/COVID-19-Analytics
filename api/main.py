"""Pandemic simulator API: the reference engine as a small web service.

The dashboard runs every scenario in the browser and never depends on this service. It exists for
two things the browser can't do well: a deep analysis (thousands of draws and Sobol sensitivity
indices) and programmatic access to the reference engine.

    GET  /health         liveness, the size of a deep analysis, and the bundled model card's version
    GET  /model          the bundled model card: learned constants, uncertainty and validation
    POST /simulate       run a scenario: headline numbers, daily series, optional Monte Carlo ranges
    POST /analyze/deep   2,000-draw ranges and Sobol sensitivity indices for a scenario

A scenario is the JSON the browser's engine consumes; ``schemas.py`` bounds every number in it.
Run locally with ``uvicorn api.main:app --reload --port 8080``; interactive docs are at ``/docs``.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from covid_pipeline.simulator import analysis

from . import schemas
from .limits import BodyLimit, Budget, Limit

VERSION = "1.0.0"
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("simulator-api")

SERIES = (
    "infections",
    "reported_cases",
    "admissions",
    "hospital",
    "icu",
    "deaths",
    "reported_deaths",
    "rt",
    "stringency",
    "vaccinated",
    "susceptible",
    "infected",
    "immune",
    "dead",
)
MODEL_CARD_KEYS = ("version", "trained_at", "constants", "uncertainty", "validation")
MAX_BODY_BYTES = 64 * 1024
MAX_PROBLEMS = 20  # validation problems reported for one request
DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:5174,https://aagamshah15.github.io"
BUSY = "Too many requests. The simulator in the dashboard runs in your browser and has no limit."
SPENT = "The service has reached its free limit for today. The simulator in the dashboard still runs in your browser."


@dataclass
class Settings:
    allowed_origins: list[str] = field(default_factory=lambda: DEFAULT_ORIGINS.split(","))
    # Sized to Cloud Run's free tier. It includes 1 GB of data sent out a month, about 33 MB a day.
    # The largest compressed answers are about 75 KB (simulate) and 25 KB (deep), so a day at these
    # limits sends at most 28 MB.
    simulate_per_minute: int = 30
    simulate_per_day: int = 300
    deep_per_minute: int = 4
    deep_per_day: int = 200
    # It also includes 180,000 vCPU-seconds a month, about 5,800 a day. This leaves room for
    # start-ups and health checks.
    compute_seconds_per_day: int = 4000
    # Sized by timing on Cloud Run, where one run of a two-year scenario takes about 6 ms: 2,000
    # draws plus 3,328 runs for the Sobol design come to about half a minute. Halving sobol_n
    # would save a third of that, but the ranking of the inputs then changes from seed to seed.
    deep_draws: int = 2000
    sobol_n: int = 256
    deep_wait_seconds: float = 20.0
    model_card_path: Path = Path(__file__).parent / "model" / "simulator.json"

    @classmethod
    def from_env(cls) -> Settings:
        s = cls()
        s.allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]
        for f in fields(cls):  # every whole-number setting can be overridden, e.g. DEEP_PER_DAY=50
            if f.type == "int" and f.name.upper() in os.environ:
                setattr(s, f.name, int(os.environ[f.name.upper()]))
        s.model_card_path = Path(os.environ.get("MODEL_CARD_PATH", s.model_card_path))
        return s


def significant(values: np.ndarray, digits: int = 6) -> list[float]:
    """Round to ``digits`` significant figures: a third of the payload of full doubles."""
    a = np.asarray(values, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        magnitude = np.where(a != 0, np.floor(np.log10(np.abs(a))), 0.0)
    factor = 10.0 ** (digits - 1 - magnitude)
    return (np.round(a * factor) / factor).tolist()


def finite(value):
    """JSON can't carry NaN or infinity: send null instead."""
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def client_address(request: Request) -> str:
    """The caller's address. Cloud Run appends the address it saw to X-Forwarded-For, so the last
    entry is trustworthy; earlier entries are whatever the caller chose to send."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def load_model_card(path: Path) -> dict | None:
    if not path.exists():
        return None
    model = json.loads(path.read_text())
    card = {k: model.get(k) for k in MODEL_CARD_KEYS}
    card["countries"] = len(model.get("countries", []))
    card["presets"] = [{"id": p["id"], "name": p["name"], "r0": p["r0"], "ifr": p["ifr"]} for p in model.get("presets", [])]
    return finite(card)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    card = load_model_card(settings.model_card_path)
    budget = Budget(settings.compute_seconds_per_day)
    deep_slot = threading.BoundedSemaphore(1)  # one heavy analysis at a time on one vCPU

    app = FastAPI(
        title="Pandemic simulator API",
        version=VERSION,
        description="The reference engine behind the COVID-19 Analytics pandemic simulator. Scenarios, not forecasts.",
    )
    app.add_middleware(BodyLimit, limit=MAX_BODY_BYTES)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    # Added last so it wraps everything: refusals carry CORS headers too and the browser can read them.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
        expose_headers=["retry-after"],
        max_age=86400,
    )

    @app.exception_handler(RequestValidationError)
    def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        """Say what is wrong without sending the caller's input back (the default echoes it)."""
        problems = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()[:MAX_PROBLEMS]]
        return JSONResponse({"detail": problems}, status_code=422)

    def guard(per_minute: int, per_day: int):
        """A dependency, so it runs (and counts the call) before the body is validated."""
        limit = Limit(per_minute, per_day)

        def check(request: Request) -> None:
            wait = budget.wait()
            if wait is None:
                wait = limit.check(client_address(request))
            if wait is not None:
                raise HTTPException(429, BUSY if wait <= 60 else SPENT, headers={"Retry-After": str(math.ceil(wait))})

        return Depends(check)

    def scenario_of(body: schemas.Scenario) -> analysis.ScenarioRun:
        return analysis.ScenarioRun.from_dict(body.model_dump())

    @app.get("/")
    def index() -> dict:
        return {"name": app.title, "version": VERSION, "docs": "/docs", "endpoints": ["/health", "/model", "/simulate", "/analyze/deep"]}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "model_version": card["version"] if card else None, "deep_draws": settings.deep_draws}

    @app.get("/model")
    def model() -> dict:
        if card is None:
            raise HTTPException(404, "No model card is bundled with this build.")
        return card

    @app.post("/simulate", dependencies=[guard(settings.simulate_per_minute, settings.simulate_per_day)])
    def simulate(body: schemas.SimulateRequest) -> dict:
        started = time.perf_counter()
        s = scenario_of(body.scenario)
        with budget.spend():
            out, summary = analysis.central(s)
            _, baseline = analysis.central(analysis.without_response(s), capacity=s.capacity())
            result: dict = {
                "days": s.days,
                "hospital_capacity": s.capacity(),
                "summary": summary,
                "no_response": baseline,
                "deaths_by_age": significant(out.deaths_by_age[0]),
            }
            if body.series:
                result["series"] = {k: significant(getattr(out, k)[0]) for k in SERIES}
            if body.draws:
                result["ensemble"] = analysis.monte_carlo(s, body.draws, body.seed)
        result["ms"] = round((time.perf_counter() - started) * 1000)
        log.info("simulate days=%d draws=%d ms=%d", s.days, body.draws, result["ms"])
        return finite(result)

    @app.post("/analyze/deep", dependencies=[guard(settings.deep_per_minute, settings.deep_per_day)])
    def deep(body: schemas.DeepRequest) -> dict:
        if not deep_slot.acquire(timeout=settings.deep_wait_seconds):
            raise HTTPException(503, "Another deep analysis is running. Try again in a moment.", headers={"Retry-After": "15"})
        try:
            started = time.perf_counter()
            s = scenario_of(body.scenario)
            with budget.spend():
                _, summary = analysis.central(s)
                result = {
                    "summary": summary,
                    "monte_carlo": analysis.monte_carlo(s, settings.deep_draws, body.seed),
                    "sobol": analysis.sobol(s, settings.sobol_n, body.seed),
                }
            result["ms"] = round((time.perf_counter() - started) * 1000)
            log.info("deep days=%d draws=%d sobol_runs=%d ms=%d", s.days, settings.deep_draws, result["sobol"]["evaluations"], result["ms"])
            return finite(result)
        finally:
            deep_slot.release()

    return app


app = create_app()
