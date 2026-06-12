"""PCA Intelligence — per-profile multivariate structure of normal behaviour.

Fits a leakage-safe scaler + PCA per supported operational profile (training
window only) and scores every row of that profile: principal-component
scores, Hotelling T², Q-residual / squared prediction error and per-feature
reconstruction contributions. Profiles that cannot support a sound PCA
(insufficient rows/features, zero variance, excessive missingness) are
skipped and reported, never silently fitted.

Consumes the persisted Behaviour Intelligence profile labels; its persisted
models and scores are consumed by Anomaly Intelligence.
"""
