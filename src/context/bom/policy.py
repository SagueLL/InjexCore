"""Pydantic policy schema for the BOM Operational Context Layer.

Materialised from ``configs/bom_context.yaml``. Every model inherits
:class:`StrictModel` — a misspelled YAML key raises. Tunables (column-name
mapping, percentage thresholds, forensic windows, upstream run ids) live
here; output schemas, status vocabularies and the signature algorithm are
the contract and stay hardcoded in the stage modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from src.preprocessing._common.models import StrictModel


class ColumnMapPolicy(StrictModel):
    """Raw CSV header per normalized name.

    The raw file ships the header typo ``Fecha Incio`` (sic) — it is mapped
    here so the code never hardcodes source spellings.
    """

    order_id: str = "EQ56_ORDRE"
    start_timestamp: str = "Fecha Incio"
    end_timestamp: str = "Fecha Fin"
    product_code: str = "Producto"
    product_name: str = "Descripcion Producto"
    recipe_version: str = "Version"
    recipe_description: str = "Descripcion version"
    material_code: str = "Materia prima"
    material_name: str = "Descripcion materia prima"
    percentage: str = "Porcentaje"
    dosing_point: str = "Punto Dosificacion"


class RawInputPolicy(StrictModel):
    """Source CSV location and parsing parameters."""

    csv_path: str = "data/context/bom/raw/Dades 20241008 - BOM.csv"
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    decimal_comma: bool = True
    columns: ColumnMapPolicy = Field(default_factory=ColumnMapPolicy)


class PercentagePolicy(StrictModel):
    """Order-total percentage warning band.

    Totals above 100% may reflect valid industrial formulation rules
    (over-dosing allowances); they are flagged for domain interpretation,
    never normalized to 100%.
    """

    expected_min: float = 99.0
    expected_max: float = 103.0
    outlier_row_max: float = Field(100.0, gt=0.0)


class TimelinePolicy(StrictModel):
    """Master-timeline alignment parameters."""

    master_path: str = "data/datasets/master/master_dataset.parquet"
    expected_master_rows: int | None = 167331  # hard gate; null disables
    boundary: Literal["closed_open"] = "closed_open"  # start <= t < end
    gap_tolerance_seconds: float = Field(0.0, ge=0.0)


class SignaturePolicy(StrictModel):
    """Deterministic BOM-composition fingerprint parameters."""

    percentage_format: str = ".6f"
    hash_prefix_len: int = Field(16, ge=8, le=64)


class ForensicWindowsPolicy(StrictModel):
    """Candidate dates and window width for Stage G event context."""

    candidate_dates: list[str] = Field(
        default_factory=lambda: [
            "2024-09-09",
            "2024-09-12",
            "2024-09-13",
            "2024-09-16",
            "2024-09-18",
        ]
    )
    window_hours: int = Field(24, ge=1)
    focus_product_codes: list[str] = Field(default_factory=lambda: ["114"])
    focus_material_codes: list[str] = Field(default_factory=lambda: ["1222"])


class ForensicAddendumPolicy(StrictModel):
    """Stage H — read-only join against persisted anomaly scores."""

    enabled: bool = True
    anomaly_root: str = "data/intelligence/anomaly"
    anomaly_run_id: str = "20260611T173316Z"  # or "latest"
    forensic_root: str = "data/intelligence/forensics"
    forensic_run_id: str = "20260612T101850Z"  # or "latest"
    output_root: str = "data/intelligence/forensics/bom_addenda"


class BomContextPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/bom_context.yaml``."""

    raw_input: RawInputPolicy = Field(default_factory=RawInputPolicy)
    percentage: PercentagePolicy = Field(default_factory=PercentagePolicy)
    timeline: TimelinePolicy = Field(default_factory=TimelinePolicy)
    signature: SignaturePolicy = Field(default_factory=SignaturePolicy)
    forensic_windows: ForensicWindowsPolicy = Field(
        default_factory=ForensicWindowsPolicy
    )
    forensic_addendum: ForensicAddendumPolicy = Field(
        default_factory=ForensicAddendumPolicy
    )


def load_policy(yaml_path: Path) -> BomContextPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"BOM-context policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return BomContextPolicy.model_validate(raw)
