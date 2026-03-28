# DesignApp Context

## Current phase

- Phase 6: debug stabilization plus PySide6 desktop UI.

## Confirmed project rules

- `api.py` is the shared public bridge for both web and desktop entry points.
- PySide6 desktop pages must call `api.py` and must not import `core/` directly.
- Calibration values in `.claude/CLAUDE_CONTEXT.md` must remain stable.

## This session

- We started by validating the roadmap against the live codebase.
- Two documented bug fixes already appear partially implemented in `ui/app.py`:
  - session slimming
  - temp file cleanup
- A likely remaining bug exists in sheet-pile export handlers, which appear to call wall exporters.
- That sheet-pile export bug is now fixed across both legacy and React-facing routes.
- The sheet-pile API now accepts legacy field aliases used by older UI layers.
- Export temp-file cleanup now uses an in-memory relay after write completion, which is more reliable on Windows than deleting during response teardown.
- The project virtualenv has been rebuilt successfully and now includes:
  - `PySide6`
  - `numpy`
  - `matplotlib`
  - `pytest-qt`
- The desktop scaffold now includes:
  - `desktop/app.py`
  - `desktop/main_window.py`
  - shared widgets under `desktop/widgets/`
  - functional `desktop/pages/slope_page.py`
  - functional `desktop/pages/foundation_page.py`
  - functional `desktop/pages/wall_page.py`
  - functional `desktop/pages/sheet_pile_page.py`
  - placeholder `desktop/pages/pile_page.py`
- Desktop theme preference is now persisted through the main window view toggle.
- `desktop/pages/project_dashboard.py` now reflects live page state from desktop analyses:
  - Slope
  - Foundation
  - Wall
  - Sheet Pile
  - placeholder Pile status
- Desktop pages now report idle, running, pass, fail, and error states back to the dashboard through the main window wiring.
- Desktop smoke coverage now verifies:
  - expected tab labels
  - dark-mode action wiring
  - dashboard card updates
- The current desktop milestone is verified:
  - `tests/test_desktop_ui.py` passes
  - Sheet Pile and Wall now match the functional pattern already used by Slope and Foundation
- Slope debugging has started and two concrete inconsistencies were fixed:
  - `api.run_slope_analysis()` and `verify_slope_da1()` now use the same search bounds and grid density
  - slope plot exports now clip the critical arc and slice borders to the actual slope intersections
- Slope result dictionaries now include `governing_combination`, which the desktop and React UI can use directly.
- The original "near-flat slope collapses" symptom has been removed in regression coverage.
- Remaining slope concern:
  - some stable geometries now return unrealistically large FoS values, so the next session should continue in the core slope engine rather than the UI layer
  - likely focus areas are meaningful-circle selection, boundary assumptions, and driving-moment filtering in the circular search

## Working approach

1. Baseline tests using the project virtualenv.
2. Fix confirmed debug issues and add regression coverage.
3. Re-verify targeted tests.
4. Scaffold the first PySide6 desktop architecture slice.
5. Current next recommended pass:
   - continue the slope-analysis calibration pass in `core/search.py`, `core/slicer.py`, and `core/limit_equilibrium.py`
   - inspect how boundary assumptions and low-driving circles should be filtered or extended
   - verify the plotted failure circle matches the physically accepted search result after that calibration
   - then implement the remaining real desktop `PilePage`
6. Handoff files prepared for the next chat:
   - `C:\DesignApp\NEXT_CHAT_PROMPT_MATH.md`
   - `C:\DesignApp\MATH_ROADMAP.md`
