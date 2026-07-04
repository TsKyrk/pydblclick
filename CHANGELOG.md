# Changelog

## 0.2.0 (2026-07) — the pivot release

The delivery mechanism moves from the deprecated `py.exe` shebang to standard
Windows file-handler registration. See [ROADMAP.md](ROADMAP.md) for the full story.

### Added
- `pip install` support with a `pyexewrap` console entry point (the
  PYTHONPATH/`add_to_pythonpath.py` installation becomes legacy).
- `pyexewrap register` / `unregister` / `diagnose` subcommands: standard
  ProgID + UserChoice file-handler registration, working with **and without**
  the MSIX Python Manager. Automatic backup before any registry change.
- PEP 723 support: scripts declaring inline dependencies (`# /// script`)
  are executed through `uv run` in an ephemeral environment, with the
  pyexewrap pause/menu UX preserved. Clear fallback message when uv is absent.
- `# pyexewrap: off` directive: per-script opt-out (plain Python behavior).
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

### Fixed
- Closing the console window with the X button no longer triggers a second
  "fallback pause" console (STATUS_CONTROL_C_EXIT is recognized as a
  deliberate user action).
- Clean tracebacks for SyntaxError (file/line/caret shown, no wrapper frames).

## 0.1.0

Initial shebang-based implementation (`#!/usr/bin/env python -m pyexewrap`
read by the classic `py.exe` launcher, PYTHONPATH installation).
