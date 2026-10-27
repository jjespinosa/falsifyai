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

export function statementFor(examples: ExampleCard[], exampleId: string): string {
  return examples.find((item) => item.example_id === exampleId)?.statement ?? "";
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
