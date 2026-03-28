# DesignApp v2.0

**Modular Python geotechnical analysis suite for Eurocode 7 (EN 1997-1:2004).**

[![CI](https://github.com/Kenvesul/DesignApp/actions/workflows/ci.yml/badge.svg)](https://github.com/Kenvesul/DesignApp/actions/workflows/ci.yml)
[![Slope Parity](https://img.shields.io/badge/slope%20parity-pySlope%20check%20active-orange)](https://github.com/Kenvesul/DesignApp/blob/main/tests/test_pyslope_parity.py)
[![EC7](https://img.shields.io/badge/standard-EC7%20EN%201997--1-blue)](https://eurocodes.jrc.ec.europa.eu/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/Kenvesul/DesignApp/blob/main/LICENSE)

DesignApp provides five core geotechnical analysis workflows, stamped PDF/DOCX/PNG exports, a shared math/API layer, and a PySide6 desktop app. Active slope work is desktop-first: the current effort is to make the slope search converge on the same governing mechanism as pySlope for Craig Example 9.1 before expanding the UI surface again.

---

## Analysis Types

| Analysis | Method | EC7 Reference | Current calibration status |
|---|---|---|---|
| Slope Stability | Bishop Simplified + Spencer | Section 11, Annex B | Craig Ex. 9.1 parity check vs pySlope in progress |
| Foundation Bearing | Hansen + Meyerhof factors | Section 6.5.2 | Dense sand benchmarked |
| Retaining Wall | Rankine/Coulomb, sliding/overturning | Section 9 | Craig Ch. 11 style sanity checks |
| Pile Capacity | Alpha-method (clay), beta-method (sand) | Section 7 | Tomlinson-aligned checks |
| Sheet Pile | Free-earth support, bisection solver | Section 9 | Craig Ex. 12.1 calibrated |

All analyses run DA1 dual combinations:

- `C1 = A1 + M1 + R1`
- `C2 = A2 + M2 + R1`

---

## Current slope status

- Desktop slope analysis now includes explicit search-zone controls, search diagnostics, and boundary warnings.
- A new regression in `tests/test_pyslope_parity.py` compares DesignApp and pySlope on Craig Example 9.1.
- That parity gate is intentionally active because the current search still disagrees materially with pySlope, which makes it a useful guide for the next round of search fixes.

---

## Quick Start

### Desktop app

```bash
git clone https://github.com/Kenvesul/DesignApp.git
cd DesignApp
pip install -r requirements.txt
python -m desktop.app
```

### Web app

The Flask and React surfaces remain available for non-slope workflows.

```bash
pip install -r requirements.txt
python -m ui.app
```

React SPA:

```bash
cd react-spa
npm install
npm run dev
```

### Dev dependencies

```bash
pip install -r requirements-dev.txt
```

This installs the desktop-test stack plus `pyslope` for slope parity checks.

---

## Project Structure

```text
DesignApp/
|-- api.py                  # Shared public bridge for analysis + export calls
|-- core/                   # Math engines and search logic
|-- models/                 # Dataclasses and geometry/material models
|-- exporters/              # PDF, DOCX, and plotting helpers
|-- desktop/                # PySide6 desktop app and analysis pages
|-- ui/                     # Flask app and retained legacy templates
|-- react-spa/              # React SPA for non-slope workflows
|-- data/                   # EC7 factors and soil library data
|-- tests/                  # Regression and integration suites
`-- deploy/                 # Deployment config
```

Desktop entry point:

- `python -m desktop.app`

Notable desktop files:

- `desktop/app.py`
- `desktop/main_window.py`
- `desktop/pages/slope_page.py`

---

## Web API endpoints

The web layer currently exposes the non-slope endpoints below:

| Method | Route | Description |
|---|---|---|
| GET | `/api/health` | Health check and session summary |
| GET | `/api/soils` | Soil library |
| POST | `/api/foundation/analyse` | Bearing + settlement |
| POST | `/api/wall/analyse` | Retaining wall |
| POST | `/api/pile/analyse` | Pile capacity |
| POST | `/api/sheet-pile/analyse` | Sheet pile free-earth support |
| GET | `/api/*/export/pdf` | PDF export |
| GET | `/api/*/export/docx` | DOCX export |
| GET | `/api/*/export/png` | PNG export |
| GET/POST | `/api/project/export/pdf` | Unified project PDF |

The slope engine remains available through the shared Python API in `api.py` and is currently driven by the desktop app rather than the web layer.

---

## Testing

Core regression examples:

- `tests/test_search.py`
- `tests/test_limit_equilibrium.py`
- `tests/test_factors_of_safety.py`
- `tests/test_api.py`
- `tests/test_desktop_ui.py`
- `tests/test_pyslope_parity.py`

Run the main desktop/math suite:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_search.py tests/test_limit_equilibrium.py tests/test_factors_of_safety.py tests/test_api.py tests/test_desktop_ui.py -q
```

Run the pySlope parity gate:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_pyslope_parity.py -q
```

Current expectation:

- Core desktop/math suites should pass.
- `tests/test_pyslope_parity.py` is the active search-quality gate and currently highlights the open Craig Ex. 9.1 mismatch.

---

## Requirements

Runtime:

- Python 3.12+
- Flask
- NumPy
- Matplotlib
- ReportLab
- python-docx
- pypdf
- PySide6

Development:

- pytest
- pytest-cov
- pytest-qt
- playwright
- pyslope

---

## License

MIT. See [LICENSE](LICENSE).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.
