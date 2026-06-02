"""InjexCore Intelligence Layer.

Sits past the preprocessing chain (``src/preprocessing/``). Where ``src/preprocessing/``
cleans and engineers parameter-free features, the intelligence layer
*fits descriptive artifacts* that characterise machine behaviour —
starting with :mod:`src.intelligence.behaviour` (operational profiles and
statistical baselines of "normal"). Fitted *predictive* estimators that
score deviation from this normal live downstream in :mod:`src.models`.
"""
