# pydblclick — architecture

## Invocation chain

`pydblclick register` sets the standard Windows file-handler registration
(ProgID + UserChoice), so a double-click resolves like this:

```
Double-click on script.py
  → Windows Explorer resolves the file handler (UserChoice → ProgID pydblclick.PyFile)
  → launches: python.exe -m pydblclick script.py      (pythonw.exe for .pyw)
  → parent supervisor spawns the child engine
  → child engine runs the script and owns the UX
```

Two ProgIDs are registered:

| Extension | ProgID | Handler command |
|---|---|---|
| `.py` | `pydblclick.PyFile` | `"...\python.exe" -m pydblclick "%1" %*` |
| `.pyw` | `pydblclick.PywFile` | `"...\pythonw.exe" -m pydblclick "%1" %*` |

The registered interpreter is the one that ran `pydblclick register` — by definition
it can import pydblclick, so no PATH or PYTHONPATH setup is involved.

## Two-process design

### Parent supervisor — `pydblclick/__main__.py` (`python -m pydblclick`)

A thin process whose single guarantee is: **the window never flashes away**. Before
launching the child it inspects the script's source (`pydblclick/_script_meta.py`):

- `# pydblclick: off` directive → runs the script with plain Python
  (pythonw for `.pyw`), no wrapping, exit code propagated. This is the per-script
  opt-out.
- PEP 723 `# /// script` block → the child is launched through
  `uv run --no-project --with <dep>... [--python <spec>] python -m pydblclick._child`,
  so dependencies are resolved in an ephemeral environment. pydblclick itself is made
  importable inside that environment via PYTHONPATH injection. If uv is missing, a
  clear message is printed and the script runs with plain Python.
- otherwise → `python -m pydblclick._child script.py [args...]`.

While the child runs, the parent ignores Ctrl+C (the child must handle it: the script
sees KeyboardInterrupt, then the pause menu shows). After the child exits, the parent
displays a **fallback pause** if — and only if — the child could not fulfil its
pause duty:

- the script closed stdin with `exit()`/`quit()` (`input()` becomes impossible in the
  child),
- the interpreter died hard (`os._exit()`, native crash, MemoryError...).

Exception: exit code `0xC000013A` (STATUS_CONTROL_C_EXIT) means the user closed the
console window — a deliberate action, no fallback pause.

### Child engine — `pydblclick/_child.py` (`python -m pydblclick._child`)

Runs the target script and owns the whole UX:

- **Execution** via `runpy.run_path(run_name="__main__")`: plain-Python module
  semantics (`__name__ == "__main__"`, `__file__`, real globals), no `exec()`
  namespace emulation, no monkey-patching. The script's directory is prepended to
  `sys.path`, like `python script.py`. Arguments after the script path become the
  script's `sys.argv[1:]`.
- **Traceback display** (`showtraceback`): the pydblclick/runpy frames are stripped
  so the traceback starts at the user's script. An excepthook installed *by the
  script itself* takes precedence (detected by snapshotting `sys.excepthook` before
  execution — comparing against `sys.__excepthook__` is not enough because some
  environments replace the hook globally).
- **Pause menu**: `<Enter>` quit, `<c>` cmd console, `<i>` interactive Python console
  on the script's real globals (post-mortem: the globals captured from the traceback
  frame), `<r>` restart.
- **Exit codes**: `sys.exit(n)` in the script is propagated through both processes
  for CLI/batch callers. Codes above INT_MAX (e.g. `0xC000013A`) are converted to
  the signed 32-bit range (`signed32()`) because `sys.exit()` overflows on them
  before Python 3.14; two's complement preserves the value that
  `GetExitCodeProcess` reports.

### Child → parent protocol

The env var `PYDBLCLICK_STATUS_FILE` points to a temp file where the child writes
`"handled"` once its pause-or-no-pause duty is fulfilled. A missing marker after the
child exits is what triggers the parent's fallback pause — it survives any way the
child may die.

## Windowless `.pyw` flow

`.pyw` files are registered with `pythonw.exe`, so the parent has **no console at
all**. The child runs fully detached (`DETACHED_PROCESS`), stdout/stderr captured in
a log file (env var `PYDBLCLICK_PYW_LOG`), stdin on NUL. Behaviour:

- script ends normally → nothing was ever displayed, the log file is deleted;
- uncaught exception → the child creates a console on the spot (`AllocConsole`),
  rewires `sys.stdin/stdout/stderr` to it (`CONIN$`/`CONOUT$`), replays the captured
  log, then shows the traceback and the pause menu (`reveal_console_for_pyw()`);
- hard crash → the parent creates the console itself and shows the fallback pause.

Legacy path: when a console already exists (e.g. a `.pyw` launched from a terminal),
it is hidden/shown with `ShowWindow` instead.

## What scripts can see and do

- Double-click detection: `'PROMPT' not in os.environ`, or the
  `pydblclick_simulate_doubleclick` env var (useful in batch files and tests).
  In console/batch contexts there is no pause and no title change.
- `pydblclick_customizations['must_pause_in_console'] = False` — skip the final
  pause unless an exception occurs. The dict is exposed through `builtins`, not
  injected into the script's globals.
- `# pydblclick: off` — full opt-out, read by the parent before launching.
- `import pydblclick` — optional first-line directive for distributed scripts.
  On import, `pydblclick/__init__.py` acts only when *all* of these hold: Windows,
  double-click context (interactive stdin required unless simulated), not already
  wrapped (no `builtins.pydblclick_customizations` marker), and imported by a user
  file. When they do, it **re-launches the script through the real pydblclick**
  (`python -m pydblclick <script> [args]` with the current interpreter, SIGINT
  ignored so the child chain owns Ctrl+C) and exits with the child's code
  (`_signed32`). One import line thus yields the full experience — menu, restart,
  clean tracebacks, PEP 723/uv — with no registry change. Because the directive
  is the first line, nothing in the original process has run yet, so raising
  `SystemExit` there is clean and nothing runs twice; and the relaunch happens
  before any not-yet-installed PEP 723 dependency import could fail.
  Recursion is impossible: the relaunched child sets the `builtins` marker before
  running the script (so its second `import pydblclick` is inert), and pydblclick's
  own `-m` startup shows nothing but interpreter machinery in the import stack, so
  it never self-activates. If the relaunch cannot even start — or if
  `PYDBLCLICK_NO_BOOTSTRAP` is set — a minimal in-process fallback takes over
  instead (excepthook + atexit pause, hint about `register`). `.pyw` double-clicks
  run under pythonw with no interactive stdin, so the directive stays inert there;
  console-less `.pyw` remains a `register`-only feature.

## The winpyfiles subpackage

`pydblclick.winpyfiles` is the Windows file-association layer: registry reads/writes
(extension → ProgID → command), UserChoice inspection, MSIX Python Manager detection,
backup/restore of associations (JSON files under `%LOCALAPPDATA%\pydblclick\backups`),
UAC elevation helpers. It is self-contained (stdlib only) and has its own CLI:
`py -m pydblclick.winpyfiles <diagnose|backup|restore|reset|set-command|remove-msix>`.
`pydblclick register/unregister/diagnose` are built on top of it.

MSIX specifics (why UserChoice is the only mechanism that always works) are documented
in [MSIX_COMPATIBILITY.md](https://github.com/TsKyrk/pydblclick/blob/main/MSIX_COMPATIBILITY.md).

## Design principles

- **Thin, invisible wrapper**: the script must behave exactly as with plain Python
  (`__name__`, `__file__`, `sys.argv`, exit codes, `exit()`/`quit()`). No code
  injection, no monkey-patching — anything the wrapper needs is process isolation.
- **Standard mechanisms only**: file-handler registration (ProgID + UserChoice) is
  the one hook every Python launcher — including the MSIX Python Manager — must
  respect; PEP 723 is the standard for inline dependencies.
- **Crash-proof by construction**: whatever kills the child (closed stdin, native
  crash, Ctrl+C), the parent survives to keep the window open.

## Tests

- `tests/` — automated pytest suite (in-process, subprocess, PEP 723/opt-out,
  supervisor fallback). Run with `python -m pytest`.
- The `.pyw` exception-path test pops a real console: gated behind
  `PYDBLCLICK_UI_TESTS=1`.
- `tests/test_system.py` checks *this machine's* file associations and is skipped
  when the `CI` env var is set.
- UX demos: double-click the scripts in
  [examples/](https://github.com/TsKyrk/pydblclick/tree/main/examples).
