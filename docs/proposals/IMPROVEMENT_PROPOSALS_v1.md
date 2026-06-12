# InjexCore — Improvement Proposals (v1 → v2 transition)

Evidence-based architecture review of the preprocessing layer ahead of the
intelligence/modeling layer (`src/models/{anomaly,forecasting,energy}/`,
`src/api/`). Scope is improvement proposals only; the project summary is
maintained separately by the orchestrator.

Severity legend: CRITICAL (blocks or actively harms v2) · IMPORTANT (will
cause churn/debt if not addressed before v2) · AWARE (track, low-cost) ·
NORMAL (acceptable, documented for completeness).

Method: every finding cites a file actually read during this review. Facts,
assumptions and recommendations are kept distinct.

---

## Priority-ranked findings

### 1. No installable package / no `pyproject.toml` — imports rely on a `sys.path` hack — CRITICAL

**Evidence.**
- [tests/conftest.py](../tests/conftest.py) lines 24-26 inject the project root onto `sys.path` (`sys.path.insert(0, str(PROJECT_ROOT))`) so that `import src.data.cleaning...` resolves. There is no `pyproject.toml` anywhere in the repo (Glob `*.toml` returns nothing; only `requirements.txt` exists).
- Every module hardcodes `PROJECT_ROOT = Path(__file__).resolve().parents[3]` (see grep: `src/data/cleaning/io.py:20`, `time_series/io.py:15`, `feature_engineering/run_feature_engineering.py:61`, `datasets/io.py:19`, etc.) and `parents[1]` in the `src/` root scripts.

**Why it matters for v2.** The modeling layer and a FastAPI app must import the
preprocessing packages. With no installed distribution, `src/models/...` and
`src/api/...` will need the same `sys.path` shim, and any tooling that runs from
a different CWD (CI runner, Docker `WORKDIR`, `uvicorn` reload) will break import
resolution. The `parents[3]` literal is also positionally brittle: the moment the
package is nested one level deeper (the project's own ML template uses
`src/<project_name>/`), every path constant silently points at the wrong directory.

**Recommendation.**
- Add a `pyproject.toml` with `[project]` metadata and a `setuptools`/`hatchling`
  backend; declare the package and install editable (`pip install -e .`). This is
  also mandated by the user-level Python rules (pinned deps in `pyproject.toml`).
- Replace per-module `parents[N]` with a single `src/config.py` (pydantic-settings
  `BaseSettings`, per the ML template) exposing `PROJECT_ROOT`, `RAW_DATA_DIR`,
  `CONFIGS_DIR`, etc. Every `io.py`/`run_*.py` imports from there.
- Delete the `sys.path` insert from `conftest.py` once the package is installable.

---

### 2. `requirements.txt` is largely unpinned and contains a junk line — CRITICAL

**Evidence.** [requirements.txt](../requirements.txt) in full:
```
pandas
numpy
matplotlib
seaborn
scikit-learn
jupyter
pydantic>=2.7.0
pyyaml>=6.0.1
pyarrow>=15.0.0
Git-GitHub
```
Lines 1-6 carry no version constraint; line 10 (`Git-GitHub`) is not a PyPI
package and will fail `pip install -r requirements.txt`.

**Why it matters.** This directly violates the project's own pinned-dependency
rule (`~/.claude/rules/python.md`: "All dependencies pinned … with exact or
minimum-upper-bound versions"). Reproducibility is a stated CRISP-DM requirement,
and v2 introduces model artifacts whose behaviour is sensitive to the exact
`scikit-learn`/`numpy` versions used to fit them. An unpinned `scikit-learn` means
a serialized Isolation Forest / LOF / Mahalanobis estimator may not deserialize or
may behave differently on a teammate's machine.

**Recommendation.**
- Remove the `Git-GitHub` line immediately (broken install).
- Pin all six unpinned packages to lower bounds with upper guards (e.g.
  `scikit-learn>=1.4,<1.6`, `numpy>=1.26,<3`). Align with the ML template baseline.
- Split tooling out into `requirements-dev.txt` (`pytest`, `ruff`, `mypy`,
  `pre-commit`, `nbstripout`); move `jupyter` there — it is not a runtime dep.
- Add the modeling runtime deps v2 needs now so they are reviewed in one place
  (`joblib` for artifact persistence, `mlflow` or a structured-JSON logger per the
  ML rules). State as assumption: forecasting library choice is still open.

---

### 3. `schema_lock.json` is wired into code but lives under fully git-ignored `/data/` — IMPORTANT

**Evidence.**
- The master-validation stage reads/writes a schema lock:
  `src/data/datasets/io.py:31` → `DEFAULT_SCHEMA_LOCK = MASTER_DIR / "schema_lock.json"`,
  consumed in `src/data/datasets/master_validation.py:155-269` and
  `run_datasets.py:105,234`.
- `MASTER_DIR = .../data/datasets/master/` (`io.py:27`).
- [.gitignore](../.gitignore) line 23 ignores `/data/` wholesale.

**Why it matters.** The schema lock is meant to be the committed contract that
fails the build when the master dataset's columns drift. Because it is written
inside `/data/`, it can never be committed, so the lock check
(`finding_type="schema_lock_match"` / `schema_lock_missing`) only ever compares
against a local, untracked file — defeating its purpose. v2 models will train
against the master schema; an uncommitted lock means a silent column change
upstream can invalidate a trained model with no CI signal.

**Recommendation.**
- Move the canonical schema lock out of `/data/` to a tracked location
  (e.g. `configs/schema_lock.json` or `src/data/datasets/schema_lock.json`), and
  point `DEFAULT_SCHEMA_LOCK` there. Keep the generated copy under `data/` if a
  runtime mirror is wanted, but the contract artifact must be version-controlled.
- Document the lock-refresh procedure in `docs/pipeline/specialized_datasets.md`.

---

### 4. No CI, no lint/type/format toolchain, no pre-commit — IMPORTANT

**Evidence.** No `.github/`, `.gitlab-ci.yml`, `.pre-commit-config.yaml`, or tool
config sections (no `pyproject.toml` to hold them). CLAUDE.md itself states
"Linting / typing tools are not wired up yet." 136 tests exist but nothing runs
them automatically.

**Why it matters for v2.** Going deeper than "tools aren't wired up": the
preprocessing layer is feature-complete and *small enough today* that retrofitting
`ruff`/`mypy --strict` is cheap. Once `src/models/` and `src/api/` land, the
surface to clean up doubles and the cost of enforcing typing rules (mandated
globally) compounds. A green test suite that no gate enforces will rot the moment
v2 churn begins.

**Recommendation.**
- Add `.pre-commit-config.yaml` with `ruff`, `ruff format`, `mypy`, and a secret
  scanner (`gitleaks`/`detect-secrets`) per the git rules.
- Add a minimal CI workflow: install editable package, `ruff check`, `mypy`,
  `pytest`. Gate merges on it before v2 work starts.
- Add tool config to the new `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`,
  `[tool.pytest.ini_options]`).

---

### 5. Inconsistent `extra="forbid"` across policy schemas — config typos silently ignored in 2 of 4 stages — IMPORTANT (NEW)

**Evidence.**
- `feature_engineering/policy.py` and `datasets/policy.py` set
  `model_config = ConfigDict(extra="forbid")` on their models (grep returns ~25
  occurrences across these two files).
- `cleaning/policy.py` (read in full) uses plain `class …(BaseModel)` with **no**
  `model_config` — e.g. `TimestampsPolicy`, `CleaningPolicy` (lines 20-77).
- `time_series/policy.py` (read in full) likewise uses plain `BaseModel`
  (`TemporalConversionPolicy` line 22, `TimeSeriesPolicy` line 98) with no
  `extra="forbid"`.

**Why it matters.** The orchestrator's mental model ("configs/*.yaml pydantic
`extra="forbid"`") is only true for half the stages. A misspelled key in
`configs/cleaning.yaml` or `configs/time_series.yaml` (e.g. `gap_facter:`) is
**silently dropped** and the default value is used — a class of bug that is very
hard to notice and exactly the kind of reproducibility footgun the ML rules warn
against. The two newer stages got it right; the two older ones were never
backfilled.

**Recommendation.** Add `model_config = ConfigDict(extra="forbid")` to every
model in `cleaning/policy.py` and `time_series/policy.py`. Cheap, mechanical,
high-value. Consider a shared `StrictModel(BaseModel)` base (see finding 6) so
this can never drift again.

---

### 6. `cleaning` is the de-facto shared base for the whole `data` layer — no neutral `_common` package — IMPORTANT

**Evidence.**
- `time_series/column_groups.py`, `feature_engineering/column_groups.py`,
  `datasets/column_groups.py` are **pure re-exports** of
  `src.data.cleaning.column_groups` (read all three; each is ~15 lines importing
  `ColumnGroups, load_groups, DEFAULT_CLASSIFICATION`).
- Same for reporting: `time_series/reporting.py`, `feature_engineering/reporting.py`,
  `datasets/reporting.py` all re-export `Finding, Severity, write_json,
  write_markdown` from `src.data.cleaning.reporting`.

**Assessment — skeptical correction of the brief's premise.** This is *not*
duplicated logic; the team already centralized it. The re-export pattern is a
reasonable, low-churn choice. The real issue is **semantic**, not duplication:
the shared contracts (`Finding`, `Severity`, `ColumnGroups`, the report writers)
physically live in the *cleaning* package, so every other stage — and soon every
model in `src/models/` — must `import from src.data.cleaning` to get them. A
forecasting model depending on a module literally named `cleaning` is a confusing
dependency edge and an inverted layering: the base layer is named after one of its
consumers.

**Why it matters for v2.** `src/models/anomaly/` will want `Finding`/`Severity`
to emit evaluation reports in the same format, and `ColumnGroups` to resolve
feature categories. Importing those from `cleaning` couples modeling to a
preprocessing sub-stage and makes the dependency graph read backwards.

**Recommendation.**
- Extract a neutral `src/data/_common/` (or `src/common/`) holding `reporting.py`
  (Finding/Severity/writers) and `column_groups.py`. Have all four stages **and**
  the future model packages import from there. Keep the existing re-export shims
  in each stage for backward compatibility during the move.
- Put the proposed `StrictModel` base (finding 5) here too.
- This is a one-time, low-risk move best done *before* v2 adds more importers.

---

### 7. EDA/build helper scripts sit directly in `src/` alongside placeholders — organization drift — IMPORTANT

**Evidence.** `src/` root currently mixes four categories:
- Production pipeline entry: `data_generation.py`.
- One-off build/EDA tooling (parents[1], not part of the importable pipeline):
  `analyze_temporal_quality.py` (docstring: streams the raw CSV, writes
  `data/features/temporal_quality_report.json`), `build_pellet_dictionary.py`,
  `build_variable_classification.py`, `build_eda_notebook.py` (generates
  `notebooks/eda_ds_pellet.ipynb`).
- Orchestration shim: `preprocessing.py`.
- **Empty placeholders**: `anomaly_detection.py` and `visualization.py` are each
  a single line (Read reports "file has 1 line").

**Why it matters for v2.** `src/anomaly_detection.py` and `src/visualization.py`
are flat-file placeholders, but CLAUDE.md plans `src/models/{anomaly,forecasting,
energy}/` packages. Leaving the flat placeholders invites someone to start writing
model code in them, immediately conflicting with the package layout. The `build_*`
and `analyze_*` scripts are EDA/setup tooling — per the project's own ML rules and
template they belong in `scripts/` (one-off management) or be regenerable from
`notebooks/`, not interleaved with the importable package.

**Recommendation.**
- Create `scripts/` and move `analyze_temporal_quality.py`,
  `build_pellet_dictionary.py`, `build_variable_classification.py`,
  `build_eda_notebook.py` there. Update the `parents[1]` constant to resolve from
  the shared config module (finding 1).
- Delete the empty `src/anomaly_detection.py` / `src/visualization.py`
  placeholders and replace with the planned `src/models/` and (later)
  `src/visualization/` packages, mirroring the 9-file stage convention.
- Note: `data_generation.py` produces `dataset_pro.csv` against the *synthetic*
  schema while the whole pipeline runs on `Dades_pellet.csv` (real schema). This
  dual-schema split is real but documented in CLAUDE.md; flagged AWARE below, not
  blocking.

---

### 8. `day_close_2026-05-29.md` committed under `data/datasets/` — content/location drift — AWARE

**Evidence.** `data/datasets/day_close_2026-05-29.md` (read: a session-close
report) sits in a **data output directory**. `.gitignore` line 23 ignores
`/data/`, so this file is either force-added or untracked-but-present.

**Why it matters.** A prose session report under a generated-data directory is a
category error: `data/datasets/` holds parquet artifacts + machine reports, not
human session logs. If force-committed it pollutes the data tree; if merely
present locally it is invisible to teammates. Either way it will accumulate
(`day_close_2026-05-30.md`, …) and clutter the dataset output area.

**Recommendation.** Move session-close reports to `docs/sessions/` (or
`docs/day_close/`) and ensure they are tracked there. Keep `data/` for
machine-generated artifacts only. Verify the file's actual git status and, if
force-added, untrack it.

---

### 9. Per-stage CLI scaffolding is repeated across four `run_*.py` — AWARE

**Evidence.** Each `run_*.py` re-implements the same shape: `argparse` setup with
`--policy`/`--no-write` flags, `DEFAULT_POLICY = PROJECT_ROOT / "configs" / "<x>.yaml"`
(grep: `run_cleaning.py:45`, `run_ts_engineering.py:49`,
`run_feature_engineering.py:62`, `run_datasets.py:71`), a `PIPELINE` list, logging
setup, and a `main()/run()` pair re-exported by `preprocessing.py`.

**Why it matters.** This is acceptable, mild duplication today — each stage has
genuinely different flags. But v2 adds 3+ more `run_*.py` (train/evaluate/predict
per model family). Without a tiny shared CLI helper the boilerplate scales
linearly and the `preprocessing.py` shim's import block (8 imports for 4 stages)
will balloon.

**Recommendation.** Extract a small `src/data/_common/cli.py` (or in the shared
package from finding 6) with a `build_stage_parser(default_policy)` helper and a
`configure_logging()` call. Low priority; do it opportunistically when adding the
first model `run_*.py`. Do **not** over-abstract the differing per-stage args.

---

### 10. Single-source data + no split artifacts on disk — scalability risk for modeling — AWARE

**Evidence.** Pipeline runs exclusively on `data/raw/Dades_pellet.csv`
(every `DEFAULT_RAW`/`DEFAULT_*_IN` constant points to one file lineage). The
specialized-datasets stage produces master + 3 projections but **no train/val/test
split artifacts** (`data/datasets/` contains only full-projection parquets).

**Why it matters for v2.** The ML rules require: "Splits are performed once, saved
as artifacts, and reused — not regenerated on every run." v2 modeling has nowhere
to read a frozen split from; each model script will be tempted to split inline,
risking train/test leakage across the three model families (anomaly/forecasting/
energy) and non-reproducible evaluation. With a single source file there is also
no held-out time period reserved.

**Recommendation.** Before training, add a split stage (or extend `datasets/`) that
writes frozen `train/val/test` indices or parquets under
`data/datasets/splits/`, with the split logic seeded and recorded. Decide the
split strategy per family (time-based holdout for forecasting; stratified for the
anomaly classifier). State as assumption: real-machine thresholds are still pending,
so the anomaly label split may need revisiting once those land.

---

## Summary table

| # | Finding | Severity | Primary evidence |
|---|---------|----------|------------------|
| 1 | No installable package; `sys.path` hack + hardcoded `parents[3]` | CRITICAL | `tests/conftest.py:24`, all `io.py` |
| 2 | `requirements.txt` unpinned + `Git-GitHub` junk line | CRITICAL | `requirements.txt` |
| 3 | `schema_lock.json` referenced but under git-ignored `/data/` | IMPORTANT | `datasets/io.py:31`, `.gitignore:23` |
| 4 | No CI / ruff / mypy / pre-commit gate | IMPORTANT | repo root (absence) |
| 5 | `extra="forbid"` missing in cleaning + time_series policies | IMPORTANT (NEW) | `cleaning/policy.py`, `time_series/policy.py` |
| 6 | Shared contracts live in `cleaning`; no neutral `_common` | IMPORTANT | `*/column_groups.py`, `*/reporting.py` re-exports |
| 7 | EDA/build scripts + empty placeholders in `src/` root | IMPORTANT | `src/build_*.py`, `src/anomaly_detection.py` (1 line) |
| 8 | Session report committed under `data/datasets/` | AWARE | `data/datasets/day_close_2026-05-29.md` |
| 9 | Repeated CLI scaffolding across `run_*.py` | AWARE | four `run_*.py` |
| 10 | Single-source data, no frozen split artifacts | AWARE | `data/datasets/` contents |

## Confidence

High on findings 1, 2, 3, 5, 6, 7, 8 (direct file evidence read in full or via
targeted grep). Medium on 4 (absence-based; CI may exist outside the repo) and 10
(split strategy depends on pending anomaly-threshold decisions). Finding 9 is a
judgment call deliberately scoped as low-priority to avoid premature abstraction.
