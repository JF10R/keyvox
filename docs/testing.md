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

- `tests/test_main_entrypoint.py`: CLI mode selection, startup failure handling, and `_run_headless_mode` exception paths
- `tests/test_hotkey_*.py`: listener-layer hotkey behavior, double-tap, and shutdown handling
- `tests/test_pipeline.py`: TranscriptionPipeline worker thread — enqueue, callbacks, error handling, reload, replay
- `tests/test_server.py`: WebSocket protocol envelope, commands, input validation error paths, and migration worker
- `tests/test_history.py`: SQLite persistence, query/filter/delete/export behavior
- `tests/test_backends_*.py`: backend factory and backend adapter contracts
- `tests/test_config_*.py`: config defaults, loading, merging, hot-reload wiring, and `get_platform_config_dir` branches
- `tests/test_text_insertion.py`: capitalization/spacing/URL normalization rules
- `tests/test_hardware.py`: GPU detection fallbacks and VRAM-based model recommendation tiers
- `tests/test_storage.py`: path resolution helpers, `directory_size`, `estimate_migration_bytes`, and `migrate_storage_root`
- `tests/test_setup_wizard.py`: wizard flows, `_resolve_hf_hub_cache` branches, `_pip_install`, and `_check_model_cached`
- `tests/test_dictionary.py`: word correction, word boundaries, empty input, and punctuation adjacency

## Policy

- Add/adjust tests in the same change as behavior changes.
- Keep regressions locked with explicit targeted tests.
- Treat failing tests as blocking for merge.
