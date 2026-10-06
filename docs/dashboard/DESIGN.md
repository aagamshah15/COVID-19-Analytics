# COVID-19 Analytics dashboard: design and build plan

Status: **built** (all seven pages, light and dark). This document is the brief the dashboard was built against; deviations are noted inline.

## 1. Brief

| | |
|---|---|
| **Subject** | The healthcare burden of COVID-19 across 239 countries, 2020–2023: deaths, cases, vaccination, hospital strain, and an 8-week outlook. |
| **Audience** | Hiring managers and data peers reviewing a portfolio (2–5 minute visit), plus curious readers who want to look up their own country. |
| **Primary job** | Tell the four-year story in under a minute, then let the reader explore any country, region or period without the numbers ever contradicting each other. |
| **Secondary job** | Show the engineering behind it. Every number traces to a named SQL query, and data gaps are drawn rather than hidden. |
| **Format** | Static, multi-page interactive web app on GitHub Pages, rebuilt from the live sources by the same pipeline. No server. |

## 2. What the references taught us

| Reference | Takeaway we adopt | What we avoid |
|---|---|---|
| **Johns Hopkins CSSE dashboard** (2022 Lasker-Bloomberg Public Service Award) | One trusted place; the headline numbers are visible without any clicks. | A map-first layout that hides the trend over time. |
| **UK Health Security Agency COVID-19 dashboard** (Royal Statistical Society award for trustworthiness, quality and value) | Metadata, definitions and downloads next to every metric; plain-language "about this data". | Dense government table pages. |
| **Our World in Data Grapher / explorers** | Chart · Map · Table tabs on one metric; per-million vs absolute toggle; country picker; sources on the chart. | A single-chart explorer with no narrative. |
| **FT coronavirus trackers** (John Burn-Murdoch) | Headline titles that state the finding; direct labels instead of legends; emphasis (one highlighted line, the rest grey). | Log scales for a general audience. |
| **Fabric "E-Commerce Sales Analysis" report** (shared reference) | Left icon rail across 5 pages, KPI tiles with sub-breakdowns, titles phrased as questions with a one-line takeaway underneath, a consistent theme. | Pie/donut charts; boxed cards around every visual. |
| **Reddit r/dataanalysis storyboard** (shared reference) | *Not reviewed yet: Reddit blocks automated access. Paste a screenshot to fold it in.* | |

## 3. Information architecture

Seven pages. The Country page is also a drill-through target: clicking any country anywhere opens it, and its URL (`#/country/IND`) is shareable.

| # | Page | The question it answers | Core views |
|---|---|---|---|
| 1 | **Overview** | What happened, in one minute? | Timeline spine (hero), 4 headline stats, 3 findings, global deaths and vaccination small multiples |
| 2 | **Where it hit** | Which places carried the heaviest burden? | Choropleth (metric switch), ranked list, continent and WHO-region small multiples |
| 3 | **Country** | What did the pandemic look like *here*? | Country vs region vs world epi curve, vaccination rollout, hospital occupancy (when published), reporting-coverage strip, peer comparison |
| 4 | **Vaccines & severity** | Did severity fall, and what can we say about vaccination? | CFR by quarter, rollout by continent, vaccination tercile vs 2022 outcomes, with a note on why the comparison is confounded |
| 5 | **Hospital strain** | How close did health systems come to the edge? | Peak COVID bed-occupancy ranking, country × week occupancy heatmap, ICU peaks |
| 6 | **Outlook** | What does the model expect next, and should we trust it? | Forecast fan charts, skill vs naive by horizon, per-country skill, "how the model works" |
| 7 | **Data & methods** | Can I trust these numbers? | Quality gate results, reporting-coverage heatmap, sources and manifest, pipeline diagram, links to the SQL pack and repo |

### Global controls (one row, above the content, scoping every view)

1. **Period**: set by brushing the timeline spine, or with presets (*Whole pandemic*, *2020*, *2021*, *2022*, *2023*, *Omicron era*).
2. **Region**: continent or WHO region, one at a time.
3. **Measure**: *per million* (default) or *absolute*.
4. **Country search**: a combobox; choosing a country opens the Country page.

Filters live in the URL (`?from=2021-01&to=2021-12&region=Europe`) so every view is linkable, and the browser Back button works.

## 4. Visual system

### The one bold element: the timeline spine

A full-width strip of 208 thin weekly bars of global deaths, with the approximate dominant-variant eras labelled underneath: *Ancestral*, *Alpha*, *Delta*, *Omicron*. It's the hero on the Overview page and stays pinned (condensed) at the top of every other page as the **period brush**. The selected weeks are inked; the rest fade to a muted tint. It's the most characteristic image of this subject, the epidemic curve, and it doubles as the main control. Everything else stays quiet.

### Color: one hue per metric, everywhere

A metric keeps its hue on every page, in every chart, legend and table key. Validated with the dataviz validator using `--pairs all` in both modes; all checks pass.

| Metric | Light | Dark | Rationale |
|---|---|---|---|
| Deaths | `#b3303e` oxblood | `#c94657` | Conventional mortality color, kept deep rather than alarm-red. |
| Cases | `#5a55c4` indigo | `#8a84ea` | Cool and secondary to deaths. |
| Vaccination | `#008675` teal | `#20aa99` | The color of surgical scrubs. |
| Hospital strain | `#b87a00` amber | `#bb8210` | Iodine and caution. |

| Role | Light | Dark |
|---|---|---|
| Page plane | `#f5f7f6` (cool clinical grey-green, not cream) | `#141a19` |
| Primary ink | `#172422` | `#eef3f1` |
| Secondary ink | `#4e5c59` | `#b5c1be` |
| Muted (axes, context series) | `#85918e` | `#7d8a87` |
| Hairline / grid | `#dde3e1` | `#26302e` |

- **Comparisons use emphasis, not more colors.** The selected country is drawn in the metric hue, its region in mid grey and the world in a light grey dashed line. Comparing more than three countries uses small multiples.
- **Choropleths** use a single-hue sequential ramp of the metric's hue (100→700).
- **Reporting gaps** are drawn with a 45° hatch in muted ink and labelled "not reported", so they never look like zero.
- **Status colors** (good, warning, critical) are used only on the Data & methods page, always with an icon and a label.

### Type

**Public Sans** (Google Fonts, 400/500/700) for everything. It is the typeface of the US Web Design System, used across US government and public-health sites: neutral, highly legible, with good tabular figures and plain zeros. (Atkinson Hyperlegible Next was tried first, but its slashed zero reads as "2Ø2Ø" in a dashboard full of years and counts, and there is no alternate glyph.) Tabular figures are used in tables and on axes; proportional figures elsewhere. The scale is a 1.25 ratio: 13 / 15 / 18 / 23 / 29 / 46 px, with body text at 15–16 px and line length capped at 72 characters. Copy is in sentence case: no all-caps eyebrows and no monospace data labels.

### Layout

- **Desktop (≥1024 px):** a 72 px left rail (icon + short label) and a fluid content column up to 1280 px, left-aligned on a 12-column grid.
- **Mobile (below 900 px):** the rail is replaced by a slim top bar showing the page name, with a menu button that opens a drawer listing every page plus the theme switch. A bottom tab bar was tried first, but seven pages plus the theme switch made it crowded; a four-tabs-plus-More bar and scrolling top tabs were also prototyped before choosing the drawer as the most standard pattern. Charts stack in one column.
- **No card chrome.** Views sit directly on the page plane, separated by whitespace and a single hairline per section. Headline stats are typographic (a large number with a label underneath), not boxed tiles.

### Chart anatomy (every view)

- **Title** states the finding or the question ("Severity fell nine-fold after 2021"). The **subtitle** says how to read it.
- **Footer:** the source, the computing SQL query (e.g. `q12_cfr_by_quarter`), and **Chart · Table** toggles; every chart has a table view.
- **Interaction:** crosshair and a single tooltip on line charts; per-mark tooltips on bars, cells and map regions; full keyboard focus. Values lead and labels follow in tooltips.
- **Marks:** 2 px lines, thin bars with a 2 px gap, recessive grid, direct labels for up to 4 series, and never a dual axis.
- **Motion:** one orchestrated moment only, when the spine draws in on first load. Everything else responds only to user actions, and `prefers-reduced-motion` is respected.

## 5. Data contract (pipeline → dashboard)

A new `covid-pipeline web-export` command writes static files to `dashboard/public/data/`:

| File | Contents | Size (est.) |
|---|---|---|
| `countries.json` | `dim_country` attributes | ~40 KB |
| `weekly.json` | Columnar: one shared `weeks[208]` axis, plus per-country arrays for deaths, cases, per-million flows, cumulative deaths per million, CFR, vaccination/booster rates, hospital/ICU per million, bed-occupancy share and the reported flags | ~3.5 MB raw / ~1 MB gzipped |
| `forecast.json` | Forecast rows + 80% intervals | ~120 KB |
| `model.json` | `reports/forecast_metrics.json` | ~5 KB |
| `quality.json` | DQ report + raw-source manifest + run timestamp | ~5 KB |
| `sql/*.json` | Results of the SQL-pack queries the pages quote (q01, q05, q06, q08, q12, q13, q15, q17, q18, q20) | ~60 KB |

Headline numbers and findings come from the SQL-pack results rather than being recomputed in JavaScript, so the dashboard, the notebooks and the SQL pack can't disagree. Interactive re-aggregation (a region plus a period) is done in the browser from `weekly.json`, using population-weighted formulas identical to the SQL. Those formulas get unit tests that check them against the SQL outputs.

## 6. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Build | **Vite + TypeScript** | Fast, static output, nothing to run in production. |
| UI | **Svelte 5** | Compiled, a tiny runtime and readable reactive filter state; well suited to a filter-driven dashboard. |
| Charts | Small custom Svelte SVG components on **d3** scales/shapes/geo | Full control of the visual system (hatching, emphasis, crosshairs, keyboard readouts). Observable Plot was planned, but the custom components ended up smaller and closer to the design. |
| Map | `world-atlas` 110m TopoJSON + `d3-geo` (Equal Earth projection) | About 100 KB and an honest area projection. |
| Tests | **Vitest** parity tests (browser aggregation vs the SQL pack) + `svelte-check`; visual QA by headless-Chrome screenshots in both themes at desktop and phone widths | Catches numbers drifting and broken pages. |
| Hosting | **GitHub Pages** via Actions: run the pipeline, then `web-export`, then `vite build`, then deploy | Free, lives with the repo and rebuilds weekly. |

Rejected options: **Observable Framework** (its releases have slowed since March 2026 and it imposes its own look), **Streamlit/Dash** (needs a server and looks generic), **DuckDB-WASM for every page** (a 6 MB+ cold start on mobile for no reader-visible gain). DuckDB-WASM may come back later as an opt-in "Run the SQL pack in your browser" panel on the Data & methods page.

## 7. Build phases

| Phase | Scope | Done when |
|---|---|---|
| **0. Design sign-off** | This document plus an Overview wireframe | You approve or redirect. |
| **1. Foundation** | `web-export` command, Vite/Svelte scaffold, design tokens (light/dark), app shell (rail, routing, URL state), timeline spine with brush, Overview page | Overview works end to end on real data, locally. |
| **2. Explore** | Where it hit (map + ranks), Country page and drill-through, Chart/Table toggles | Any country can be reached in 2 clicks; the map is keyboard-navigable. |
| **3. Analysis** | Vaccines & severity, Hospital strain, Outlook | Every quoted number matches the SQL pack (tests). |
| **4. Trust and ship** | Data & methods page, a11y pass (keyboard, contrast, reduced motion, screen-reader labels), mobile pass, Playwright smoke, GitHub Pages workflow | The public URL is live and linked from the README. |

## 8. Addendum: the Simulator page

Added after the seven pages above shipped. The other pages describe what happened; this one lets a visitor ask what could happen. The modelling is covered in the README and [`docs/simulator/RESEARCH.md`](../simulator/RESEARCH.md); this section records the design decisions.

**Who it is for.** The first version put every control and every chart on one screen and updated live. A review found it overwhelming for anyone who is not a modeller, so the page was rebuilt around four rules:

1. **Start blank, with examples.** Nothing is pre-selected. Six ready-made scenarios, each one sentence long, run in one click.
2. **Three plain questions, then an explicit Run.** Where? What disease? How does the place respond? Each step offers everyday choices (a country, "Like measles", "Lock down early") and keeps the numeric controls behind "Fine-tune". Edits change a draft; only Run applies it, so the results on screen always match the settings shown.
3. **The story first.** Results open with one sentence in everyday numbers ("about half of all people would catch it"), four large figures, one chart with the "if nothing were done" path for contrast, the three inputs that matter most in words, and a plain statement that this is a scenario, not a prediction.
4. **Depth on demand.** Detailed charts, the sensitivity analysis, the classifier's second opinion, similar real countries, the written report and the model card sit in one collapsed "Explore the details" section.

**What carries over from the visual system.** Each metric keeps its hue (deaths oxblood, infections indigo, vaccination teal, hospital load amber). Uncertainty is a band in the same hue, never a second colour. Every chart keeps its table view. The scenario lives in the URL, so a link reproduces exactly what was seen; the URL only ever holds a scenario that was run.

**What is new.**

| | |
|---|---|
| Data | `simulator.json` (about 435 KB) is loaded only on this page: learned constants, uncertainty spreads, 14 disease presets, 236 country profiles and the validation scores. |
| Compute | The engine runs in a Web Worker: 200 Monte Carlo draws and a one-at-a-time sensitivity analysis, without blocking the page. A short running screen names each stage. |
| Report | A three-page PDF with vector charts, built in the browser with jsPDF. The library loads only when the button is pressed. |
| Cloud | An optional panel inside the details sends the scenario to a small service for 2,000 draws and Sobol indices ([`docs/simulator/CLOUD.md`](../simulator/CLOUD.md)). It appears only if the service is configured and answering, and it is the only part of the site that sends a visitor's choices anywhere. |
| Tests | Golden scenarios hold the TypeScript engine to the Python reference; a schema generated from the service's request models checks every scenario the page can build. |
