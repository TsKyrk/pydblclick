# pydblclick and the MSIX Python Manager — compatibility notes

## How pydblclick is invoked

Since the 2026 pivot, pydblclick registers itself as the Windows file handler
(`pydblclick register`): the ProgIDs `pydblclick.PyFile`/`pydblclick.PywFile` point
directly to `python.exe -m pydblclick` / `pythonw.exe -m pydblclick`. No launcher,
no shebang in the chain:

```
Double-click on script.py
  → Windows Explorer resolves the file handler (UserChoice → ProgID)
  → launches: python.exe -m pydblclick script.py
  → pydblclick wraps and executes the script
```

The **legacy mechanism** (project's former name *pyexewrap*) relied on `py.exe` reading a
`#!/usr/bin/env python -m pydblclick` shebang, with the package made importable through a
system-wide PYTHONPATH. That chain is what MSIX broke — this document records why.

## Full compatibility matrix (confirmed by testing)

| Invocation method | Works with MSIX? | Works without MSIX? |
|---|---|---|
| `pydblclick register` → ProgID + UserChoice | **Yes** ✓ | **Yes** ✓ |
| Shebang `#!/usr/bin/env python -m pydblclick` on double-click (legacy) | **No** ✗ | **Yes** ✓ |
| HKLM ftype layer alone | **No** ✗ | **Yes** ✓ |

### Why the shebang approach does not work under MSIX

The shebang requires `py.exe` to be in the chain: only `py.exe` reads shebang lines and
re-invokes `python -m pydblclick`. `python.exe` itself treats `#!` as a regular comment.

Under MSIX, the Python Manager intercepts double-clicks via `appxmanifest.xml` and invokes
`python.exe` **directly** on the script — `py.exe` is never called, the shebang is never
read, and pydblclick is never invoked. The script runs as plain Python.

This was confirmed by testing: adding `input("press enter")` to the script and double-clicking
shows the script output with no pydblclick output whatsoever, even with verbose mode on.

> Since the pivot this is moot: the registered handler command invokes
> `python.exe -m pydblclick` directly, with pydblclick installed via pip in that
> interpreter — no shebang, no PYTHONPATH involved.

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
the HKLM ftype layer) have **no effect** on double-click behavior while the MSIX
package is installed. The App Model reads `appxmanifest.xml` directly.

### What is NOT bypassed

`HKCU\Software\Classes\pydblclick.PyFile\shell\open\command` is a standard HKCU ProgID key,
not an AppX key. UserChoice set via the Windows UI is honored by the MSIX launcher.
This is why the ProgID + UserChoice approach of `pydblclick register` works under MSIX.

## How to switch pydblclick on and off

### Enable (all .py/.pyw files wrapped)

```
pydblclick register
```

On MSIX systems, it registers the `pydblclick.PyFile`/`pydblclick.PywFile` ProgIDs and then
prompts you to set them as the default via Windows Settings (UserChoice). On classic systems,
it also updates the HKLM ftype automatically (UAC prompt appears if needed).

### Disable (back to plain Python on double-click)

```
pydblclick unregister
```

Removes the pydblclick ProgIDs and resets the HKLM ftype on classic systems.
On MSIX, shows instructions if UserChoice needs to be cleared manually.

### Diagnose current state

```
pydblclick diagnose
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
- **`pydblclick register` (ProgID + UserChoice)**: continues to work — the pymanager
  launcher honors UserChoice and reads the pydblclick HKCU ProgIDs.
- **HKLM ftype layer**: stops working when the classic Setup.exe disappears, as there
  will be no `Python.File` HKLM ftype to patch. Harmless: the ProgID path remains.
- **Legacy shebang approach on double-click**: does **not** work under MSIX — the Python
  Manager invokes `python.exe` directly, bypassing `py.exe` and the shebang entirely.
