"""Component dispatcher for the InjexCore Intelligence Layer.

Runs an Intelligence-Layer component from a single entry point. Components
register their ``main`` in ``_COMPONENTS`` and get a ``--component`` value
for free. The expected execution order mirrors the artifact dependencies::

    behaviour → correlation / pca → anomaly

Usage::

    python -m src.intelligence                          # default component (behaviour)
    python -m src.intelligence --component behaviour
    python -m src.intelligence --component correlation --no-write --log-level DEBUG
    python -m src.intelligence --component pca
    python -m src.intelligence --component anomaly --pca-run latest

Flags after ``--component X`` are forwarded verbatim to that component's own
CLI — e.g. ``python -m src.intelligence.pca.run_pca --help`` lists the pca
flags. A component can always still be invoked directly via its own
``run_*`` module; this dispatcher is a convenience over the layer.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from src.intelligence.anomaly.run_anomaly import main as anomaly_main
from src.intelligence.behaviour.run_behaviour import main as behaviour_main
from src.intelligence.correlation.run_correlation import main as correlation_main
from src.intelligence.pca.run_pca import main as pca_main

# Registry: component name -> its ``main(argv) -> int`` entry point.
# Add new Intelligence-Layer components here as they are built.
_COMPONENTS: dict[str, Callable[[list[str] | None], int]] = {
    "behaviour": behaviour_main,
    "correlation": correlation_main,
    "pca": pca_main,
    "anomaly": anomaly_main,
}
_DEFAULT_COMPONENT = "behaviour"


def _split_component_arg(argv: list[str]) -> tuple[str, list[str]]:
    """Extract ``--component X`` from ``argv``; default to the only component.

    Consumed here so each component's own ``argparse`` sees only the args it
    understands. Supports ``--component X`` and ``--component=X``.
    """
    component = _DEFAULT_COMPONENT
    rest: list[str] = []
    it = iter(argv)
    for tok in it:
        if tok == "--component":
            component = next(it, component)
        elif tok.startswith("--component="):
            component = tok.split("=", 1)[1]
        else:
            rest.append(tok)
    if component not in _COMPONENTS:
        raise SystemExit(
            f"Unknown --component {component!r}; expected one of {tuple(_COMPONENTS)}."
        )
    return component, rest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    component, rest = _split_component_arg(argv)
    return _COMPONENTS[component](rest)


if __name__ == "__main__":
    sys.exit(main())
