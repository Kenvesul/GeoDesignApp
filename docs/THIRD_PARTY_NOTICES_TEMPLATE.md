# Third-Party Notices Template

Use this file in the new desktop-only folder and fill in exact versions after copy.

## Runtime dependencies

| Package | Purpose | License | Notes |
|---|---|---|---|
| PySide6 | Desktop UI | LGPL/commercial terms from Qt distribution | Review packaging obligations before redistribution |
| matplotlib | Plot rendering | Matplotlib license | Include notice if redistributed |
| reportlab | PDF export | BSD-style | Include notice if redistributed |
| python-docx | DOCX export | MIT | Safe for bundled use |
| pypdf | PDF merge/read | BSD-style | Safe for bundled use |
| flask | Shared API/web helper | BSD-style | Only needed if retained |

## Development and validation dependencies

| Package | Purpose | License | Notes |
|---|---|---|---|
| pytest | Tests | MIT | Dev only |
| pytest-qt | Desktop tests | MIT | Dev only |
| playwright | E2E tests | Apache-2.0 | Dev only |
| pyslope | Slope parity oracle | MIT | Good reference implementation for validation |

## If code is copied from third-party projects

Record each project here:

| Project | URL | License | What was copied | Action |
|---|---|---|---|---|
| pySlope | https://github.com/JesseBonanno/PySlope | MIT | Example: search setup or adapter code | Keep copyright + license text |
| pyCSS | https://github.com/eamontoyaa/pyCSS | MIT | Example: circular-search helper ideas | Keep copyright + license text |
| pyBIMstab | https://github.com/ElsevierSoftwareX/SOFTX_2018_137 | BSD-2-Clause | Example: geometry helpers | Keep copyright + license text |

## Notes

- Keep the upstream `LICENSE` text for any vendored code.
- If you copy code instead of depending on the package, add a dedicated `vendor/` folder and preserve attribution.
- Re-check PySide6/Qt redistribution obligations before packaging binaries.
