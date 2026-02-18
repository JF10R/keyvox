# Testing and Coverage

Keyvox uses pytest as the validation gate for CLI runtime, backend protocol/server behavior, and history/config flows.

**Current suite: 268 tests.**

## Commands

```bash
# Fast pass
python -m pytest -q

# Coverage pass
python -m pytest --cov=keyvox --cov-report=term-missing -q
```

## CI

GitHub Actions runs the full suite on every push and PR:

- **Test**: Python 3.11 + 3.12, `windows-latest` (sounddevice/pynput require Windows)
- **Lint**: `ruff check` + `ruff format --check`, `ubuntu-latest`
- **Typecheck**: `mypy --ignore-missing-imports`, `ubuntu-latest`, `continue-on-error`

## Scope

- `tests/test_main_entrypoint.py`: CLI mode selection, startup failure handling, and `_run_headless_mode` exception paths
- `tests/test_hotkey_*.py`: listener-layer hotkey behavior, double-tap, and shutdown handling
- `tests/test_pipeline.py`: TranscriptionPipeline worker thread — enqueue, callbacks, error handling (including CUDA OOM continue-and-hint), reload, replay
- `tests/test_server.py`: WebSocket protocol envelope, commands, input validation error paths, and migration worker
- `tests/test_history.py`: SQLite persistence, query/filter/delete/export behavior
- `tests/test_backends_factory.py`: backend factory, auto-detection, ImportError hints (print + ValueError)
- `tests/test_backends_impl.py`: backend adapter contracts, model-load failure cache-delete hints
- `tests/test_backends_base.py`: base class contracts
- `tests/test_config_*.py`: config defaults, loading, merging, hot-reload wiring, `get_platform_config_dir` branches, schema versioning (auto-migration, future-version guard, idempotency)
- `tests/test_text_insertion.py`: capitalization/spacing/URL normalization rules
- `tests/test_hardware.py`: GPU detection fallbacks and VRAM-based model recommendation tiers
- `tests/test_storage.py`: path resolution helpers, `directory_size`, `estimate_migration_bytes`, and `migrate_storage_root`
- `tests/test_setup_wizard.py`: wizard flows, `_resolve_hf_hub_cache` branches, `_pip_install`, and `_check_model_cached`
- `tests/test_dictionary.py`: word correction, word boundaries, empty input, and punctuation adjacency
- `tests/test_recorder.py`: stream init, callbacks, PortAudioError hint (device list + `--setup` pointer)

## Policy

- Add/adjust tests in the same change as behavior changes.
- Keep regressions locked with explicit targeted tests.
- Treat failing tests as blocking for merge.
