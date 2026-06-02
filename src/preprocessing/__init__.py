"""Preprocessing layer for InjexCore.

The linear data pipeline, one subpackage per stage:

    cleaning → time_series → feature_engineering → datasets

Neutral cross-stage contracts (``Finding``/``Severity``, ``ColumnGroups``,
``StrictModel``) live in :mod:`src.preprocessing._common` and are re-exported
by every stage via thin shims.

Run the combined pipeline through the package CLI::

    python -m src.preprocessing                  # cleaning only (default)
    python -m src.preprocessing --stage all      # cleaning → ts → fe → datasets

See :mod:`src.preprocessing.__main__` for the full ``--stage`` surface, or
invoke a single stage directly, e.g.
``python -m src.preprocessing.cleaning.run_cleaning``.
"""
