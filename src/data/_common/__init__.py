"""Neutral shared contracts for the InjexCore data layer.

Holds the cross-stage primitives every preprocessing stage (and the future
``src/models/`` packages) depend on, so no stage has to import them from a
sibling stage:

* :mod:`reporting` — :class:`Finding`, :class:`Severity`, JSON/Markdown writers.
* :mod:`column_groups` — :class:`ColumnGroups`, ``load_groups``, classification path.
* :mod:`models` — :class:`StrictModel` Pydantic base (``extra="forbid"``).
"""
