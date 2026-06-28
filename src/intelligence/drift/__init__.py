"""Drift Intelligence — structural-change detection over persisted artifacts.

Answers "has the process (or a sensor, or the context mix) changed
structurally, when, and in what shape?" by comparing windowed statistics
against behaviour's persisted train window. Consumes the master dataset plus
the persisted anomaly / pca / correlation / sensor-health / operational-
context runs — strictly read-only: it never refits a model, never modifies
thresholds, profiles or the reference window, and never overwrites an
upstream artifact.

Two analytical views are computed: ``raw`` (all configured process sensors)
and ``healthy_only`` (sensors flagged faulty / quarantine-recommended by
Sensor Health are excluded *analytically* for the affected timestamps). The
healthy-only view is an interpretive comparison — upstream anomaly scores
are never mutated, and the optional multivariate proxy is always labeled
``healthy_only_proxy``, never presented as true rescoring.
"""
