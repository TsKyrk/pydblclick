# Future improvement: make the `import pydblclick` directive work for `.pyw`

## The gap

The one-line `import pydblclick` directive gives a distributed **`.py`** script the
full experience (pause menu, clean tracebacks, PEP 723) when the recipient has
pip-installed pydblclick but not registered it. For **`.pyw`** scripts the
directive is currently **inert**: a double-clicked `.pyw` runs under `pythonw.exe`
with no console and no stdin, so the guard in `pydblclick/__init__.py` bails out
(`sys.stdin is None or not sys.stdin.isatty()` → `return False`).

Consequence: a `.pyw` that `import pydblclick` and then raises an uncaught
exception dies **silently** — no console appears — whereas a *registered*
`.pyw` would pop a console with the traceback. This is demonstrated by the
`examples/11a` / `examples/11b` pair (`11b` is suffixed `FAILS` on purpose).
A *successful* windowed `.pyw` (the `10a` / `10b` pair) shows nothing either way,
by design, so it is unaffected.

## Why it is fixable

Nothing fundamental blocks it. If the directive, under pythonw with no console,
relaunched `pythonw -m pydblclick script.pyw`, that goes straight down the
existing **windowless path** already implemented for the registered case:
DETACHED child, stdout/stderr captured to a log, `AllocConsole()` + stream
rewiring on exception, then the traceback and pause menu
(`reveal_console_for_pyw()` in `pydblclick/_child.py`).

- **No recursion**: the relaunched child sets `builtins.pydblclick_customizations`
  before running the script, so the script's second `import pydblclick` is inert
  — the same guard that already protects the `.py` bootstrap.
- **Reuses everything**: no new UX code; the windowless pipeline is untouched.

## The one real design problem: double-click detection under pythonw

The current heuristic (`PROMPT` absent, or an interactive tty) cannot be used as-is:
pythonw has no tty, and `PROMPT`-absent alone also matches **legitimate windowless
automation** (scheduled tasks, GUI helpers) that run a `.pyw` on purpose to stay
silent. Activating there would hijack scripts that deliberately want no console.

Two mitigations make it safe:

1. **Explicit author consent** — the behavior only ever fires on scripts that
   *chose* to write `import pydblclick`.
2. **Parent-process check** — a real double-click is launched from `explorer.exe`;
   a scheduled task is launched from `taskeng.exe` / `svchost.exe`. Walking the
   parent process (a small ctypes call: `CreateToolhelp32Snapshot` /
   `Process32First` to map the parent PID to its image name) distinguishes a
   double-click from automation cleanly, so we do not rely on `PROMPT` alone.

## Sketch of the implementation

In `pydblclick/__init__.py::_maybe_enable_import_fallback()`:

- When `sys.stdin` is not an interactive tty **and** the script extension is
  `.pyw` **and** the parent process is Explorer (double-click) on Windows,
  do **not** return early — instead bootstrap-relaunch
  `[pythonw_exe, "-m", "pydblclick", script, *args]` and `raise SystemExit`
  with its code (mirroring the `.py` path, using `pythonw.exe` as the launcher).
- Keep every other early-return intact (console/CI/piped contexts, the
  `# pydblclick: off` opt-out, the already-wrapped `builtins` marker, the
  imported-by-a-user-file stack check).
- Add a parent-process helper (Explorer detection) — likely alongside the
  existing `User32` ctypes wrappers, or a small `kernel32` snapshot helper.

## Tests to add

- `.pyw` + directive + exception, simulated double-click with an Explorer-parent
  stub → a console/traceback path is taken (gate behind `PYDBLCLICK_UI_TESTS=1`
  like the existing windowless exception test, which pops a real console).
- `.pyw` + directive under a **non-Explorer** parent (automation) → stays inert
  (no relaunch), proving the false-positive guard.
- `.pyw` + directive, successful script → still silent (no regression to `10b`).

## Status

Deferred. Tracked as a TODO in the main `README.md`. The `examples/11b_*_FAILS.pyw`
example documents the current limitation until this lands.
