# Changelog

## 0.2.1 (2026-07)

Documentation-only release.

- New [ARCHITECTURE.md](https://github.com/TsKyrk/pydblclick/blob/main/ARCHITECTURE.md):
  two-process design, protocols, windowless `.pyw` flow, PEP 723 delegation,
  design principles.
- README reworked: installation instructions show `pip install pydblclick`
  (the 0.2.0 PyPI page was built before publication), legacy/pyexewrap
  considerations consolidated into a single History paragraph, absolute links
  so the PyPI project page works, stale todo removed.

## 0.2.0 (2026-07) — the pivot release

The delivery mechanism moves from the deprecated `py.exe` shebang to standard
Windows file-handler registration. See [ROADMAP.md](ROADMAP.md) for the full story.

### Renamed
- The project is renamed **pyexewrap → pydblclick**: the old name referenced
  wrapping the (now deprecated) `py.exe` launcher and wrongly suggested
  exe-building tools (py2exe/PyInstaller family). Legacy compatibility kept:
  the `# pyexewrap: off` directive, the `pyexewrap_customizations` name and
  the `pyexewrap_simulate_doubleclick` env var still work; `register`/
  `unregister` clean up registry entries from the old name.

### Added
- `pip install` support with a `pydblclick` console entry point (the
  PYTHONPATH/`add_to_pythonpath.py` installation becomes legacy).
- `pydblclick register` / `unregister` / `diagnose` subcommands: standard
  ProgID + UserChoice file-handler registration, working with **and without**
  the MSIX Python Manager. Automatic backup before any registry change.
- PEP 723 support: scripts declaring inline dependencies (`# /// script`)
  are executed through `uv run` in an ephemeral environment, with the
  pydblclick pause/menu UX preserved. Clear fallback message when uv is absent.
- `# pydblclick: off` directive: per-script opt-out (plain Python behavior).
- Truly windowless `.pyw` execution: registered with `pythonw.exe`, no console
  at all; on exception a console is created on demand (AllocConsole), replaying
  the script's captured output before the traceback and pause menu.
- Script arguments are forwarded (`sys.argv`) and exit codes propagated to
  CLI/batch callers.

### Changed
- Two-process architecture: a parent supervisor guarantees the window never
  flashes away (fallback pause on hard crash or closed stdin); a child engine
  runs the script via `runpy.run_path()` with plain-Python semantics
  (`__name__`, `__file__`, real globals — no more `exec()` namespace emulation).
- The `<i>` interactive console now uses the script's real globals; on
  exception, the post-mortem globals are captured from the traceback frame.
- `exit()`/`quit()` monkey-patching removed.

- winpyfiles becomes the `pydblclick.winpyfiles` subpackage: the wheel ships a
  single top-level package (no risk of colliding with a future `winpyfiles`
  distribution on PyPI). CLI: `py -m pydblclick.winpyfiles <command>`.

### Removed
- Legacy installation and activation scripts, superseded by `pip install` +
  `pydblclick register`: `add_to_pythonpath.py`, `tools/ByDefaultActivation/`,
  `tools/pyexewrap_exe/`, `run_tests.py`, and the manual `unit_tests/` scenarios
  (now covered by the automated suite in `tests/`).

### Fixed
- Closing the console window with the X button no longer triggers a second
  "fallback pause" console (STATUS_CONTROL_C_EXIT is recognized as a
  deliberate user action).
- Clean tracebacks for SyntaxError (file/line/caret shown, no wrapper frames).

## 0.1.0

Initial shebang-based implementation, under the original name *pyexewrap*
(`#!/usr/bin/env python -m pyexewrap` read by the classic `py.exe` launcher,
PYTHONPATH installation).
