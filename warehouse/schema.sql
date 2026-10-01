CREATE TABLE IF NOT EXISTS dim_date (
    date_key       INTEGER PRIMARY KEY,
    date           DATE,
    day            INTEGER,
    month          INTEGER,
    month_name     VARCHAR,
    quarter        INTEGER,
    year           INTEGER,
    iso_week       INTEGER
);

CREATE TABLE IF NOT EXISTS dim_country (
    country_key                  INTEGER PRIMARY KEY,
    iso_code                     VARCHAR,
    country_name                 VARCHAR,
    continent                    VARCHAR,
    population                   BIGINT,
    hospital_beds_per_thousand   DOUBLE,
    aged_65_older                DOUBLE,
    gdp_per_capita               DOUBLE
);

CREATE TABLE IF NOT EXISTS fact_covid_daily (
    fact_daily_key        BIGINT PRIMARY KEY,
    date_key              INTEGER REFERENCES dim_date(date_key),
    country_key           INTEGER REFERENCES dim_country(country_key),
    new_cases             DOUBLE,
    new_deaths            DOUBLE,
    rolling_7d_cases      DOUBLE,
    rolling_7d_deaths     DOUBLE,
    cases_per_million     DOUBLE,
    deaths_per_million    DOUBLE,
    case_fatality_rate    DOUBLE,
    vaccination_rate      DOUBLE
);

CREATE TABLE IF NOT EXISTS fact_covid_weekly (
    fact_weekly_key       BIGINT PRIMARY KEY,
    date_key              INTEGER REFERENCES dim_date(date_key),
    country_key           INTEGER REFERENCES dim_country(country_key),
    new_cases             DOUBLE,
    new_deaths            DOUBLE,
    rolling_7d_cases      DOUBLE,
    rolling_7d_deaths     DOUBLE,
    cases_per_million     DOUBLE,
    deaths_per_million    DOUBLE,
    case_fatality_rate    DOUBLE,
    vaccination_rate      DOUBLE
);
