import type { ExampleCard, RunResult } from "./types";

function base(): string {
  return import.meta.env.VITE_API_BASE ?? "";
}

export async function loadExamples(): Promise<ExampleCard[]> {
  const response = await fetch(`${base()}/api/v1/examples`);
  if (!response.ok) {
    throw new Error("The example catalog could not be loaded.");
  }
  const body = (await response.json()) as { examples: ExampleCard[] };
  return body.examples;
}

export async function runHypothesis(
  statement: string,
  mode: "stub" | "live",
  reasoningProfile: "economy" | "balanced",
): Promise<RunResult> {
  const response = await fetch(`${base()}/api/v1/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      hypothesis: { statement },
      mode,
      reasoning_profile: reasoningProfile,
    }),
  });
  if (!response.ok) {
    throw new Error("Pipeline execution failed");
  }
  return (await response.json()) as RunResult;
}
