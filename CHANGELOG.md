# GeoDesignApp — Changelog

All notable changes are recorded here in reverse chronological order.

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
