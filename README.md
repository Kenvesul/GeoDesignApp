# GeoDesignApp

**PySide6 desktop geotechnical analysis suite — Eurocode 7 (EN 1997-1:2004)**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![EC7](https://img.shields.io/badge/standard-EC7%20EN%201997--1-blue)](https://eurocodes.jrc.ec.europa.eu/)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/Kenvesul/GeoDesignApp/blob/main/LICENSE)

GeoDesignApp is a standalone desktop application for Eurocode 7 geotechnical analysis. It provides five core analysis workflows, stamped PDF/DOCX/PNG exports, and a shared Python math layer.

---

## Analysis types

| Analysis | Method | EC7 reference | Status |
|---|---|---|---|
| Slope stability | Bishop simplified + Spencer + infinite-slope | §11, Annex B | ✅ Craig Ex. 9.1 calibrated |
| Foundation bearing | Hansen + Meyerhof factors | §6.5.2 | ✅ Dense sand benchmarked |
| Retaining wall | Rankine/Coulomb, sliding/overturning | §9 | ✅ Craig Ch. 11 |
| Pile capacity | α-method (clay), β-method (sand) | §7 | ✅ Tomlinson-aligned |
| Sheet pile | Free-earth support, bisection solver | §9 | ✅ Craig Ex. 12.1 |

All analyses run DA1 dual combinations: `C1 = A1+M1+R1` and `C2 = A2+M2+R1`.

---

## Slope stability engine — design & known behaviour

### Two failure mechanisms are checked in parallel

**1. Circular (Bishop Simplified / Spencer)**
Grid-searches over candidate circle centres and radii to find the minimum FoS
rotational arc. Five geometric quality filters reject degenerate circles:

| Filter | What it rejects |
|---|---|
| Too few slices (`< 5`) | Near-empty arcs |
| Tiny mass (`< 0.5 % of slope area`) | Negligible sliding mass |
| Extreme base angles (`> 75 °`) | Circles clipping only a steep corner |
| Arc off slope face | Arcs that span only the flat crest or toe |
| Arc centroid outside face zone | Arcs dominated by flat-region weight |
| Circle too deep (`> 1.5 H below toe`) | Unrealistically deep graben circles |

**2. Infinite-slope / planar (Taylor 1937, Craig §9.2)**
Applies only when `c′ ≈ 0`. For each inclined slope segment:

    FoS_inf = (1 − rᵤ / cos²β) · tan φ′ / tan β

`fos_char` is always `min(FoS_circular, FoS_infinite_slope)`.

### Mirrored (right→left descending) slopes

The driving-sum sign convention was fixed in this release. All three LE
methods (Ordinary, Bishop, Spencer) now use `|Σ W·sinα|` as the denominator,
so slopes descending in either direction give correct FoS values and plots.

### Calibration for Craig Example 9.1

| Mechanism | FoS | Notes |
|---|---|---|
| Infinite-slope | **1.400** | `tan 35° / tan 26.6°` — exact theory |
| Bishop circular | ~2.17 | Valid circular arcs have higher FoS than planar for c=0 |
| Governing (`fos_char`) | **1.400** | Planar governs; confirmed by pySlope (reports same) |

For cohesive soils (c′ > 0) the circular mechanism typically governs. pySlope
and DesignApp may report different absolute values because pySlope models a
30 m deep soil block while DesignApp models only the defined slope profile.
Both agree the slope is stable (FoS > 1) for the Craig cohesive example.

---

## API result keys — slope

`run_slope_analysis()` returns these slope-specific keys in addition to the
standard schema:

| Key | Type | Description |
|---|---|---|
| `fos_char` | float | Governing characteristic FoS (`min(circular, infinite_slope)`) |
| `fos_char_circular` | float | Bishop circular FoS from grid search |
| `fos_char_infinite_slope` | float or null | Infinite-slope FoS (null if `c′ > 0.5 kPa`) |
| `governing_mechanism` | str | `"circular"` or `"infinite_slope"` |
| `critical_circle` | dict | `{cx, cy, r}` of the critical Bishop arc |

The export helpers rebuild the stored critical circle from cached analysis
data, so `export_slope_plot_png()`, `export_heatmap_png()`, `export_pdf()`,
and `export_docx()` stay consistent without rerunning the full grid search.

---

## Quick start

```bash
git clone https://github.com/Kenvesul/GeoDesignApp.git
cd GeoDesignApp
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python -m desktop.app
```

---

## Project structure

```
GeoDesignApp/
├── api.py                  ← Shared public bridge — only file desktop/ imports from math
├── core/
│   ├── limit_equilibrium.py  ← Ordinary, Bishop Simplified, Spencer methods
│   ├── search.py             ← Grid search + quality filters
│   ├── slicer.py             ← Slice geometry
│   └── factors_of_safety.py  ← EC7 DA1 verification
├── models/                 ← Dataclasses (Soil, SlopeGeometry, SlipCircle …)
├── exporters/
│   ├── plot_slope.py         ← Cross-section + arc plot (fixed for large R circles)
│   └── plot_bishop.py        ← FoS heatmap
├── desktop/
│   ├── app.py                ← Entry point: python -m desktop.app
│   ├── main_window.py
│   └── pages/slope_page.py
├── data/                   ← EC7 factor tables + soil library
└── tests/
    ├── test_pyslope_parity.py  ← 4-test parity gate (all pass)
    ├── test_limit_equilibrium.py
    ├── test_search.py
    └── test_slicer.py
```

---

## Running tests

```bash
# Core slope math (15 tests, ~8 s)
python -m pytest tests/test_search.py tests/test_limit_equilibrium.py tests/test_slicer.py -q

# pySlope parity gate (4 tests — all expected to pass)
python -m pytest tests/test_pyslope_parity.py -q

# Full suite
python -m pytest -q
```

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

## Requirements

**Runtime:** Python 3.12+, PySide6 ≥ 6.6, numpy ≥ 1.26, matplotlib ≥ 3.8,
reportlab ≥ 4.0, python-docx ≥ 1.1, pypdf ≥ 4.0

**Development:** pytest, pytest-qt, pytest-cov, pyslope
(`pip install -r requirements-dev.txt`)

---

## License

MIT — see [LICENSE](LICENSE).
