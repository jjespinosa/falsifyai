# FalsifyAI

FalsifyAI is an adversarial scientific AI. It does not try to prove a user's hypothesis. It looks for the strongest experiment that could falsify it.

This repository is a new project for the Meta Global AI Developer Hackathon 2026, Indie Developer track, theme Push the Frontier. Work presented from this repository is built during the hackathon window, October 26–November 4, 2026.

## Pipeline

The target pipeline is:

Hypothesis → Hypothesis Parser → Adversarial Critic → Null Model → Observable → Simulation → Experiment → Falsification Judge

The implemented milestone is M5: the verified pipeline from parser through falsification judge, one synchronous run, and a local screen that shows the result. Later product work is not implemented.

## Scientific rules

1. No verdict without a measurable observable.
2. No discrimination without a null model.
3. Never invent experimental measurements.
4. Keep provenance distinct from epistemic status and from operationality. Provenance is measured, literature-derived, assumed, or simulated. Epistemic status is established, hypothesis, speculative, or unknown.
5. A hypothesis may legitimately end as `NOT_YET_FALSIFIABLE`.
6. Do not execute arbitrary model-generated Python.
7. Simulations use validated declarative specifications and registered numerical routines. The planner returns blocked when H1 has no quantitative law.
8. DQ-12, when it is added, is only a speculative adversarial stress test. It is not established physics.
9. A Duffing oscillator comparison, when it is added, is an independent control case.

Rules 1, 3, 4, and 6 constrain the claim schemas. A measured claim must name an observable. A literature-derived claim must name a source. A simulated claim must name a specification id and a routine id. Established status requires one of those evidence-bearing origins. A speculative status can still be operational when the quantities are defined. There is no field for executable code. The pipeline registers four numerical families, designs an experiment, and the judge may return `NOT_YET_FALSIFIABLE`.

## Stack

- Python 3.12
- FastAPI, Uvicorn, and Pydantic v2
- pytest
- React, TypeScript, and Vite for the local screen

NumPy evaluates the registered families. SciPy, SymPy, and SQLite are intentionally absent.

## Milestone M5

`GET /health` and `GET /help` both report milestone `M5`.

Included:

- FastAPI application, `GET /health`, and `GET /help`
- `HypothesisInput` and `ScientificClaim` schemas
- the verified per-stage analysis routes and `POST /api/v1/simulate`
- `POST /api/v1/run` and `GET /api/v1/examples`
- reasoning profiles `economy` and `balanced`
- a local React screen for one hypothesis and one result
- environment configuration for the Meta Model API
- a stub provider for tests and an explicit live provider

Not included:

- database, authentication, DQ-12 demo, Duffing demo, and deployment

## Configuration

`MODEL_API_KEY` is read only from the environment. Copy `.env.example` to `.env` and set the key locally. The real key must not be committed, logged, or placed in source, tests, or this README.

```text
MODEL_API_KEY=
META_BASE_URL=https://api.meta.ai/v1
META_MODEL_ID=muse-spark-1.3
```

`muse-spark-1.3` is the currently verified primary model. Set `META_MODEL_ID` explicitly. An empty value does not select a model.

`MODEL_API_KEY` is required only for live calls. Tests stay network-free by default: the default provider is `StubModelProvider`, and the pytest suite does not call the Meta Model API. `MetaModelProvider` refuses to initialize when `MODEL_API_KEY` is missing, `META_MODEL_ID` is missing, or `META_BASE_URL` is not an absolute https URL. Live structured output sets `response_format.json_schema.strict` to true. Manual canaries load the repository-root `.env` and do not override variables already set in the process. `python scripts/live_m1_smoke.py` calls the parser and the critic. `python scripts/live_m2_smoke.py` continues through the null model and the observable designer. `python scripts/live_m3_smoke.py` adds the simulation planner and does not call `/simulate` when the plan is blocked. `python scripts/local_m3_engine.py` runs the synthetic numerical fixture and does not call the model. `python scripts/live_m4_smoke.py` continues through the experiment designer and the judge, and it does not call the simulator. `python scripts/local_m4_verdicts.py` runs the four stub verdict classes and does not call the model. `python scripts/live_m5_smoke.py` is the manual live run canary. Pytest does not run these scripts.

This package does not load `.env` itself. Pass it to Uvicorn when you want the server process to see it.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
uvicorn app.main:app --app-dir backend --env-file .env --reload --port 8010
```

The screen, from `frontend/`, in its own process:

```powershell
npm install
npm run dev
```

`frontend/.env.development` sets `VITE_API_BASE_URL=http://127.0.0.1:8010`. Vite does not start or proxy the API. Do not put a key in a `VITE_` variable. Development CORS allows `http://localhost:5173` and `http://127.0.0.1:5173` only. See [docs/m5.md](docs/m5.md).

`GET /health` returns the service name and milestone `M5`. It does not call the model and does not expose configuration.

## Documentation

The operator guide for the shell is [docs/m0.md](docs/m0.md). Parser and critic usage is [docs/m1.md](docs/m1.md). Null-model and observable usage is [docs/m2.md](docs/m2.md). Simulation planning and the local evaluator are [docs/m3.md](docs/m3.md). Experiment design and the judge are [docs/m4.md](docs/m4.md). The run and the local screen are [docs/m5.md](docs/m5.md). `GET /help` returns the current contract as JSON and does not echo the process environment. `GET /docs` and `GET /redoc` serve the OpenAPI reference.
