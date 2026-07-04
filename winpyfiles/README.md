# winpyfiles

Windows Python file association manager. A standalone utility to inspect, configure, backup, and restore the Windows registry entries that control how `.py` and `.pyw` files are opened on double-click.

## Why this tool exists

When you double-click a `.py` file in Windows Explorer, the OS goes through a two-step lookup:

1. **Extension → ProgID** — `.py` maps to a named file type (e.g. `Python.File`)
2. **ProgID → Command** — the ProgID defines the executable that Windows runs

These mappings live in the Windows registry (`HKCU` / `HKLM`), but they can be overridden or bypassed by:
- **UserChoice** (`HKCU\...\Explorer\FileExts\<ext>\UserChoice`) — set via "Open with > Always use this app", highest priority, hash-protected
- **MSIX App Model** — packages installed via the Microsoft Store or MSIX declare file type associations in `appxmanifest.xml`, bypassing all registry ftype settings

winpyfiles makes this chain visible and configurable.

## CLI usage

```
py -m winpyfiles <command> [options]
```

| Command | Description |
|---|---|
| `diagnose` | Display the full file association chain with warnings (default) |
| `backup` | Snapshot current associations to a JSON file |
| `restore <file>` | Write back associations from a backup file (requires admin) |
| `reset` | Reset all Python extension commands to `py.exe` directly (requires admin) |
| `set-command <ProgID> <cmd>` | Set the open command for a given ProgID (requires admin) |
| `remove-msix` | Uninstall the MSIX Python Manager package for the current user |

Options:
- `--elevate` — trigger a UAC prompt automatically for commands that require admin rights

### Examples

```
py -m winpyfiles diagnose
py -m winpyfiles backup
py -m winpyfiles backup C:\backups\py_assoc.json
py -m winpyfiles restore winpyfiles_backup_20250101_120000.json --elevate
py -m winpyfiles reset --elevate
py -m winpyfiles set-command Python.File "\"C:\Windows\py.exe\" \"%1\" %*" --elevate
py -m winpyfiles remove-msix
```

## Python API

```python
from winpyfiles import diagnose, find_py_exe, set_command, AssocDiagnosis

d = diagnose()
for ext in d.extensions:
    print(ext.extension, "->", ext.prog_id_effective)

for prog_id, info in d.prog_ids.items():
    print(prog_id, "->", info.command_effective)

print(d.msix_package)   # path to MSIX Python Manager install dir, or None
print(d.msix_handlers)  # dict of AppX ProgID -> shell open command
```

### Key data classes

**`AssocDiagnosis`**
- `extensions` — list of `ExtensionInfo` (one per `.py`/`.pyw`)
- `prog_ids` — dict of ProgID → `ProgIdInfo`
- `msix_handlers` — dict of AppX ProgID → command (empty if no MSIX block)
- `msix_package` — install path of `PythonSoftwareFoundation.PythonManager`, or `None`

**`ExtensionInfo`**
- `extension` — e.g. `.py`
- `user_choice` — UserChoice ProgID (Explorer priority, hash-protected)
- `prog_id_hkcu` — ProgID from HKCU
- `prog_id_hklm` — ProgID from HKLM
- `prog_id_effective` — the ProgID actually used (HKCU wins over HKLM)

**`ProgIdInfo`**
- `prog_id` — e.g. `Python.File`
- `command_hkcu` — shell open command from HKCU
- `command_hklm` — shell open command from HKLM
- `command_effective` — the command actually used

## Known compatibility risk: MSIX Python Manager

The `PythonSoftwareFoundation.PythonManager` MSIX package (installed via the Microsoft Store or
via the "Python Install Manager" from python.org) intercepts `.py`/`.pyw` double-clicks through
Windows App Model activation declared in `appxmanifest.xml`. This **bypasses all registry-based**
ftype/assoc/shell\open\command settings.

**Detection:** `py -m winpyfiles diagnose` shows a `[!!] MSIX Python Manager detected` warning.

**Resolution:** Run `py -m winpyfiles remove-msix`, or uninstall "Python Manager" manually from
Windows Settings > Apps > Installed apps.

> Note: the "Python Install Manager" from python.org is itself an MSIX package and does **not**
> resolve this issue. Use the classic `python-3.x.x-amd64.exe` Setup.exe installer instead.

## Module structure

| File | Role |
|---|---|
| `__main__.py` | CLI entry point and command implementations |
| `_assoc.py` | Core logic: registry reads, `diagnose()`, `set_command()`, MSIX detection |
| `_backup.py` | `backup()` and `restore()` to/from JSON |
| `_registry.py` | Low-level `winreg` helpers (`read_value`, `write_value`, `delete_value`) |
| `_elevation.py` | UAC elevation helpers (`is_admin`, `elevate_and_rerun`) |

## Requirements

- Windows 10 or 11
- Python 3.8+
- No external dependencies (uses only the standard library)

## Installation

winpyfiles is currently bundled with pydblclick. Add the repo root to `PYTHONPATH` and it becomes
importable system-wide:

```
python add_to_pythonpath.py  # from the pydblclick repo root, admin rights required
```
