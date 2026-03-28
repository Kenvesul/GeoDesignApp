# Desktop-Only Folder Guide

This guide shows the safest way to create a clean desktop-only copy of DesignApp.

## Recommendation

The current lowest-risk split is:

- keep the whole `desktop/` folder
- keep the shared `api.py`
- keep the whole `core/`, `models/`, `exporters/`, and `data/` folders

Reason:

- `desktop/*` imports `api.py`
- `api.py` still imports every analysis family, not just slope
- because of that, a partial copy usually breaks unless you also refactor `api.py`

If you want a quick clean desktop package, copy the **full desktop runtime set** first, then trim it later.

## Full desktop runtime set

Copy these files and folders:

- `desktop/`
- `api.py`
- `core/`
- `models/`
- `exporters/`
- `data/`
- `requirements.txt`
- `requirements-dev.txt`
- `LICENSE`
- `README.md`

Copy these documents too if you want the current slope work context:

- `MATH_ROADMAP.md`
- `NEXT_CHAT_PROMPT_MATH.md`
- `SESSION_DIARY.md`
- `context.md`

## Safe to leave behind

You do not need these for a desktop-only package:

- `ui/`
- `react-spa/`
- `deploy/`
- `docker-compose.yml`
- `Dockerfile`
- `package.json`
- `package-lock.json`
- `playwright.config.js`
- web-only tests such as `tests/test_app.py` and `tests/e2e/`

## Smallest slope-only copy

This is the smallest *logical* slope slice, but it is **not** the lowest-effort copy because `api.py` is still broad:

- `desktop/app.py`
- `desktop/main_window.py`
- `desktop/theme.py`
- `desktop/workers.py`
- `desktop/widgets/`
- `desktop/pages/slope_page.py`
- `api.py`
- `core/search.py`
- `core/limit_equilibrium.py`
- `core/slicer.py`
- `core/factors_of_safety.py`
- `models/geometry.py`
- `models/soil.py`
- `exporters/plot_slope.py`
- `exporters/plot_bishop.py`
- `exporters/report_pdf.py`
- `exporters/report_docx.py`
- `data/soil_library.json`
- `data/ec7.json`

Before this smaller slice will work cleanly, you should first extract a dedicated slope-only bridge such as `api_slope.py` or `desktop_api.py`.

## Clean folder template

Use this as the new folder structure:

```text
DesignAppDesktop/
|-- README.md
|-- LICENSE
|-- requirements.txt
|-- requirements-dev.txt
|-- THIRD_PARTY_NOTICES.md
|-- MIGRATION_NOTES.md
|-- api.py
|-- data/
|   |-- ec7.json
|   `-- soil_library.json
|-- core/
|   |-- search.py
|   |-- limit_equilibrium.py
|   |-- slicer.py
|   |-- factors_of_safety.py
|   `-- ...
|-- models/
|   |-- soil.py
|   |-- geometry.py
|   `-- ...
|-- exporters/
|   |-- plot_slope.py
|   |-- plot_bishop.py
|   |-- report_pdf.py
|   |-- report_docx.py
|   `-- ...
|-- desktop/
|   |-- app.py
|   |-- main_window.py
|   |-- theme.py
|   |-- workers.py
|   |-- widgets/
|   `-- pages/
|-- docs/
|   `-- desktop-only/
|-- tests/
|   |-- test_search.py
|   |-- test_limit_equilibrium.py
|   |-- test_factors_of_safety.py
|   |-- test_api.py
|   |-- test_desktop_ui.py
|   `-- test_pyslope_parity.py
|-- MATH_ROADMAP.md
|-- NEXT_CHAT_PROMPT_MATH.md
`-- SESSION_DIARY.md
```

## Suggested next cleanup step

After you create the new folder, the best next refactor is:

1. create `desktop_api.py` with only desktop-needed calls
2. move slope-only imports out of the monolithic `api.py`
3. only then trim unrelated wall/pile/foundation modules

