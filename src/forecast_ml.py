from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CLEAN_WEEKLY_PATH, FORECAST_TOP5_METRICS_PATH, PROCESSED_DIR, REPORTS_DIR, ensure_directories

try:
    from xgboost import XGBRegressor

    MODEL_NAME = "XGBoost"

    def _make_model() -> XGBRegressor:
        return XGBRegressor(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            objective="reg:squarederror",
        )

except Exception:  # pragma: no cover - fallback path only used when xgboost missing
    MODEL_NAME = "LinearRegressionNumpy"

    class NumpyLinearRegressor:
        def __init__(self) -> None:
            self.coef_: np.ndarray | None = None
            self.mean_: np.ndarray | None = None
            self.std_: np.ndarray | None = None

        def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
            x = np.asarray(X, dtype=float)
            y_arr = np.asarray(y, dtype=float)
            self.mean_ = x.mean(axis=0)
            self.std_ = x.std(axis=0)
            self.std_[self.std_ == 0] = 1.0
            x = (x - self.mean_) / self.std_
            ones = np.ones((x.shape[0], 1))
            design = np.hstack([ones, x])
            ridge = 1e-4 * np.eye(design.shape[1])
            self.coef_ = np.linalg.solve(design.T @ design + ridge, design.T @ y_arr)

        def predict(self, X: pd.DataFrame) -> np.ndarray:
            if self.coef_ is None or self.mean_ is None or self.std_ is None:
                raise ValueError("Model is not trained.")
            x = np.asarray(X, dtype=float)
            x = (x - self.mean_) / self.std_
            ones = np.ones((x.shape[0], 1))
            design = np.hstack([ones, x])
            return design @ self.coef_

    def _make_model() -> NumpyLinearRegressor:
        return NumpyLinearRegressor()


def _mae(y_true: pd.Series, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float))))


def _rmse(y_true: pd.Series, y_pred: np.ndarray) -> float:
    err = np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean(err**2)))


def _make_features(country_df: pd.DataFrame) -> pd.DataFrame:
    df = country_df.copy().sort_values("date")
    target = "new_deaths"
    df[target] = pd.to_numeric(df[target], errors="coerce").fillna(0.0)
    df["vaccination_rate"] = pd.to_numeric(df.get("vaccination_rate"), errors="coerce").ffill().bfill().fillna(0.0)
    df["cases_per_million"] = pd.to_numeric(df.get("cases_per_million"), errors="coerce").ffill().bfill().fillna(0.0)

    for lag in [1, 2, 3, 4, 8]:
        df[f"lag_{lag}"] = df[target].shift(lag)

    df["rolling_4_mean_deaths"] = df[target].rolling(4).mean().shift(1)
    df["rolling_8_mean_deaths"] = df[target].rolling(8).mean().shift(1)
    df["week_of_year"] = pd.to_datetime(df["date"]).dt.isocalendar().week.astype(int)
    df["month"] = pd.to_datetime(df["date"]).dt.month

    features = [
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_4",
        "lag_8",
        "rolling_4_mean_deaths",
        "rolling_8_mean_deaths",
        "week_of_year",
        "month",
        "vaccination_rate",
        "cases_per_million",
    ]

    model_df = df[["date", target] + features].dropna().copy()
    return model_df


def _naive_forecast(country_df: pd.DataFrame, horizon_weeks: int, country: str) -> pd.DataFrame:
    base = pd.to_numeric(country_df["new_deaths"], errors="coerce").fillna(0.0)
    baseline = float(base.tail(4).mean() if len(base) >= 4 else base.iloc[-1])
    last_date = pd.to_datetime(country_df["date"]).max()
    rows = []
    for step in range(1, horizon_weeks + 1):
        rows.append(
            {
                "date": last_date + pd.Timedelta(days=7 * step),
                "pred_new_deaths": max(baseline, 0.0),
                "country": country,
            }
        )
    return pd.DataFrame(rows)


def train_and_forecast_country(
    country: str = "India",
    horizon_weeks: int = 12,
    input_path: Path = CLEAN_WEEKLY_PATH,
) -> dict:
    ensure_directories()

    weekly = pd.read_csv(input_path, parse_dates=["date"])
    country_df = weekly[weekly["location"] == country].copy()

    if len(country_df) < 20:
        raise ValueError(f"Not enough weekly data for {country} to train model.")

    model_df = _make_features(country_df)
    if len(model_df) < 10:
        forecast_df = _naive_forecast(country_df, horizon_weeks, country)
        forecast_path = PROCESSED_DIR / f"forecast_{country.lower().replace(' ', '_')}.csv"
        forecast_df.to_csv(forecast_path, index=False)
        metrics = {
            "country": country,
            "model": "NaiveMovingAverage",
            "train_rows": int(len(model_df)),
            "test_rows": 0,
            "mae": None,
            "rmse": None,
            "mape_pct": None,
            "feature_importance": {},
            "forecast_output": str(forecast_path),
        }
        metrics_path = REPORTS_DIR / f"forecast_metrics_{country.lower().replace(' ', '_')}.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
        return metrics

    split_idx = int(len(model_df) * 0.8)

    train = model_df.iloc[:split_idx]
    test = model_df.iloc[split_idx:]

    X_train = train.drop(columns=["date", "new_deaths"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y_train = train["new_deaths"]
    X_test = test.drop(columns=["date", "new_deaths"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y_test = test["new_deaths"]

    model = _make_model()
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    mae = _mae(y_test, pred)
    rmse = _rmse(y_test, pred)
    mape = float((np.abs((y_test - pred) / np.maximum(y_test, 1))).mean() * 100)

    feature_importance = {}
    if hasattr(model, "feature_importances_"):
        feature_importance = {
            col: float(val)
            for col, val in sorted(
                zip(X_train.columns, model.feature_importances_),
                key=lambda x: x[1],
                reverse=True,
            )
        }

    forecast_rows = []
    working = country_df.sort_values("date").copy()
    for _ in range(horizon_weeks):
        next_date = working["date"].max() + pd.Timedelta(days=7)
        row = {
            "date": next_date,
            "new_deaths": np.nan,
            "vaccination_rate": working["vaccination_rate"].iloc[-1],
            "cases_per_million": working["cases_per_million"].iloc[-1],
        }
        working = pd.concat([working, pd.DataFrame([row])], ignore_index=True)

        tmp = _make_features(working)
        if tmp.empty:
            y_next = float(pd.to_numeric(working["new_deaths"], errors="coerce").fillna(0.0).tail(4).mean())
        else:
            X_next = tmp.drop(columns=["date", "new_deaths"]).replace([np.inf, -np.inf], np.nan).fillna(0.0).iloc[[-1]]
            y_next = float(model.predict(X_next)[0])
        working.loc[working.index[-1], "new_deaths"] = max(y_next, 0.0)

        forecast_rows.append({"date": next_date, "pred_new_deaths": max(y_next, 0.0), "country": country})

    forecast_df = pd.DataFrame(forecast_rows)
    forecast_path = PROCESSED_DIR / f"forecast_{country.lower().replace(' ', '_')}.csv"
    forecast_df.to_csv(forecast_path, index=False)

    metrics = {
        "country": country,
        "model": MODEL_NAME,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape_pct": round(mape, 4),
        "feature_importance": feature_importance,
        "forecast_output": str(forecast_path),
    }

    metrics_path = REPORTS_DIR / f"forecast_metrics_{country.lower().replace(' ', '_')}.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return metrics


def train_and_forecast_top_countries(
    top_n: int = 5,
    horizon_weeks: int = 12,
    input_path: Path = CLEAN_WEEKLY_PATH,
) -> dict:
    weekly = pd.read_csv(input_path, parse_dates=["date"], low_memory=False)
    top_countries = (
        weekly.groupby("location", as_index=False)["new_deaths"]
        .sum()
        .sort_values("new_deaths", ascending=False)
        .head(top_n)["location"]
        .tolist()
    )

    results = []
    for country in top_countries:
        results.append(train_and_forecast_country(country=country, horizon_weeks=horizon_weeks, input_path=input_path))

    summary = {
        "top_n": top_n,
        "countries": top_countries,
        "horizon_weeks": horizon_weeks,
        "results": results,
    }
    with open(FORECAST_TOP5_METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary
