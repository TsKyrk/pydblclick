# pydblclick and the MSIX Python Manager — compatibility notes

## How pydblclick is invoked (the normal chain)

pydblclick relies on a specific chain of events when a user double-clicks a `.py` file:

```
Double-click on script.py
  → Windows Explorer resolves the file handler
  → launches py.exe "script.py"
  → py.exe reads the shebang: #!/usr/bin/env python -m pydblclick
  → py.exe re-invokes: python.exe -m pydblclick script.py
  → pydblclick wraps and executes the script
```

Two components are essential:

1. **`py.exe`** (the Windows Python Launcher) must be the program that opens `.py` files.
   Only `py.exe` knows how to read shebang lines — `python.exe` itself ignores them entirely
   (the `#!` line is treated as a regular Python comment).

2. **pydblclick must be importable** by the Python environment that `py.exe` selects.
   This is ensured by `add_to_pythonpath.py`, which adds the repo to the system PYTHONPATH.

## Full compatibility matrix (confirmed by testing)

| Invocation method | Works with MSIX? | Works without MSIX? |
|---|---|---|
| `activate.py` → ByDefaultActivation (UserChoice) | **Yes** ✓ | **Yes** ✓ |
| Shebang `#!/usr/bin/env python -m pydblclick` on double-click | **No** ✗ | **Yes** ✓ |
| `activate.py` HKLM ftype layer | **No** ✗ | **Yes** ✓ |

### Why the shebang approach does not work under MSIX

The shebang requires `py.exe` to be in the chain: only `py.exe` reads shebang lines and
re-invokes `python -m pydblclick`. `python.exe` itself treats `#!` as a regular comment.

Under MSIX, the Python Manager intercepts double-clicks via `appxmanifest.xml` and invokes
`python.exe` **directly** on the script — `py.exe` is never called, the shebang is never
read, and pydblclick is never invoked. The script runs as plain Python.

This was confirmed by testing: adding `input("press enter")` to the script and double-clicking
shows the script output with no pydblclick output whatsoever, even with `pydblclick_verbose = True`.

> **Note on `.pth`:** `add_to_pythonpath.py` still installs a `pydblclick.pth` file in
> site-packages. This is a safety net for ByDefaultActivation (UserChoice), ensuring pydblclick
> remains findable even if PYTHONPATH is not propagated in the App Model activation context.
> It does not help the shebang approach.

## The MSIX Python Manager

The `PythonSoftwareFoundation.PythonManager` package (from the Microsoft Store or the
"Python Install Manager" on python.org) uses **Windows App Model activation** to handle
`.py`/`.pyw` double-clicks. This activation is declared in `appxmanifest.xml`:

```xml
<Application Id="Python.Exe" ...>
  <Extensions>
    <uap3:Extension Category="windows.fileTypeAssociation">
      <uap3:FileTypeAssociation Name="python-file">
        <uap:SupportedFileTypes>
          <uap:FileType>.py</uap:FileType>
          <uap:FileType>.pyw</uap:FileType>
        </uap:SupportedFileTypes>
      </uap3:FileTypeAssociation>
    </uap3:Extension>
  </Extensions>
</Application>
```

When this package is installed, Windows bypasses the registry ftype entirely and invokes the
MSIX application declared in the manifest — the pymanager launcher (`py.exe`). This launcher:

- **Honors UserChoice** → if UserChoice is set to `pydblclick.PyFile`, the launcher invokes
  pydblclick for all `.py` files (the recommended approach).
- **Does NOT read shebang lines for module invocation** → invokes `python.exe` directly on
  the script. The `#!` line is treated as a Python comment. pydblclick is never invoked.

### What is bypassed by MSIX

All changes to `shell\open\command` registry keys (made by `winpyfiles set-command` or
`activate.py`'s HKLM layer) have **no effect** on double-click behavior while the MSIX
package is installed. The App Model reads `appxmanifest.xml` directly.

### What is NOT bypassed

`HKCU\Software\Classes\pydblclick.PyFile\shell\open\command` is a standard HKCU ProgID key,
not an AppX key. UserChoice set via the Windows UI is honored by the MSIX launcher.
This is why `activate.py`'s ProgID + UserChoice approach works under MSIX.

## How to switch ByDefaultActivation on and off

### Enable (all .py files wrapped, with or without shebang)

```
py tools/ByDefaultActivation/activate.py
```

On MSIX systems, `activate.py` registers the `pydblclick.PyFile` ProgID and then prompts you
to set it as the default via Windows Settings (UserChoice). On classic systems, it also
updates the HKLM ftype automatically (UAC prompt appears if needed).

### Disable (back to plain Python on double-click)

```
py tools/ByDefaultActivation/disable.py
```

Removes the `pydblclick.PyFile` ProgID and resets the HKLM ftype on classic systems.
On MSIX, shows instructions if UserChoice needs to be cleared manually.

> **Note (MSIX):** after `disable.py`, pydblclick is not invoked on any double-click.
> The shebang approach does not work under MSIX regardless of `.pth` or PYTHONPATH —
> the Python Manager bypasses py.exe entirely. Re-enable via `activate.py` (UserChoice)
> to restore wrapping.

### Diagnose current state

```
py tools/ByDefaultActivation/diagnose.py
# or equivalently:
py -m winpyfiles diagnose
```

## Long-term outlook

The Python 3.14 documentation officially deprecates the classic Python Launcher:

> *"Deprecated since Python 3.14, will not be produced for Python 3.16+"*

And the python.org downloads page states:

> *"The traditional installer will remain available throughout the 3.14 and 3.15 releases."*

This means:
- `C:\Windows\py.exe` (classic launcher) disappears with Python 3.16
- The classic Setup.exe (which configures the HKLM ftype registry) may also disappear

**Impact on pydblclick:**
- **ByDefaultActivation via `activate.py` (MSIX path)**: continues to work — the pymanager
  launcher honors UserChoice and reads the `pydblclick.PyFile` HKCU ProgID.
- **ByDefaultActivation via `activate.py` HKLM layer**: stops working when the classic
  Setup.exe disappears, as there will be no `Python.File` HKLM ftype to patch.
- **Shebang approach on double-click**: does **not** work under MSIX — the Python Manager
  invokes `python.exe` directly, bypassing `py.exe` and the shebang entirely.
