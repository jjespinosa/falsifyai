import { describe, expect, it } from "vitest";

import {
  VERDICT_LABELS,
  simulationVisual,
  statementFor,
  verdictLabel,
  visualStatus,
} from "./presentation";
import type { ExampleCard, RunResult } from "./types";

const examples: ExampleCard[] = [
  {
    example_id: "pendulum",
    title: "Pendulum",
    purpose: "Not yet finite.",
    statement: "At fixed pendulum length and within the small-angle regime, increasing the bob mass changes the oscillation period.",
    notice: null,
  },
  {
    example_id: "synthetic",
    title: "Synthetic",
    purpose: "Finite comparison.",
    statement: "Synthetic quantitative check.",
    notice: "Synthetic demonstration — not experimental evidence.",
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
});
