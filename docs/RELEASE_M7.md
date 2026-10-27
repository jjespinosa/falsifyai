# Release M7

M7 packages the verified scientific pipeline for a hackathon judge. It does not add a scientific agent and it does not change verdict rules.

| Milestone | What landed |
|---|---|
| M0 | Service shell, schemas, and the provider boundary |
| M1 | Parser and adversarial critic |
| M2 | Null model and observable designer |
| M3 | Restricted simulator on registered numerical families |
| M4 | Experiment designer and falsification judge |
| M5 | One orchestrated run and the local result screen |
| M6 | Duffing quantitative control and DQ-12 stress test |
| M7 | One-origin release, demo limits, and judge-facing materials |

`GET /health` reports milestone `M7`.

The production process is one container. Node builds `frontend/`. Python runs FastAPI, which serves `/api/v1/*` and the built screen. `MODEL_API_KEY` stays on the server. `LIVE_RUNS_ENABLED=false` keeps stub examples working and refuses live calls without substituting a stub result.

Development still uses Vite on port 5173 and the API on port 8010. The container command is:

```text
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}
```
