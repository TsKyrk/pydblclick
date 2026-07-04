#!/usr/bin/env python
"""Disable pydblclick as the default handler for .py and .pyw double-clicks.

Restores the default Python behavior on double-click. Automatically detects the
Python installation type and undoes the corresponding configuration:

  - MSIX Python Manager (Microsoft Store / Python Install Manager):
      Removes the pydblclick.PyFile ProgID. If UserChoice was set to pydblclick,
      Windows will typically clear it automatically -- but if .py files still
      open with pydblclick afterwards, a one-time manual step is shown.

  - Classic Python (no MSIX, python-x.x.x-amd64.exe installer):
      Removes the pydblclick.PyFile ProgID and resets the HKLM ftype to the
      plain Python launcher (requires admin -- a UAC prompt will appear automatically).

Backs up the current registry state before any change.
"""
import sys
import os
import winreg

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_repo_root,):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from winpyfiles import diagnose, find_py_exe, find_python_appx_prog_ids, set_command
from winpyfiles._assoc import find_msix_python_package
from winpyfiles._registry import HKCU, notify_shell_assoc_changed
from winpyfiles._elevation import is_admin, elevate_and_rerun
from winpyfiles._backup import backup

PROG_ID = "pydblclick.PyFile"
APP_KEY = "pydblclick"
EXTENSIONS = (".py", ".pyw")


def _delete_key_tree(hive, key_path):
    """Recursively delete a registry key and all its subkeys."""
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, 0)
                    _delete_key_tree(hive, f"{key_path}\\{subkey_name}")
                except OSError:
                    break
        winreg.DeleteKey(hive, key_path)
    except FileNotFoundError:
        pass


def _delete_value(hive, key_path, value_name):
    """Delete a single registry value, ignoring errors if absent."""
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, value_name)
    except FileNotFoundError:
        pass


def _unregister():
    """Remove the pydblclick.PyFile ProgID and all related registry entries."""
    _delete_key_tree(HKCU, f"Software\\Classes\\{PROG_ID}")
    _delete_key_tree(HKCU, f"Software\\Classes\\Applications\\{APP_KEY}")
    _delete_value(HKCU, "Software\\RegisteredApplications", APP_KEY)
    _delete_key_tree(HKCU, f"Software\\{APP_KEY}")
    for ext in EXTENSIONS:
        _delete_value(HKCU, f"Software\\Classes\\{ext}\\OpenWithProgids", PROG_ID)
    notify_shell_assoc_changed()
    print("  [OK] pydblclick.PyFile ProgID removed.")


def main():
    # Capture UserChoice state before making any changes.
    d = diagnose()
    had_user_choice = [e for e in d.extensions if e.user_choice == PROG_ID]

    saved = backup()
    print(f"Backup saved: {saved}\n")

    # Step 1: remove the ProgID (works for both MSIX and classic).
    _unregister()

    # Step 2: apply the appropriate deactivation mechanism.
    msix = find_msix_python_package() or find_python_appx_prog_ids()
    if msix:
        print()
        if had_user_choice:
            exts = " and ".join(e.extension for e in had_user_choice)
            print(f"[i] UserChoice for {exts} was set to pydblclick.PyFile.")
            print("    Windows may clear it automatically now that the ProgID is gone.")
            print("    If .py files still open with pydblclick, clear it manually:")
            print("      Parametres > Applications > Applications par defaut > .py")
            print("      and select a different application (e.g. Python).")
        else:
            print("[OK] pydblclick was not set as UserChoice -- no manual steps needed.")
    else:
        # Classic: reset HKLM ftype to plain Python launcher (requires admin).
        if not is_admin():
            print("\n  Admin rights required to reset HKLM ftype. Requesting elevation...")
            elevate_and_rerun()
            return

        py_exe = find_py_exe()
        if not py_exe:
            print("[!] No usable Python executable found.")
        else:
            command = f'"{py_exe}" "%1" %*'
            d2 = diagnose()
            prog_ids_done = set()
            print("\n  Resetting HKLM ftype:")
            for ext in d2.extensions:
                pid = ext.prog_id_effective
                if not pid or pid in prog_ids_done:
                    continue
                set_command(pid, command)
                print(f"    Set {pid} -> {command}")
                prog_ids_done.add(pid)

    print()
    print("Done. Run 'py -m winpyfiles diagnose' to verify.")

    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass  # Running non-interactively (e.g. piped input in tests)


if __name__ == "__main__":
    main()
