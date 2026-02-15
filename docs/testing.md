# Testing and Coverage

This repository follows a test-driven workflow and keeps full module-level visibility on behavior and regressions.

## Current Status

- Total tests: **154**
- Previous baseline (at `HEAD` before this test expansion): **51**
- Tests added: **+103**
- Coverage command: `python -m pytest --cov=keyvox --cov-report=term-missing -q`
- Current coverage: **100%** (`812/812` statements)

## Test Inventory

| Test file | Count | Scope |
|---|---:|---|
| `tests/test_backends_base.py` | 1 | Abstract backend contract |
| `tests/test_backends_factory.py` | 10 | Backend selection, dependency errors, factory behavior |
| `tests/test_backends_impl.py` | 11 | Backend implementations (`faster-whisper`, `qwen-asr`, `qwen-asr-vllm`) |
| `tests/test_config_hot_reload.py` | 7 | File reloader polling and change detection |
| `tests/test_config_module.py` | 13 | Config load/save, merge, discovery per platform |
| `tests/test_dictionary.py` | 4 | Dictionary matching and key normalization |
| `tests/test_hotkey_runtime.py` | 19 | Runtime hotkey flow, paste modes, runtime reload |
| `tests/test_hotkey_shutdown.py` | 7 | ESC/Ctrl+C shutdown paths and edge cases |
| `tests/test_main_entrypoint.py` | 9 | CLI entrypoint paths and fatal handling |
| `tests/test_recorder.py` | 6 | Recorder stream lifecycle and audio concatenation |
| `tests/test_setup_wizard.py` | 8 | Wizard flows, GPU/CPU branches, cache env setup |
| `tests/test_text_insertion.py` | 51 | Capitalization, spacing, URL normalization, WWW policy |
| `tests/test_ui_styles.py` | 8 | Theme loading/cache/token replacement |

## TDD Standard Used

1. **Red**
   - Add or update a failing test first for each new behavior or bug path.
2. **Green**
   - Implement the smallest change that makes the test pass.
3. **Refactor**
   - Clean up while keeping tests green and behavior stable.
4. **Regression lock**
   - Keep a dedicated regression test for each bug fixed.
5. **Coverage verification**
   - Re-run with `--cov=keyvox --cov-report=term-missing` before commit.

## Local Commands

```bash
# Fast pass
python -m pytest -q

# Coverage gate
python -m pytest --cov=keyvox --cov-report=term-missing -q
```

## Tracking Policy

- Every new feature/bugfix should include tests in the same change.
- Coverage drops should be treated as a blocking signal unless explicitly justified.
- Failing tests are fixed before merge; no skipped failing suites.
