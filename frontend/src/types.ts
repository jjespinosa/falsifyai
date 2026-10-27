export type StageStatus = "pending" | "running" | "success" | "blocked" | "failed" | "skipped";

export interface StageRecord {
  name: string;
  status: StageStatus;
  detail: string;
  elapsed_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
}

export interface ExampleCard {
  example_id: "pendulum" | "vague_field" | "synthetic" | "duffing" | "dq12";
  category: "FOUNDATIONAL" | "VAGUE" | "SYNTHETIC CONTROL" | "FRONTIER STRESS TEST";
  title: string;
  label: string;
  purpose: string;
  statement: string;
  notice: string | null;
}

export interface RunResult {
  run_id: string;
  status: "completed" | "scientifically_blocked" | "failed";
  hypothesis_text: string;
  stages: StageRecord[];
  parser: {
    claims: Array<{
      claim_id: string;
      statement: string;
      epistemic_status: string;
      is_operational: boolean;
      missing_definitions: Array<{ statement: string; critical: boolean }>;
    }>;
  } | null;
  critique: {
    blocking_issues: unknown[];
    major_issues: unknown[];
    minor_issues: unknown[];
    conventional_explanations: Array<{ explanation_id: string; statement: string }>;
    required_clarifications: string[];
  } | null;
  null_model: {
    models: Array<{
      model_id: string;
      description: string;
      can_mimic_claim: boolean;
      known_confounders: string[];
      equations: Array<{ statement: string }>;
    }>;
  } | null;
  observable_design: {
    observables: Array<{
      observable_id: string;
      name: string;
      definition: string;
      h1_prediction: string;
      h0_prediction: string;
      required_controls: string[];
      discriminating: boolean;
    }>;
    blocking_issues: string[];
  } | null;
  simulation_plan: {
    status: string;
    blocking_missing_definitions: string[];
    summary: string;
    spec: {
      simulation_id: string;
      h0: { family: string };
      h1: { family: string };
    } | null;
  } | null;
  simulation_result: {
    simulation_id: string;
    x: number[];
    h0: number[];
    h1: number[];
    delta: number[];
  } | null;
  experiment: {
    status: string;
    blocking_missing_definitions: string[];
    experiment: {
      experiment_id: string;
      objective: string;
      observable_ids: string[];
      independent_variables: Array<{ name: string }>;
      measured_variables: Array<{ name: string }>;
      controlled_variables: Array<{ name: string }>;
      required_resolution: { status: string; value: number | null; units: string };
      falsifier_candidate: string;
    } | null;
  } | null;
  verdict: {
    status: "TESTABLE" | "BELOW_SENSITIVITY" | "NON_DISCRIMINATING" | "NOT_YET_FALSIFIABLE";
    primary_reason: string;
    falsifier: string;
    required_next_definition: string | null;
    delta_over_sigma: number | null;
    evidence_refs: string[];
  } | null;
  summary: {
    claim: string;
    null_model: string;
    observable: string | null;
    simulation_status: string;
    experiment_status: string;
    verdict: string;
    primary_reason: string;
    required_next_definition: string | null;
  } | null;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    reasoning_tokens: number;
    total_tokens: number;
    model_calls: number;
    elapsed_ms: number;
  };
  error: string | null;
  failure: {
    stage: string;
    failure_kind: "schema_validation" | "json_decode" | "system";
    safe_message: string;
    validation_paths: string[];
  } | null;
}
