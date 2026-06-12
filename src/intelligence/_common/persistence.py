"""Fitted-model persistence for Intelligence-Layer components.

scikit-learn estimators (scalers, PCA, IsolationForest) are persisted with
joblib next to a ``model_meta.json`` recording the runtime versions, so a
reload under a different environment is detectable instead of silently
wrong. Small linear-algebra artifacts (e.g. a Mahalanobis mean/precision
pair) are persisted as plain JSON by their own component — transparent and
diff-able beats pickled for a 17x17 matrix.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

import joblib


def save_model(obj: Any, path: Path) -> None:
    """Persist a fitted estimator with joblib (mkdir parents)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, path)


def load_model(path: Path) -> Any:
    """Reload a joblib-persisted estimator."""
    if not path.exists():
        raise FileNotFoundError(f"Model artifact not found at {path}")
    return joblib.load(path)


def runtime_versions() -> dict[str, str]:
    """Library versions that determine artifact compatibility."""
    import sklearn

    return {
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "joblib": joblib.__version__,
    }
