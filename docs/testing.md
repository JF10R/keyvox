# Testing and Coverage

Keyvox uses pytest as the validation gate for CLI runtime, backend protocol/server behavior, and history/config flows.

## Commands

```bash
# Fast pass
python -m pytest -q

# Coverage pass
python -m pytest --cov=keyvox --cov-report=term-missing -q
```

## Scope

- `tests/test_main_entrypoint.py`: CLI mode selection and startup failure handling
- `tests/test_hotkey_*.py`: runtime hotkey behavior and shutdown handling
- `tests/test_server.py`: WebSocket protocol envelope, commands, and events
- `tests/test_history.py`: SQLite persistence, query/filter/delete/export behavior
- `tests/test_backends_*.py`: backend factory and backend adapter contracts
- `tests/test_config_*.py`: config defaults, loading, merging, and hot-reload wiring
- `tests/test_text_insertion.py`: capitalization/spacing/URL normalization rules

## Policy

- Add/adjust tests in the same change as behavior changes.
- Keep regressions locked with explicit targeted tests.
- Treat failing tests as blocking for merge.
