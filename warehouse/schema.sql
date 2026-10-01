-- Star schema for the COVID-19 healthcare burden warehouse.
-- Portable across DuckDB and PostgreSQL (DOUBLE PRECISION / VARCHAR(n) are accepted by both).
--
-- Grain
--   fact_covid_daily     one row per country per day
--   fact_covid_weekly    one row per country per ISO week (date_key = week-ending Sunday)
--   fact_forecast_weekly one row per country per forecast target week
--
-- Metric conventions: weekly_* are flows (safe to sum/average over time); cumulative_* are
-- running totals (take the latest value, never average them across dates); *_rate are shares (0-1).

DROP TABLE IF EXISTS fact_forecast_weekly;
DROP TABLE IF EXISTS fact_covid_weekly;
DROP TABLE IF EXISTS fact_covid_daily;
DROP TABLE IF EXISTS dim_country;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,           -- YYYYMMDD
    date            DATE NOT NULL UNIQUE,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      VARCHAR(12) NOT NULL,
    day             INTEGER NOT NULL,
    iso_year        INTEGER NOT NULL,
    iso_week        INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,              -- 1 = Monday ... 7 = Sunday
    is_week_end     BOOLEAN NOT NULL               -- Sunday: the key used by weekly facts
);

CREATE TABLE dim_country (
    country_key                 INTEGER PRIMARY KEY,
    iso_code                    VARCHAR(10) NOT NULL UNIQUE,
    country_name                VARCHAR(100) NOT NULL,
    continent                   VARCHAR(20),
    who_region                  VARCHAR(10),
    population                  BIGINT,
    hospital_beds_per_thousand  DOUBLE PRECISION,
    median_age                  DOUBLE PRECISION,
    gdp_per_capita              DOUBLE PRECISION,
    life_expectancy             DOUBLE PRECISION,
    human_development_index     DOUBLE PRECISION
);

CREATE TABLE fact_covid_daily (
    date_key                       INTEGER NOT NULL REFERENCES dim_date (date_key),
    country_key                    INTEGER NOT NULL REFERENCES dim_country (country_key),
    new_cases                      DOUBLE PRECISION,
    new_deaths                     DOUBLE PRECISION,
    rolling_7d_cases               DOUBLE PRECISION,
    rolling_7d_deaths              DOUBLE PRECISION,
    rolling_7d_deaths_per_million  DOUBLE PRECISION,
    cumulative_cases_per_million   DOUBLE PRECISION,
    cumulative_deaths_per_million  DOUBLE PRECISION,
    case_fatality_rate             DOUBLE PRECISION,
    first_dose_rate                DOUBLE PRECISION,
    vaccination_rate               DOUBLE PRECISION,
    booster_rate                   DOUBLE PRECISION,
    hosp_patients_per_million      DOUBLE PRECISION,
    icu_patients_per_million       DOUBLE PRECISION,
    covid_bed_occupancy_share      DOUBLE PRECISION,
    PRIMARY KEY (date_key, country_key)
);

CREATE TABLE fact_covid_weekly (
    date_key                       INTEGER NOT NULL REFERENCES dim_date (date_key),
    country_key                    INTEGER NOT NULL REFERENCES dim_country (country_key),
    new_cases                      DOUBLE PRECISION,
    new_deaths                     DOUBLE PRECISION,
    weekly_cases_per_million       DOUBLE PRECISION,
    weekly_deaths_per_million      DOUBLE PRECISION,
    cumulative_cases_per_million   DOUBLE PRECISION,
    cumulative_deaths_per_million  DOUBLE PRECISION,
    case_fatality_rate             DOUBLE PRECISION,
    first_dose_rate                DOUBLE PRECISION,
    vaccination_rate               DOUBLE PRECISION,
    booster_rate                   DOUBLE PRECISION,
    hosp_patients_per_million      DOUBLE PRECISION,
    icu_patients_per_million       DOUBLE PRECISION,
    covid_bed_occupancy_share      DOUBLE PRECISION,
    PRIMARY KEY (date_key, country_key)
);

CREATE TABLE fact_forecast_weekly (
    date_key            INTEGER NOT NULL REFERENCES dim_date (date_key),   -- target week
    country_key         INTEGER NOT NULL REFERENCES dim_country (country_key),
    origin_date_key     INTEGER NOT NULL REFERENCES dim_date (date_key),   -- last observed week
    horizon_weeks       INTEGER NOT NULL,
    predicted_deaths    DOUBLE PRECISION NOT NULL,
    lower_80            DOUBLE PRECISION,
    upper_80            DOUBLE PRECISION,
    model               VARCHAR(50) NOT NULL,
    PRIMARY KEY (date_key, country_key)
);
