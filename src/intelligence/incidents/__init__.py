"""Incident Aggregation — row-level findings become reviewable incidents.

Consumes the persisted sensor-health events + quarantine recommendations,
drift events, anomaly severity timeline and the operational/BOM context
transitions, and consolidates thousands of row-level flags into a compact
set of operational incidents with relationships, recommended actions and a
prioritized human-review pack.

Strictly read-only over upstream artifacts. Incident relationships are
associative and temporal — ``causality_status`` is always ``unknown``;
nothing here establishes causality. Every new incident defaults to
``review_status = "pending_review"``; quarantine-class actions always carry
``approval_required=True, approved=False``.
"""
