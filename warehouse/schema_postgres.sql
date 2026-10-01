CREATE TABLE IF NOT EXISTS dim_date (
    date_key       INTEGER PRIMARY KEY,
    date           DATE,
    day            INTEGER,
    month          INTEGER,
    month_name     VARCHAR(20),
    quarter        INTEGER,
    year           INTEGER,
    iso_week       INTEGER
);

CREATE TABLE IF NOT EXISTS dim_country (
    country_key                  INTEGER PRIMARY KEY,
    iso_code                     VARCHAR(10),
    country_name                 VARCHAR(150),
    continent                    VARCHAR(50),
    population                   BIGINT,
    hospital_beds_per_thousand   DOUBLE PRECISION,
    aged_65_older                DOUBLE PRECISION,
    gdp_per_capita               DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS fact_covid_daily (
    fact_daily_key        BIGINT PRIMARY KEY,
    date_key              INTEGER REFERENCES dim_date(date_key),
    country_key           INTEGER REFERENCES dim_country(country_key),
    new_cases             DOUBLE PRECISION,
    new_deaths            DOUBLE PRECISION,
    rolling_7d_cases      DOUBLE PRECISION,
    rolling_7d_deaths     DOUBLE PRECISION,
    cases_per_million     DOUBLE PRECISION,
    deaths_per_million    DOUBLE PRECISION,
    case_fatality_rate    DOUBLE PRECISION,
    vaccination_rate      DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS fact_covid_weekly (
    fact_weekly_key       BIGINT PRIMARY KEY,
    date_key              INTEGER REFERENCES dim_date(date_key),
    country_key           INTEGER REFERENCES dim_country(country_key),
    new_cases             DOUBLE PRECISION,
    new_deaths            DOUBLE PRECISION,
    rolling_7d_cases      DOUBLE PRECISION,
    rolling_7d_deaths     DOUBLE PRECISION,
    cases_per_million     DOUBLE PRECISION,
    deaths_per_million    DOUBLE PRECISION,
    case_fatality_rate    DOUBLE PRECISION,
    vaccination_rate      DOUBLE PRECISION
);
