"""Run versioning for Intelligence-Layer components.

Iteration B components write into ``<component_root>/runs/<run_id>/`` so a
re-run never overwrites an earlier one. Conventions:

* ``run_id`` defaults to a UTC timestamp (``20260611T143052Z``) — sortable
  lexicographically, so "latest" is simply the greatest id. A ``-2``/``-3``
  suffix is appended on collision; an existing run directory is never reused.
* Each orchestrator writes its **fit manifest last**, so the manifest's
  presence marks a *completed* run. ``resolve_run`` only ever resolves
  completed runs — a crashed half-written run can never be picked up as
  ``latest``. The directory listing is the registry; there are no pointer
  files to go stale.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

RUNS_SUBDIR = "runs"
LATEST = "latest"


def new_run_id(component_root: Path, now: datetime | None = None) -> str:
    """Mint a fresh run id; never reuses an existing run directory."""
    now = now or datetime.now(UTC)
    base = now.strftime("%Y%m%dT%H%M%SZ")
    run_id = base
    suffix = 2
    while (component_root / RUNS_SUBDIR / run_id).exists():
        run_id = f"{base}-{suffix}"
        suffix += 1
    return run_id


def run_dir(component_root: Path, run_id: str) -> Path:
    """Directory all artifacts of one run live under."""
    return component_root / RUNS_SUBDIR / run_id


def list_completed_runs(component_root: Path, manifest_name: str) -> list[str]:
    """Sorted run ids under ``runs/`` whose directory holds the fit manifest."""
    runs_root = component_root / RUNS_SUBDIR
    if not runs_root.is_dir():
        return []
    return sorted(
        d.name
        for d in runs_root.iterdir()
        if d.is_dir() and (d / manifest_name).exists()
    )


def resolve_run(component_root: Path, run_id: str, manifest_name: str) -> Path:
    """Resolve ``run_id`` (or ``"latest"``) to a completed run directory.

    Raises ``FileNotFoundError`` when no completed run matches — the caller
    should run the upstream component first.
    """
    if run_id == LATEST:
        completed = list_completed_runs(component_root, manifest_name)
        if not completed:
            raise FileNotFoundError(
                f"No completed runs under {component_root / RUNS_SUBDIR} "
                f"(no {manifest_name} found) — run the upstream component first."
            )
        return run_dir(component_root, completed[-1])
    candidate = run_dir(component_root, run_id)
    if not (candidate / manifest_name).exists():
        raise FileNotFoundError(
            f"Run {run_id!r} not found or incomplete under "
            f"{component_root / RUNS_SUBDIR} (missing {manifest_name})."
        )
    return candidate
