"""Canonical identifier patterns shared by the schemas sent to the model."""

from typing import Annotated

from pydantic import Field

CLAIM_ID_PATTERN = r"^c[1-9][0-9]*$"
ASSUMPTION_ID_PATTERN = r"^a[1-9][0-9]*$"
REGISTERED_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
ISSUE_ID_PATTERN = r"^i[1-9][0-9]{0,3}$"
EXPLANATION_ID_PATTERN = r"^e[1-9][0-9]{0,3}$"

ClaimId = Annotated[str, Field(pattern=CLAIM_ID_PATTERN)]
AssumptionId = Annotated[str, Field(pattern=ASSUMPTION_ID_PATTERN)]
