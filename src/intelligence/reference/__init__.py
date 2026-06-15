"""Reference Governance — Iteration C Part 3.

Tracks the *current* reference, *candidate* references and *quarantine*
proposals as reviewable, run-versioned records. It reads the persisted
sensor-health, incident and drift runs read-only and turns their evidence
into proposals — it never approves a quarantine, never excludes a sensor,
never refits a model and never touches the original reference window.

Everything it emits defaults to ``pending_review`` / ``approved=False``:
the layer proposes and tracks decisions for a human reviewer; it does not
make them. See :mod:`src.intelligence.reference.run_reference`.
"""
