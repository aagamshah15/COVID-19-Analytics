# Pandemic simulator: research brief

Status: **approved 2 Oct 2026** (Phase 1 of the simulator plan). Agreed at review: homogeneous mixing for v1, contact matrices in a later version; five extra presets; a "how contagious vs how deadly" scatter as the pathogen picker. This brief covers how existing epidemic simulators work, what the literature says about the parameters we need, and the design decisions that follow. Every number marked *assumption* is ours, not a cited estimate, and the app labels it the same way.

## 1. Bottom line

| Question | Decision | Why |
|---|---|---|
| What kind of model? | A **deterministic, age-structured compartmental model** (SEIR, plus hospital, ICU, vaccination and deaths), with **learned country effects** | It's the family used by browser tools that stay interactive (covid19-scenarios, CHIME). Agent-based models are richer but take seconds to minutes per run. |
| Where does it run? | Scenarios in the **browser** (a Web Worker); training and calibration on **GitHub Actions**; heavy analyses on **Cloud Run** | covid19-scenarios showed that an age-structured SEIR model completes in under a second in a browser. Ours is smaller, so live re-runs are realistic. |
| How is uncertainty shown? | **Monte Carlo** over parameter distributions, drawn as 50% and 90% bands | CHIME and covid19-scenarios both use this approach. Ensembles that keep the spread between models were the most reliable in the CDC Scenario Hub evaluation. |
| How do lockdowns enter? | As a **multiplicative reduction in transmission**, estimated from our own stringency and Rt data | This is how Flaxman et al. (2020) and Brauner et al. (2021) modelled interventions. We benchmark our estimate against their published effect sizes. |
| How does severity vary by country? | The **age curve of the infection fatality rate** times the country's own age structure, times a **learned multiplier** for health-system quality | O'Driscoll et al. (2021) found that IFR below age 65 is consistent across countries, while differences at older ages reflect care homes, health systems and missing deaths. |
| What happens when hospitals are full? | Mortality rises with ICU strain. The default comes from Bravata et al. (2021) unless our data supports its own estimate | ICU strain of 75–100% was associated with roughly double mortality for ICU patients. |
| Do people change behaviour on their own? | Yes: **awareness-driven behaviour**. Transmission falls as recent reported deaths rise, with the threshold estimated from data. *Added in Phase 3:* without it, validation errors were four times larger | Weitz et al. (PNAS 2020) show awareness of deaths turns single peaks into the plateaus and shoulders seen in real COVID-19 data. |
| Does transmission follow the seasons? | Yes, for SARS-CoV-2 and influenza-like presets: a yearly cycle at full strength from 40° latitude, fading to nothing at the edge of the tropics (23.5°). The timing is estimated from Rt (M1) and the strength from deaths (M2). *Added at checkpoint 2* to capture the autumn-2020 wave in the Northern Hemisphere | [Gavenčiak et al. (PLOS Comp Biol 2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9455844): R falls 42% (25–53%) from winter to summer in temperate Europe, after adjusting for interventions and mobility. |
| How do we present results? | As **conditional scenario projections**, never forecasts | The CDC Scenario Hub found that scenarios stayed close to reality for only about 22 weeks on average before a new variant broke their assumptions. |

## 2. How existing simulators work

| Tool | Family | What it simulates | Where it runs and how fast | What we borrow |
|---|---|---|---|---|
| [COVID-19 Scenarios](https://www.medrxiv.org/content/10.1101/2020.05.05.20091363v2) (Neher lab, Basel) | Age-structured SEIR with severe and critical compartments | Spread, hospital and ICU load, deaths; mitigation periods; age-specific isolation | **Entirely in the browser**, under one second per run; parameters and results exportable | The overall architecture: client-side engine, editable parameters, mitigation timeline, Monte Carlo |
| [Epidemic Calculator](https://gabgoh.github.io/COVID/index.html) (G. Goh) | SEIR | One epidemic curve with an intervention date | Browser, instant | Plain-language explanations next to each slider |
| [CHIME](https://pmc.ncbi.nlm.nih.gov/articles/PMC7153364) (Penn Medicine; Weissman et al., *Ann Intern Med* 2020) | SIR with a 1-day cycle, Monte Carlo | Hospital, ICU and ventilator demand vs capacity | Lightweight web app | Capacity lines and "days until capacity is exceeded" as headline outputs |
| [Covasim](https://doi.org/10.1371/journal.pcbi.1009149) (IDM; Kerr et al., *PLOS Comp Biol* 2021) | Agent-based, pure Python | Individuals in household, school, work and community layers; testing, tracing, vaccines | Realistic scenarios in **under a minute** on a laptop | The intervention vocabulary (testing, isolation, vaccine prioritisation). The runtime rules it out for live sliders. |
| [CovidSim](https://github.com/mrc-ide/covid-sim) (Imperial; Report 9) | Individual-based microsimulation, C++ | Whole-country populations at household and school level | Research computing | A reminder that the most detailed models need servers, which is why policy runs were batch jobs |
| [GLEAM](https://pmc.ncbi.nlm.nih.gov/articles/PMC2793313/) (Balcan et al., *PNAS* 2009) | Stochastic metapopulation over air-travel and commuting networks | Global spatial spread | Heavy compute | Out of scope: we simulate one country with homogeneous mixing and say so |
| [squire](https://doi.org/10.1126/science.abc0035) (Imperial; Walker et al., *Science* 2020) | Age-structured SEIR with health-system capacity | Low- and middle-income countries; deaths rise when critical-care demand exceeds supply | R package | Explicit capacity limits feeding back into mortality. Their mitigated scenarios projected critical-care demand at **25×** supply in a typical low-income setting vs **7×** in a high-income one. |
| IHME COVID-19 model | Started as statistical curve fitting ([CurveFit](https://github.com/ihmeuw-msca/CurveFit)), moved to an SEIR hybrid | National and subnational deaths | Server | A cautionary tale: pure curve fitting broke down, and the field moved to mechanistic models plus statistics |
| [US COVID-19 Scenario Modeling Hub](https://midasnetwork.us/papers/evaluation-of-the-us-covid-19-scenario-modeling-hub-for-informing-pandemic-response-under-uncertainty/) (CDC-funded) | An ensemble of many teams' models | Months-ahead scenario projections, about 1.8 million in total | Many teams' clusters | Present outputs as *scenarios*, and keep spread rather than averaging it away |

### Speed versus fidelity

| Family | Cost per run | Strength | Weakness |
|---|---|---|---|
| Compartmental ODE (SIR/SEIR) | Microseconds to milliseconds | Fast, transparent, easy to calibrate | Homogeneous mixing within each group; no networks |
| Age-structured compartmental | Milliseconds | Captures the age gradient in severity and vaccine prioritisation | Needs a contact pattern (or assumes homogeneous mixing) |
| Metapopulation | Seconds | Spatial spread between regions | Needs mobility data |
| Agent-based | Seconds to hours | Individual behaviour, networks, testing and tracing | Slow, many parameters, hard to calibrate. Practitioners fit fast surrogates (e.g. [Gaussian-process emulators](https://arxiv.org/abs/2502.19550)) to calibrate them. |
| Statistical / ML only | Microseconds | Learns patterns directly from data | Can't extrapolate to a new pathogen or untried policy |

**Our choice:** an age-structured compartmental engine. It's the cheapest family that still handles age-dependent severity and "vaccinate the oldest first". The models trained on our data add what the mechanics can't know: how a given kind of country responds. Our engine is already fast, so we don't need an emulator.

## 3. What the literature says about interventions

| Study | Method | Finding we use |
|---|---|---|
| [Flaxman et al., *Nature* 2020](https://doi.org/10.1038/s41586-020-2405-7) | Bayesian semi-mechanistic model, 11 European countries, to 4 May 2020 | Rt fell from an average of **3.8 to 0.66**; lockdown alone was associated with an **81%** reduction in transmission |
| [Brauner et al., *Science* 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC7877495/) | Bayesian hierarchical model, 41 countries, Jan–May 2020 | Rt reductions: gatherings ≤10 people **42%**, schools and universities closed **38%**, most nonessential businesses closed **27%**, stay-at-home order on top of these **13%**. **All combined: 77% (67–85%)** |
| [Haug et al., *Nat Hum Behav* 2020](https://doi.org/10.1038/s41562-020-01009-0) | 6,068 coded interventions in 79 territories, four methods | The right combination matters, and cheaper measures can match lockdowns; effectiveness depends on timing and context |
| [Hale et al., *Nat Hum Behav* 2021](https://www.nature.com/articles/s41562-021-01079-8.pdf) (OxCGRT) | Policy database, 180+ countries | Defines the **Stringency Index** (0–100, the mean of nine containment indicators) that OWID publishes. It measures how strict policies are, not how well they work. |
| [Arroyo-Marioli et al., *PLOS ONE* 2021](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7806155/) | Kalman filter on case growth | The method behind OWID's `reproduction_rate`. It's an estimate derived from cases, so it inherits testing changes. |

**How we use it:** model M1 regresses log Rt on stringency, with country and week fixed effects, interactions with country features, vaccination and variant era. Its implied effect at stringency 80–100 should land in the 60–85% range of Flaxman and Brauner. If it doesn't, we report the gap and say why: OWID Rt is estimated from cases, and stringency measures policy, not compliance.

## 4. Severity, hospitals and capacity

- **IFR by age (SARS-CoV-2, pre-vaccine).** [Levin et al., *Eur J Epidemiol* 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7721859/) is a meta-regression over 27 studies:
  - **log₁₀(IFR %) = −3.27 + 0.0524 × age** (SE 0.07 and 0.0013)
  - This gives 0.002% at age 10, 0.01% at 25, 0.4% at 55, 1.4% at 65, 4.6% at 75 and 15% at 85.
  - We evaluate it at the population-weighted mean age within each of our five bands.
- **Consistency across countries.** [O'Driscoll et al., *Nature* 2021](https://doi.org/10.1038/s41586-020-2918-0) covered 45 countries: IFR from 0.001% at ages 5–9 to 8.3% at 80+. Below 65 it was consistent across countries; at older ages it varied with care-home deaths and under-reporting. This is why the learned severity multiplier applies mainly to the 60+ bands.
- **Hospitalisation.** [Salje et al., *Science* 2020](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7223792/) (France): **2.6%** of infections hospitalised and 0.53% died. In the same study, lockdown cut transmission by 84%, which is another benchmark for M1.
- **Hospital overload.** [Bravata et al., *JAMA Netw Open* 2021](https://depts.washington.edu/pandemicalliance/?p=3331) studied 8,516 patients in 88 Veterans Affairs hospitals.
  - Compared with ICU demand under 25%, the adjusted mortality hazard ratio was **1.19 at 50–75%** demand and **1.94 at 75–100%**.
  - There was no association for non-ICU patients.
  - Our default overload multiplier applies only to deaths among ICU-level patients.
- **Variant severity.**
  - Delta vs pre-variant strains: hospitalisation +105%, ICU +241%, death +121% ([Fisman & Tuite, *CMAJ* 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8562985)).
  - Omicron BA.1 vs Delta: hospitalisation HR **0.41**, death HR **0.31** ([Nyberg et al., *Lancet* 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC8926409)).
- **Immunity after infection.** Protection against severe disease stayed at **88% or higher at 10 months**, but protection against reinfection was much lower for Omicron ([COVID-19 Forecasting Team, *Lancet* 2023](https://www.healthdata.org/node/10346)). Presets therefore pair a short waning time for infection with a separate, stronger protection against death.

## 5. Pathogen presets

Defaults only: every value is editable in the app. *Assumption* marks values we chose where no single cited estimate fits.

| Preset | R0 | Latent / infectious (days) | Overall IFR | Age profile | Hospitalised | Sources |
|---|---|---|---|---|---|---|
| Seasonal flu | **1.28** (median) | 1 / 3 *assumption* | ≈0.05% *assumption*: 0.096% of *symptomatic* illnesses died in the US 2018–19, assuming about half of infections are symptomatic | rises with age | 1.4% of symptomatic illnesses | [Biggerstaff 2014](https://www.biomedcentral.com/1471-2334/14/480); [CDC 2018–19 burden](https://archive.cdc.gov/www_cdc_gov/flu/about/burden/2018-2019/archive-09292021.html) |
| 2009 H1N1 | **1.46** (IQR 1.30–1.70) | 1 / 3 *assumption* | **0.001–0.01%** (1–10 per 100,000 infections) | rises with age | *assumption* 0.5% | Biggerstaff 2014; [Wong et al., *Epidemiology* 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC3809029/) |
| 1918 flu | **1.80** (IQR 1.47–2.27) | 1 / 3 *assumption* | ≈2% *assumption*, from case fatality **>2.5%** | **W-shaped**: peaks in infants, adults 20–40 and the elderly; under-65s were >99% of excess deaths | *assumption* 5% | Biggerstaff 2014; [Taubenberger & Morens 2006](https://pmc.ncbi.nlm.nih.gov/articles/PMC3291398/) |
| SARS-CoV-2 ancestral | **2.79** (median) | 3 / 5 (incubation median **5.1**) | from the Levin age curve (≈0.5–1% for a typical high-income age mix) | rises steeply with age | **2.6%** of infections | [Liu & Rocklöv 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8436367); [Lauer 2020](https://publichealth.jhu.edu/2020/new-study-on-COVID-19-estimates-5-days-for-incubation-period); Levin 2020; Salje 2020 |
| SARS-CoV-2 Delta | **5.08** (range 3.2–8) | 3 / 5 | ancestral × 2.2 (death +121%) | rises steeply with age | ancestral × 2.05 | Liu & Rocklöv 2021; Fisman & Tuite 2021 |
| SARS-CoV-2 Omicron BA.1 | **8.2** (average) | 2 / 5 *assumption* | Delta × 0.31 | rises steeply with age | Delta × 0.41 | [Liu & Rocklöv 2022](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8992231/); Nyberg 2022 |
| SARS (2003) | **2.7** (range 2.2–3.6) | 4 / 7 *assumption* | **9.6%** case fatality (774 deaths, 8,098 cases); few mild infections, so IFR ≈ CFR *assumption* | rises with age | *assumption* 70% | [CDC MMWR 2003](https://Www.cdc.gov/mmwr/PDF/wk/mm5216.pdf); [Riley et al., *Science* 2003](https://researchonline.lshtm.ac.uk/id/eprint/13189) |
| Measles-like (no prior immunity) | **12–18** (often-cited range; the review finds wider variation) | 10 / 8 *assumption* | **0.1–0.3%** in high-income settings; mean **1.5%** in community studies in low- and middle-income countries | highest in young children | 20% of unvaccinated US cases | [Guerra et al., *Lancet ID* 2017](https://insight.jci.org/references/scholar/6805/B7); [CDC](https://Www.Cdc.gov/measles/symptoms/complications.html); [Portnoy et al., *Lancet Glob Health* 2019](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6418190/) |
| 1957 flu (H2N2) | **1.65** (IQR 1.53–1.70) | 1 / 3 *assumption* | ≈0.1% *assumption*: case fatality **<0.1%** in pandemics other than 1918; about 1.1 million excess deaths worldwide | rises with age (under-65s were **36%** of deaths) | *assumption* 1% | Biggerstaff 2014; Taubenberger & Morens 2006; [Viboud et al., *J Infect Dis* 2016](https://repositorio.uchile.cl/handle/2250/139285) |
| 1968 flu (H3N2) | **1.80** (IQR 1.56–1.85) | 1 / 3 *assumption* | ≈0.05% *assumption*: case fatality **<0.1%**; about 1 million deaths worldwide | rises with age (under-65s were **48%** of deaths) | *assumption* 1% | Biggerstaff 2014; Taubenberger & Morens 2006; [CDC](https://archive.cdc.gov/www_cdc_gov/flu/pandemic-resources/1968-pandemic.html) |
| MERS-like | **0.60–0.69** (below 1: it never takes off) | 5 / 7 *assumption* | **36%** of confirmed cases died (947 of 2,627, 2012–Aug 2025). That is an upper bound on IFR, because mild infections go undetected | rises with age | *assumption* 60% | [Breban et al., *Lancet* 2013](https://research.pasteur.fr/en/b/6Ee); [WHO EMRO, Aug 2025](https://www.emro.who.int/health-topics/mers-cov/regional-situation-update.html) |
| H5N1-like "what if" (**hypothetical**) | **1.8** *assumption*: "if it spread like 1918 flu". Real H5N1 hasn't sustained human-to-human spread | 2 / 4 *assumption* | 10% *assumption*: **48%** of confirmed cases died (477 of 993, 2003–2025), but mild cases are under-detected. The slider goes up to 48% | rises with age *assumption* | *assumption* 30% | [WHO WPRO avian influenza weekly update, Jan 2026](https://cdn.who.int/media/docs/default-source/wpro---documents/emergency/surveillance/avian-influenza/ai_20260116.pdf) |
| Smallpox-like (no prior immunity) | **3.5–6** (default 4.5) | 12 / 9 *assumption* (incubation **10–12 days**, range 7–17) | about **30%** (variola major); few subclinical infections, so IFR ≈ CFR *assumption* | flat *assumption* | *assumption* 50% | [Gani & Leach, *Nature* 2001](https://www.nature.com/articles/414748a); [Merck Manual](https://www.merckmanuals.com/professional/infectious-diseases/pox-viruses/smallpox) |
| Disease X (blank slate) | 2.5 *assumption* | 3 / 5 *assumption* | 0.5% *assumption* | rises with age | 3% | A neutral starting point the visitor edits |

The pathogen step shows every preset as a dot on a **"how contagious (R0) vs how deadly (IFR, log scale)" scatter**. Clicking a dot loads the preset; dragging the "your disease" point sets R0 and IFR directly. The shaded region marks the range the COVID-trained country models have seen.

How country effects carry over to non-COVID presets:
- The country multipliers learned from COVID-19 data are applied to every pathogen, scaled by its own age curve.
- The report flags the result as *extrapolated* whenever R0, IFR or the age profile falls outside the SARS-CoV-2 range the models were trained on.

## 6. Data for learning: final signal list for review

Checked against the live APIs on 1 Oct 2026.

**OWID (already downloaded, columns not yet used):**

| Column | Countries | Coverage | Use |
|---|---|---|---|
| `stringency_index` | 185 | 2020–2022 | M1 (intervention effect), calibration inputs |
| `reproduction_rate` | 194 | Jan 2020 – Jan 2023 | M1 target |
| `excess_mortality_cumulative_absolute` | 127 | 2020–2023 | M5 (reporting completeness), calibration targets |
| `population_density` | 233 | static | transmission features |
| `diabetes_prevalence` | 209 | static | severity features |
| `extreme_poverty` | 163 | static | adherence and severity features |
| `handwashing_facilities` | 120 | static | transmission features (sparse; World Bank sanitation is the fallback) |
| `human_development_index` | **0** | n/a | **dropped**: empty in the current OWID file |

**World Bank WDI** (source 2; latest value 2015–2022 per country):

| Indicator | Code | Countries | Use |
|---|---|---|---|
| Population by 5-year age group and sex (0–4 … 80+) | `SP.POP.{0004…7579}.{FE,MA}.5Y`, `SP.POP.80UP.{FE,MA}.5Y`, `SP.POP.TOTL.FE.ZS` | 260 | **Exact five-band age structure**, so we don't need to fit a pyramid from median age |
| Urban population % | `SP.URB.TOTL.IN.ZS` | 260 | transmission |
| Hospital beds per 1,000 | `SH.MED.BEDS.ZS` | 189 | fills OWID gaps |
| Physicians per 1,000 | `SH.MED.PHYS.ZS` | 230 | access to care |
| Health spending per capita (US$) | `SH.XPD.CHEX.PC.CD` | 236 | access to care, rollout speed |
| Out-of-pocket share of health spending | `SH.XPD.OOPC.CH.ZS` | 236 | access to care (financial barrier) |
| UHC service coverage index | `SH_UHC_SCI` | 236 | access to care |
| Basic sanitation % | `SH.STA.BASS.ZS` | 257 | transmission (complete replacement for handwashing) |
| Measles immunisation % | `SH.IMM.MEAS` | 236 | vaccine acceptance prior (M4) |
| DTP3 immunisation % | `SH.IMM.IDPT` | 236 | vaccine acceptance prior (M4) |

**Not available anywhere we can use, so set by assumption and editable:**
- **ICU beds.** The default is 5% of hospital beds (*assumption*); OECD countries range widely.
- **Contact patterns by age.** We use homogeneous mixing in v1. [Prem et al., *PLOS Comp Biol* 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8354454) publishes synthetic contact matrices for 177 regions; they're the obvious upgrade.

## 7. Speed budget

One run is 730 days × 4 sub-steps × 5 age bands × about 11 compartments, roughly 160,000 state updates. With 200 Monte Carlo draws that's about 32 million floating-point updates, an estimated **30–60 ms** in a Web Worker on a mid-range laptop. Sensitivity analysis (14 inputs × 2 directions) adds about 28 more runs. We'll measure this in Phase 4 and report the numbers; 100 ms is the target for live re-runs.

Heavy jobs go to Cloud Run:
- **Global Sobol sensitivity**, which needs tens of thousands of runs (Saltelli sampling).
- **5,000-draw intervals**, which are vectorised in NumPy.

## 8. What the simulator won't do (stated in the app)

- **No spatial spread.** One well-mixed population per country, with no regions or travel network.
- **Behaviour feedback is one mechanism.** People cut contacts as reported deaths rise (awareness) and lockdowns lose effect over time (fatigue). There's nothing else, such as risk compensation after vaccination.
- **Homogeneous mixing between age groups.**
- **Country effects learned from one pandemic.** Applying them to other pathogens is an extrapolation, and it's flagged.
- **Rt and stringency are indirect measures.** OWID's Rt is estimated from reported cases, and stringency measures policy rather than compliance.
- **Reported deaths undercount.** The calibration targets use excess mortality where it exists (127 countries) and fall back to reported deaths corrected by model M5.

## References

1. Levin AT et al. Assessing the age specificity of infection fatality rates for COVID-19. *Eur J Epidemiol* 2020;35:1123–38. [PMC7721859](https://pmc.ncbi.nlm.nih.gov/articles/PMC7721859/)
2. O'Driscoll M et al. Age-specific mortality and immunity patterns of SARS-CoV-2. *Nature* 2021;590:140–5. [doi:10.1038/s41586-020-2918-0](https://doi.org/10.1038/s41586-020-2918-0)
3. Flaxman S et al. Estimating the effects of non-pharmaceutical interventions on COVID-19 in Europe. *Nature* 2020;584:257–61. [doi:10.1038/s41586-020-2405-7](https://doi.org/10.1038/s41586-020-2405-7)
4. Brauner JM et al. Inferring the effectiveness of government interventions against COVID-19. *Science* 2021;371:eabd9338. [PMC7877495](https://pmc.ncbi.nlm.nih.gov/articles/PMC7877495/)
5. Haug N et al. Ranking the effectiveness of worldwide COVID-19 government interventions. *Nat Hum Behav* 2020;4:1303–12. [doi:10.1038/s41562-020-01009-0](https://doi.org/10.1038/s41562-020-01009-0)
6. Hale T et al. A global panel database of pandemic policies (OxCGRT). *Nat Hum Behav* 2021;5:529–38. [PDF](https://www.nature.com/articles/s41562-021-01079-8.pdf)
7. Arroyo-Marioli F et al. Tracking R of COVID-19: a new real-time estimation using the Kalman filter. *PLOS ONE* 2021. [PMC7806155](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7806155/)
8. Salje H et al. Estimating the burden of SARS-CoV-2 in France. *Science* 2020;369:208–11. [PMC7223792](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7223792/)
9. Bravata DM et al. Association of intensive care unit patient load and demand with mortality rates in US Department of Veterans Affairs hospitals during the COVID-19 pandemic. *JAMA Netw Open* 2021. [summary](https://depts.washington.edu/pandemicalliance/?p=3331)
10. Walker PGT et al. The impact of COVID-19 and strategies for mitigation and suppression in low- and middle-income countries. *Science* 2020;369:413–22. [doi:10.1126/science.abc0035](https://doi.org/10.1126/science.abc0035)
11. Fisman DN, Tuite AR. Evaluation of the relative virulence of novel SARS-CoV-2 variants. *CMAJ* 2021. [PMC8562985](https://pmc.ncbi.nlm.nih.gov/articles/PMC8562985)
12. Nyberg T et al. Comparative analysis of the risks of hospitalisation and death associated with omicron and delta. *Lancet* 2022;399:1303–12. [PMC8926409](https://pmc.ncbi.nlm.nih.gov/articles/PMC8926409)
13. Liu Y, Rocklöv J. The reproductive number of the Delta variant of SARS-CoV-2 is far higher compared to the ancestral virus. *J Travel Med* 2021. [PMC8436367](https://pmc.ncbi.nlm.nih.gov/articles/PMC8436367)
14. Liu Y, Rocklöv J. The effective reproductive number of the Omicron variant is several times relative to Delta. *J Travel Med* 2022. [PMC8992231](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8992231/)
15. Lauer SA et al. The incubation period of COVID-19. *Ann Intern Med* 2020. [JHU summary](https://publichealth.jhu.edu/2020/new-study-on-COVID-19-estimates-5-days-for-incubation-period)
16. Biggerstaff M et al. Estimates of the reproduction number for seasonal, pandemic, and zoonotic influenza. *BMC Infect Dis* 2014;14:480. [article](https://www.biomedcentral.com/1471-2334/14/480)
17. Wong JY et al. Case fatality risk of influenza A(H1N1pdm09): a systematic review. *Epidemiology* 2013. [PMC3809029](https://pmc.ncbi.nlm.nih.gov/articles/PMC3809029/)
18. Taubenberger JK, Morens DM. 1918 influenza: the mother of all pandemics. *Emerg Infect Dis* 2006;12:15–22. [PMC3291398](https://pmc.ncbi.nlm.nih.gov/articles/PMC3291398/)
19. Guerra FM et al. The basic reproduction number (R0) of measles: a systematic review. *Lancet Infect Dis* 2017. [reference](https://insight.jci.org/references/scholar/6805/B7)
20. Portnoy A et al. Estimates of case-fatality ratios of measles in low-income and middle-income countries. *Lancet Glob Health* 2019. [PMC6418190](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6418190/)
21. CDC. Severe acute respiratory syndrome, worldwide summary. *MMWR* 2003;52(16). [PDF](https://Www.cdc.gov/mmwr/PDF/wk/mm5216.pdf); Riley S et al. *Science* 2003. [record](https://researchonline.lshtm.ac.uk/id/eprint/13189)
22. Neher RA et al. COVID-19 Scenarios: an interactive tool to explore the spread and associated morbidity and mortality of SARS-CoV-2. *medRxiv* 2020. [preprint](https://www.medrxiv.org/content/10.1101/2020.05.05.20091363v2)
23. Weissman GE et al. Locally informed simulation to predict hospital capacity needs during the COVID-19 pandemic (CHIME). *Ann Intern Med* 2020. [PMC7153364](https://pmc.ncbi.nlm.nih.gov/articles/PMC7153364)
24. Kerr CC et al. Covasim: an agent-based model of COVID-19 dynamics and interventions. *PLOS Comput Biol* 2021;17:e1009149. [doi](https://doi.org/10.1371/journal.pcbi.1009149)
25. Balcan D et al. Multiscale mobility networks and the spatial spreading of infectious diseases. *PNAS* 2009;106:21484–9. [PMC2793313](https://pmc.ncbi.nlm.nih.gov/articles/PMC2793313/)
26. Howerton E et al. Evaluation of the US COVID-19 Scenario Modeling Hub for informing pandemic response under uncertainty. *Nat Commun* 2023. [summary](https://midasnetwork.us/papers/evaluation-of-the-us-covid-19-scenario-modeling-hub-for-informing-pandemic-response-under-uncertainty/)
27. COVID-19 Forecasting Team. Past SARS-CoV-2 infection protection against re-infection: a systematic review and meta-analysis. *Lancet* 2023. [IHME](https://www.healthdata.org/node/10346)
28. Prem K et al. Projecting contact matrices in 177 geographical regions. *PLOS Comput Biol* 2021. [PMC8354454](https://pmc.ncbi.nlm.nih.gov/articles/PMC8354454)
29. CDC. Estimated influenza disease burden, 2018–2019 season. [archive](https://archive.cdc.gov/www_cdc_gov/flu/about/burden/2018-2019/archive-09292021.html); CDC. Complications of measles. [page](https://Www.Cdc.gov/measles/symptoms/complications.html)
30. Viboud C et al. Global mortality impact of the 1957–1959 influenza pandemic. *J Infect Dis* 2016;213:738–45. [record](https://repositorio.uchile.cl/handle/2250/139285); CDC. 1968 pandemic (H3N2 virus). [archive](https://archive.cdc.gov/www_cdc_gov/flu/pandemic-resources/1968-pandemic.html)
31. Breban R, Riou J, Fontanet A. Interhuman transmissibility of Middle East respiratory syndrome coronavirus: estimation of pandemic risk. *Lancet* 2013;382:694–9. [record](https://research.pasteur.fr/en/b/6Ee)
32. WHO EMRO. MERS situation update, August 2025. [page](https://www.emro.who.int/health-topics/mers-cov/regional-situation-update.html)
33. WHO WPRO. Avian influenza weekly update, 16 January 2026 (cumulative H5N1 cases 2003–2025). [PDF](https://cdn.who.int/media/docs/default-source/wpro---documents/emergency/surveillance/avian-influenza/ai_20260116.pdf)
34. Gani R, Leach S. Transmission potential of smallpox in contemporary populations. *Nature* 2001;414:748–51. [article](https://www.nature.com/articles/414748a)
35. Merck Manual Professional Version. Smallpox. [page](https://www.merckmanuals.com/professional/infectious-diseases/pox-viruses/smallpox)
36. Weitz JS, Park SW, Eksin C, Dushoff J. Awareness-driven behavior changes can shift the shape of epidemics away from peaks and toward plateaus, shoulders, and oscillations. *PNAS* 2020;117:32764–71. [PMC7768772](https://pmc.ncbi.nlm.nih.gov/articles/PMC7768772)
37. Gavenčiak T et al. Seasonal variation in SARS-CoV-2 transmission in temperate climates: a Bayesian modelling study in 143 European regions. *PLOS Comput Biol* 2022;18:e1010435. [PMC9455844](https://pmc.ncbi.nlm.nih.gov/articles/PMC9455844)
