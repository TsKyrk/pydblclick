"""
Adds the root of this repository to the system-wide PYTHONPATH environment variable,
and drops a pydblclick.pth file in the system Python's site-packages directory.

Usage: double-click this file, or run it from any terminal:
    python add_to_pythonpath.py

Why two mechanisms?

  1. PYTHONPATH (registry, HKLM):
       Works for interactive terminals (cmd, PowerShell, VS Code).
       Broadcasts WM_SETTINGCHANGE so the change takes effect in new terminals
       without requiring a reboot.

  2. pydblclick.pth in site-packages:
       Processed by Python's `site` module at interpreter startup, before any
       environment variable is read. This is the only mechanism that works when
       Python is launched by the MSIX App Model (e.g. double-click via the
       PythonSoftwareFoundation.PythonManager Store package), which activates
       processes in an isolated environment that does NOT inherit PYTHONPATH.
       Without this file, the shebang approach (#!/usr/bin/env python -m pydblclick)
       fails silently under MSIX double-click even though it works in a terminal.

Note: why not `pip install -e .` ?
    pydblclick is invoked by py.exe via a shebang line. py.exe uses the system Python,
    not a virtual environment. An editable install inside a venv would therefore not
    be visible to py.exe when launching scripts from the file explorer.
"""

import os
import subprocess
import sys
import winreg
import ctypes
from pathlib import Path


def _ensure_admin() -> None:
    """Re-launches the script with admin privileges if not already elevated."""
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False

    if not is_admin:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()


def add_to_pythonpath(path: str) -> bool:
    """Add 'path' to the system-wide PYTHONPATH environment variable.

    Returns True if a change was made, False if already configured.
    """
    reg_key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        R"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    )

    try:
        current_value, _ = winreg.QueryValueEx(reg_key, "PYTHONPATH")
    except FileNotFoundError:
        current_value = ""

    existing_paths = set(p.strip("\\").lower() for p in current_value.split(";") if p)

    if path.strip("\\").lower() in existing_paths:
        winreg.CloseKey(reg_key)
        return False

    new_value = f"{current_value};{path}" if current_value else path
    winreg.SetValueEx(reg_key, "PYTHONPATH", 0, winreg.REG_EXPAND_SZ, new_value)
    winreg.CloseKey(reg_key)

    # Broadcast the change so terminals pick it up without reboot
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 2, 5000, None
    )

    print(f"PYTHONPATH updated: {new_value}")
    return True


def add_pth_file(repo_root: str) -> bool:
    """Drop a pydblclick.pth file in the system Python's site-packages.

    .pth files are processed by Python's site module at interpreter startup,
    before any environment variable lookup. This makes pydblclick importable
    even when PYTHONPATH is not inherited (e.g. MSIX App Model activation).

    Returns True if a change was made, False if already configured.
    Prints a warning and returns False if py.exe is not found.
    """
    result = subprocess.run(
        ["py", "-c", "import site; print(site.getsitepackages()[0])"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("[!] Could not determine site-packages location via py.exe.")
        print("    The .pth file was NOT created. The shebang approach may be")
        print("    unreliable under MSIX. Run this script again after installing py.exe.")
        return False

    site_packages = Path(result.stdout.strip())
    pth_file = site_packages / "pydblclick.pth"

    if pth_file.exists() and pth_file.read_text(encoding="utf-8").strip() == repo_root.strip():
        return False

    pth_file.write_text(repo_root, encoding="utf-8")
    print(f"Created {pth_file}")
    return True


if __name__ == "__main__":
    _ensure_admin()
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    pythonpath_done = add_to_pythonpath(parent_dir)
    pth_done = add_pth_file(parent_dir)
    if not pythonpath_done and not pth_done:
        print("Already configured. Nothing to do.")
    else:
        print("pydblclick is now findable in all Python execution contexts (including MSIX).")
    input("Press a key...")
