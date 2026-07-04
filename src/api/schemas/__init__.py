"""Pydantic response models for the read-only dashboard API.

Response models serialize to camelCase JSON per the approved API contract
(docs/dashboard/dashboard_api_contract.md §4): field names use the ``to_camel``
alias generator; enum *values* stay snake_case verbatim.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base response model: snake_case in Python, camelCase over the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
