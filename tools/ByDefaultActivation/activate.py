#!/usr/bin/env python
"""Enable pydblclick as the default handler for .py and .pyw double-clicks.

Automatically detects the Python installation type and applies the right configuration:

  - MSIX Python Manager (Microsoft Store / Python Install Manager):
      Registers the pydblclick.PyFile ProgID (so pydblclick appears as a choice),
      then prompts you to set it as the default via Windows Settings.
      This manual step is required because the MSIX App Model bypasses all
      registry ftype changes -- only UserChoice (set via the UI) takes effect.

  - Classic Python (no MSIX, python-x.x.x-amd64.exe installer):
      Registers the pydblclick.PyFile ProgID and updates the HKLM ftype registry
      (requires admin -- a UAC prompt will appear automatically).
      pydblclick becomes the default immediately, no UI interaction needed.

Backs up the current registry state before any change.
"""
import sys
import os
import winreg

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_this_dir = os.path.dirname(os.path.abspath(__file__))
for _p in (_repo_root, _this_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from winpyfiles import diagnose, find_py_exe, find_python_appx_prog_ids, set_command
from winpyfiles._assoc import find_msix_python_package
from winpyfiles._registry import HKCU, write_value, notify_shell_assoc_changed
from winpyfiles._elevation import is_admin, elevate_and_rerun
from winpyfiles._backup import backup

PROG_ID = "pydblclick.PyFile"
APP_KEY = "pydblclick"
APP_DISPLAY_NAME = "pydblclick"
APP_DESCRIPTION = "Python script launcher with automatic virtual environment activation"
EXTENSIONS = (".py", ".pyw")


def _register(py_exe):
    """Create the pydblclick.PyFile ProgID and related registry entries."""
    command = f'"{py_exe}" -m pydblclick "%1" %*'
    icon = f'"{py_exe}",0'

    write_value(HKCU, f"Software\\Classes\\{PROG_ID}", APP_DISPLAY_NAME)
    write_value(HKCU, f"Software\\Classes\\{PROG_ID}\\DefaultIcon", icon)
    write_value(HKCU, f"Software\\Classes\\{PROG_ID}\\shell\\open\\command", command)
    with winreg.CreateKeyEx(HKCU, f"Software\\Classes\\{PROG_ID}\\shell\\open",
                            access=winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "FriendlyAppName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)

    write_value(HKCU, f"Software\\Classes\\Applications\\{APP_KEY}\\shell\\open\\command", command)
    with winreg.CreateKeyEx(HKCU, f"Software\\Classes\\Applications\\{APP_KEY}\\shell\\open",
                            access=winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "FriendlyAppName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)
    with winreg.CreateKeyEx(HKCU, f"Software\\Classes\\Applications\\{APP_KEY}\\SupportedTypes",
                            access=winreg.KEY_WRITE) as k:
        for ext in EXTENSIONS:
            winreg.SetValueEx(k, ext, 0, winreg.REG_SZ, "")

    caps_path = f"Software\\{APP_KEY}\\Capabilities"
    write_value(HKCU, caps_path, APP_DISPLAY_NAME, value_name="ApplicationName")
    write_value(HKCU, caps_path, APP_DESCRIPTION, value_name="ApplicationDescription")
    with winreg.CreateKeyEx(HKCU, f"{caps_path}\\FileAssociations",
                            access=winreg.KEY_WRITE) as k:
        for ext in EXTENSIONS:
            winreg.SetValueEx(k, ext, 0, winreg.REG_SZ, PROG_ID)
    with winreg.CreateKeyEx(HKCU, "Software\\RegisteredApplications",
                            access=winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, APP_KEY, 0, winreg.REG_SZ, caps_path)

    for ext in EXTENSIONS:
        with winreg.CreateKeyEx(HKCU, f"Software\\Classes\\{ext}\\OpenWithProgids",
                                access=winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, PROG_ID, 0, winreg.REG_NONE, b"")

    notify_shell_assoc_changed()
    print(f"  [OK] pydblclick.PyFile ProgID registered (command: {command})")


def main():
    saved = backup()
    print(f"Backup saved: {saved}\n")

    py_exe = find_py_exe()
    if not py_exe:
        print("[!] No usable Python executable found. Is Python installed?")
        sys.exit(1)

    # Step 1: register the ProgID (works for both MSIX and classic).
    _register(py_exe)

    # Step 2: apply the appropriate activation mechanism.
    msix = find_msix_python_package() or find_python_appx_prog_ids()
    if msix:
        # MSIX: UserChoice is the only working mechanism.
        # It cannot be set programmatically (protected by a hash) -- guide the user.
        print()
        d = diagnose()
        already_active = [e for e in d.extensions if e.user_choice == PROG_ID]
        if already_active:
            exts = " and ".join(e.extension for e in already_active)
            print(f"[OK] ByDefaultActivation already active for {exts} (UserChoice set).")
        else:
            print("[i] MSIX Python Manager detected.")
            print("    Step 1 is done: pydblclick.PyFile ProgID is registered.")
            print()
            print("    Step 2 (manual): set pydblclick as the default via Windows.")
            print("      Right-click a .py file > Ouvrir avec > Choisir une autre application")
            print("      > pydblclick > Toujours utiliser cette application")
            print()
            print("    Or: Parametres > Applications > Applications par defaut > .py")
            print("        and select pydblclick.")
    else:
        # Classic: update HKLM ftype (requires admin, auto-elevate).
        if not is_admin():
            print("\n  Admin rights required to update HKLM ftype. Requesting elevation...")
            elevate_and_rerun()
            return

        command = f'"{py_exe}" -m pydblclick "%1" %*'
        d = diagnose()
        prog_ids_done = set()
        print("\n  Updating HKLM ftype:")
        for ext in d.extensions:
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
