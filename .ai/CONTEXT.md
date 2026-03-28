# CLAUDE_CONTEXT.md — GeoDesignApp AI Session Guide
**Last updated:** 2026-03-28
**Read this file at the start of every new session.**

---

## 1. Project identity

| Item | Value |
|---|---|
| App | GeoDesignApp — PySide6 Desktop Geotechnical Suite |
| Standard | Eurocode 7 — EN 1997-1:2004 |
| Language | Python 3.12 |
| UI | PySide6 6.6+ (desktop) |
| Repo | https://github.com/Kenvesul/GeoDesignApp |
| Related repo | https://github.com/Kenvesul/DesignApp (web/Flask/React) |
| Current phase | Phase 2 — slope engine calibration |

---

## 2. Architecture rules — never break these

```
models/ → core/ → api.py → desktop/pages/  (PySide6)
                         → ui/app.py        (Flask, companion repo)
                ↘ exporters/
```

| Layer | Hard rule |
|---|---|
| `models/` | stdlib only; no imports from `core/` |
| `core/` | stdlib + numpy only; NO UI, NO Qt, NO Flask |
| `api.py` | accepts/returns plain dicts only; NO Qt, NO Flask |
| `exporters/` | matplotlib + reportlab only; NO Qt, NO Flask |
| `desktop/` | PySide6 only; imports ONLY from `api.py` — never `core/` directly |

---

## 3. Import style — always full package paths

```python
# ✅ CORRECT
from models.soil import Soil
from core.bearing_capacity import bearing_capacity_hansen
from core.seepage import PhreaticSurface
from exporters.report_pdf import generate_slope_report

# ❌ WRONG
from soil import Soil
from seepage import PhreaticSurface
```

---

## 4. Calibration values — never break these

| Analysis | Value | Tolerance | Source |
|---|---|---|---|
| Slope FoS_k | 1.441 | ±0.005 | Craig Ex. 9.1, Bishop, φ=35°, γ=19, ru=0 |
| Sheet pile d (DA1-C2) | 2.1363 m | <0.002% | Craig Ex. 12.1, φ=38°, γ=20, h=6m |
| Sheet pile T (DA1-C2) | 54.780 kN/m | <0.002% | Craig Ex. 12.1 |
| Sheet pile M (DA1-C2) | 154.221 kN·m/m | <0.002% | Craig Ex. 12.1 |
| Sheet pile d (DA1-C1) | 1.5102 m | <0.002% | Craig Ex. 12.1 |
| Sheet pile T (DA1-C1) | 38.298 kN/m | <0.002% | Craig Ex. 12.1 |
| Sheet pile M (DA1-C1) | 102.445 kN·m/m | <0.002% | Craig Ex. 12.1 |
| Foundation q_ult_k | 1010–1050 kPa | ±5% | Hansen, φ=30°, γ=18, B=2m, Df=1m |

---

## 5. Current session starting point

Run these before making any changes:

```bash
cd C:\GeoDesignApp
.venv\Scripts\activate
python -m pytest tests/test_search.py tests/test_limit_equilibrium.py tests/test_factors_of_safety.py tests/test_api.py tests/test_desktop_ui.py -q
python -m pytest tests/test_pyslope_parity.py -q
```

Expected: core/desktop suites pass; parity gate highlights Craig Ex. 9.1 gap (intentional).

---

## 6. Open issues — work on these in order

| ID | Priority | File(s) | Issue |
|---|---|---|---|
| SLOPE-1 | 🔴 | `core/search.py`, `core/limit_equilibrium.py` | Stable geometries returning unrealistically large FoS |
| SLOPE-2 | 🔴 | `core/search.py`, `tests/test_pyslope_parity.py` | pySlope parity gap on Craig Ex. 9.1 |
| SLOPE-3 | 🟡 | `core/search.py` | Auto bounds may bias toward edge-adjacent circles |
| SLOPE-4 | 🟡 | `core/search.py`, `api.py` | Diagnostics not rich enough to explain circle selection |
| PILE-1 | 🟡 | `desktop/pages/pile_page.py` | PilePage is placeholder — not yet functional |

---

## 7. Primary files for slope calibration work

```
core/search.py              ← search zone, _auto_bounds(), _evaluate_circle()
core/slicer.py              ← slice generation
core/limit_equilibrium.py   ← Bishop/Spencer, _validate_driving_sum()
core/factors_of_safety.py   ← DA1 partial factor application
api.py                      ← run_slope_analysis(), verify_slope_da1()
exporters/plot_slope.py     ← arc clipping, heatmap
tests/test_search.py
tests/test_limit_equilibrium.py
tests/test_factors_of_safety.py
tests/test_api.py
tests/test_pyslope_parity.py
```

---

## 8. Recommended next actions

1. Reproduce unrealistic-high-FoS cases with a targeted test in `tests/test_search.py`.
2. Inspect `_evaluate_circle()` — add minimum sliding-mass width and arc-engagement checks.
3. Inspect `_validate_driving_sum()` — tighten threshold relative to geometry.
4. Review `_auto_bounds()` against slope height and crest/toe location.
5. Add `boundary_warning` trigger for radius proximity to min/max limits.
6. Surface search zone controls in `desktop/pages/slope_page.py` only after core engine is trusted.

---

## 9. Desktop threading model

All `api.run_*()` calls must run in a QThread worker, never on the main thread:

```python
class AnalysisWorker(QRunnable):
    def run(self):
        try:
            result = api.run_slope_analysis(self.payload)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
```

---

## 10. EC7 DA1 quick reference

```
DA1-C1 (A1+M1+R1):  γ_φ=1.00  γ_c=1.00  γ_G=1.35  γ_Q=1.50
DA1-C2 (A2+M2+R1):  γ_φ=1.25  γ_c=1.25  γ_G=1.00  γ_Q=1.30
                     γ_cu=1.40 (undrained clay, C2 only)

Design angle:    φ′_d = arctan(tan(φ′_k) / γ_φ)
Design cohesion: c′_d = c′_k / γ_c
Governing = whichever gives lower resistance / higher demand
```

---

## 11. Search zone data contract

```python
search_zone = {
    "xc_min": float, "xc_max": float,
    "yc_min": float, "yc_max": float,
    "r_min":  float, "r_max":  float,
    "n_cx":   int,   "n_cy":   int,   "n_r": int,
}

search_diagnostics = {
    "tested": int, "accepted": int,
    "invalid_geometry": int, "too_few_slices": int,
    "tiny_mass": int, "low_driving": int,
    "nonconvergent": int, "nonpositive_fos": int,
}
```
