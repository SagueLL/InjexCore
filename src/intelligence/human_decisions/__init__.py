"""Human Decision Overlay — Iteration C Part 3 (Phase 1 closure).

Encodes a *human* decision — the reviewer's approval of a scoped
``inlet_hopper_points`` quarantine treatment and the deferral of Reference v2 —
as a structured, run-versioned, dashboard-consumable artifact under
``data/intelligence/forensics/human_decisions/<run_id>/``.

It is decision-support *metadata* only. It mutates no existing artifact,
approves nothing in the pipeline, refits nothing, rescores nothing, applies no
quarantine and builds no dashboard UI. The overlay keeps four states distinct:
``artifact_state`` (the persisted proposal — still ``approved=False``),
``human_review_state`` (this approval), ``applied_pipeline_state`` (not applied)
and ``dashboard_overlay_state`` (how the read-only dashboard should surface it).

See :mod:`src.intelligence.human_decisions.run_human_decision_overlay`.
"""
