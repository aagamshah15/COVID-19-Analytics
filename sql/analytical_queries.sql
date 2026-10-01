-- COVID-19 healthcare burden: analytical query pack
-- Runs against the star schema in warehouse/schema.sql (DuckDB or PostgreSQL; no dialect-only syntax).
--
-- Rules these queries follow
--   * Flows (new_*, weekly_*) are summed or averaged over time.
--   * Cumulative metrics (cumulative_*, *_rate) are read at a single point in time, never averaged
--     across dates (averaging a running total over time weights early and late periods arbitrarily).
--   * Cross-country rates are population-weighted: SUM(deaths) / SUM(population), not AVG(rate).
--   * Weeks where a country stopped reporting are NULL (not zero), so SUM/AVG ignore them.
--   * Country rankings exclude populations under 1M, where one death swings per-million rates.
--
-- Each query starts with a "-- name:" line; tests/test_sql_pack.py executes every one of them.

-- ===================================================================== A. Executive pulse

-- name: q01_executive_kpis
-- Headline KPI tiles for the whole window.
WITH latest AS (
    SELECT MAX(date_key) AS date_key FROM fact_covid_weekly
)
SELECT
    COUNT(DISTINCT f.country_key)                                   AS countries,
    MIN(d.date)                                                     AS first_week,
    MAX(d.date)                                                     AS last_week,
    SUM(f.new_cases)                                                AS total_cases,
    SUM(f.new_deaths)                                               AS total_deaths,
    SUM(f.new_deaths) / NULLIF(SUM(f.new_cases), 0)                 AS overall_cfr,
    (SELECT SUM(w.vaccination_rate * c.population) / SUM(c.population)
       FROM fact_covid_weekly w
       JOIN dim_country c ON c.country_key = w.country_key
       JOIN latest l ON l.date_key = w.date_key
      WHERE w.vaccination_rate IS NOT NULL)                         AS fully_vaccinated_share_at_end
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key;

-- name: q02_global_weekly_trend
-- Global weekly cases and deaths with a 4-week moving average of deaths.
SELECT
    d.date                                                          AS week_end,
    SUM(f.new_cases)                                                AS global_cases,
    SUM(f.new_deaths)                                               AS global_deaths,
    AVG(SUM(f.new_deaths)) OVER (ORDER BY d.date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS deaths_4wk_avg
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY d.date
ORDER BY d.date;

-- name: q03_global_deaths_per_million_weekly
-- Population-weighted weekly deaths per million across countries that reported that week.
SELECT
    d.date                                                          AS week_end,
    SUM(f.new_deaths) * 1e6 / SUM(c.population)                     AS deaths_per_million,
    COUNT(*)                                                        AS reporting_countries
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key
JOIN dim_country c ON c.country_key = f.country_key
WHERE f.new_deaths IS NOT NULL
GROUP BY d.date
ORDER BY d.date;

-- name: q04_deaths_by_year_and_continent
SELECT
    d.year,
    c.continent,
    SUM(f.new_deaths)                                               AS deaths,
    SUM(f.new_deaths) / SUM(SUM(f.new_deaths)) OVER (PARTITION BY d.year) AS share_of_year
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY d.year, c.continent
ORDER BY d.year, deaths DESC;

-- name: q05_deadliest_global_weeks
SELECT week_end, global_deaths, deaths_rank
FROM (
    SELECT
        d.date                                                      AS week_end,
        SUM(f.new_deaths)                                           AS global_deaths,
        RANK() OVER (ORDER BY SUM(f.new_deaths) DESC)               AS deaths_rank
    FROM fact_covid_weekly f
    JOIN dim_date d ON d.date_key = f.date_key
    GROUP BY d.date
) ranked
WHERE deaths_rank <= 10
ORDER BY deaths_rank;

-- ===================================================================== B. Country burden

-- name: q06_top_countries_cumulative_deaths_per_million
-- Cumulative deaths per million at the end of the window (the fair cross-country burden measure).
SELECT c.country_name, c.continent, f.cumulative_deaths_per_million, f.case_fatality_rate
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
WHERE f.date_key = (SELECT MAX(date_key) FROM fact_covid_weekly)
  AND c.population >= 1000000
  AND f.cumulative_deaths_per_million IS NOT NULL
ORDER BY f.cumulative_deaths_per_million DESC
LIMIT 15;

-- name: q07_peak_weekly_deaths_per_million
-- Worst single week per country and when it happened.
SELECT country_name, continent, peak_week, weekly_deaths_per_million
FROM (
    SELECT
        c.country_name,
        c.continent,
        d.date                                                      AS peak_week,
        f.weekly_deaths_per_million,
        ROW_NUMBER() OVER (PARTITION BY c.country_key ORDER BY f.weekly_deaths_per_million DESC) AS rn
    FROM fact_covid_weekly f
    JOIN dim_country c ON c.country_key = f.country_key
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE c.population >= 1000000 AND f.weekly_deaths_per_million IS NOT NULL
) ranked
WHERE rn = 1
ORDER BY weekly_deaths_per_million DESC
LIMIT 20;

-- name: q08_continent_burden
-- Population-weighted deaths per million over the full window, by continent.
SELECT
    c.continent,
    SUM(f.new_deaths)                                               AS deaths,
    SUM(f.new_deaths) * 1e6 / (SELECT SUM(c2.population) FROM dim_country c2 WHERE c2.continent = c.continent) AS deaths_per_million
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY c.continent
ORDER BY deaths_per_million DESC;

-- name: q09_who_region_burden
SELECT
    COALESCE(c.who_region, 'Not assigned')                          AS who_region,
    COUNT(DISTINCT c.country_key)                                   AS countries,
    SUM(f.new_deaths)                                               AS deaths,
    SUM(f.new_cases)                                                AS cases,
    SUM(f.new_deaths) / NULLIF(SUM(f.new_cases), 0)                 AS cfr
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY COALESCE(c.who_region, 'Not assigned')
ORDER BY deaths DESC;

-- name: q10_deadliest_quarter_per_country
SELECT country_name, year, quarter, deaths
FROM (
    SELECT
        c.country_name,
        d.year,
        d.quarter,
        SUM(f.new_deaths)                                           AS deaths,
        ROW_NUMBER() OVER (PARTITION BY c.country_key ORDER BY SUM(f.new_deaths) DESC) AS rn
    FROM fact_covid_weekly f
    JOIN dim_country c ON c.country_key = f.country_key
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE c.population >= 1000000
    GROUP BY c.country_key, c.country_name, d.year, d.quarter
) ranked
WHERE rn = 1 AND deaths > 0
ORDER BY deaths DESC;

-- ===================================================================== C. Vaccination

-- name: q11_vaccination_rollout_by_continent
-- Population-weighted fully-vaccinated share at each quarter end.
SELECT
    d.year,
    d.quarter,
    c.continent,
    SUM(f.vaccination_rate * c.population) / SUM(c.population)      AS fully_vaccinated_share
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key
WHERE f.vaccination_rate IS NOT NULL
  AND d.date >= DATE '2020-12-01'
  AND f.date_key = (
        SELECT MAX(f2.date_key) FROM fact_covid_weekly f2 JOIN dim_date d2 ON d2.date_key = f2.date_key
        WHERE d2.year = d.year AND d2.quarter = d.quarter)
GROUP BY d.year, d.quarter, c.continent
ORDER BY d.year, d.quarter, c.continent;

-- name: q12_cfr_by_quarter
-- Global case fatality rate per quarter (flows): shows severity falling as immunity and treatment improved.
SELECT
    d.year,
    d.quarter,
    SUM(f.new_deaths) / NULLIF(SUM(f.new_cases), 0)                 AS cfr
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key
WHERE f.new_deaths IS NOT NULL AND f.new_cases IS NOT NULL
GROUP BY d.year, d.quarter
ORDER BY d.year, d.quarter;

-- name: q13_vaccination_tercile_vs_2022_mortality
-- Countries grouped by fully-vaccinated share at end-2021, compared on 2022 deaths per million and CFR.
-- Association, not causation: vaccination tracks income, age structure and testing intensity.
WITH vax_2021 AS (
    SELECT f.country_key, f.vaccination_rate
    FROM fact_covid_weekly f
    WHERE f.date_key = (SELECT MAX(date_key) FROM fact_covid_weekly WHERE date_key <= 20211231)
      AND f.vaccination_rate IS NOT NULL
), outcomes_2022 AS (
    SELECT f.country_key,
           SUM(f.new_deaths)                                        AS deaths,
           SUM(f.new_cases)                                         AS cases
    FROM fact_covid_weekly f
    WHERE f.date_key BETWEEN 20220101 AND 20221231
    GROUP BY f.country_key
), tagged AS (
    SELECT v.country_key, v.vaccination_rate, o.deaths, o.cases,
           NTILE(3) OVER (ORDER BY v.vaccination_rate)              AS tercile
    FROM vax_2021 v
    JOIN outcomes_2022 o ON o.country_key = v.country_key
    JOIN dim_country c ON c.country_key = v.country_key
    WHERE c.population >= 1000000
)
SELECT
    t.tercile,
    COUNT(*)                                                        AS countries,
    MIN(t.vaccination_rate)                                         AS min_vax_end_2021,
    MAX(t.vaccination_rate)                                         AS max_vax_end_2021,
    SUM(t.deaths) * 1e6 / SUM(c.population)                         AS deaths_per_million_2022,
    SUM(t.deaths) / NULLIF(SUM(t.cases), 0)                         AS cfr_2022
FROM tagged t
JOIN dim_country c ON c.country_key = t.country_key
GROUP BY t.tercile
ORDER BY t.tercile;

-- name: q14_mortality_around_50pct_vaccination
-- Average weekly deaths per million in the 26 weeks before vs after each country first reached 50%
-- fully vaccinated. Uses weekly flows; still confounded by variant waves (e.g. Omicron), so read it
-- alongside q12/q13 rather than as an effect estimate.
WITH crossing AS (
    SELECT f.country_key, MIN(d.date) AS crossed_on
    FROM fact_covid_weekly f
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE f.vaccination_rate >= 0.5
    GROUP BY f.country_key
), windowed AS (
    SELECT
        f.country_key,
        CASE WHEN d.date < x.crossed_on THEN 'before' ELSE 'after' END AS period,
        f.weekly_deaths_per_million
    FROM fact_covid_weekly f
    JOIN dim_date d ON d.date_key = f.date_key
    JOIN crossing x ON x.country_key = f.country_key
    WHERE d.date >= x.crossed_on - INTERVAL '182' DAY
      AND d.date <  x.crossed_on + INTERVAL '182' DAY
)
SELECT
    c.country_name,
    AVG(CASE WHEN period = 'before' THEN weekly_deaths_per_million END) AS avg_weekly_dpm_before,
    AVG(CASE WHEN period = 'after'  THEN weekly_deaths_per_million END) AS avg_weekly_dpm_after
FROM windowed w
JOIN dim_country c ON c.country_key = w.country_key
WHERE c.population >= 1000000
GROUP BY c.country_name
ORDER BY c.country_name;

-- ===================================================================== D. Health system strain

-- name: q15_peak_covid_bed_occupancy
-- Highest weekly share of total hospital bed capacity occupied by COVID-19 patients.
SELECT country_name, peak_week, covid_bed_occupancy_share, hosp_patients_per_million
FROM (
    SELECT
        c.country_name,
        d.date                                                      AS peak_week,
        f.covid_bed_occupancy_share,
        f.hosp_patients_per_million,
        ROW_NUMBER() OVER (PARTITION BY c.country_key ORDER BY f.covid_bed_occupancy_share DESC) AS rn
    FROM fact_covid_weekly f
    JOIN dim_country c ON c.country_key = f.country_key
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE f.covid_bed_occupancy_share IS NOT NULL
) ranked
WHERE rn = 1
ORDER BY covid_bed_occupancy_share DESC
LIMIT 20;

-- name: q16_peak_icu_load
SELECT c.country_name, MAX(f.icu_patients_per_million) AS peak_icu_patients_per_million
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
WHERE f.icu_patients_per_million IS NOT NULL
GROUP BY c.country_name
ORDER BY peak_icu_patients_per_million DESC
LIMIT 20;

-- name: q17_peer_groups_beds_and_age
-- 3x3 peer grid: hospital beds tercile x median age tercile -> end-of-window deaths per million.
WITH latest AS (
    SELECT f.country_key, f.cumulative_deaths_per_million
    FROM fact_covid_weekly f
    WHERE f.date_key = (SELECT MAX(date_key) FROM fact_covid_weekly)
), peers AS (
    SELECT
        c.country_key,
        c.population,
        l.cumulative_deaths_per_million,
        NTILE(3) OVER (ORDER BY c.hospital_beds_per_thousand)       AS beds_tercile,
        NTILE(3) OVER (ORDER BY c.median_age)                       AS age_tercile
    FROM dim_country c
    JOIN latest l ON l.country_key = c.country_key
    WHERE c.population >= 1000000
      AND c.hospital_beds_per_thousand IS NOT NULL
      AND c.median_age IS NOT NULL
      AND l.cumulative_deaths_per_million IS NOT NULL
)
SELECT
    beds_tercile,
    age_tercile,
    COUNT(*)                                                        AS countries,
    SUM(cumulative_deaths_per_million * population) / SUM(population) AS deaths_per_million
FROM peers
GROUP BY beds_tercile, age_tercile
ORDER BY beds_tercile, age_tercile;

-- name: q18_income_quartile_outcomes
WITH latest AS (
    SELECT f.country_key, f.cumulative_deaths_per_million, f.vaccination_rate
    FROM fact_covid_weekly f
    WHERE f.date_key = (SELECT MAX(date_key) FROM fact_covid_weekly)
), q AS (
    SELECT c.country_key, c.population, l.cumulative_deaths_per_million, l.vaccination_rate,
           NTILE(4) OVER (ORDER BY c.gdp_per_capita)                AS gdp_quartile
    FROM dim_country c
    JOIN latest l ON l.country_key = c.country_key
    WHERE c.gdp_per_capita IS NOT NULL AND c.population >= 1000000
)
SELECT
    gdp_quartile,
    COUNT(*)                                                        AS countries,
    SUM(cumulative_deaths_per_million * population) / SUM(population) AS deaths_per_million,
    SUM(vaccination_rate * population) / SUM(CASE WHEN vaccination_rate IS NOT NULL THEN population END) AS fully_vaccinated_share
FROM q
GROUP BY gdp_quartile
ORDER BY gdp_quartile;

-- ===================================================================== E. Segmentation, data coverage, outlook

-- name: q19_burden_vaccination_quadrants
-- Quadrant segmentation against the cross-country medians (end-of-window values).
WITH latest AS (
    SELECT c.country_name, c.continent, f.cumulative_deaths_per_million AS dpm, f.vaccination_rate AS vax
    FROM fact_covid_weekly f
    JOIN dim_country c ON c.country_key = f.country_key
    WHERE f.date_key = (SELECT MAX(date_key) FROM fact_covid_weekly)
      AND c.population >= 1000000
      AND f.cumulative_deaths_per_million IS NOT NULL
      AND f.vaccination_rate IS NOT NULL
), medians AS (
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dpm) AS dpm_median,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY vax) AS vax_median
    FROM latest
)
SELECT
    l.country_name,
    l.continent,
    l.dpm                                                           AS cumulative_deaths_per_million,
    l.vax                                                           AS vaccination_rate,
    CASE
        WHEN l.dpm >= m.dpm_median AND l.vax <  m.vax_median THEN 'High burden, low vaccination'
        WHEN l.dpm >= m.dpm_median AND l.vax >= m.vax_median THEN 'High burden, high vaccination'
        WHEN l.dpm <  m.dpm_median AND l.vax <  m.vax_median THEN 'Low burden, low vaccination'
        ELSE 'Low burden, high vaccination'
    END                                                             AS segment
FROM latest l
CROSS JOIN medians m
ORDER BY segment, l.dpm DESC;

-- name: q20_reporting_coverage
-- How long each country kept reporting deaths (NULL weeks = reporting stopped).
SELECT
    c.country_name,
    COUNT(*)                                                        AS weeks,
    COUNT(f.new_deaths)                                             AS weeks_with_death_reports,
    COUNT(f.new_deaths) * 1.0 / COUNT(*)                            AS reporting_share,
    MAX(CASE WHEN f.new_deaths IS NOT NULL THEN d.date END)         AS last_reported_week
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key
WHERE c.population >= 1000000
GROUP BY c.country_name
ORDER BY reporting_share, c.country_name;

-- name: q21_forecast_outlook
-- Recent actuals alongside the forecast for focus countries (empty until `covid-pipeline forecast` runs).
SELECT c.country_name, d.date AS week_end, 'actual' AS record_type,
       f.new_deaths AS deaths, CAST(NULL AS DOUBLE PRECISION) AS lower_80, CAST(NULL AS DOUBLE PRECISION) AS upper_80
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key
WHERE f.country_key IN (SELECT DISTINCT country_key FROM fact_forecast_weekly)
  AND d.date > (SELECT MAX(d2.date) FROM fact_covid_weekly f2 JOIN dim_date d2 ON d2.date_key = f2.date_key) - INTERVAL '182' DAY
UNION ALL
SELECT c.country_name, d.date, 'forecast', p.predicted_deaths, p.lower_80, p.upper_80
FROM fact_forecast_weekly p
JOIN dim_country c ON c.country_key = p.country_key
JOIN dim_date d ON d.date_key = p.date_key
ORDER BY country_name, week_end;

-- name: q22_death_volatility
-- Coefficient of variation of weekly deaths per million: how "wavy" each country's epidemic was.
SELECT
    c.country_name,
    AVG(f.weekly_deaths_per_million)                                AS mean_weekly_dpm,
    STDDEV_SAMP(f.weekly_deaths_per_million) / NULLIF(AVG(f.weekly_deaths_per_million), 0) AS coefficient_of_variation
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
WHERE c.population >= 1000000
GROUP BY c.country_name
HAVING AVG(f.weekly_deaths_per_million) >= 1
ORDER BY coefficient_of_variation DESC
LIMIT 20;
