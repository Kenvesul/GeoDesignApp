# Math Improvement Roadmap

## Current priority

Stabilize and calibrate the slope-stability calculation path before more feature expansion.

The project notes, session diary, and current code all point to the same issue:
- the desktop/UI layer is in usable shape
- the shared slope calculation path is the active engineering risk
- the remaining defects are most likely in search acceptance and limit-equilibrium filtering, not page wiring

## Current state from docs and code

Confirmed from `README.md`, `context.md`, `NEXT_CHAT_PROMPT_MATH.md`, and the current core files:

- `api.run_slope_analysis()` and `verify_slope_da1()` now share bounds and grid density
- plot clipping was corrected so the exported arc matches the real slope intersection limits
- `core/search.py` already supports a `search_zone` object and boundary warnings
- `core/search.py` already filters some weak candidates with:
  - minimum effective slices
  - minimum sliding-mass area
  - non-convergent / invalid / low-driving statuses
- `core/limit_equilibrium.py` already rejects some near-zero driving cases

The remaining gap is therefore not "add search controls from scratch".
The gap is "tighten the physical acceptance rules and calibrate the search defaults so the selected critical circle is realistic."

## Primary failure hypotheses

1. Some trial circles still survive filtering even when their driving term is too small to represent a meaningful failure mechanism.
2. The current auto-bounds may still bias the search toward edge-adjacent or overly large circles.
3. Slice geometry may be numerically valid while still representing an implausibly small or poorly shaped moving mass.
4. The search currently records the minimum valid FoS, but "valid" is still too permissive for engineering use.
5. The parity gap versus `pyslope` is likely dominated by circle acceptance and search-space coverage rather than by EC7 factoring itself.

## Roadmap

### Phase 1 - Build a reliable calibration baseline

Goal:
- make the current failure modes reproducible and measurable before changing formulas

Tasks:
- inventory the slope tests in:
  - `tests/test_search.py`
  - `tests/test_limit_equilibrium.py`
  - `tests/test_factors_of_safety.py`
  - `tests/test_api.py`
  - `tests/test_pyslope_parity.py`
- add named regression fixtures for:
  - near-flat safe slope
  - ordinary dry slope
  - steep slope with many invalid circles
  - known unrealistically-high-FoS case
  - Craig Example 9.1 parity case
- capture not just final FoS, but also:
  - number of circles tested
  - accepted vs rejected counts by status
  - critical circle location
  - whether the winning circle is near a search boundary

Target files:
- `core/search.py`
- `tests/test_search.py`
- `tests/test_api.py`
- `tests/test_pyslope_parity.py`

Exit criteria:
- every known bad geometry can be reproduced from a test
- diagnostics clearly show why the chosen circle won

### Phase 2 - Tighten physical admissibility of trial circles

Goal:
- reject circles that are numerically solvable but physically meaningless

Tasks:
- strengthen `_evaluate_circle()` in `core/search.py` with extra acceptance checks for:
  - minimum slice count relative to search geometry
  - minimum sliding-mass width
  - minimum arc engagement across the slope
  - extreme center/radius combinations that only graze the slope
- expand `CircleEvaluation.status` usage so rejected circles are categorized explicitly
- refine `_validate_driving_sum()` in `core/limit_equilibrium.py` so "tiny driving force" is screened with thresholds tied to geometry or total weight, not only fixed absolutes
- review whether additional guards are needed for:
  - very small resisting/driving sums
  - denominator terms that remain positive but produce inflated FoS
  - circles whose accepted slices are clustered too narrowly

Target files:
- `core/search.py`
- `core/limit_equilibrium.py`
- `core/slicer.py`

Exit criteria:
- unrealistically large FoS outliers are rejected or reduced to physically credible values
- rejection reasons are visible in diagnostics

### Phase 3 - Recalibrate the automatic search zone

Goal:
- keep auto-search convenient without letting it silently miss or distort the governing mechanism

Tasks:
- review `_auto_bounds()` in `core/search.py`
- compare current bounds against:
  - slope height
  - crest/toe location
  - benchmark examples from existing tests
- adjust default center/radius ranges so they better cover deep and toe-passing circles without over-favoring edge minima
- keep explicit `search_zone` override support, but make defaults more engineering-friendly
- refine `boundary_warning` so it triggers on both:
  - center proximity to zone edges
  - critical radius proximity to min/max radius limits

Target files:
- `core/search.py`
- `api.py`
- `tests/test_search.py`

Exit criteria:
- default search behaves sensibly on the existing benchmark set
- edge-dominated results surface as warnings instead of silently appearing trustworthy

### Phase 4 - Improve result transparency

Goal:
- make it easier to trust or challenge the selected circle

Tasks:
- enrich `SearchResult.search_diagnostics` with stable counters such as:
  - `invalid_geometry`
  - `too_few_slices`
  - `tiny_mass`
  - `low_driving`
  - `nonconvergent`
  - `accepted`
- return enough structured search-surface data for visual QA
- ensure `api.py` exposes:
  - search zone used
  - boundary warning
  - diagnostics
  - heatmap-ready grid data
- update `exporters/plot_bishop.py` so the heatmap highlights rejected/valid regions more clearly if needed

Target files:
- `core/search.py`
- `api.py`
- `exporters/plot_bishop.py`

Exit criteria:
- a user or tester can explain why a given circle was selected
- exported/visual diagnostics match the accepted search result

### Phase 5 - Re-run parity and EC7 verification

Goal:
- prove the tightened search still behaves correctly under both characteristic and design checks

Tasks:
- rerun the parity comparison against `pyslope`
- verify that DA1-C1 and DA1-C2 still use the same search assumptions when intended
- confirm no regression in:
  - governing combination selection
  - warning propagation
  - plot/export consistency
- only after the core math is credible, surface any extra controls in the desktop UI

Target files:
- `core/factors_of_safety.py`
- `api.py`
- `tests/test_factors_of_safety.py`
- `tests/test_api.py`
- `tests/test_pyslope_parity.py`

Exit criteria:
- parity gap is reduced or at least explained by deliberate modeling differences
- EC7 outputs remain internally consistent

## Recommended implementation order

1. Add/upgrade tests and diagnostics first.
2. Tighten circle admissibility in `core/search.py` and `core/limit_equilibrium.py`.
3. Recalibrate `_auto_bounds()` and boundary detection.
4. Expose richer diagnostics through `api.py`.
5. Update heatmap/export support.
6. Add UI controls only after the core path is trusted.

## Working data contract

Keep the existing search-zone shape and extend diagnostics rather than replacing them:

```python
search_zone = {
    "xc_min": float,
    "xc_max": float,
    "yc_min": float,
    "yc_max": float,
    "r_min": float,
    "r_max": float,
    "n_cx": int,
    "n_cy": int,
    "n_r": int,
}
```

Recommended diagnostic payload:

```python
search_diagnostics = {
    "tested": int,
    "accepted": int,
    "invalid_geometry": int,
    "too_few_slices": int,
    "tiny_mass": int,
    "low_driving": int,
    "nonconvergent": int,
    "nonpositive_fos": int,
}
```

## Validation checklist

- Confirm the critical circle is not a boundary artifact.
- Confirm the accepted sliding mass has credible width, area, and driving action.
- Confirm large FoS values only appear for genuinely stable geometries, not grazing circles.
- Confirm the same physical circle is reflected in API output and plotted export.
- Confirm `tests/test_pyslope_parity.py` improves or produces clearer discrepancy diagnostics.
- Confirm DA1/C1 and DA1/C2 remain aligned with the intended search setup.

## Out of scope until the above is done

- broad desktop UX redesign
- React slope-page expansion
- new analysis families
- packaging/refactor work unrelated to slope-engine trustworthiness
