"""Lineage warnings served by /dashboard/meta must never carry filesystem paths.

``/meta`` stays reachable when lineage is invalid — precisely when the warning
list is longest — so this is the one endpoint most likely to leak deployment
layout. The core validator (src/dashboard/lineage.py) keeps its verbose paths for
local diagnostics; the API projection redacts them.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.redaction import REDACTED, redact_paths
from src.api.services import lineage_gate
from src.api.services.lineage_gate import ApiLineageResult

# Every shape the contract forbids on the wire.
_FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("windows drive letter", r"[A-Za-z]:[\\/]"),
    ("backslash separator", r"\\"),
    ("posix absolute path", r"(?<![\w.])/[\w.\-]+/"),
    ("data/ directory", r"\bdata/"),
    ("runs/ directory", r"\bruns/"),
    ("parquet artifact", r"\.parquet\b"),
    ("json artifact", r"\.json\b"),
    ("local user directory", r"Users|Desktop|home/"),
)

_PATH_WARNINGS = [
    r"Legacy fixed-path behaviour artifact present at C:\Users\User\Desktop"
    r"\InjexCore\data\intelligence\behaviour\behaviour_fit_manifest.json; the "
    r"dashboard must consume only the run-versioned behaviour run.",
    r"anomaly: no run directory at C:\Users\User\Desktop\InjexCore\data"
    r"\intelligence\anomaly\runs\remat-v1-20260616T102558Z.",
    "drift: no run directory at /home/ci/injexcore/data/intelligence/drift/runs/"
    "abc/drift_manifest.json.",
    "incidents: unreadable data/intelligence/incidents/runs/remat-v1-x/"
    "incidents.parquet.",
    r"pca: unreadable \\build-server\share\artifacts\pca_model.joblib.",
    "behaviour: see ./src/api/main.py for details.",
    "behaviour: bare behaviour_fit_manifest.json in the fixed path.",
]

# The four warnings the canonical chain actually emits carry no path at all and
# must survive byte-identical; the lineage-edge and non-canonical-chain warnings
# embed run ids, which are public (/meta.runId) and must never be redacted.
_PATH_FREE_WARNINGS = [
    "correlation: manifest lacks explicit behaviour provenance (behaviour_run_id); "
    "regenerate on the next rematerialization.",
    "anomaly: run 'remat-v1-20260616T102558Z' is not a valid completed 'anomaly' "
    "run (manifest missing, malformed, pending, wrong run id, or wrong component).",
    "lineage behaviour->pca: recorded parent run 'remat-v1-20260616T102558Z' != "
    "expected 'remat-v1-20260616T102558Z'.",
    "Chain 'a'/'b' is not the canonical chain (remat-v1-20260616T102558Z/"
    "20260612T124909Z); surface only as non-canonical/stale, never as authoritative.",
]


def _assert_no_paths(text: str) -> None:
    for label, pattern in _FORBIDDEN:
        assert not re.search(pattern, text), f"{label} leaked in: {text!r}"


@pytest.mark.parametrize("warning", _PATH_WARNINGS)
def test_redact_paths_removes_every_forbidden_shape(warning: str) -> None:
    redacted = redact_paths(warning)
    _assert_no_paths(redacted)
    assert REDACTED in redacted


@pytest.mark.parametrize("warning", _PATH_FREE_WARNINGS)
def test_redact_paths_is_a_no_op_on_path_free_text(warning: str) -> None:
    # A warning must keep its component name and failure class verbatim.
    assert redact_paths(warning) == warning


@pytest.mark.parametrize("warning", _PATH_WARNINGS + _PATH_FREE_WARNINGS)
def test_redact_paths_is_idempotent(warning: str) -> None:
    once = redact_paths(warning)
    assert redact_paths(once) == once


def test_redact_paths_preserves_sentence_punctuation() -> None:
    # The validator writes `... at {run_path}.` — the trailing stop is prose,
    # not part of the path.
    assert (
        redact_paths(r"anomaly: no run directory at C:\a\b\runs\id.")
        == f"anomaly: no run directory at {REDACTED}."
    )


def test_redact_paths_keeps_run_ids() -> None:
    warning = (
        "lineage pca->anomaly: recorded parent run 'remat-v1-20260616T102558Z' "
        "!= expected 'remat-v1-20260616T999999Z'."
    )
    redacted = redact_paths(warning)
    assert "remat-v1-20260616T102558Z" in redacted
    assert "remat-v1-20260616T999999Z" in redacted


def test_meta_endpoint_never_serves_a_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        lineage_gate,
        "validate_dashboard_chain",
        lambda: _chain_validation(_PATH_WARNINGS + _PATH_FREE_WARNINGS),
    )
    with TestClient(app) as client:
        body = client.get("/api/v1/dashboard/meta").json()
    warnings = body["lineage"]["warnings"]
    assert len(warnings) == len(_PATH_WARNINGS) + len(_PATH_FREE_WARNINGS)
    for warning in warnings:
        _assert_no_paths(warning)
    # Failure classes survive: the response is still diagnostically useful.
    assert any("no run directory" in warning for warning in warnings)
    assert any(
        "Legacy fixed-path behaviour artifact" in warning for warning in warnings
    )


def test_evaluate_lineage_redacts_before_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        lineage_gate,
        "validate_dashboard_chain",
        lambda: _chain_validation(_PATH_WARNINGS),
    )
    result: ApiLineageResult = lineage_gate.evaluate_lineage()
    for warning in result.warnings:
        _assert_no_paths(warning)


class _ChainValidation:
    """Minimal stand-in for DashboardChainValidation (only the projected fields)."""

    def __init__(self, warnings: list[str]) -> None:
        self.is_valid = False
        self.canonical_match = True
        self.severity = "invalid"
        self.warnings = warnings


def _chain_validation(warnings: list[str]) -> _ChainValidation:
    return _ChainValidation(list(warnings))
