# GeoDesignApp — Roadmap
**Last updated:** 2026-04-01

---

## Current priority

Stabilise and calibrate the slope stability calculation path before expanding any other features. The desktop UI is in usable shape. The shared slope engine is the active engineering risk.

---

## Confirmed done

- PySide6 desktop scaffold with functional pages for Slope, Foundation, Wall, Sheet Pile, and Project Dashboard.
- Dashboard reflects live page state (idle / running / pass / fail / error).
- Sheet-pile export and session bugs fixed across legacy and React-facing routes.
- `api.run_slope_analysis()` and `verify_slope_da1()` now use the same search bounds and grid density.
- Slope plot exports now clip arcs and slice borders to actual slope intersections.
- `governing_combination` exposed in slope result dicts.
- Near-flat dry slope false-collapse behaviour removed.
- `core/search.py` already supports `search_zone` object and boundary warnings.
- March 31 slope regressions fixed: export rebuild helper restored, slope plotter repaired, and adaptive filters keep shallow profiles stable.

---

## Open issues

| ID | Severity | Description |
|---|---|---|
| SLOPE-3 | 🟡 MED | Auto search bounds may bias results toward edge-adjacent or oversized circles |
| SLOPE-4 | 🟡 MED | Diagnostics not rich enough to explain why a given circle was selected |
| PILE-1 | 🟡 MED | Desktop `PilePage` is placeholder only — not yet functional |

---

## Phase 1 — Build a reliable calibration baseline
**Files:** `core/search.py`, `tests/test_search.py`, `tests/test_api.py`, `tests/test_pyslope_parity.py`

- Keep named regression fixtures for: near-flat safe slope, ordinary dry slope, steep slope with many invalid circles, Craig Ex. 9.1 parity case.
- Capture not just final FoS but also: circles tested, accepted vs rejected counts, critical circle location, boundary proximity.

**Exit criteria:** core calibration cases remain green; diagnostics show why the chosen circle won.

---

## Phase 2 — Tighten physical admissibility of trial circles
**Files:** `core/search.py`, `core/limit_equilibrium.py`, `core/slicer.py`

- Keep acceptance checks in `_evaluate_circle()` for: minimum slice count, minimum sliding-mass width, minimum arc engagement across slope, extreme center/radius combinations that only graze the slope.
- Keep `CircleEvaluation.status` categories explicit and add regression coverage when new failure modes appear.
- Refine `_validate_driving_sum()` only if future geometries show a new tiny-driving edge case.

**Exit criteria:** outliers remain rejected without breaking shallow stable profiles; rejection reasons stay visible in diagnostics.

---

## Phase 3 — Recalibrate automatic search zone
**Files:** `core/search.py`, `api.py`, `tests/test_search.py`

- Review `_auto_bounds()` against slope height, crest/toe location, and benchmark examples if new profiles demand it.
- Adjust default center/radius ranges only if a new benchmark exposes edge bias.
- Refine `boundary_warning` to trigger on both center proximity to zone edges and radius proximity to min/max limits if needed.
- Keep explicit `search_zone` override and the current engineering-friendly defaults.

**Search zone data contract:**
```python
search_zone = {
    "xc_min": float, "xc_max": float,
    "yc_min": float, "yc_max": float,
    "r_min":  float, "r_max":  float,
    "n_cx":   int,   "n_cy":   int,   "n_r": int,
}
```

**Exit criteria:** default search behaves sensibly on the benchmark set; edge-dominated results surface as warnings.

---

## Phase 4 — Improve result transparency
**Files:** `core/search.py`, `api.py`, `exporters/plot_bishop.py`

- Enrich `SearchResult.search_diagnostics` with counters: `invalid_geometry`, `too_few_slices`, `tiny_mass`, `low_driving`, `nonconvergent`, `accepted`.
- `api.py` exposes: search zone used, boundary warning, diagnostics, heatmap-ready grid data.
- Update `exporters/plot_bishop.py` to highlight rejected/valid regions on heatmap.

**Diagnostic payload:**
```python
search_diagnostics = {
    "tested": int, "accepted": int,
    "invalid_geometry": int, "too_few_slices": int,
    "tiny_mass": int, "low_driving": int,
    "nonconvergent": int, "nonpositive_fos": int,
}
```

**Exit criteria:** a user can explain why a given circle was selected; visual diagnostics match the accepted result.

---

## Phase 5 — pySlope parity and EC7 verification
**Files:** `core/factors_of_safety.py`, `api.py`, `tests/test_factors_of_safety.py`, `tests/test_pyslope_parity.py`

- Rerun parity comparison against pySlope on Craig Ex. 9.1.
- Verify DA1-C1 and DA1-C2 use the same search assumptions when intended.
- Confirm no regression in governing combination selection, warning propagation, or plot/export consistency.

**Exit criteria:** parity gap reduced or clearly explained by deliberate modelling differences; EC7 outputs internally consistent.

---

## Phase 6 — Desktop UI completion
**Files:** `desktop/pages/pile_page.py`, `desktop/pages/slope_page.py`

- Implement functional `PilePage` (currently placeholder).
- Surface search zone controls and live heatmap on `SlopePage` once core engine is trusted.
- Add user-defined search zone input panel with real-time FoS heatmap update via `QThread`.

---

## Phase 7 — Future (after core math is trusted)

- Non-circular slip surface search via pyBIMstab A-star algorithm.
- FEM-based strength reduction method (FEniCSx or PyFEM) as an optional analysis mode.
- React SPA slope page expansion.
- WCAG 2.1 AA accessibility audit on desktop and web.

---

## Validation checklist (slope engine)

- Critical circle is not a boundary artifact.
- Accepted sliding mass has credible width, area, and driving action.
- Large FoS values only appear for genuinely stable geometries, not grazing circles.
- Same physical circle reflected in API output and plotted export.
- `tests/test_pyslope_parity.py` improves or produces clearer discrepancy diagnostics.
- DA1-C1 and DA1-C2 remain aligned with intended search setup.
