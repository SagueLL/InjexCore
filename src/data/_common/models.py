"""Shared Pydantic base model for all policy schemas.

Every policy model in the data layer inherits :class:`StrictModel` so an
unknown / misspelled key in a ``configs/*.yaml`` file raises a
``ValidationError`` instead of being silently dropped. Centralising the
base here means the ``extra="forbid"`` guarantee can never drift between
stages.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Pydantic base that rejects unknown keys."""

    model_config = ConfigDict(extra="forbid")
