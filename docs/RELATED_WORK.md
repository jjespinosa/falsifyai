# Related Work and Positioning

## Emerging category

Adversarial hypothesis testing is emerging as an AI-assisted scientific workflow. Several projects ask a model to challenge a claim, name assumptions, and propose a test that could weaken it. That category is broader than any one implementation.

## FALSIFY — Kalaris Labs

FALSIFY by Kalaris Labs is a related project published before this hackathon. Public materials, including the repository [KalarisLabs/Falsify](https://github.com/KalarisLabs/Falsify) and the August 2026 project description, present it as an adversarial research pre-mortem.

Those materials describe hypothesis decomposition, hidden assumptions, confounders, competing explanations, proposed falsification tests, a minimum next experiment, and research-passport style outputs that can be exported. This document reports that public focus. It does not audit the implementation, and it does not assert what the project cannot do.

## FalsifyAI

FalsifyAI addresses the broader category from an executable-systems perspective. A run extracts a typed claim, critiques it, constructs a strong null model, and searches for a discriminating observable. When the hypothesis states a quantitative law inside a registered numerical family, a local simulator compares the curves. An experiment designer then states the measurement. A judge returns one constrained status: `TESTABLE`, `BELOW_SENSITIVITY`, `NON_DISCRIMINATING`, or `NOT_YET_FALSIFIABLE`.

## Demonstrated distinction

FalsifyAI does not stop at suggesting how a hypothesis might fail. It attempts to compile the hypothesis into an executable falsification contract.

The M6 benchmarks are the evidence, and they use the same pipeline.

**Duffing.** The hypothesis states both curves, the domain, and the uncertainty. The restricted simulator compares them, the experiment is ready, and the justified outcome can be `TESTABLE`. The chart is a model prediction, not experimental evidence.

**DQ-12.** The hypothesis does not supply an operational mapping from laboratory-controlled quantities to the proposed twelve-dimensional separation. The pipeline does not invent that law. Simulation stays blocked, and the justified outcome can be `NOT_YET_FALSIFIABLE`. That status is not experimental support for extra dimensions.

Same pipeline. Different scientific completeness. Different justified outcome.

## What we do not claim

FalsifyAI does not claim to be the first AI system to apply adversarial reasoning to scientific hypotheses.

It does not claim the first adversarial scientific workflow, and it does not claim a unique use of AI for scientific pre-mortems.

The demonstrated distinction is the attempt to compile an adversarial analysis into a constrained, executable falsification workflow: typed artifacts, a closed numerical registry, and an explicit refusal when the quantitative science required for execution is missing.
