"""Run versioning for Intelligence-Layer components.

Run-versioned components write into ``<component_root>/runs/<run_id>/`` so a
re-run never overwrites an earlier one. Conventions:

* ``run_id`` defaults to a UTC timestamp (``20260611T143052Z``) — sortable
  lexicographically, so "latest" is simply the greatest id. A ``-2``/``-3``
  suffix is appended on collision; an existing run directory is never reused.
* Run directories are created with :func:`create_run_dir` — an *atomic*
  ``mkdir(exist_ok=False)``. An explicit ``--run-id`` (or any id) that already
  has a directory fails closed with :class:`RunCollisionError` **before**
  anything is written; a completed run can never be clobbered or merged.
* Each orchestrator writes its **fit manifest last**, so the manifest's
  presence marks a *completed* run. Resolution does **not** trust presence
  alone: the manifest must parse, carry the required fields, report
  ``completion_status == "complete"``, name the ``run_id`` matching its own
  directory and (when supplied) match the expected component. A crashed,
  half-written or wrong-component manifest can never be picked up as
  ``latest``. The directory listing is the registry; there are no pointer
  files to go stale.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUNS_SUBDIR = "runs"
LATEST = "latest"

#: Status value a manifest must report to count as a completed run.
COMPLETE = "complete"
#: Fields every completed-run manifest must carry (validated on resolution).
REQUIRED_MANIFEST_FIELDS = ("component", "run_id", "completion_status")


class RunCollisionError(FileExistsError):
    """A run directory to be created already exists; refusing to overwrite."""


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


def create_run_dir(component_root: Path, run_id: str) -> Path:
    """Atomically create a fresh run directory; never reuse or overwrite.

    Raises :class:`RunCollisionError` if the directory already exists. This is
    the single safe entry point for *writing* a run — it protects both
    auto-generated ids and an explicit ``--run-id`` from clobbering, merging
    into, or silently reusing a prior (possibly completed) run.
    """
    target = run_dir(component_root, run_id)
    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise RunCollisionError(
            f"Run directory already exists: {target}. Refusing to overwrite a "
            "prior run — omit --run-id for a fresh timestamp, or choose a new one."
        ) from exc
    return target


def _read_manifest(path: Path) -> dict[str, Any] | None:
    """Parse a manifest file; return ``None`` when missing or malformed."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_completed_run(
    run_path: Path,
    manifest_name: str,
    expected_component: str | None = None,
) -> bool:
    """True iff ``run_path`` holds a valid, *completed* manifest.

    Presence is not enough: the manifest must parse to a dict, carry every
    field in :data:`REQUIRED_MANIFEST_FIELDS`, report
    ``completion_status == "complete"``, declare a ``run_id`` equal to its
    own directory name, and — when ``expected_component`` is given — match it.
    """
    manifest = _read_manifest(run_path / manifest_name)
    if manifest is None:
        return False
    if any(field not in manifest for field in REQUIRED_MANIFEST_FIELDS):
        return False
    if manifest.get("completion_status") != COMPLETE:
        return False
    if str(manifest.get("run_id")) != run_path.name:
        return False
    return not (
        expected_component is not None
        and manifest.get("component") != expected_component
    )


def list_completed_runs(
    component_root: Path,
    manifest_name: str,
    expected_component: str | None = None,
) -> list[str]:
    """Sorted run ids under ``runs/`` whose manifest validates as completed."""
    runs_root = component_root / RUNS_SUBDIR
    if not runs_root.is_dir():
        return []
    return sorted(
        d.name
        for d in runs_root.iterdir()
        if d.is_dir() and is_completed_run(d, manifest_name, expected_component)
    )


def resolve_run(
    component_root: Path,
    run_id: str,
    manifest_name: str,
    expected_component: str | None = None,
) -> Path:
    """Resolve ``run_id`` (or ``"latest"``) to a *completed* run directory.

    Raises ``FileNotFoundError`` when no completed run matches — the caller
    should run the upstream component first. A run whose manifest is missing,
    malformed, pending, names a different run id, or (when checked) belongs to
    another component is never resolved.
    """
    if run_id == LATEST:
        completed = list_completed_runs(
            component_root, manifest_name, expected_component
        )
        if not completed:
            raise FileNotFoundError(
                f"No completed runs under {component_root / RUNS_SUBDIR} "
                f"(no valid completed {manifest_name}) — run the upstream "
                "component first."
            )
        return run_dir(component_root, completed[-1])
    candidate = run_dir(component_root, run_id)
    if not is_completed_run(candidate, manifest_name, expected_component):
        raise FileNotFoundError(
            f"Run {run_id!r} not found or incomplete under "
            f"{component_root / RUNS_SUBDIR} (missing/invalid {manifest_name})."
        )
    return candidate
