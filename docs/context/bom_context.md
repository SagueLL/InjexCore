# BOM Operational Context Layer

`src/context/bom/` — first component of the external-context layer
(`src/context/`). Transforms the raw BOM / production-order CSV into
validated contextual datasets joined safely against the master timeline.

> **The BOM layer is currently contextual and analytical. It enriches
> interpretation but does not modify model fitting or scoring.** It never
> touches the master dataset, never refits Intelligence-Layer models, and
> never changes anomaly thresholds, Behaviour profiles, or the training
> window.

## 1. Purpose

Answer operational-context questions over the same June–October 2024 period
the master dataset covers: which production order / product / recipe was
active at any master timestamp, whether the BOM composition changed, whether
order overlaps or gaps affect interpretation, and whether anomaly findings
(September–October shift) temporally coincide with BOM events. It also lays
the identity groundwork (`recipe_context_key`, `bom_signature`) for scoping
future reference versions by product/recipe — but those consumers
(Context Overlay, Reference Governance, Drift Intelligence) are explicitly
not implemented yet.

## 2. Source schema

`data/context/bom/raw/Dades 20241008 - BOM.csv` — UTF-8-sig, comma-delimited,
4,465 data rows, one row per BOM component of a production order:

| Raw header | Normalized name | Notes |
|---|---|---|
| `EQ56_ORDRE` | `order_id` | 211 unique orders |
| `Fecha Incio` | `start_timestamp` | typo is in the source file; mapped in config |
| `Fecha Fin` | `end_timestamp` | |
| `Producto` | `product_code` | 5 products (114 = CC-21, …) |
| `Descripcion Producto` | `product_name` | |
| `Version` | `recipe_version` | 39 versions |
| `Descripcion version` | `recipe_description` | |
| `Materia prima` | `material_code` | 28 materials (1222 = HARINILLA DE MAIZ) |
| `Descripcion materia prima` | `material_name` | |
| `Porcentaje` | `percentage` | comma decimals (`"37,86"`) |
| `Punto Dosificacion` | `dosing_point` | PP / DO |

Every normalized row keeps `source_row_number` + `source_file` traceability.

## 3. Pipeline stages

| Stage | Module | What it does |
|---|---|---|
| A — inspect | `validation.py` | Required-column blocker gate; raw quality stats (missingness, duplicates, invalid timestamps, `start >= end`, percentage parse failures/outliers, potential overlaps, metadata conflicts). |
| B — normalize | `normalize.py` | Trim + type into `bom_components.parquet`; rejected/duplicate rows routed to side tables with explicit reasons. Nulls preserved; totals **never** renormalized to 100%; nothing dropped silently. |
| C — aggregate | `aggregate.py` | One row per order (`bom_orders.parquet`) with `bom_signature`, `recipe_context_key`, percentage/conflict/window flags, `context_quality_status`. |
| D — intervals | `aggregate.py` | Boundary-event sweep → `bom_order_overlaps` / `bom_order_gaps` / classified `bom_order_transitions`. |
| E — timeline | `timeline.py` | Master-aligned `bom_context_timeline.parquet` — exactly one row per master timestamp (hard-gated 167,331). |
| F — summaries | `aggregate.py` | Product / recipe / signature / coverage summary tables. |
| G — event windows | `timeline.py` | BOM activity around the forensic candidate dates (2024-09-09/12/13/16/18, configurable). |
| H — addendum | `forensic_addendum.py` | Read-only join with the persisted anomaly scores + forensic run; anomaly-rate tables, figures, executive summary answering the ten addendum questions with non-causal wording. |

## 4. BOM signature and recipe context key

`bom_signature` is a deterministic composition fingerprint: per order, the
`(material_code, dosing_point, percentage)` tuples are formatted stably
(percentage as `%.6f`, `null` for missing), sorted lexicographically, joined
(`|` within a tuple, `;` between tuples) and hashed (sha256, 16-hex prefix).
Row order and float-repr noise cannot change it; any effective composition
change does. `recipe_context_key = product_code:recipe_version:bom_signature`
— the recipe-description text is never used as identity.

## 5. Timeline join policy

Windows are half-open (`start <= t < end`, `boundary: closed_open`):

| Active orders at `t` | `bom_context_status` | Scalar columns | List columns |
|---|---|---|---|
| 0 (inside coverage) | `no_active_order` | null | empty |
| 0 (before first start / after last end) | `outside_bom_coverage` | null | empty |
| 1 | `matched_single_order` | filled | single value |
| 2+ | `transition_overlap` | **null — one order is never silently chosen** | all matching values, sorted, pipe-joined |
| 0, but inside an invalid (`start >= end`) order's span | `invalid_window` | null | empty |

Alignment is enforced by a blocker gate: row count must equal the master's
(and `timeline.expected_master_rows` when set), timestamps must be identical
and ordered, scalars must be null wherever the count is not exactly 1.
Implementation is vectorized (`searchsorted` + difference arrays), no
row-by-row Python over the 167k master rows.

Overlap/gap handling: every maximal 2+-active window becomes one row in
`bom_order_overlaps` (union membership, max simultaneous count); windows with
no active order inside coverage become `bom_order_gaps` (gaps shorter than
`gap_tolerance_seconds` count as contiguous). Transitions between
start-sorted consecutive orders are classified with interval relations taking
precedence over content: `overlap_transition` → `gap_transition` → `unknown`
(missing metadata) → `product_change` → `same_product_recipe_change` →
`composition_change` → `same_product_same_recipe`.

## 6. Outputs

```
data/context/bom/runs/<run_id>/            (run-versioned, never overwritten)
├── normalized/   bom_components / bom_rejected_rows / bom_duplicate_rows .parquet
├── orders/       bom_orders / bom_order_overlaps / bom_order_gaps / bom_order_transitions .parquet
├── timeline/     bom_context_timeline.parquet
├── summaries/    bom_product_summary / bom_recipe_summary / bom_signature_summary / bom_context_coverage .parquet
├── forensics/    bom_forensic_event_context.parquet
├── bom_quality_report.md · bom_context_report.md · bom_context_findings.json
└── bom_context_manifest.json              ← written LAST (completion marker)

data/intelligence/forensics/bom_addenda/<run_id>/
├── anomaly_rates_by_{product,recipe,bom_signature,order,context_status}.parquet
├── candidate_dates_bom_context.parquet · recipe_transition_anomaly_summary.parquet
├── executive_summary.md · limitations.md · figures/*.png (5)
└── bom_addendum_manifest.json             ← written last within its directory
```

## 7. CLI

```bash
python -m src.context.bom --config configs/bom_context.yaml                  # full run
python -m src.context.bom --config configs/bom_context.yaml --no-write \
                          --log-level DEBUG                                  # diagnostic only
python -m src.context.bom --skip-addendum                                    # without Stage H
```

Flags: `--config --csv --master --output-root --addendum-root --run-id
--no-write --skip-addendum --log-level`. Run ids default to UTC timestamps;
an existing run directory is never reused. The Stage H upstream runs are
pinned in `configs/bom_context.yaml` (`anomaly_run_id: 20260611T173316Z`,
`forensic_run_id: 20260612T101850Z`; `latest` is supported).

## 8. Configuration

`configs/bom_context.yaml`, validated against `policy.py` (StrictModel —
unknown keys raise). Tunables: the raw column-name mapping (the `Fecha Incio`
typo lives there, never in code), percentage warning band
(`expected_min: 99.0` / `expected_max: 103.0` — totals above 100% may be
valid industrial formulation rules and are flagged, not repaired),
`expected_master_rows` hard gate, `gap_tolerance_seconds`, signature
formatting, forensic candidate dates / window hours / focus codes, and the
Stage H run pins.

## 9. What the first real run showed (run `20260612T124909Z`)

* 4,465 raw rows → 4,465 components; **0 rejected, 0 duplicates**; 211
  orders, 5 products, 39 recipe versions, **40 distinct BOM signatures**.
* 79 overlap windows and 131 gaps between orders — order records are not a
  continuous timeline: only **36.6%** of master rows match exactly one order,
  62.7% have no active order (machine time outside recorded orders), 0.69%
  fall in overlap windows, 0.01% outside BOM coverage.
* The September shift: **the BOM data does not show a recipe-version,
  composition or product change within ±2 days of 2024-09-16 or 2024-09-18**
  — only routine order handovers (gap/overlap transitions). The shift is
  global across products (validation anomaly rates 47–100%). The two
  October-only recipe context keys run at 100% validation anomaly rate, but
  they operate entirely inside the post-09-18 shifted regime, so the BOM
  layer alone cannot separate recipe effect from regime effect.

## 10. Limitations

The BOM source is declarative (planned orders/recipes, not measured flows);
ERP↔historian clock skew cannot be excluded; overlaps are preserved
unresolved by design and excluded from per-product attribution; the anomaly
models were fitted blind to BOM context. All addendum statements are
temporal associations — see `limitations.md` in each addendum run.

## 11. Deferred (explicitly out of scope)

Context Overlay consumption by models, Reference Governance / reference v2,
Drift Intelligence, recipe-scoped model selection, steam-conditioning
overlay, automatic retraining, any modification of upstream artifacts. A
multi-source `src/context/` dispatcher mirrors
`src/intelligence/__main__.py` when a second context source exists.
