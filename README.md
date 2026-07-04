# What is pyexewrap ?

pyexewrap makes Python scripts pleasant to run **by double-click** on Windows — for you,
your colleagues, or anyone you share a one-file script with:

- The console window **never flashes away**: a pause prompt appears at the end of the
  script, *including* when an exception occurs (even a syntax error), so the traceback
  is always readable.
- Scripts that declare their dependencies inline ([PEP 723](https://peps.python.org/pep-0723/))
  are executed through [uv](https://docs.astral.sh/uv/): **dependencies are resolved
  automatically** in an ephemeral environment — the recipient never manages venvs or
  `pip install`.
- An interactive menu at the pause prompt: `<i>` opens a Python console **with the
  script's real variables** (post-mortem debugging), `<c>` opens a cmd console,
  `<r>` restarts the script.
- `.pyw` (windowed) scripts run with **no console at all** (they are registered with
  `pythonw.exe`) — but if they crash, a console is created on the spot showing the
  script's output and the traceback, instead of dying silently.
- When a script is run from a console, called by another script or a batch file,
  pyexewrap stays out of the way: no pause, exit codes and arguments faithfully
  propagated.

## Python's native problems for Windows users

- A double-clicked `.py` file pops a console that flashes away, unless the last line is
  a blocking `input()` — and even then, any exception (a syntax error, a missing module)
  skips that line and the window vanishes before the traceback can be read.
- That blocking `input()` becomes undesirable when the same script is run from a console
  or called by another script.
- A `.pyw` script that crashes dies silently: there is no console to show the traceback.
- Sharing a script that needs `requests` or `pandas` means asking the recipient to
  understand pip, venvs, and PATH — or it just crashes with `ModuleNotFoundError`.

# Installation

```commandline
pip install <path-to-this-repo>       (PyPI package coming soon)
pyexewrap register
```

`pyexewrap register` sets pyexewrap as the default handler for `.py`/`.pyw` double-clicks
using the standard Windows mechanism (ProgID + UserChoice). This works on **all** Python
installations — classic installer *and* MSIX Python Manager (see
[MSIX_COMPATIBILITY.md](MSIX_COMPATIBILITY.md)). A backup of the previous file
associations is saved automatically before any change.

To undo everything:

```commandline
pyexewrap unregister
```

To inspect the Windows file association chain (and detect MSIX interference):

```commandline
pyexewrap diagnose
```

For automatic dependency resolution (PEP 723 scripts), also install
[uv](https://docs.astral.sh/uv/getting-started/installation/). Without uv, PEP 723
scripts still run with plain Python, and a message explains what to install.

# Usage

## Double-click (the main purpose)

Once registered, **every** `.py`/`.pyw` file you double-click runs enhanced. Nothing to
add to the scripts themselves. Try the scripts in the [examples](examples/) folder.

## Sharing dependency-aware one-file scripts (PEP 723 + uv)

Declare dependencies at the top of the script, in standard PEP 723 format:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "rich"]
# ///
import requests
...
```

On a machine with pyexewrap + uv, double-clicking this file "just works": uv resolves
the dependencies in an ephemeral environment, and pyexewrap keeps the window open with
its usual menu. This is a standard format — the same file also runs with `uv run` alone
on any platform. Use `uv add --script myscript.py requests` to maintain the block.

## Opting a script out

Add this comment anywhere in a script to make pyexewrap step aside (plain Python
behavior, no pause):

```python
# pyexewrap: off
```

## Pause only on error

To make an individual script skip the final pause *unless an exception occurred*:

```python
pyexewrap_customizations['must_pause_in_console'] = False
```

## Command line

`pyexewrap <script.py> [args...]` (or `python -m pyexewrap <script.py> [args...]`) wraps
a script explicitly. In a console there is no pause; set the
`pyexewrap_simulate_doubleclick` env var to force double-click behavior (useful in
batch files and tests).

## Custom icons

Scripts launched via pyexewrap show the registered Python icon. For a custom icon,
create a shortcut to the script and set the icon in its properties (see the example in
[examples](examples/)).

# How it works

Two processes (see [CLAUDE.md](CLAUDE.md) architecture notes and [ROADMAP.md](ROADMAP.md)):

- a thin **parent supervisor** (`python -m pyexewrap`) which guarantees the window
  survives anything — even `os._exit()`, a native crash, or a script that closes stdin;
- a **child engine** (`python -m pyexewrap._child`) which runs your script with exact
  plain-Python semantics (`runpy`), shows clean tracebacks (no wrapper frames), and
  owns the pause menu. For PEP 723 scripts the child runs inside the uv-provisioned
  environment.

No monkey-patching, no code injection: `__name__`, `__file__`, `sys.argv`, exit codes
and `exit()`/`quit()` behave exactly as with plain Python.

# Legacy: the shebang method (deprecated)

Before the 2026 pivot, scripts were enhanced individually with a shebang line
(`#!/usr/bin/env python -m pyexewrap`) read by the classic `py.exe` launcher, and
installation went through `add_to_pythonpath.py`. This mechanism **still works on
classic-installer systems** but is a dead end:

- the classic `py.exe` launcher is deprecated since Python 3.14 and will not be produced
  for Python 3.16+;
- the MSIX Python Manager (Microsoft Store / "Python Install Manager" on python.org)
  never reads shebangs on double-click, and its shebang support
  [does not allow arguments](https://docs.python.org/3/using/windows.html) such as
  `-m pyexewrap`.

Use `pyexewrap register` instead; per-script granularity is provided by the
`# pyexewrap: off` directive. See [MSIX_COMPATIBILITY.md](MSIX_COMPATIBILITY.md) for the
full compatibility matrix and history.

# Compatibility with the MSIX Python Manager (python/pymanager)

The `PythonSoftwareFoundation.PythonManager` MSIX package intercepts `.py`/`.pyw`
double-clicks through Windows App Model activation, bypassing shebangs and registry
ftype settings. **`pyexewrap register` works with it**: the MSIX launcher honors
UserChoice pointing to the `pyexewrap.PyFile` ProgID (confirmed by testing).

If double-clicks don't reach pyexewrap, run `pyexewrap diagnose` — it detects MSIX
interference and tells you what to fix. Details in
[MSIX_COMPATIBILITY.md](MSIX_COMPATIBILITY.md).

# Note about py.exe

`py.exe` was the Windows wrapper for multiple Python interpreters, making pyexewrap a
wrapper of a wrapper. Its pymanager successor confirms that launcher-level wrapping is
not extensible — which is why pyexewrap now registers itself as the file handler, the
one mechanism every launcher must respect.

# Todos

- Publish to PyPI (`pip install pyexewrap`)
- Standalone `pyexewrap.exe` handler (no Python required to bootstrap; uv can even
  provision Python itself) — see `tools/pyexewrap_exe` for the current prototype
- Offer to install uv when a PEP 723 script is double-clicked and uv is missing
- Context menu items "Run with pyexewrap" / "Bypass pyexewrap"

# Contributions

Your contributions would be greatly appreciated. Feel free to copy the project.
