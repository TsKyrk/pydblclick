# pydblclick — Roadmap (2026 pivot)

## Why this pivot

The original delivery mechanism — a shebang line `#!/usr/bin/env python -m pydblclick`
read by the classic `py.exe` launcher — is dying:

- The classic `py.exe` launcher is **deprecated since Python 3.14** and will not be
  produced for Python 3.16+.
- The **MSIX Python Manager** (pymanager), now the default way to install Python on
  Windows, intercepts `.py`/`.pyw` double-clicks via App Model activation, never reads
  the shebang for module invocation, and its shebang support **does not allow arguments**
  such as `-m pydblclick` (custom `shebang_templates` only accept `py`, `py -3.x`,
  `py -V:<tag>`).

What survives — confirmed by testing (see [MSIX_COMPATIBILITY.md](MSIX_COMPATIBILITY.md)):
the **ProgID + UserChoice** registration (`pydblclick.PyFile`), i.e. the standard way any
Windows application registers itself as a file handler. It works with and without MSIX.

The pivot therefore recomposes the project around three ideas:

1. **ProgID/UserChoice registration is the primary mechanism** (ByDefaultActivation +
   winpyfiles are promoted from "add-on" to core).
2. **Subprocess execution replaces in-process `exec()`** — removes the monkey-patching
   of `exit()`/`quit()` and the manual namespace reconstruction. The child engine runs
   the script via `runpy` (plain-Python semantics) and keeps the interactive console
   on the script's real globals; the parent supervisor guarantees the pause even on
   hard crash or closed stdin.
3. **PEP 723 + uv integration** finally covers the dependency half of the original goal:
   one-file scripts that colleagues can double-click without managing venvs — the handler
   detects the `# /// script` metadata block and delegates execution to `uv run`.

Dropping the shebang also **frees the installation story**: the registered handler command
can point to anything, so `pip install pydblclick` / a standalone `pydblclick.exe` become
possible (the PYTHONPATH hack existed only because the shebang went through the system
Python).

## Phases

### Phase 0 — Acknowledge the pivot (docs)
- [x] Fix the README ↔ MSIX_COMPATIBILITY.md contradiction (shebang under MSIX: **No**)
- [x] Mark the shebang method as legacy in the README, point to ByDefaultActivation
- [x] Write this roadmap

### Phase 1 — Core: subprocess execution model
- [x] Refactor to a two-process model: child engine (`pydblclick._child`, runs the
      script via `runpy` and owns the pause menu) + parent supervisor (fallback
      pause when the child cannot pause: closed stdin, hard crash)
- [x] Post-mortem REPL (`<i>` menu option) with the script's real globals
      (captured from the traceback frame on exception)
- [x] Remove the `exit()`/`quit()` monkey-patching and the `globalsParameter`
      namespace reconstruction (both become unnecessary with a child process)
- [x] `.pyw` handling in subprocess mode: hidden console, re-shown when the child
      exit code is non-zero
- [x] Detect failure via child exit code; keep `<c>`/`<i>`/`<r>` menu behaviour
- [x] Adapt `tests/` (pytest) and `unit_tests/` (manual UX scenarios) to the new model

### Phase 2 — Modern installation
- [x] Make the package pip-installable: `pyproject.toml` with a `pydblclick` console
      entry point (the PYTHONPATH/`add_to_pythonpath.py` approach becomes legacy)
- [x] `pydblclick register` / `pydblclick unregister` CLI commands — merge
      `tools/ByDefaultActivation/activate.py`/`disable.py` and winpyfiles into the
      main CLI (ProgID + UserChoice flow, automatic backup)
- [ ] Build a small standalone handler exe so the registered command does not
      depend on which Python is on PATH (a PyInstaller prototype existed in
      tools/, removed during the 0.2.0 cleanup — see git history)

### Phase 3 — Dependency management (PEP 723 / uv)
- [x] Detect the PEP 723 `# /// script` block in the target script; if present,
      execute via `uv run` instead of plain `python`
- [x] Graceful fallback when uv is not installed (clear message + install link;
      optionally offer to install it)
- [x] Per-script opt-out directive read by the wrapper itself (e.g. `# pydblclick: off`
      comment) — replaces the per-script granularity the shebang used to provide

### Phase 4 — Distribution
- [x] Rewrite the README around the new flow: install → `pydblclick register` →
      double-click any script (PEP 723 aware)
- [x] Publish to PyPI (0.2.0, 2026-07-05)

## Non-goals

- Becoming a home-made IDE. The value of pydblclick is being a thin, invisible wrapper;
  IDE-like features (code injection, heavy customization) are out of scope.
- Supporting the shebang mechanism beyond legacy documentation.

## References

- [MSIX_COMPATIBILITY.md](MSIX_COMPATIBILITY.md) — tested compatibility matrix
- [Using Python on Windows](https://docs.python.org/3/using/windows.html) — pymanager
  shebang rules, deprecation timeline
- [PEP 773](https://peps.python.org/pep-0773/) — the Python Install Manager
- [PEP 723](https://peps.python.org/pep-0723/) — inline script metadata
- [uv — Running scripts](https://docs.astral.sh/uv/guides/scripts/)
