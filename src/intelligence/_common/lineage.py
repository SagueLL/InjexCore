"""Strict cross-component lineage assertions (DAT-01).

Downstream components verify they consume a *coherent* upstream chain — the
same master dataset (file sha, or the projection-invariant row-count/index-span
fingerprint) and the same pinned run ids — and **fail closed** when they cannot.
A semantic lineage mismatch is never downgraded to a warning: reasoning over
incompatible evidence is worse than stopping. Run resolution already proves the
upstream manifest is *complete* (see :mod:`src.intelligence._common.runs`);
these helpers prove it is *compatible*.

Each downstream component owns its own ``*BlockerError``; the assert helpers
raise the class the caller passes so error types stay component-specific.
"""

from __future__ import annotations

from typing import Any


def fingerprint_matches(manifest: dict[str, Any], own: dict[str, Any]) -> bool:
    """Projection-invariant identity: row count + index span match the master.

    Used where the downstream loads a *column-projected* master (so the upstream
    structural sha can never match) — the honest comparison is the shape.
    """
    fp = manifest.get("dataset_fingerprint", {})
    return (
        fp.get("n_rows") == own.get("n_rows")
        and fp.get("index_start") == own.get("index_start")
        and fp.get("index_end") == own.get("index_end")
    )


def assert_fingerprint(
    name: str,
    manifest: dict[str, Any],
    own: dict[str, Any],
    error_cls: type[Exception],
) -> None:
    """Block unless the upstream fingerprint matches the loaded master shape."""
    if not fingerprint_matches(manifest, own):
        fp = manifest.get("dataset_fingerprint", {})
        raise error_cls(
            f"Upstream {name} run does not match the loaded master "
            f"(rows {fp.get('n_rows')} vs {own.get('n_rows')}, index "
            f"[{fp.get('index_start')}..{fp.get('index_end')}] vs "
            f"[{own.get('index_start')}..{own.get('index_end')}]); re-run the "
            "upstream chain before this component."
        )


def assert_master_sha(
    name: str,
    manifest: dict[str, Any],
    own_file_sha: str,
    error_cls: type[Exception],
) -> None:
    """Block unless the upstream recorded master sha exists and matches."""
    recorded = manifest.get("master_dataset_sha256")
    if recorded is None:
        raise error_cls(
            f"Upstream {name} run records no master_dataset_sha256; lineage "
            "cannot be verified. Re-run the upstream component."
        )
    if recorded != own_file_sha:
        raise error_cls(
            f"Upstream {name} run was fitted on a different master "
            f"(sha {recorded} != {own_file_sha}); re-run the upstream chain "
            "before this component."
        )


def assert_run_pin(
    name: str,
    pinned: Any,
    resolved: Any,
    error_cls: type[Exception],
) -> None:
    """Block when an upstream manifest pins a different run than was resolved.

    A missing pin (older upstream that did not record it) is *not* a match we
    can verify — treat absence as ``unknown`` and leave it to the dedicated
    sha/fingerprint checks rather than guessing.
    """
    if pinned is not None and pinned != resolved:
        raise error_cls(
            f"Upstream run divergence for {name}: a consumed run pins "
            f"{pinned!r} but this run resolved {resolved!r}; the chain is "
            "incoherent. Re-run so every component shares one chain."
        )
