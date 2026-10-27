"""Deterministic null-model and observable fixtures.

None of these fixtures adds a measured value or an effect size.
"""

from app.schemas.null_model import KnowledgeBasis, NullModel, NullModelResult, SourcedStatement
from app.schemas.observable import ObservableCandidate, ObservableDesignResult, PredictedDifference
from app.services.fixtures import CASE_B, CASE_C, normalize_statement

CASE_MASS = (
    "At fixed pendulum length and within the small-angle regime, "
    "increasing the bob mass changes the oscillation period."
)


def case_mass_null() -> NullModelResult:
    return NullModelResult(
        models=[
            NullModel(
                model_id="h0",
                description=(
                    "For an ideal simple pendulum in the small-angle regime, the period "
                    "depends on length and gravity and does not depend on bob mass. An "
                    "apparent mass effect can still come from bob size, drag, amplitude, "
                    "or a shift in the distance from the pivot to the center of mass."
                ),
                target_claim_ids=["c1"],
                assumptions=[
                    SourcedStatement(
                        statement=(
                            "Length and the small-angle condition stay fixed only when "
                            "the comparison controls them."
                        ),
                        basis=KnowledgeBasis.COMPARISON_ASSUMPTION,
                    )
                ],
                equations=[
                    SourcedStatement(
                        statement=(
                            "In the ideal small-angle pendulum, the period does not "
                            "contain bob mass."
                        ),
                        basis=KnowledgeBasis.STANDARD_KNOWLEDGE,
                    )
                ],
                free_parameters=["bob size", "aerodynamic drag", "initial amplitude"],
                known_confounders=[
                    "bob size",
                    "aerodynamic drag",
                    "initial amplitude",
                    "distance from the pivot to the center of mass",
                ],
                can_mimic_claim=True,
                mimicry_reason=(
                    "Changing the bob can change its size, drag, or center of mass, and "
                    "those changes can alter the period while the ideal mass-independent "
                    "relation still holds."
                ),
                limitations=[
                    "No measured period was supplied, and none was added. "
                    "No numerical effect size was assigned."
                ],
                basis=KnowledgeBasis.STANDARD_KNOWLEDGE,
                blocking_missing_definitions=[],
            )
        ],
        summary=(
            "The strongest conventional account says the ideal period does not depend "
            "on bob mass, while uncontrolled size, drag, or amplitude can imitate a "
            "mass effect. This is not a verdict about the claim."
        ),
    )


def case_b_null() -> NullModelResult:
    return NullModelResult(
        models=[
            NullModel(
                model_id="h0",
                description=(
                    "The named effect has no quantity, so no conventional equation "
                    "can be aimed at it."
                ),
                target_claim_ids=["c1"],
                assumptions=[],
                equations=[],
                free_parameters=[],
                known_confounders=[],
                can_mimic_claim=False,
                mimicry_reason=(
                    "The effect is not defined as a quantity, so a conventional model "
                    "cannot be shown to reproduce it."
                ),
                limitations=["No mechanism was invented to fill the missing definitions."],
                basis=KnowledgeBasis.COMPARISON_ASSUMPTION,
                blocking_missing_definitions=[
                    "quantum biofield resonance has no stated quantity or unit",
                    "systemic healing has no stated quantity or unit",
                ],
            )
        ],
        summary=(
            "A meaningful null model is blocked because the claim names no measurable "
            "quantity. No competing mechanism was fabricated."
        ),
    )


def case_c_null() -> NullModelResult:
    return NullModelResult(
        models=[
            NullModel(
                model_id="h0",
                description=(
                    "Light, temperature, water, airflow, and air movement from a speaker "
                    "can change plant growth without the claimed mechanism."
                ),
                target_claim_ids=["c1", "c2"],
                assumptions=[
                    SourcedStatement(
                        statement=(
                            "The positions beside the speaker and away from it are not "
                            "stated to be matched for ordinary growing conditions."
                        ),
                        basis=KnowledgeBasis.COMPARISON_ASSUMPTION,
                    )
                ],
                equations=[
                    SourcedStatement(
                        statement=(
                            "Plant growth commonly changes with light, temperature, water, "
                            "and airflow."
                        ),
                        basis=KnowledgeBasis.STANDARD_KNOWLEDGE,
                    )
                ],
                free_parameters=["light", "temperature", "water", "airflow"],
                known_confounders=[
                    "light",
                    "temperature",
                    "water",
                    "airflow",
                    "air movement from the speaker",
                ],
                can_mimic_claim=True,
                mimicry_reason=(
                    "Those ordinary conditions can differ beside a speaker and can "
                    "change growth without vital energy."
                ),
                limitations=[
                    "No growth measurement was supplied, and none was added."
                ],
                basis=KnowledgeBasis.STANDARD_KNOWLEDGE,
                blocking_missing_definitions=[
                    "growth has no stated measure or time window"
                ],
            )
        ],
        summary=(
            "Ordinary growing conditions can mimic a growth change. The null model "
            "does not treat that mimicry as support for the claimed mechanism."
        ),
    )


def case_mass_observable() -> ObservableDesignResult:
    return ObservableDesignResult(
        observables=[
            ObservableCandidate(
                observable_id="o1",
                name="oscillation period",
                symbol="T",
                definition=(
                    "The time for one complete oscillation at fixed length and within "
                    "the small-angle regime, compared across bob masses."
                ),
                units="s",
                measurement_method=(
                    "Time the same counted run of cycles, with the same release, at "
                    "two bob masses. No instrument precision is assumed."
                ),
                target_claim_ids=["c1"],
                h1_prediction=(
                    "The period changes when bob mass changes while length and the "
                    "small-angle condition stay fixed."
                ),
                h0_prediction=(
                    "The period stays the same when length, angle, and bob size or "
                    "drag stay fixed."
                ),
                predicted_difference=PredictedDifference.QUALITATIVE_DIFFERENCE,
                required_controls=[
                    "pendulum length held fixed",
                    "initial angle held inside the small-angle regime",
                    "bob size or drag held fixed or separately estimated",
                    "the same release and timing procedure",
                ],
                known_confounders=[
                    "bob size",
                    "aerodynamic drag",
                    "initial amplitude",
                    "distance from the pivot to the center of mass",
                ],
                blocking_missing_definitions=[],
                non_blocking_missing_definitions=[
                    "a numeric small-angle tolerance is not stated"
                ],
                discriminating=True,
            )
        ],
        blocking_issues=[],
        summary=(
            "Period versus bob mass can separate a mass-dependent claim from the "
            "ideal mass-independent account only when length, angle, and bob size "
            "or drag are controlled. No effect size is assigned, and the claim is "
            "not declared supported."
        ),
    )


def case_b_observable() -> ObservableDesignResult:
    return ObservableDesignResult(
        observables=[],
        blocking_issues=[
            "quantum biofield resonance has no stated quantity or unit",
            "systemic healing has no stated quantity or unit",
        ],
        summary=(
            "No discriminating observable follows until the effect is defined as a "
            "measurable quantity. None was invented."
        ),
    )


def case_c_observable() -> ObservableDesignResult:
    return ObservableDesignResult(
        observables=[],
        blocking_issues=["growth has no stated measure or time window"],
        summary=(
            "No observable is returned because the growth measure itself is undefined. "
            "Ordinary conditions are recorded on the null model and were not turned into a measurement."
        ),
    )


GOLDEN_NULLS = {
    normalize_statement(CASE_MASS): case_mass_null,
    normalize_statement(CASE_B): case_b_null,
    normalize_statement(CASE_C): case_c_null,
}

GOLDEN_OBSERVABLES = {
    normalize_statement(CASE_MASS): case_mass_observable,
    normalize_statement(CASE_B): case_b_observable,
    normalize_statement(CASE_C): case_c_observable,
}

GOLDEN_M2_CLAIM_IDS = {
    normalize_statement(CASE_MASS): {"c1"},
    normalize_statement(CASE_B): {"c1"},
    normalize_statement(CASE_C): {"c1", "c2"},
}
