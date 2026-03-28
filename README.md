# GeoDesignApp

**PySide6 desktop geotechnical analysis suite — Eurocode 7 (EN 1997-1:2004)**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![EC7](https://img.shields.io/badge/standard-EC7%20EN%201997--1-blue)](https://eurocodes.jrc.ec.europa.eu/)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/Kenvesul/GeoDesignApp/blob/main/LICENSE)

GeoDesignApp is a standalone desktop application for Eurocode 7 geotechnical analysis. It provides five core analysis workflows, stamped PDF/DOCX/PNG exports, and a shared Python math layer that can also be driven by the companion web interface in [DesignApp](https://github.com/Kenvesul/DesignApp).

The current development focus is the slope stability engine — specifically tightening the slip circle search so the governing mechanism is physically credible and calibrated against reference examples.

---

## Analysis types

| Analysis | Method | EC7 reference | Calibration status |
|---|---|---|---|
| Slope stability | Bishop simplified + Spencer | §11, Annex B | Craig Ex. 9.1 — parity check vs pySlope in progress |
| Foundation bearing | Hansen + Meyerhof factors | §6.5.2 | Dense sand benchmarked |
| Retaining wall | Rankine/Coulomb, sliding/overturning | §9 | Craig Ch. 11 sanity checks |
| Pile capacity | α-method (clay), β-method (sand) | §7 | Tomlinson-aligned |
| Sheet pile | Free-earth support, bisection solver | §9 | Craig Ex. 12.1 calibrated |

All analyses run DA1 dual combinations: `C1 = A1+M1+R1` and `C2 = A2+M2+R1`.

---

## Quick start

```bash
git clone https://github.com/Kenvesul/GeoDesignApp.git
cd GeoDesignApp
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
python -m desktop.app
```

---

## Project structure

```
GeoDesignApp/
├── api.py                  ← Shared public bridge — only file desktop/ imports from
├── core/                   ← Math engines (bearing, slope, wall, pile, sheet pile)
├── models/                 ← Dataclasses and geometry models
├── exporters/              ← PDF, DOCX, and matplotlib plot helpers
├── desktop/                ← PySide6 application
│   ├── app.py              ← Entry point — python -m desktop.app
│   ├── main_window.py      ← QMainWindow + QTabWidget
│   ├── widgets/            ← Shared UI components
│   └── pages/              ← One QWidget per analysis type
├── data/                   ← EC7 partial factor tables + soil library
└── tests/                  ← Regression and integration suites
```

### Architecture rule

Desktop pages call `api.py` only — never `core/` directly. The same `api.py` is used by the web layer in DesignApp, so both surfaces stay in sync automatically.

---

## Running tests

```bash
# Core math and desktop smoke tests
.venv\Scripts\python.exe -m pytest tests/test_search.py tests/test_limit_equilibrium.py tests/test_factors_of_safety.py tests/test_api.py tests/test_desktop_ui.py -q

# pySlope parity gate (active calibration check — expected to highlight Craig Ex. 9.1 gap)
.venv\Scripts\python.exe -m pytest tests/test_pyslope_parity.py -q
```

The parity gate is intentionally left active because it guides the slope search calibration work. It is not expected to pass until the search improvements in the roadmap are complete.

---

## Calibration values

These must remain stable across all changes:

| Check | Value | Tolerance |
|---|---|---|
| Craig Ex. 9.1 — slope FoS | 1.441 | ±0.005 |
| Craig Ex. 12.1 — sheet pile d (DA1-C2) | 2.1363 m | <0.002% |
| Craig Ex. 12.1 — sheet pile T (DA1-C2) | 54.780 kN/m | <0.002% |
| Craig Ex. 12.1 — sheet pile M (DA1-C2) | 154.221 kN·m/m | <0.002% |
| Foundation q_ult_k | 1010–1050 kPa | ±5% |

---

## Requirements

**Runtime:**
```
Python 3.12+
PySide6 >= 6.6
numpy >= 1.26
matplotlib >= 3.8
reportlab >= 4.0
python-docx >= 1.1
pypdf >= 4.0
flask >= 3.0
```

**Development:**
```
pytest
pytest-qt >= 4.4
pytest-cov
pyslope
```

Install dev dependencies: `pip install -r requirements-dev.txt`

---

## EC7 DA1 partial factors

| Factor | DA1-C1 | DA1-C2 | Applied to |
|---|---|---|---|
| γ_φ | 1.00 | **1.25** | tan φ′_k |
| γ_c | 1.00 | **1.25** | c′_k |
| γ_cu | 1.00 | **1.40** | cu_k (undrained) |
| γ_G | 1.35 | 1.00 | Permanent loads |
| γ_Q | 1.50 | 1.30 | Variable loads |

---

## Related repository

The web interface (Flask + React SPA) lives in [DesignApp](https://github.com/Kenvesul/DesignApp). Both repositories share the same `core/`, `models/`, `exporters/`, and `api.py` math layer.

---

## License

MIT — see [LICENSE](https://github.com/Kenvesul/GeoDesignApp/blob/main/LICENSE).
