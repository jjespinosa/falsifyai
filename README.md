# FalsifyAI

FalsifyAI is an adversarial scientific AI. It does not try to prove a user's hypothesis. It looks for the strongest experiment that could falsify it.

This repository is a new project for the Meta Global AI Developer Hackathon 2026, Indie Developer track, theme Push the Frontier. Work presented from this repository is built during the hackathon window, October 26–November 4, 2026.

## Pipeline

The target pipeline is:

Hypothesis → Hypothesis Parser → Adversarial Critic → Null Model → Observable → Simulation → Experiment → Falsification Judge

Milestone M0 is only the application shell. None of those stages are implemented.

## Scientific rules

1. No verdict without a measurable observable.
2. No discrimination without a null model.
3. Never invent experimental measurements.
4. Keep these origins distinct: measured, literature-derived, assumed, and simulated.
5. A hypothesis may legitimately end as `NOT_YET_FALSIFIABLE`.
6. Do not execute arbitrary model-generated Python.
7. Simulations must use validated declarative specifications and registered numerical routines.
8. DQ-12, when it is added, is only a speculative adversarial stress test. It is not established physics.
9. A Duffing oscillator comparison, when it is added, is an independent control case.

Rules 1, 3, 4, 6, and 7 constrain the M0 schemas. A measured claim must name an observable. A literature-derived claim must name a source. A simulated claim must name a specification id and a routine id. There is no field for executable code. M0 does not register routines, run them, or produce a verdict. `NOT_YET_FALSIFIABLE` is a reserved future outcome of the judge, not a result this milestone can return.

## Stack

- Python 3.12
- FastAPI, Uvicorn, and Pydantic v2
- pytest

React, Vite, TypeScript, NumPy, SciPy, SymPy, and SQLite are intentionally absent.

## Milestone M0

Included:

- FastAPI application and `GET /health`
- `HypothesisInput` and `ScientificClaim` schemas
- environment configuration for the Meta Model API
- a provider interface, a Meta provider that refuses live calls, and an in-memory stub

Not included:

- Hypothesis Parser, Critic, Null Model, Observable Designer, Simulator, Experiment Designer, or Judge
- frontend, database, DQ-12 demo, and Duffing demo

## Configuration

`MODEL_API_KEY` is read only from the environment. Copy `.env.example` to `.env` and set the key locally. The real key must not be committed, logged, or placed in source, tests, or this README.

```text
MODEL_API_KEY=
META_BASE_URL=https://api.meta.ai/v1
META_MODEL_ID=muse-spark-1.3
```

`muse-spark-1.3` is the currently verified primary model. Set `META_MODEL_ID` explicitly. An empty value does not select a model.

`MODEL_API_KEY` is required only for live calls. Tests stay network-free by default: the default provider is `StubModelProvider`, and the pytest suite does not call the Meta Model API. `MetaModelProvider` is the live-mode gate. It refuses to initialize when `MODEL_API_KEY` is missing, `META_MODEL_ID` is missing, or `META_BASE_URL` is not an absolute https URL. This milestone still performs no live HTTP.

This package does not load `.env` itself. Pass it to Uvicorn when you want the server process to see it.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
uvicorn app.main:app --app-dir backend --env-file .env --reload
```

`GET /health` returns the service name and milestone. It does not call the model and does not expose configuration.
