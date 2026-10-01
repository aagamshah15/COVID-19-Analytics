from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from .config import POSTGRES_SCHEMA_PATH
from .warehouse import build_star_schema_frames


def load_star_schema_postgres(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    postgres_url: str,
    schema_path: Path = POSTGRES_SCHEMA_PATH,
) -> dict[str, int]:
    frames = build_star_schema_frames(daily=daily, weekly=weekly)

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fact_covid_weekly"))
        conn.execute(text("DROP TABLE IF EXISTS fact_covid_daily"))
        conn.execute(text("DROP TABLE IF EXISTS dim_country"))
        conn.execute(text("DROP TABLE IF EXISTS dim_date"))

        with open(schema_path, "r", encoding="utf-8") as f:
            conn.execute(text(f.read()))

    for table_name in ["dim_date", "dim_country", "fact_covid_daily", "fact_covid_weekly"]:
        frames[table_name].to_sql(table_name, engine, if_exists="append", index=False)

    counts = {}
    with engine.begin() as conn:
        for table_name in ["dim_date", "dim_country", "fact_covid_daily", "fact_covid_weekly"]:
            counts[table_name] = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()

    return counts
