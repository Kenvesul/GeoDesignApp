# Desktop-Only Copy Checklist

## Copy first

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

## Copy if you want project context

- `MATH_ROADMAP.md`
- `NEXT_CHAT_PROMPT_MATH.md`
- `SESSION_DIARY.md`
- `context.md`

## Add or update in the new folder

- `THIRD_PARTY_NOTICES.md`
- `MIGRATION_NOTES.md`
- desktop-specific `README.md`

## Verify after copy

- `python -m desktop.app`
- `.\.venv\Scripts\python.exe -m pytest tests/test_search.py tests/test_limit_equilibrium.py tests/test_factors_of_safety.py tests/test_api.py tests/test_desktop_ui.py -q`
- `.\.venv\Scripts\python.exe -m pytest tests/test_pyslope_parity.py -q`

## Remove later, not first

- unrelated web folders
- unused tests
- unused exporters
- unused non-slope analysis modules

Only remove those after the copied desktop folder boots and tests pass.

