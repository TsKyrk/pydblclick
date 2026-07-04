"""Management CLI of pyexewrap: register / unregister / diagnose.

`pyexewrap register` makes pyexewrap the default double-click handler for
.py/.pyw files through the standard Windows mechanism (ProgID + UserChoice),
which works with and without the MSIX Python Manager. This replaces the
legacy shebang approach (see ROADMAP.md).

The registered handler command points to the interpreter running this CLI
(sys.executable): by definition it can import pyexewrap, so no PYTHONPATH
setup is needed. Consolidates tools/ByDefaultActivation/activate.py and
disable.py into the package itself.
"""
import ctypes
import os
import sys
import winreg

from winpyfiles import diagnose, find_py_exe, find_python_appx_prog_ids, set_command
from winpyfiles._assoc import find_msix_python_package
from winpyfiles._registry import HKCU, write_value, notify_shell_assoc_changed
from winpyfiles._elevation import is_admin
from winpyfiles._backup import backup

PROG_ID = "pyexewrap.PyFile"
APP_KEY = "pyexewrap"
APP_DISPLAY_NAME = "pyexewrap"
APP_DESCRIPTION = "Python script launcher with pause prompt, error display and interactive menu"
EXTENSIONS = (".py", ".pyw")

COMMANDS = ("register", "unregister", "diagnose")


def _handler_command():
    """The shell open command to register for .py/.pyw files."""
    return '"' + sys.executable + '" -m pyexewrap "%1" %*'


def _elevate_and_rerun(subcommand):
    """Re-run this subcommand in an elevated console via UAC."""
    params = "-m pyexewrap " + subcommand + " --elevated"
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)


def _pause_if_elevated(elevated):
    """Keep the elevated console window open so its output can be read."""
    if elevated:
        try:
            input("\nPress Enter to close...")
        except EOFError:
            pass


def _delete_key_tree(hive, key_path):
    """Recursively delete a registry key and all its subkeys."""
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, 0)
                    _delete_key_tree(hive, key_path + "\\" + subkey_name)
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


def _register_prog_id(command):
    """Create the pyexewrap.PyFile ProgID and related registry entries."""
    icon = '"' + sys.executable + '",0'

    write_value(HKCU, "Software\\Classes\\" + PROG_ID, APP_DISPLAY_NAME)
    write_value(HKCU, "Software\\Classes\\" + PROG_ID + "\\DefaultIcon", icon)
    write_value(HKCU, "Software\\Classes\\" + PROG_ID + "\\shell\\open\\command", command)
    with winreg.CreateKeyEx(HKCU, "Software\\Classes\\" + PROG_ID + "\\shell\\open",
                            access=winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "FriendlyAppName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)

    write_value(HKCU, "Software\\Classes\\Applications\\" + APP_KEY + "\\shell\\open\\command", command)
    with winreg.CreateKeyEx(HKCU, "Software\\Classes\\Applications\\" + APP_KEY + "\\shell\\open",
                            access=winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "FriendlyAppName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)
    with winreg.CreateKeyEx(HKCU, "Software\\Classes\\Applications\\" + APP_KEY + "\\SupportedTypes",
                            access=winreg.KEY_WRITE) as k:
        for ext in EXTENSIONS:
            winreg.SetValueEx(k, ext, 0, winreg.REG_SZ, "")

    caps_path = "Software\\" + APP_KEY + "\\Capabilities"
    write_value(HKCU, caps_path, APP_DISPLAY_NAME, value_name="ApplicationName")
    write_value(HKCU, caps_path, APP_DESCRIPTION, value_name="ApplicationDescription")
    with winreg.CreateKeyEx(HKCU, caps_path + "\\FileAssociations",
                            access=winreg.KEY_WRITE) as k:
        for ext in EXTENSIONS:
            winreg.SetValueEx(k, ext, 0, winreg.REG_SZ, PROG_ID)
    with winreg.CreateKeyEx(HKCU, "Software\\RegisteredApplications",
                            access=winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, APP_KEY, 0, winreg.REG_SZ, caps_path)

    for ext in EXTENSIONS:
        with winreg.CreateKeyEx(HKCU, "Software\\Classes\\" + ext + "\\OpenWithProgids",
                                access=winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, PROG_ID, 0, winreg.REG_NONE, b"")

    notify_shell_assoc_changed()
    print("  [OK] " + PROG_ID + " ProgID registered")
    print("       command: " + command)


def _unregister_prog_id():
    """Remove the pyexewrap.PyFile ProgID and all related registry entries."""
    _delete_key_tree(HKCU, "Software\\Classes\\" + PROG_ID)
    _delete_key_tree(HKCU, "Software\\Classes\\Applications\\" + APP_KEY)
    _delete_value(HKCU, "Software\\RegisteredApplications", APP_KEY)
    _delete_key_tree(HKCU, "Software\\" + APP_KEY)
    for ext in EXTENSIONS:
        _delete_value(HKCU, "Software\\Classes\\" + ext + "\\OpenWithProgids", PROG_ID)
    notify_shell_assoc_changed()
    print("  [OK] " + PROG_ID + " ProgID removed.")


def cmd_register(elevated=False):
    saved = backup()
    print("Backup saved: " + str(saved) + "\n")

    command = _handler_command()

    # Step 1: register the ProgID (works for both MSIX and classic).
    _register_prog_id(command)

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
            print("[OK] pyexewrap already active for " + exts + " (UserChoice set).")
        else:
            print("[i] MSIX Python Manager detected.")
            print("    Step 1 is done: " + PROG_ID + " ProgID is registered.")
            print()
            print("    Step 2 (manual): set pyexewrap as the default via Windows.")
            print("      Right-click a .py file > Open with > Choose another app")
            print("      > pyexewrap > Always use this app")
            print()
            print("    Or: Settings > Apps > Default apps > .py and select pyexewrap.")
    else:
        # Classic: update HKLM ftype (requires admin, auto-elevate).
        if not is_admin():
            print("\n  Admin rights required to update HKLM ftype. Requesting elevation...")
            _elevate_and_rerun("register")
            return 0

        d = diagnose()
        prog_ids_done = set()
        print("\n  Updating HKLM ftype:")
        for ext in d.extensions:
            pid = ext.prog_id_effective
            if not pid or pid in prog_ids_done:
                continue
            set_command(pid, command)
            print("    Set " + pid + " -> " + command)
            prog_ids_done.add(pid)

    print()
    print("Done. Run 'pyexewrap diagnose' to verify.")
    _pause_if_elevated(elevated)
    return 0


def cmd_unregister(elevated=False):
    # Capture UserChoice state before making any changes.
    d = diagnose()
    had_user_choice = [e for e in d.extensions if e.user_choice == PROG_ID]

    saved = backup()
    print("Backup saved: " + str(saved) + "\n")

    # Step 1: remove the ProgID (works for both MSIX and classic).
    _unregister_prog_id()

    # Step 2: apply the appropriate deactivation mechanism.
    msix = find_msix_python_package() or find_python_appx_prog_ids()
    if msix:
        print()
        if had_user_choice:
            exts = " and ".join(e.extension for e in had_user_choice)
            print("[i] UserChoice for " + exts + " was set to " + PROG_ID + ".")
            print("    Windows may clear it automatically now that the ProgID is gone.")
            print("    If .py files still open with pyexewrap, clear it manually:")
            print("      Settings > Apps > Default apps > .py")
            print("      and select a different application (e.g. Python).")
        else:
            print("[OK] pyexewrap was not set as UserChoice -- no manual steps needed.")
    else:
        # Classic: reset HKLM ftype to plain Python launcher (requires admin).
        if not is_admin():
            print("\n  Admin rights required to reset HKLM ftype. Requesting elevation...")
            _elevate_and_rerun("unregister")
            return 0

        py_exe = find_py_exe()
        if not py_exe:
            print("[!] No usable Python executable found.")
        else:
            command = '"' + py_exe + '" "%1" %*'
            d2 = diagnose()
            prog_ids_done = set()
            print("\n  Resetting HKLM ftype:")
            for ext in d2.extensions:
                pid = ext.prog_id_effective
                if not pid or pid in prog_ids_done:
                    continue
                set_command(pid, command)
                print("    Set " + pid + " -> " + command)
                prog_ids_done.add(pid)

    print()
    print("Done. Run 'pyexewrap diagnose' to verify.")
    _pause_if_elevated(elevated)
    return 0


def cmd_diagnose():
    from winpyfiles.__main__ import cmd_diagnose as winpyfiles_diagnose
    winpyfiles_diagnose()
    return 0


def main(argv):
    """Dispatch a management subcommand. argv starts at the subcommand name."""
    subcommand = argv[0]
    elevated = "--elevated" in argv[1:]
    if subcommand == "register":
        return cmd_register(elevated)
    if subcommand == "unregister":
        return cmd_unregister(elevated)
    if subcommand == "diagnose":
        return cmd_diagnose()
    print("Unknown command: " + subcommand)
    return 2
