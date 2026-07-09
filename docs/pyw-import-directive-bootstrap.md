# Design note: the `import pydblclick` directive for `.pyw` (implemented in 0.5.0)

## The gap it closed

Through 0.4.0 the one-line `import pydblclick` directive gave a distributed
**`.py`** script the full experience (pause menu, clean tracebacks, PEP 723)
when the recipient had pip-installed pydblclick but not registered it. For
**`.pyw`** scripts it was **inert**: a double-clicked `.pyw` runs under
`pythonw.exe` with no console and no stdin, so the tty-based guard bailed out.

Consequence (pre-0.5.0): a `.pyw` that did `import pydblclick` and then raised
an uncaught exception died **silently** — no console — whereas a *registered*
`.pyw` would pop a console with the traceback. That limitation was the
`examples/11a` / `examples/11b` pair (`11b` was suffixed `FAILS`). A *successful*
windowed `.pyw` (the `10a` / `10b` pair) shows nothing either way by design and
was unaffected.

## How it works now

When the directive fires under pythonw, it relaunches
`pythonw -m pydblclick script.pyw`, which goes straight down the existing
**windowless path**: DETACHED child, stdout/stderr captured to a log,
`AllocConsole()` + stream rewiring on exception, then the traceback and pause
menu (`reveal_console_for_pyw()` in `pydblclick/_child.py`). The relaunch command
already uses `sys.executable`, which *is* pythonw for a `.pyw` double-click, so
no interpreter-selection code was needed.

- **No recursion**: the relaunched child sets `builtins.pydblclick_customizations`
  before running the script, so the script's second `import pydblclick` is inert
  — the same guard that protects the `.py` bootstrap.
- **Reuses everything**: no new UX code; the windowless pipeline is untouched.

## The real design problem: detecting a `.pyw` double-click

A `.pyw` has no tty, and `PROMPT`-absent alone also matches **legitimate
windowless automation** (services, scheduled tasks, GUI helpers). Activating
there would hijack scripts that deliberately want no console.

The solution is `_launched_by_explorer()` in `pydblclick/__init__.py`: it snapshots
the process table (`CreateToolhelp32Snapshot` / `Process32First`/`Next` via ctypes,
stdlib only) and walks the ancestry of the current process. It returns:

- **True** if it reaches `explorer.exe` **before** any shell/console host — a GUI
  double-click, tolerating launcher hops (py.exe, python.exe, pythonw.exe, the
  MSIX Python Manager).
- **False** as soon as it hits a shell/console host (`cmd.exe`, `powershell.exe`,
  `pwsh.exe`, `conhost.exe`, Windows Terminal, ...). This is the crucial guard:
  a `.pyw` launched from a terminal has that terminal — itself an Explorer
  descendant — in its ancestry, so a naive "is Explorer an ancestor?" check would
  false-positive. Stopping at the shell prevents that.
- **False** for automation (svchost/taskeng ancestry reaches neither marker) and
  on any failure (best-effort: stay inert).

Only scripts that *chose* to write `import pydblclick` are ever affected, so this
sits behind explicit author consent as well.

## Implementation summary

In `pydblclick/__init__.py::_maybe_enable_import_fallback()`, the double-click
gate became: proceed if stdin is an interactive tty (the `.py` case) **or** the
script extension is `.pyw` and `_launched_by_explorer()` is true. Every other
early-return is intact (console/CI/piped, `# pydblclick: off` opt-out, the
already-wrapped `builtins` marker, the imported-by-a-user-file stack check). The
bootstrap and `SystemExit` propagation are shared with the `.py` path unchanged.

## Tests

In `tests/test_import_fallback.py`:

- `test_pyw_directive_inert_without_explorer` — `.pyw` + directive under a shell
  ancestry (the test runner) stays inert; proves the false-positive guard.
- `test_pyw_directive_relaunches_windowless_on_crash` — simulated `.pyw`
  double-click that crashes relaunches and blocks at the menu on a fresh console;
  pops a real console, so gated behind `PYDBLCLICK_UI_TESTS=1` (like the existing
  windowless exception test).

Manual verification also confirmed a marker-file probe: a simulated `.pyw`
double-click records `WRAPPED` (relaunched through pydblclick), while the same
`.pyw` run from a terminal records `PLAIN` (inert).

## Status

Implemented in **0.5.0**. `examples/11b_HelloWorld.pyw_with_exception_WITH_pydblclick.pyw`
now demonstrates the working feature (the `FAILS` suffix was dropped).
