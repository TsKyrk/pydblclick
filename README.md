# What is pydblclick ?

pydblclick makes Python scripts pleasant to run **by double-click** on Windows — for you,
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
  pydblclick stays out of the way: no pause, exit codes and arguments faithfully
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
pip install pydblclick
pydblclick register
```

`pydblclick register` sets pydblclick as the default handler for `.py`/`.pyw` double-clicks
using the standard Windows mechanism (ProgID + UserChoice). This works on **all** Python
installations — classic installer *and* MSIX Python Manager (see
[MSIX_COMPATIBILITY.md](https://github.com/TsKyrk/pydblclick/blob/main/MSIX_COMPATIBILITY.md)).
A backup of the previous file associations is saved automatically before any change.

> **One manual confirmation may be required.** Windows protects the user's default-app
> choice (UserChoice): it cannot be set programmatically. If pydblclick is not invoked
> on double-click after `register` — always the case with the MSIX Python Manager, or
> when another app was previously chosen — confirm it once in Explorer:
>
> right-click a `.py` file → **Open with** → **Choose another app** → **pydblclick** →
> **Always** — then do the same once with a `.pyw` file.
>
> `pydblclick register` detects your installation type and prints these instructions
> when the manual step is needed.

To undo everything:

```commandline
pydblclick unregister
```

To inspect the Windows file association chain (and detect MSIX interference):

```commandline
pydblclick diagnose
```

For automatic dependency resolution (PEP 723 scripts), also install
[uv](https://docs.astral.sh/uv/getting-started/installation/). Without uv, PEP 723
scripts still run with plain Python, and a message explains what to install.

# Usage

## Main usage

### Double-click

Once registered, **every** `.py`/`.pyw` file you double-click runs enhanced. Nothing to
add to the scripts themselves. Try the scripts in the
[examples](https://github.com/TsKyrk/pydblclick/tree/main/examples) folder.

### Sharing dependency-aware one-file scripts (PEP 723 + uv)

Declare dependencies at the top of the script, in standard PEP 723 format:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "rich"]
# ///
import requests
...
```

On a machine with pydblclick + uv, double-clicking this file "just works": uv resolves
the dependencies in an ephemeral environment, and pydblclick keeps the window open with
its usual menu. This is a standard format — the same file also runs with `uv run` alone
on any platform. Use `uv add --script myscript.py requests` to maintain the block.

### Distributing to people who may not have pydblclick

There are two ways to adopt pydblclick, and you can mix them:

- **Machine-wide** — `pydblclick register` once, and *every* `.py`/`.pyw` is
  wrapped on double-click, no per-script change. Best for your own machine.
- **Per-script** — add one optional line to the script you distribute. The
  recipient only needs `pip install pydblclick` (no `register`, no registry
  change) to get the full experience on that script.

For distribution, prefer the per-script line — keep it on the **first line**:

```python
import pydblclick  # optional: pip install pydblclick -- or delete this line
```

- **pydblclick registered**: the line is inert — full experience.
- **pydblclick pip-installed but not registered**: on double-click the import
  re-launches the script through pydblclick, so the recipient gets the *full*
  experience — the pause menu, clean tracebacks, and PEP 723 dependency
  resolution — from that single line. This works for `.pyw` too: a crashing
  windowed script shows a console with its traceback instead of dying silently.
  In a console it does strictly nothing. (Keeping the import first means nothing
  above it runs twice, and the relaunch happens before any not-yet-installed
  PEP 723 dependency would fail to import.)
- **Machine without pydblclick**: the recipient gets an `ImportError`, reads the
  comment, and chooses — install pydblclick or delete the line.

If you want even the bare machine to see a friendly message instead of an
`ImportError`, use this 3-line variant:

```python
try: import pydblclick  # optional: pip install pydblclick -- or delete these 3 lines
except ImportError:
    import os; "PROMPT" in os.environ or input("Tip: 'pip install pydblclick' makes this script double-click friendly. (Enter to run anyway)")
```

## Advanced usage

Optional, per-script features for seasoned users — plain scripts need none of this.

### Opting a script out

Add this comment anywhere in a script to make pydblclick step aside (plain Python
behavior, no pause):

```python
# pydblclick: off
```

### Pause only on error

To make an individual script skip the final pause *unless an exception occurred*:

```python
pydblclick_customizations['must_pause_in_console'] = False
```

### Command line

`pydblclick <script.py> [args...]` (or `python -m pydblclick <script.py> [args...]`) wraps
a script explicitly. In a console there is no pause; set the
`pydblclick_simulate_doubleclick` env var to force double-click behavior (useful in
batch files and tests).

### Custom icons

Scripts launched via pydblclick show the registered Python icon. For a custom icon,
create a shortcut to the script (ALT+drag & drop) and set the icon in its properties.

# How it works

Two processes: a thin **parent supervisor** which guarantees the window survives
anything — even `os._exit()`, a native crash, or a script that closes stdin — and a
**child engine** which runs your script with exact plain-Python semantics (`runpy`),
shows clean tracebacks (no wrapper frames), and owns the pause menu. For PEP 723
scripts the child runs inside the uv-provisioned environment.

No monkey-patching, no code injection: `__name__`, `__file__`, `sys.argv`, exit codes
and `exit()`/`quit()` behave exactly as with plain Python.

Full details in [ARCHITECTURE.md](https://github.com/TsKyrk/pydblclick/blob/main/ARCHITECTURE.md).

# Security

pydblclick is designed to be fully auditable:

- **Pure Python, no binaries**: the published wheel contains only readable `.py` files
  (tag `py3-none-any`) — no compiled extension, no bundled executable. The
  `pydblclick.exe` that appears in `Scripts\` is generated locally by **pip** itself,
  the same standard launcher stub every console-script package gets (`pip.exe`,
  `pytest.exe`...).
- **No dependencies**: standard library only. Nothing else gets pulled onto your machine.
- **Nothing runs at install time**: installing a wheel is a plain file copy (PEP 427).
  The first pydblclick code that executes is the one you launch — identical to what you
  can read in `site-packages` or on GitHub.
- **Traceable builds**: releases are built and published by
  [GitHub Actions](https://github.com/TsKyrk/pydblclick/blob/main/.github/workflows/publish.yml)
  from public tags via PyPI trusted publishing, with provenance attestations attached to
  the files on PyPI.
- **Reversible system changes**: the only thing touching your system is
  `pydblclick register`, which writes standard per-user file-association registry keys —
  backed up automatically beforehand, and fully removed by `pydblclick unregister`.

# Compatibility with the MSIX Python Manager (python/pymanager)

The `PythonSoftwareFoundation.PythonManager` MSIX package intercepts `.py`/`.pyw`
double-clicks through Windows App Model activation, bypassing registry ftype settings.
**`pydblclick register` works with it**: the MSIX launcher honors UserChoice pointing
to the `pydblclick.PyFile` ProgID (confirmed by testing).

If double-clicks don't reach pydblclick, run `pydblclick diagnose` — it detects MSIX
interference and tells you what to fix. Details in
[MSIX_COMPATIBILITY.md](https://github.com/TsKyrk/pydblclick/blob/main/MSIX_COMPATIBILITY.md).

# Todos

- Standalone `pydblclick.exe` handler (no Python required to bootstrap; uv can even
  provision Python itself)
- Offer to install uv when a PEP 723 script is double-clicked and uv is missing
- Context menu items "Run with pydblclick" / "Bypass pydblclick"

# History

pydblclick was born as **pyexewrap**: scripts were enhanced one by one with a shebang
line (`#!/usr/bin/env python -m pyexewrap`) read by the classic `py.exe` launcher, and
installed via a system-wide PYTHONPATH. That mechanism died with the platform — the
classic launcher is deprecated since Python 3.14, and the MSIX Python Manager neither
reads shebangs on double-click nor allows arguments in them — so the project pivoted in
2026 to standard file-handler registration (`pydblclick register`) and was renamed, the
old name wrongly suggesting exe-building tools. A few compatibility aliases from that
era are still honored (`# pyexewrap: off`, `pyexewrap_customizations`, the
`pyexewrap_simulate_doubleclick` env var), and `register`/`unregister` clean up registry
entries left by old installs. The full investigation is preserved in
[MSIX_COMPATIBILITY.md](https://github.com/TsKyrk/pydblclick/blob/main/MSIX_COMPATIBILITY.md).

# Contributions

Your contributions would be greatly appreciated. Feel free to copy the project.
