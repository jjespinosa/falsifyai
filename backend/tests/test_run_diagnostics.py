"""Run diagnostics, checkpoints, and resume. These tests do not call the network."""

import importlib.util
import json
from pathlib import Path

import pytest

from app.config import load_settings
from app.diagnostics.run_checkpoint import (
    ResumeRefused,
    build_resume_request,
    load_resume,
    parse_resume_args,
    select_resume,
)
from app.prompts.parser import PARSER_SYSTEM_PROMPT, parser_user_prompt
from app.providers.schema_json import strict_json_schema
from app.schemas.hypothesis import HypothesisInput
from app.schemas.parser import ParserResult
from app.schemas.run import RunRequest
from app.services.m2_fixtures import CASE_MASS
from app.services.modes import ExecutionMode
from app.services.run import RunDiagnostics, execute_run

_SECRET = "LLM_run_diagnostic_secret"


class _RecordingTransport:
    def __init__(self, content: str) -> None:
        self.content = content
        self.bodies: list[dict[str, object]] = []
        self.last_body: dict[str, object] | None = None
        self.last_http_status: int | None = None
        self.last_usage: dict[str, int] | None = None

    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
        self.bodies.append(body)
        self.last_http_status = 200
        self.last_usage = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "reasoning_tokens": 3,
            "total_tokens": 18,
        }
        self.last_body = {
            "model": "muse-spark-1.3",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": self.content},
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
        }
        return self.last_body


def _settings():
    return load_settings(
        {
            "MODEL_API_KEY": _SECRET,
            "META_BASE_URL": "https://api.meta.ai/v1",
            "META_MODEL_ID": "muse-spark-1.3",
        }
    )


def _diagnostics(tmp_path: Path) -> RunDiagnostics:
    return RunDiagnostics(
        checkpoint_path=tmp_path / "live_run_checkpoint.json",
        parser_response_path=tmp_path / "live_run_parser_response.json",
        secret=_SECRET,
    )


def test_orchestrator_reuses_the_canonical_parser_prompt_and_reports_safe_paths(tmp_path: Path) -> None:
    baseline = execute_run(
        RunRequest(hypothesis=HypothesisInput(statement=CASE_MASS)),
        settings=load_settings({}),
        run_id_factory=lambda: "run_stub0001",
    )
    assert baseline.parser is not None
    payload = json.loads(baseline.parser.model_dump_json())
    payload["claims"][0]["claim_id"] = "C1"
    payload["claims"][0]["statement"] = f"see {_SECRET} Bearer super-secret-token"
    transport = _RecordingTransport(json.dumps(payload))
    diagnostics = _diagnostics(tmp_path)
    hypothesis = HypothesisInput(statement=CASE_MASS)
    result = execute_run(
        RunRequest(
            hypothesis=hypothesis,
            mode=ExecutionMode.LIVE,
            reasoning_profile="economy",
        ),
        settings=_settings(),
        transport=transport,
        run_id_factory=lambda: "run_parser01",
        diagnostics=diagnostics,
    )

    body = transport.bodies[0]
    assert len(transport.bodies) == 1
    assert body["reasoning_effort"] == "minimal"
    messages = body["messages"]
    assert messages[0]["content"] == PARSER_SYSTEM_PROMPT
    assert messages[1]["content"] == parser_user_prompt(hypothesis.model_dump_json())
    assert PARSER_SYSTEM_PROMPT not in messages[1]["content"]
    schema = body["response_format"]["json_schema"]
    assert schema["name"] == "ParserResult"
    assert schema["schema"] == strict_json_schema(ParserResult)
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.stage == "parser"
    assert result.failure.failure_kind == "schema_validation"
    assert result.failure.safe_message == "Parser response did not satisfy ParserResult"
    assert "claims.0.claim_id" in result.failure.validation_paths
    assert result.summary is None
    assert next(stage.status for stage in result.stages if stage.name == "judge") == "skipped"
    assert result.usage.model_calls == 1
    saved_result = result.model_dump_json()
    assert _SECRET not in saved_result
    assert "super-secret-token" not in saved_result
    assert "Bearer " not in saved_result
    parser_file = diagnostics.parser_response_path.read_text(encoding="utf-8")
    checkpoint_file = diagnostics.checkpoint_path.read_text(encoding="utf-8")
    assert _SECRET not in parser_file
    assert "super-secret-token" not in parser_file
    assert "Authorization" not in parser_file
    assert json.loads(checkpoint_file)["last_valid_stage"] == "hypothesis"
    replayed = json.loads(parser_file)["content"]
    with pytest.raises(Exception) as captured:
        ParserResult.model_validate(replayed)
    assert any(error["loc"] == ("claims", 0, "claim_id") for error in captured.value.errors())


def test_checkpoint_sanitizer_and_resume_from_critic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    diagnostics = _diagnostics(tmp_path)
    execute_run(
        RunRequest(
            hypothesis=HypothesisInput(
                statement=CASE_MASS,
                context=f"Bearer super-secret-token {_SECRET}",
            )
        ),
        settings=_settings(),
        run_id_factory=lambda: "run_stub0002",
        diagnostics=diagnostics,
    )
    saved = diagnostics.checkpoint_path.read_text(encoding="utf-8")
    document = json.loads(saved)

    assert _SECRET not in saved
    assert "super-secret-token" not in saved
    assert document["last_valid_stage"] == "judge"
    assert document["simulation_skipped"] is True
    selection = load_resume(diagnostics.checkpoint_path, "critic")
    assert selection.parser is not None
    assert selection.parser.claims[0].claim_id == "c1"
    broken = json.loads(saved)
    broken["stages"]["parser"] = {"claims": []}
    with pytest.raises(ResumeRefused, match="parser checkpoint failed validation"):
        select_resume(broken, "critic")
    without_simulation = json.loads(saved)
    without_simulation["simulation_skipped"] = None
    with pytest.raises(ResumeRefused, match="explicit skip"):
        select_resume(without_simulation, "experiment")

    def parser_must_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("resume called the parser")

    monkeypatch.setattr("app.services.run.parse_hypothesis", parser_must_not_run)
    request = RunRequest(hypothesis=selection.hypothesis)
    resumed = execute_run(
        request,
        settings=_settings(),
        run_id_factory=lambda: "run_resume01",
        resume=selection,
    )

    assert resumed.status == "scientifically_blocked"
    assert resumed.verdict is not None
    assert resumed.verdict.status == "NOT_YET_FALSIFIABLE"
    assert next(stage.detail for stage in resumed.stages if stage.name == "parser").startswith("Resumed")
    assert resumed.usage.model_calls == 0


def test_downstream_schema_failure_keeps_the_last_valid_checkpoint(tmp_path: Path) -> None:
    baseline = execute_run(
        RunRequest(hypothesis=HypothesisInput(statement=CASE_MASS)),
        settings=load_settings({}),
        run_id_factory=lambda: "run_stub0003",
    )
    assert baseline.parser is not None
    transport = _SequenceTransport([baseline.parser.model_dump_json(), "{}"])
    diagnostics = _diagnostics(tmp_path)
    result = execute_run(
        RunRequest(
            hypothesis=HypothesisInput(statement=CASE_MASS),
            mode=ExecutionMode.LIVE,
            reasoning_profile="economy",
        ),
        settings=_settings(),
        transport=transport,
        run_id_factory=lambda: "run_critic01",
        diagnostics=diagnostics,
    )
    saved = json.loads(diagnostics.checkpoint_path.read_text(encoding="utf-8"))
    critic_file = tmp_path / "live_run_critic_response.json"

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.stage == "critic"
    assert result.failure.failure_kind == "schema_validation"
    assert result.failure.validation_paths
    assert saved["last_valid_stage"] == "parser"
    assert critic_file.is_file()
    assert _SECRET not in critic_file.read_text(encoding="utf-8")
    assert next(stage.status for stage in result.stages if stage.name == "judge") == "skipped"
    assert len(transport.bodies) == 2


class _SequenceTransport(_RecordingTransport):
    def __init__(self, contents: list[str]) -> None:
        super().__init__(contents[0])
        self._contents = contents
        self._index = 0

    def post_json(self, *, url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
        self.content = self._contents[self._index]
        self._index += 1
        return super().post_json(url=url, headers=headers, body=body)


def test_resume_request_stays_live_and_arguments_reject_unknown_stages() -> None:
    hypothesis = HypothesisInput(statement="A claim with a defined quantity is still unchecked here.")
    selection = select_resume(
        {"stages": {"hypothesis": json.loads(hypothesis.model_dump_json())}},
        "parser",
    )
    request = build_resume_request(selection)

    assert request.mode is ExecutionMode.LIVE
    assert request.reasoning_profile == "economy"
    assert parse_resume_args(["--from", "experiment"]) == ("experiment", None)
    for stage in ("parser", "critic", "null_model", "observable", "simulation_plan", "experiment"):
        assert parse_resume_args(["--from", stage])[0] == stage
    with pytest.raises(ResumeRefused):
        parse_resume_args(["--from", "balanced"])
    with pytest.raises(ResumeRefused):
        parse_resume_args([])


def test_resume_script_refuses_a_bad_checkpoint_without_the_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during resume refusal")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    module = _load_resume_script()
    broken = tmp_path / "checkpoint.json"
    broken.write_text("{", encoding="utf-8")

    assert module.main(["--from", "high"]) == 2
    assert module.main(["--from", "critic", "--checkpoint", str(broken)]) == 2


def test_resume_script_import_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call during resume import")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    module = _load_resume_script()

    assert module.__name__ != "__main__"


def _load_resume_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "live_m5_resume.py"
    spec = importlib.util.spec_from_file_location("live_m5_resume_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
