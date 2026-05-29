"""Pydantic policy schema for the specialized-datasets pipeline.

Single source of truth for master-validation thresholds and the column
selectors of each specialized dataset. Materialised from
``configs/specialized_datasets.yaml`` at startup and passed read-only
into every projection module.

Selectors use a **hybrid** strategy:

* ``include_patterns`` — regex applied to column names.
* ``include_categories`` — semantic categories from
  ``variable_classification.csv``.
* ``include_columns`` — explicit allow list.
* ``exclude_patterns`` / ``exclude_columns`` — overrides applied last.
* ``include_metadata`` — when ``True``, the master metadata columns
  (``timestamp`` plus all ``Metadata`` rows in the classification CSV)
  are always preserved so the dataset can be joined back to master.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Master validation
# ---------------------------------------------------------------------------


class MasterValidationPolicy(BaseModel):
    """Integrity checks the engineered parquet must pass before being
    promoted to ``master_dataset.parquet``."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    require_monotonic_timestamps: bool = True
    require_unique_timestamps: bool = True
    max_nan_fraction_per_column: float = Field(default=0.30, ge=0.0, le=1.0)
    schema_lock: bool = True
    drop_columns: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared selector spec
# ---------------------------------------------------------------------------


class SelectorSpec(BaseModel):
    """Hybrid regex + category + explicit-override column selector."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    include_metadata: bool = True
    include_patterns: list[str] = Field(default_factory=list)
    include_categories: list[str] = Field(default_factory=list)
    include_columns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    exclude_columns: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Aggregate policy
# ---------------------------------------------------------------------------


class SpecializedDatasetsPolicy(BaseModel):
    """Aggregate policy loaded from ``configs/specialized_datasets.yaml``."""

    model_config = ConfigDict(extra="forbid")

    master_validation: MasterValidationPolicy = Field(
        default_factory=MasterValidationPolicy
    )
    anomaly_detection: SelectorSpec = Field(default_factory=SelectorSpec)
    forecasting: SelectorSpec = Field(default_factory=SelectorSpec)
    energy: SelectorSpec = Field(default_factory=SelectorSpec)


def load_policy(yaml_path: Path) -> SpecializedDatasetsPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Specialized-datasets policy not found at {yaml_path}"
        )
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return SpecializedDatasetsPolicy.model_validate(raw)
