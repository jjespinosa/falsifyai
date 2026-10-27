import { describe, expect, it } from "vitest";

import {
  BENCHMARK_NOTE,
  DUFFING_NOTICE,
  FRONTIER_ADVERSARIAL,
  SPECULATIVE_NOTICE,
  executionLabel,
  isDemoMode,
  VERDICT_LABELS,
  curveLabels,
  exampleMatching,
  formatQuantity,
  maximumSeparation,
  simulationVisual,
  statementFor,
  verdictLabel,
  visualStatus,
} from "./presentation";
import type { ExampleCard, RunResult } from "./types";

const examples: ExampleCard[] = [
  {
    example_id: "pendulum",
    category: "FOUNDATIONAL",
    title: "Pendulum",
    label: "Foundational comparison",
    purpose: "Not yet finite.",
    statement: "At fixed pendulum length and within the small-angle regime, increasing the bob mass changes the oscillation period.",
    notice: null,
  },
  {
    example_id: "synthetic",
    category: "SYNTHETIC CONTROL",
    title: "Synthetic",
    label: "Synthetic quantitative claim",
    purpose: "Finite comparison.",
    statement: "Synthetic quantitative check.",
    notice: "Synthetic demonstration — not experimental evidence.",
  },
  {
    example_id: "duffing",
    category: "SYNTHETIC CONTROL",
    title: "DUFFING BENCHMARK",
    label: "Synthetic quantitative control",
    purpose: "A fully specified model comparison.",
    statement: "Synthetic Duffing benchmark.",
    notice: DUFFING_NOTICE,
  },
  {
    example_id: "dq12",
    category: "FRONTIER STRESS TEST",
    title: "DQ-12 speculative stress test",
    label: "Speculative frontier stress test",
    purpose: "Challenges an under-specified hypothesis.",
    statement: "DQ-12 toy statement.",
    notice: SPECULATIVE_NOTICE,
  },
];

describe("presentation", () => {
  it("renders every verdict label", () => {
    expect(verdictLabel("TESTABLE")).toBe("TESTABLE");
    expect(verdictLabel("BELOW_SENSITIVITY")).toBe("BELOW SENSITIVITY");
    expect(verdictLabel("NON_DISCRIMINATING")).toBe("NON-DISCRIMINATING");
    expect(verdictLabel("NOT_YET_FALSIFIABLE")).toBe("NOT YET FALSIFIABLE");
    expect(Object.keys(VERDICT_LABELS)).toHaveLength(4);
  });

  it("keeps a blocked simulation distinct from a failed stage", () => {
    expect(simulationVisual("blocked", "skipped")).toBe("blocked");
    expect(simulationVisual("failed", "skipped")).toBe("failed");
    expect(visualStatus({ simulation_plan: "blocked", simulation: "skipped" }, "simulation")).toBe(
      "blocked",
    );
    expect(visualStatus({ parser: "failed" }, "parser")).toBe("failed");
    expect(visualStatus({ simulation_plan: "blocked", simulation: "skipped" }, "simulation")).not.toBe(
      "failed",
    );
  });

  it("selects an example statement", () => {
    expect(statementFor(examples, "pendulum")).toContain("bob mass");
    expect(statementFor(examples, "synthetic")).toContain("Synthetic");
    expect(statementFor(examples, "missing")).toBe("");
  });

  it("reads a fixture run without treating a scientific block as failure", () => {
    const run = {
      status: "scientifically_blocked",
      stages: [
        { name: "simulation_plan", status: "blocked" },
        { name: "simulation", status: "skipped" },
        { name: "judge", status: "success" },
      ],
      verdict: { status: "NOT_YET_FALSIFIABLE" },
    } as RunResult;

    expect(run.status).not.toBe("failed");
    expect(visualStatus(
      Object.fromEntries(run.stages.map((item) => [item.name, item.status])),
      "simulation",
    )).toBe("blocked");
    expect(run.verdict?.status).toBe("NOT_YET_FALSIFIABLE");
  });

  it("labels the synthetic control and the speculative stress test", () => {
    const duffing = exampleMatching(examples, "Synthetic Duffing benchmark.");
    const frontier = exampleMatching(examples, "DQ-12 toy statement.");

    expect(duffing?.category).toBe("SYNTHETIC CONTROL");
    expect(duffing?.notice).toBe(DUFFING_NOTICE);
    expect(curveLabels("duffing")).toEqual({
      h0: "H0 — harmonic",
      h1: "H1 — Duffing",
      caption: BENCHMARK_NOTE,
    });
    expect(frontier?.category).toBe("FRONTIER STRESS TEST");
    expect(frontier?.notice).toBe(SPECULATIVE_NOTICE);
    expect(FRONTIER_ADVERSARIAL).toContain("adversarially");
    expect(FRONTIER_ADVERSARIAL).not.toContain("confirmed");
    expect(DUFFING_NOTICE).toContain("not experimental data");
    expect(BENCHMARK_NOTE).toContain("not experimental evidence");
    expect(isDemoMode("?demo=1")).toBe(true);
    expect(isDemoMode("")).toBe(false);
    expect(executionLabel("stub")).toBe("Deterministic demo");
    expect(executionLabel("live")).toBe("LIVE");
    expect(maximumSeparation([0, -0.075, 0.02])).toBeCloseTo(0.075);
    expect(formatQuantity(0.01)).toBe("0.01");
  });
});
