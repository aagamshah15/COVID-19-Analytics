# The simulator's cloud API

The simulator page runs every scenario in the visitor's browser. This service is an optional extra: the Python reference engine behind a small web API on Google Cloud Run. It does two things a browser tab does badly:

- **A deeper analysis.** 5,000 Monte Carlo runs instead of 200, plus Sobol sensitivity indices, which measure how much of the uncertainty in deaths each input accounts for, alone and in combination with the others.
- **Programmatic access.** Anyone can post a scenario and get the reference engine's answer as JSON.

**The dashboard never depends on it.** If the service is not configured, not deployed, asleep, over its limits or deleted, the page hides the "deeper look" panel and everything else works as before.

## Endpoints

| | |
|---|---|
| `GET /health` | Liveness, and the version of the bundled model card |
| `GET /model` | The model card: learned constants, uncertainty spreads, validation scores and the disease presets |
| `POST /simulate` | One scenario: headline numbers, the no-response comparison, daily series, and ranges from up to 500 draws |
| `POST /analyze/deep` | 5,000-draw ranges and Sobol indices for one scenario |
| `GET /docs` | Interactive documentation generated from the request models |

A scenario is the same JSON the browser's engine consumes: a place, a pathogen, a response, a variant, the learned constants, where each learned value came from, and the spreads to draw from. [`api/scenario.schema.json`](../../api/scenario.schema.json) describes it and bounds every number. In that JSON, `null` means "never" or "lifelong" (JSON cannot carry infinity).

```bash
curl -s https://<service-url>/model | jq '.constants, .presets[0]'
curl -s -X POST https://<service-url>/simulate \
  -H 'content-type: application/json' \
  -d '{"scenario": { ... }, "draws": 200}' | jq '.summary, .ensemble.quantiles.deaths'
```

The easiest way to get a full scenario is to run one on the simulator page and copy the request from the browser's network tab after pressing "Run the deeper analysis".

### Keeping the two engines honest

- `tests/test_api.py` posts the golden scenarios and checks the answers against the same fixtures the browser engine is tested against.
- `dashboard/src/lib/sim/cloud.test.ts` checks every scenario the page can build (all countries, diseases, plans and vaccine choices) against the schema generated from the service's request models, so the two sides cannot drift apart unnoticed.
- The "deeper look" panel shows the browser's ranges beside the service's. They come from two implementations drawing their own random inputs. On 5,000 draws each they agree to within a few percent.

## What it costs

**On Google's free trial, nothing: a trial account is never billed.** When the trial ends or its credit runs out, Google stops the project's resources unless the billing account is upgraded to a paid one. The service then stops answering and the dashboard hides the panel.

After an upgrade, usage is billed beyond Cloud Run's monthly free tier: 180,000 vCPU-seconds, 360,000 GiB-seconds of memory, 2 million requests and 1 GB of data sent out. The service is built to stay inside it:

| Guard | Setting | What it bounds |
|---|---|---|
| Instances | At most 1, none when idle, billed only while serving requests | Instance time |
| Size | 1 vCPU, 1 GiB, 4 requests at a time, 120-second timeout | Instance time and memory |
| Compute budget | 4,000 seconds of scenario computing a day, across all callers | Instance time: about 120,000 vCPU-seconds a month at most |
| Daily calls | 300 `/simulate` and 200 `/analyze/deep` a day, across all callers | Data sent out: about 28 MB a day at most |
| Per caller | 30 `/simulate` and 4 `/analyze/deep` a minute per address | One caller using everyone's share |
| Heavy work | One deep analysis at a time | Memory (378 MiB at the measured worst case) |
| Requests | Bodies over 64 KB refused; every number in a scenario bounded; at most 3 simulated years | Work per request |
| Answers | Compressed; validation errors do not echo the request | Data sent out |
| Images | Artifact Registry keeps the two newest | Storage (0.5 GB free) |
| Browsers | Only the dashboard's origin may call from a browser | Use from other sites |
| Alert | A budget emails the billing administrators at 50% and 100% of 1 USD | Early warning |

The limits live in memory, which is enough for a single instance. They reset when the instance restarts.

**What the guards cannot stop.** Google counts and bills requests before the service can refuse them, and an instance kept busy refusing requests is still running. On a paid account, a sustained flood from many addresses could therefore exceed the free tier however the service is written. Cloud Run has no spending cap. The budget alert is the warning, and deleting the service (below) is the off switch. For a hard cap, Google documents how to have a budget notification disable billing automatically; that is not set up here.

## One-time setup

You need a Google Cloud project with a billing account linked, and the `gcloud` CLI signed in as its owner.

```bash
PROJECT_ID=<your-project-id> ./infra/gcp_setup.sh
```

[`infra/gcp_setup.sh`](../../infra/gcp_setup.sh) enables the APIs, then creates:

- an Artifact Registry repository with the keep-two cleanup policy
- a service account the service runs as, with no permissions at all
- a service account GitHub Actions deploys as, which can deploy Cloud Run services, push to that one repository and nothing else
- Workload Identity Federation limited to this repository's `main` branch, so no key is ever stored in GitHub
- the budget alert

It deploys nothing and is safe to run again. It ends by printing four `gh variable set` commands; run them to tell the deploy workflow where to deploy.

## Deploying

[`.github/workflows/api.yml`](../../.github/workflows/api.yml) runs when the API or the engine changes on `main`, or on demand (Actions > api > Run workflow). It runs the API's tests, bundles the live site's model card, builds the image from [`api/Dockerfile`](../../api/Dockerfile), pushes it and deploys it with the settings in the table above, then checks `/health` on the live service. Until the repository variables exist it does nothing.

To show the panel on the dashboard, set the service's address and rebuild the site:

```bash
gh variable set SIM_API_URL --body "https://<service-url>"
gh workflow run pipeline
```

## Running it locally

```bash
pip install -e ".[dev,api]"
uvicorn api.main:app --reload --port 8080      # http://localhost:8080/docs
pytest tests/test_api.py tests/test_sim_analysis.py
```

Or as the container Cloud Run would run, with the same limits:

```bash
docker build -f api/Dockerfile -t simulator-api .
docker run --rm -p 8080:8080 --cpus 1 --memory 1g simulator-api
```

To point a local dashboard at it, put `VITE_SIM_API_URL=http://localhost:8080` in `dashboard/.env.local` and restart `npm run dev`.

Measured in that container on a laptop: about 1 second to start, 6 to 17 seconds for a deep analysis of a one- to three-year scenario, and a 117 MB image. Cloud Run's processors are slower, so expect roughly double.

Every limit can be changed without a rebuild by setting an environment variable on the service, for example `DEEP_PER_DAY=50` or `COMPUTE_SECONDS_PER_DAY=2000` (see `Settings` in [`api/main.py`](../../api/main.py)). After changing the request models, regenerate the schema with `python -m api.schemas`; a test fails if it is stale.

## Turning it off

```bash
gcloud run services delete simulator-api --region us-central1 --project <your-project-id>
gh variable delete SIM_API_URL        # then rebuild the site, or leave it: the panel hides itself
```

Deleting the project removes everything the setup script created.
