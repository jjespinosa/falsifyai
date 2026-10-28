import { useEffect, useState } from "react";

import { loadExamples, runHypothesis } from "./api";
import { CurveChart } from "./Chart";
import {
  BENCHMARK_NOTE,
  FEATURED_EXAMPLES,
  FRONTIER_ADVERSARIAL,
  MISSING_LINK,
  curveLabels,
  exampleMatching,
  executionLabel,
  formatQuantity,
  isDemoMode,
  isFeaturedExample,
  maximumSeparation,
  statementFor,
  traceIds,
  verdictLabel,
  visualStatus,
  stageMap,
  VISUAL_STAGES,
} from "./presentation";
import type { ExampleCard, RunResult } from "./types";

function ExampleButton({ item, onSelect }: { item: ExampleCard; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect}>
      <span className="category">{item.category}</span>
      {item.category === "FRONTIER STRESS TEST" ? <span className="badge speculative">SPECULATIVE</span> : null}
      <strong>{item.title}</strong>
      <span className="card-label">{item.label}</span>
      <span className="card-purpose">{item.purpose}</span>
    </button>
  );
}

export function App() {
  const [examples, setExamples] = useState<ExampleCard[]>([]);
  const [statement, setStatement] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [mode, setMode] = useState<"stub" | "live">("stub");
  const [profile, setProfile] = useState<"economy" | "balanced">("economy");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [resultMode, setResultMode] = useState<"stub" | "live">("stub");
  const demo = isDemoMode(window.location.search);
  const [transportError, setTransportError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  useEffect(() => {
    loadExamples()
      .then(setExamples)
      .catch(() => setCatalogError("The example catalog could not be loaded."));
  }, []);

  async function submit() {
    setRunning(true);
    setTransportError(null);
    setResult(null);
    try {
      setResultMode(mode);
      setResult(await runHypothesis(statement, mode, profile));
    } catch (error) {
      setTransportError(error instanceof Error ? error.message : "Pipeline execution failed");
    } finally {
      setRunning(false);
    }
  }

  const stages = stageMap(result, running);
  const claim = result?.parser?.claims[0];
  const critique = result?.critique;
  const nullModel = result?.null_model?.models[0];
  const observable = result?.observable_design?.observables.find((item) => item.discriminating)
    ?? result?.observable_design?.observables[0];
  const plan = result?.experiment?.experiment;
  const matched = exampleMatching(examples, result?.hypothesis_text ?? statement);
  const labels = curveLabels(matched?.example_id);
  const separation = result?.simulation_result ? maximumSeparation(result.simulation_result.delta) : null;
  const resolution = plan?.required_resolution;
  const frontier = matched?.category === "FRONTIER STRESS TEST";
  const duffing = matched?.example_id === "duffing";
  const featured = FEATURED_EXAMPLES.flatMap((id) => examples.filter((item) => item.example_id === id));
  const secondary = examples.filter((item) => !isFeaturedExample(item.example_id));
  const scan = plan?.parameter_scan?.[0];

  return (
    <main className={demo ? "app demo" : "app"}>
      <header className="masthead">
        <h1>FalsifyAI</h1>
        <p className="identity">Executable Scientific Falsification Engine</p>
        <p className="subtitle">Compile a scientific hypothesis into an executable falsification test.</p>
        <p className="support">
          Most AI systems help defend an idea.
          FalsifyAI constructs the strongest competing explanation, searches for a discriminating observable, executes only justified numerical comparisons, and identifies what experiment could prove the hypothesis wrong.
        </p>
        <p className="flow" aria-label="Scientific pipeline">
          <b>Hypothesis</b><span>→</span>
          <b>Critique</b><span>→</span>
          <b>H₀</b><span>→</span>
          <b>Observable</b><span>→</span>
          <b>Simulation</b><span>→</span>
          <b>Experiment</b><span>→</span>
          <b>Verdict</b>
        </p>
      </header>

      <section className="composer">
        <label htmlFor="hypothesis">Scientific hypothesis</label>
        <textarea
          id="hypothesis"
          value={statement}
          placeholder="State one claim you want FalsifyAI to try to falsify..."
          onChange={(event) => {
            setStatement(event.target.value);
            setNotice(null);
          }}
        />
        <div className="examples">
          {featured.map((item) => (
            <ExampleButton
              key={item.example_id}
              item={item}
              onSelect={() => {
                setStatement(statementFor(examples, item.example_id));
                setNotice(item.notice);
              }}
            />
          ))}
        </div>
        {secondary.length > 0 ? (
          <details className="more-examples">
            <summary>More examples</summary>
            <div className="examples">
              {secondary.map((item) => (
                <ExampleButton
                  key={item.example_id}
                  item={item}
                  onSelect={() => {
                    setStatement(statementFor(examples, item.example_id));
                    setNotice(item.notice);
                  }}
                />
              ))}
            </div>
          </details>
        ) : null}
        {catalogError ? <p className="notice">{catalogError}</p> : null}
        {notice ? <p className="notice">{notice}</p> : null}
        <div className="actions">
          <button className="primary" type="button" disabled={running || statement.trim() === ""} onClick={submit}>
            TRY TO FALSIFY
          </button>
          <span className={`mode-flag ${mode === "live" ? "live" : ""}`}>{executionLabel(mode)}</span>
        </div>
        <details className="execution">
          <summary>Execution</summary>
          <div className="choices">
            <label className="choice"><input type="radio" checked={mode === "stub"} onChange={() => setMode("stub")} /> stub</label>
            <label className="choice"><input type="radio" checked={mode === "live"} onChange={() => setMode("live")} /> live</label>
            <label className="choice"><input type="radio" checked={profile === "economy"} onChange={() => setProfile("economy")} /> economy</label>
            <label className="choice"><input type="radio" checked={profile === "balanced"} onChange={() => setProfile("balanced")} /> balanced</label>
          </div>
        </details>
      </section>

      <section className="pipeline" aria-label="Falsification pipeline">
        {VISUAL_STAGES.map((item, index) => {
          const status = visualStatus(stages, item.key);
          return (
            <article key={item.key} className={`stage ${status}`}>
              <b>{index + 1}. {item.label}</b>
              <small>{status}</small>
            </article>
          );
        })}
      </section>

      {transportError ? (
        <section className="failure">
          <h2>Pipeline execution failed</h2>
          <p>{transportError}</p>
        </section>
      ) : null}

      {result?.status === "failed" ? (
        <>
          <section className="failure">
            <h2>Pipeline execution failed</h2>
          </section>
          <details className="developer">
            <summary>Developer</summary>
            {result.failure ? (
              <>
                <p>{result.failure.stage} · {result.failure.failure_kind}</p>
                <p>{result.failure.safe_message}</p>
                {result.failure.validation_paths.length > 0 ? (
                  <p>{result.failure.validation_paths.join(" · ")}</p>
                ) : null}
              </>
            ) : null}
            <p>
              calls {result.usage.model_calls} · prompt {result.usage.prompt_tokens} · completion {result.usage.completion_tokens} · reasoning {result.usage.reasoning_tokens} · total {result.usage.total_tokens} · {result.usage.elapsed_ms} ms
            </p>
          </details>
        </>
      ) : null}

      {result && result.status !== "failed" ? (
        <>
          <section className="grid">
            <article className="panel">
              <h2>Claim</h2>
              <p>{claim?.statement}</p>
              <p>Epistemic status: {claim?.epistemic_status}</p>
              <p>Operational: {claim?.is_operational ? "yes" : "no"}</p>
              <ul>
                {(claim?.missing_definitions ?? []).map((item) => <li key={item.statement}>{item.statement}</li>)}
              </ul>
            </article>
            <article className="panel">
              <h2>Adversarial critic</h2>
              <p>Blocking issues: {critique?.blocking_issues.length ?? 0}</p>
              <p>Major issues: {critique?.major_issues.length ?? 0}</p>
              <p>Minor issues: {critique?.minor_issues.length ?? 0}</p>
              <ul>
                {(critique?.conventional_explanations ?? []).slice(0, 3).map((item) => (
                  <li key={item.explanation_id}>{item.statement}</li>
                ))}
              </ul>
              <ul>
                {(critique?.required_clarifications ?? []).map((item) => <li key={item}>{item}</li>)}
              </ul>
            </article>
          </section>

          <article className="panel">
            <h2>Strongest null model — H₀</h2>
            <p className="mono">{nullModel?.model_id}</p>
            <p>{nullModel?.description}</p>
            <p>Can mimic an apparent H₁ effect: {nullModel?.can_mimic_claim ? "yes" : "no"}</p>
            <ul>{(nullModel?.known_confounders ?? []).slice(0, 4).map((item) => <li key={item}>{item}</li>)}</ul>
            {nullModel?.equations[0] ? <p className="mono">{nullModel.equations[0].statement}</p> : null}
          </article>

          <article className="panel">
            <h2>{observable?.discriminating ? "Discriminating observable" : "Observable"}</h2>
            {observable ? (
              <>
                {observable.discriminating ? null : <p>This candidate does not yet discriminate H1 from H0.</p>}
                <p><strong>{observable.name}</strong></p>
                <p>{observable.definition}</p>
                <p>H₁ prediction: {observable.h1_prediction}</p>
                <p>H₀ prediction: {observable.h0_prediction}</p>
                <ul>{observable.required_controls.map((item) => <li key={item}>{item}</li>)}</ul>
              </>
            ) : (
              <>
                <p>No discriminating observable is currently defined.</p>
                <p>{result.observable_design?.blocking_issues[0]}</p>
              </>
            )}
          </article>

          <article className="panel">
            {result.simulation_result ? (
              <>
                <h2>Simulation</h2>
                <CurveChart
                  {...result.simulation_result}
                  h0Label={labels.h0}
                  h1Label={labels.h1}
                  caption={labels.caption}
                />
                <div className="separation">
                  {separation !== null ? <p>Maximum model separation: {formatQuantity(separation)}</p> : null}
                  {resolution?.status === "defined" && resolution.value !== null ? (
                    <p>Specified uncertainty: {formatQuantity(resolution.value)} {resolution.units}</p>
                  ) : null}
                  {duffing && result.verdict?.delta_over_sigma !== null && result.verdict?.delta_over_sigma !== undefined ? (
                    <p>delta/sigma: {formatQuantity(result.verdict.delta_over_sigma)}</p>
                  ) : null}
                </div>
                {duffing ? (
                  <div className="facts">
                    <p>H₀ {observable?.h0_prediction}</p>
                    <p>H₁ {observable?.h1_prediction}</p>
                    {scan && scan.status === "defined" && scan.lower !== null && scan.upper !== null ? (
                      <p>Range: {formatQuantity(scan.lower)} &lt;= {scan.name} &lt;= {formatQuantity(scan.upper)}</p>
                    ) : null}
                    <p>{BENCHMARK_NOTE}</p>
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <h2>Simulation blocked</h2>
                <p>{result.simulation_plan?.blocking_missing_definitions[0] ?? result.simulation_plan?.summary}</p>
              </>
            )}
          </article>

          <article className="panel">
            <h2>Experiment <span className={`badge ${result.experiment?.status ?? ""}`}>{(result.experiment?.status ?? "").toUpperCase()}</span></h2>
            {plan ? (
              <>
                <p>{plan.objective}</p>
                <p>Independent variable: {plan.independent_variables.map((item) => item.name).join(", ")}</p>
                <p>Measured variable: {plan.measured_variables.map((item) => item.name).join(", ")}</p>
                <ul>{plan.controlled_variables.map((item) => <li key={item.name}>{item.name}</li>)}</ul>
                <p>
                  {plan.required_resolution.status === "undefined"
                    ? "Required sensitivity not yet defined."
                    : `Required resolution: ${plan.required_resolution.value} ${plan.required_resolution.units}`}
                </p>
                <p>{plan.falsifier_candidate}</p>
              </>
            ) : (
              <p>{result.experiment?.blocking_missing_definitions[0]}</p>
            )}
          </article>

          {result.verdict ? (
            <article className="verdict">
              <h2>Falsification status</h2>
              <p className={`mode-flag ${resultMode === "live" ? "live" : ""}`}>{executionLabel(resultMode)}</p>
              {frontier ? <p className="badge speculative">SPECULATIVE HYPOTHESIS</p> : null}
              <p className="label">{verdictLabel(result.verdict.status)}</p>
              {frontier ? <p>{FRONTIER_ADVERSARIAL}</p> : null}
              <h2>Why</h2>
              <p>{result.verdict.primary_reason}</p>
              {result.verdict.required_next_definition ? (
                <div className={frontier && result.verdict.status === "NOT_YET_FALSIFIABLE" ? "missing-link" : undefined}>
                  <h2>{frontier && result.verdict.status === "NOT_YET_FALSIFIABLE" ? "KEY MISSING LINK" : "What is missing"}</h2>
                  {frontier && result.verdict.status === "NOT_YET_FALSIFIABLE" ? <p>{MISSING_LINK}</p> : null}
                  <p>{result.verdict.required_next_definition}</p>
                </div>
              ) : null}
              <h2>What would falsify it</h2>
              <p>{result.verdict.falsifier}</p>
            </article>
          ) : null}

          <details className="trace">
            <summary>Scientific trace</summary>
            <p className="ids">{traceIds(result).join("  ")}</p>
            <pre>{JSON.stringify({
              claim,
              h0: nullModel,
              observable,
              simulation_decision: {
                plan_status: result.simulation_plan?.status ?? null,
                simulation_id: result.simulation_result?.simulation_id ?? result.simulation_plan?.spec?.simulation_id ?? null,
                families: result.simulation_plan?.spec
                  ? { h0: result.simulation_plan.spec.h0.family, h1: result.simulation_plan.spec.h1.family }
                  : null,
                arrays: result.simulation_result
                  ? {
                      x: result.simulation_result.x,
                      h0: result.simulation_result.h0,
                      h1: result.simulation_result.h1,
                      delta: result.simulation_result.delta,
                    }
                  : null,
              },
              experiment: result.experiment,
              verdict: result.verdict,
            }, null, 2)}</pre>
          </details>
          <details className="developer">
            <summary>Developer</summary>
            <p>
              calls {result.usage.model_calls} · prompt {result.usage.prompt_tokens} · completion {result.usage.completion_tokens} · reasoning {result.usage.reasoning_tokens} · total {result.usage.total_tokens} · {result.usage.elapsed_ms} ms
            </p>
          </details>
        </>
      ) : null}

      <section className="principles">
        <h2>WHY FALSIFYAI?</h2>
        <ul>
          <li><span>NO NULL MODEL</span><span>NO DISCRIMINATION</span></li>
          <li><span>NO OBSERVABLE</span><span>NO CLAIM OF TESTABILITY</span></li>
          <li><span>NO QUANTITATIVE LAW</span><span>NO INVENTED SIMULATION</span></li>
          <li><span>NO ARBITRARY MODEL-GENERATED CODE EXECUTION</span></li>
          <li>
            <span>FAIL CLOSED</span>
            <span>If the model provider, structured contract, or scientific prerequisite fails, downstream stages are skipped rather than fabricated.</span>
          </li>
        </ul>
      </section>

      <footer className="footer">
        <p>
          FalsifyAI compiles a hypothesis into an executable falsification contract. Model outputs are schema-validated, numerical execution is restricted to registered functions, and no arbitrary model-generated code is executed.
        </p>
        <p>Built for Meta Global AI Developer Hackathon 2026.</p>
      </footer>
    </main>
  );
}
