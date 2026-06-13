"""Intelligence-Layer dispatcher: registration and argv forwarding."""

from __future__ import annotations

import pytest
from src.intelligence.__main__ import _COMPONENTS, _split_component_arg


def test_all_components_registered() -> None:
    assert set(_COMPONENTS) == {
        "behaviour",
        "correlation",
        "pca",
        "anomaly",
        "sensor-health",
        "drift",
        "incidents",
    }
    assert all(callable(main) for main in _COMPONENTS.values())


@pytest.mark.parametrize(
    "component",
    [
        "behaviour",
        "correlation",
        "pca",
        "anomaly",
        "sensor-health",
        "drift",
        "incidents",
    ],
)
def test_component_arg_extracted_and_rest_forwarded(component: str) -> None:
    name, rest = _split_component_arg(
        ["--component", component, "--no-write", "--log-level", "DEBUG"]
    )
    assert name == component
    assert rest == ["--no-write", "--log-level", "DEBUG"]


def test_component_equals_syntax() -> None:
    name, rest = _split_component_arg(["--component=pca", "--no-write"])
    assert name == "pca"
    assert rest == ["--no-write"]


def test_default_component_is_behaviour() -> None:
    name, rest = _split_component_arg(["--no-write"])
    assert name == "behaviour"
    assert rest == ["--no-write"]


def test_unknown_component_raises_with_known_names() -> None:
    with pytest.raises(SystemExit, match="behaviour"):
        _split_component_arg(["--component", "lstm"])
