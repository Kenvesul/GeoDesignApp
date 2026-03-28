# Next Chat Prompt - Math Improvement Phase

Continue the DesignApp project from the current local workspace at `C:\DesignApp`.

Current focus:
- Improve the core math/calculation layer before more UI work.
- Highest-priority issue is slope stability search/calibration.
- Desktop scaffold is already in good shape and should not be the focus of the next pass unless needed for verification.

What is already done:
- PySide6 desktop scaffold exists with functional pages for Slope, Foundation, Wall, and Sheet Pile.
- Dashboard reflects live page state.
- Sheet-pile export/session bugs were fixed.
- Slope false-collapse behavior for a near-flat dry profile was removed.
- `api.run_slope_analysis()` and `verify_slope_da1()` now use the same bounds/grid density.
- Slope plot export now clips arcs/slice borders to actual slope intersections.
- `governing_combination` is exposed in slope results.

What still appears wrong:
- Some stable slope geometries now produce unrealistically large FoS values.
- The remaining issue is likely in the core slope engine rather than desktop/UI.

Primary files to inspect first:
- `C:\DesignApp\core\search.py`
- `C:\DesignApp\core\slicer.py`
- `C:\DesignApp\core\limit_equilibrium.py`
- `C:\DesignApp\core\factors_of_safety.py`
- `C:\DesignApp\api.py`
- `C:\DesignApp\exporters\plot_slope.py`
- `C:\DesignApp\tests\test_api.py`
- `C:\DesignApp\tests\test_search.py`
- `C:\DesignApp\tests\test_limit_equilibrium.py`
- `C:\DesignApp\tests\test_factors_of_safety.py`

Recommended next goal:
1. Reproduce the unrealistic-high-FoS cases in the core slope path.
2. Implement the proposed search-zone architecture captured in `C:\DesignApp\MATH_ROADMAP.md`.
3. Add targeted tests before and after each change.
4. Verify that the chosen critical circle is physically meaningful and not a boundary or near-zero-driving artifact.
5. Only after core verification, surface the new search controls in desktop/web UI if still needed.

Verification expectations:
- Run targeted slope-related pytest suites first.
- Keep exports/plots consistent with the accepted critical circle.
- Preserve existing calibrations unless a failing test proves they are already wrong.

