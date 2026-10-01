-- Q01: Top 10 countries by peak deaths per million
SELECT c.country_name, MAX(f.deaths_per_million) AS peak_deaths_per_million
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;

-- Q02: Top 10 countries by peak weekly new deaths
SELECT c.country_name, MAX(f.new_deaths) AS peak_weekly_deaths
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;

-- Q03: Global weekly trend of deaths per million (average)
SELECT d.date, AVG(f.deaths_per_million) AS avg_deaths_per_million
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY 1
ORDER BY 1;

-- Q04: Global weekly trend of cases per million (average)
SELECT d.date, AVG(f.cases_per_million) AS avg_cases_per_million
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY 1
ORDER BY 1;

-- Q05: Continent mortality ranking
SELECT c.continent, AVG(f.deaths_per_million) AS avg_deaths_per_million
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
ORDER BY 2 DESC;

-- Q06: Countries with strongest vaccination and lower mortality
SELECT c.country_name,
       AVG(f.vaccination_rate) AS avg_vaccination_rate,
       AVG(f.deaths_per_million) AS avg_deaths_per_million
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
HAVING AVG(f.vaccination_rate) IS NOT NULL
ORDER BY avg_vaccination_rate DESC, avg_deaths_per_million ASC
LIMIT 25;

-- Q07: Weekly CFR trend by country
SELECT c.country_name, d.date, f.case_fatality_rate
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key
WHERE c.country_name IN ('India', 'United States', 'Brazil', 'United Kingdom')
ORDER BY c.country_name, d.date;

-- Q08: Country peer groups by health capacity proxy
SELECT c.country_name,
       c.continent,
       c.hospital_beds_per_thousand,
       c.aged_65_older,
       AVG(f.deaths_per_million) AS avg_deaths_per_million
FROM dim_country c
JOIN fact_covid_weekly f ON f.country_key = c.country_key
GROUP BY 1,2,3,4
ORDER BY c.hospital_beds_per_thousand DESC NULLS LAST, avg_deaths_per_million ASC;

-- Q09: Highest burden quarter by country
SELECT c.country_name,
       d.year,
       d.quarter,
       SUM(f.new_deaths) AS deaths_in_quarter
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY 1,2,3
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.country_name ORDER BY SUM(f.new_deaths) DESC) = 1;

-- Q10: Countries with lowest average CFR (min 100k cases per million peak)
SELECT c.country_name,
       AVG(f.case_fatality_rate) AS avg_cfr,
       MAX(f.cases_per_million) AS peak_cases_per_million
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
HAVING MAX(f.cases_per_million) >= 100000
ORDER BY avg_cfr ASC
LIMIT 20;

-- Q11: Countries with highest volatility in weekly deaths
SELECT c.country_name,
       STDDEV_SAMP(f.new_deaths) AS deaths_volatility
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
ORDER BY 2 DESC NULLS LAST
LIMIT 20;

-- Q12: Weekly global cases and deaths totals
SELECT d.date,
       SUM(f.new_cases) AS global_weekly_cases,
       SUM(f.new_deaths) AS global_weekly_deaths
FROM fact_covid_weekly f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY 1
ORDER BY 1;

-- Q13: Vaccination acceleration by country (first vs last observed)
WITH first_last AS (
  SELECT c.country_name,
         FIRST_VALUE(f.vaccination_rate) OVER (PARTITION BY c.country_name ORDER BY d.date) AS first_vax,
         LAST_VALUE(f.vaccination_rate) OVER (PARTITION BY c.country_name ORDER BY d.date
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_vax
  FROM fact_covid_weekly f
  JOIN dim_country c ON c.country_key = f.country_key
  JOIN dim_date d ON d.date_key = f.date_key
)
SELECT country_name, MAX(first_vax) AS first_vax, MAX(last_vax) AS last_vax, MAX(last_vax - first_vax) AS vax_gain
FROM first_last
GROUP BY 1
ORDER BY vax_gain DESC NULLS LAST
LIMIT 20;

-- Q14: Top countries by rolling deaths burden
SELECT c.country_name,
       MAX(f.rolling_7d_deaths) AS peak_rolling_7d_deaths
FROM fact_covid_daily f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;

-- Q15: Mortality before and after vaccination threshold (40%)
WITH threshold_date AS (
  SELECT country_key,
         MIN(date_key) AS first_threshold_date_key
  FROM fact_covid_weekly
  WHERE vaccination_rate >= 0.40
  GROUP BY 1
), tagged AS (
  SELECT f.country_key,
         CASE WHEN t.first_threshold_date_key IS NULL THEN 'no_threshold'
              WHEN f.date_key < t.first_threshold_date_key THEN 'before_threshold'
              ELSE 'after_threshold' END AS period,
         f.deaths_per_million
  FROM fact_covid_weekly f
  LEFT JOIN threshold_date t ON f.country_key = t.country_key
)
SELECT c.country_name, period, AVG(deaths_per_million) AS avg_deaths_per_million
FROM tagged t
JOIN dim_country c ON c.country_key = t.country_key
GROUP BY 1,2
ORDER BY 1,2;

-- Q16: Monthly burden summary
SELECT d.year, d.month,
       SUM(f.new_cases) AS monthly_cases,
       SUM(f.new_deaths) AS monthly_deaths
FROM fact_covid_daily f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY 1,2
ORDER BY 1,2;

-- Q17: Country ranking by cumulative deaths per million (weekly summed)
SELECT c.country_name,
       SUM(f.new_deaths) / NULLIF(MAX(c.population), 0) * 1000000 AS deaths_per_million_proxy
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
ORDER BY 2 DESC
LIMIT 25;

-- Q18: Correlation helper extract for Tableau/Power BI
SELECT c.country_name,
       d.date,
       f.new_cases,
       f.new_deaths,
       f.vaccination_rate,
       f.case_fatality_rate,
       c.hospital_beds_per_thousand,
       c.aged_65_older,
       c.gdp_per_capita
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key;

-- Q19: Countries with highest data completeness in vaccination
SELECT c.country_name,
       AVG(CASE WHEN f.vaccination_rate IS NOT NULL THEN 1.0 ELSE 0.0 END) AS vaccination_data_completeness
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1
ORDER BY 2 DESC, 1;

-- Q20: Peak healthcare burden week by continent
SELECT c.continent,
       d.date,
       SUM(f.new_deaths) AS weekly_deaths
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY 1,2
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.continent ORDER BY SUM(f.new_deaths) DESC) = 1;

-- Q21: Country segmentation by burden and vaccination
SELECT c.country_name,
       AVG(f.deaths_per_million) AS avg_deaths_per_million,
       AVG(f.vaccination_rate) AS avg_vaccination_rate,
       CASE
         WHEN AVG(f.deaths_per_million) >= 1000 AND AVG(f.vaccination_rate) < 0.5 THEN 'High burden, low vaccination'
         WHEN AVG(f.deaths_per_million) >= 1000 AND AVG(f.vaccination_rate) >= 0.5 THEN 'High burden, high vaccination'
         WHEN AVG(f.deaths_per_million) < 1000 AND AVG(f.vaccination_rate) < 0.5 THEN 'Low burden, low vaccination'
         ELSE 'Low burden, high vaccination'
       END AS segment
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
GROUP BY 1;

-- Q22: Executive summary KPIs
SELECT
  COUNT(DISTINCT c.country_key) AS countries,
  MIN(d.date) AS min_date,
  MAX(d.date) AS max_date,
  SUM(f.new_cases) AS total_cases,
  SUM(f.new_deaths) AS total_deaths,
  AVG(f.case_fatality_rate) AS avg_cfr,
  AVG(f.vaccination_rate) AS avg_vaccination_rate
FROM fact_covid_weekly f
JOIN dim_country c ON c.country_key = f.country_key
JOIN dim_date d ON d.date_key = f.date_key;
