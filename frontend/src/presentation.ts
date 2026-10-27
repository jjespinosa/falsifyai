import type { ExampleCard, RunResult, StageStatus } from "./types";

export const VERDICT_LABELS = {
  TESTABLE: "TESTABLE",
  BELOW_SENSITIVITY: "BELOW SENSITIVITY",
  NON_DISCRIMINATING: "NON-DISCRIMINATING",
  NOT_YET_FALSIFIABLE: "NOT YET FALSIFIABLE",
} as const;

export const VISUAL_STAGES = [
  { key: "parser", label: "Parse" },
  { key: "critic", label: "Critique" },
  { key: "null_model", label: "Null Model" },
  { key: "observable", label: "Observable" },
  { key: "simulation", label: "Simulation" },
  { key: "experiment", label: "Experiment" },
  { key: "judge", label: "Verdict" },
] as const;

export function verdictLabel(status: keyof typeof VERDICT_LABELS): string {
  return VERDICT_LABELS[status];
}

export function stageMap(result: RunResult | null, running: boolean): Record<string, StageStatus> {
  if (running) {
    return Object.fromEntries(VISUAL_STAGES.map((item) => [item.key, "running"])) as Record<
      string,
      StageStatus
    >;
  }
  const found: Record<string, StageStatus> = {};
  for (const stage of result?.stages ?? []) {
    found[stage.name] = stage.status;
  }
  return found;
}

export function simulationVisual(plan: StageStatus | undefined, execution: StageStatus | undefined): StageStatus {
  if (plan === "failed" || execution === "failed") {
    return "failed";
  }
  if (plan === "running" || execution === "running") {
    return "running";
  }
  if (plan === "blocked") {
    return "blocked";
  }
  if (plan === "success" && execution === "success") {
    return "success";
  }
  if (execution === "skipped" && plan !== "success") {
    return plan ?? "skipped";
  }
  return plan ?? execution ?? "pending";
}

export function visualStatus(stages: Record<string, StageStatus>, key: string): StageStatus {
  if (key === "simulation") {
    return simulationVisual(stages.simulation_plan, stages.simulation);
  }
  return stages[key] ?? "pending";
}

export const DUFFING_NOTICE = "Synthetic Duffing benchmark — model prediction, not experimental data.";
export const SPECULATIVE_NOTICE = "Speculative hypothesis — not established physics.";
export const FRONTIER_ADVERSARIAL =
  "FalsifyAI is testing this hypothesis adversarially. It is not attempting to validate DQ-12.";

export function statementFor(examples: ExampleCard[], exampleId: string): string {
  return examples.find((item) => item.example_id === exampleId)?.statement ?? "";
}

export function exampleMatching(examples: ExampleCard[], statement: string): ExampleCard | undefined {
  return examples.find((item) => item.statement === statement);
}

export function curveLabels(exampleId: string | undefined): { h0: string; h1: string; caption: string } {
  if (exampleId === "duffing") {
    return {
      h0: "H0 — harmonic",
      h1: "H1 — Duffing",
      caption: DUFFING_NOTICE,
    };
  }
  return {
    h0: "H₀",
    h1: "H₁",
    caption: "Model prediction — not experimental data.",
  };
}

export function maximumSeparation(delta: number[]): number | null {
  if (delta.length === 0 || delta.some((value) => !Number.isFinite(value))) {
    return null;
  }
  return Math.max(...delta.map((value) => Math.abs(value)));
}

export function formatQuantity(value: number): string {
  if (!Number.isFinite(value)) {
    return "";
  }
  return String(Number(value.toPrecision(6)));
}

export function traceIds(result: RunResult): string[] {
  const ids = [
    result.parser?.claims[0]?.claim_id,
    result.null_model?.models[0]?.model_id,
    result.observable_design?.observables[0]?.observable_id,
    result.simulation_result?.simulation_id,
    result.experiment?.experiment?.experiment_id,
  ];
  return ids.filter((item): item is string => Boolean(item));
}
