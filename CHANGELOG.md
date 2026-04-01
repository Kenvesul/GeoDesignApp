# GeoDesignApp — Changelog

All notable changes are recorded here in reverse chronological order.

---

## 2026-03-31

### Fixed — Slope stability engine (critical bug fixes)

#### 1. Mirrored (right→left descending) slopes crashed with no results
- **Root cause:** `_validate_driving_sum` in `core/limit_equilibrium.py` raised
  `ValueError` for any circle where `Σ(W·sinα) ≤ 0`.  For a right→left
  descending slope every valid circle produces a negative driving sum, so
  every candidate was rejected and the analysis returned nonsense.
- **Fix:** All three LE engines (Ordinary, Bishop, Spencer) now use
  `abs(Σ W·sinα)` as the FoS denominator.  Sign encodes sliding direction
  only and does not affect the stability ratio.
  Files: `core/limit_equilibrium.py` — `_validate_driving_sum`,
  `ordinary_method`, `bishop_simplified`, `spencer_method`.

#### 2. Critical circle search returned wrong (too-optimistic) FoS
- **Root cause A — narrow auto-bounds:** `_auto_bounds` in `core/search.py`
  generated `cy_max = y_max + 3H` and `r_max = 3H` which was far too small.
  For Craig Ex. 9.1 the search settled for a tiny boundary circle at FoS 1.72
  instead of the correct ≈1.40.
- **Fix:** New `_auto_bounds` uses `cy_max = y_max + 5H`,
  `r_max = max(3×slope_face_length, 3H)`, and `cx` spanning full width ± H.
  Also added `_slope_direction()` to correctly orient mirrored-slope bounds.

- **Root cause B — degenerate circles not filtered:** Small circles clipping
  only the flat crest or toe passed the area check and "won" the search with
  physically meaningless very-low FoS values.
- **Fix:** Five new geometric quality filters in `_evaluate_circle`:
  - `_MAX_BASE_ANGLE_DEG = 75°` — rejects steep-corner clips
  - `_MIN_SPAN_FRACTION = 0.25` — arc must span ≥ 25 % of slope width
  - Slope-face intersection check — arc must overlap an inclined segment
  - Arc-centroid check — arc centroid must lie within the slope face zone
  - Depth filter — circle bottom ≤ 1.5H below slope toe

#### 3. Infinite-slope (planar) failure not checked for c′ ≈ 0 soils
- **Root cause:** Bishop circular method produces FoS > 1.40 for valid circles
  on this geometry, while the critical planar mechanism gives FoS = tan φ/tan β
  = 1.40.  The planar failure was never computed.
- **Fix:** New `_infinite_slope_fos()` helper in `api.py` computes the
  planar FoS for every inclined slope segment.  `run_slope_analysis()` returns
  `min(FoS_circular, FoS_planar)` as `fos_char`, plus separate keys
  `fos_char_circular`, `fos_char_infinite_slope`, and `governing_mechanism`.

#### 4. Slope cross-section plot dropped most of the arc for large circles
- **Root cause:** Arc drawing in `exporters/plot_slope.py` looped over 360°
  and split the polyline every time a point left `[x_min, x_max]`.  For a
  critical circle with centre outside the plot bounds this discarded nearly
  the entire arc silently.
- **Fix:** Arc now computed as a continuous `linspace` from `x_entry` to
  `x_exit` (from `_find_circle_slope_intersections`).  A thin full-circle
  outline provides geometric context even when the centre is off-screen.
  `y_min` also fixed to include the arc bottom.

### Updated — `tests/test_pyslope_parity.py`
Replaced the single broken parity test with four targeted tests:
- **Test A:** `fos_char_infinite_slope` matches `tan φ/tan β` within 0.5 %
- **Test B:** `fos_char_infinite_slope` matches pySlope within 2 %
  (pySlope converges to the same planar approximation for c=0)
- **Test C:** For c=0, valid circular FoS > infinite-slope FoS
  (planar governs; confirmed)
- **Test D:** Cohesive slope gives FoS > 1 in both engines
  (absolute values differ because pySlope uses a 30 m deep soil model)

All four tests pass.

### Updated — `README.md`
- Slope engine section rewritten to document both failure mechanisms,
  the five quality filters, mirrored-slope support, and the API result keys.
- Test run commands updated.
- Calibration table updated to reflect correct Craig Ex. 9.1 values.

---

## 2026-03-26

### Fixed
- Sheet-pile export routing for PDF and DOCX — was incorrectly calling wall exporters.
- Sheet-pile legacy field aliases in `api.py`: `h_retain` → `h_retained`, `surcharge_kpa` → `q`, with backward-compatible mapping.
- Added `governing_combination` output to sheet-pile results.
- Slope API/verification inconsistency: `api.run_slope_analysis()` and `verify_slope_da1()` now share the same auto-bounds and grid density.
- Slope plot export: critical arc and slice borders now clipped to actual slope intersections.
- Near-flat dry slope false-collapse removed — no longer reports failure for geometrically stable profiles.
- Temp-file export cleanup: files now deleted immediately after reading into memory, resolving Windows temp-file leak in tests.
- Flask session payload size: `_slim_for_session()` strips large regenerable keys before cookie storage.

### Added
- Dedicated sheet-pile export functions in `api.py`, `exporters/report_pdf.py`, `exporters/report_docx.py`.
- Missing `/api/sheet-pile/export/pdf` and `/api/sheet-pile/export/docx` endpoints.
- `governing_combination` field in slope result dicts.
- Flask regression coverage for: sheet-pile analysis/export wiring, export temp-file cleanup, session payload size.
- Desktop scaffold (`desktop/`):
  - `app.py` — application entry point
  - `main_window.py` — QMainWindow with QTabWidget and dark-mode toggle with persisted preference
  - `widgets/` — shared UI components
  - `pages/slope_page.py` — functional slope analysis page with threaded worker
  - `pages/foundation_page.py` — functional foundation page
  - `pages/wall_page.py` — functional retaining wall page with export actions
  - `pages/sheet_pile_page.py` — functional sheet pile page with pressure diagram and export actions
  - `pages/pile_page.py` — placeholder (not yet functional)
  - `pages/project_dashboard.py` — live status board reflecting pass/fail state from all pages
- Desktop smoke tests in `tests/test_desktop_ui.py` (3 passing):
  - expected tab labels present
  - dark-mode action wired correctly
  - dashboard card updates when a page reports a result
- pySlope parity gate in `tests/test_pyslope_parity.py` — intentionally active to guide slope search calibration.

### Environment
- Rebuilt `.venv` with: `PySide6`, `numpy`, `matplotlib`, `pytest-qt`, `pyslope`.

### Known open issues
- Some stable slope geometries return unrealistically large FoS values — next session continues in `core/search.py`, `core/slicer.py`, and `core/limit_equilibrium.py`.
- `tests/test_pyslope_parity.py` parity gate currently highlights open Craig Ex. 9.1 mismatch.

---

## Earlier sessions (DesignApp web — see DesignApp repo for full history)

The web interface history (Flask routes, React SPA, CI pipeline, Playwright E2E) is tracked in the [DesignApp repository](https://github.com/Kenvesul/DesignApp).
