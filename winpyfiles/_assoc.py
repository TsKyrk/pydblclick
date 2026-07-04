"""Windows file association management for Python scripts."""
import os
import shutil
import winreg
from dataclasses import dataclass
from typing import Dict, List, Optional

from ._registry import HKCR, HKCU, HKLM, read_value, write_value, notify_shell_assoc_changed

EXTENSIONS = (".py", ".pyw")


@dataclass
class ExtensionInfo:
    extension: str
    prog_id_hkcu: Optional[str]       # HKCU\Software\Classes\<ext>  (user override)
    prog_id_hklm: Optional[str]       # HKLM\SOFTWARE\Classes\<ext>  (system)
    prog_id_effective: Optional[str]  # HKCR\<ext>                   (merged, what Windows uses)
    user_choice: Optional[str] = None  # HKCU\...\Explorer\FileExts\<ext>\UserChoice  (Windows 8+, Explorer priority)


@dataclass
class ProgIdInfo:
    prog_id: str
    command_hkcu: Optional[str]      # HKCU\Software\Classes\<id>\shell\open\command
    command_hklm: Optional[str]      # HKLM\SOFTWARE\Classes\<id>\shell\open\command
    command_effective: Optional[str]  # HKCR\<id>\shell\open\command  (what Windows uses)


@dataclass
class AssocDiagnosis:
    extensions: List[ExtensionInfo]
    prog_ids: Dict[str, ProgIdInfo]
    msix_handlers: Dict[str, str]   # AppX ProgID -> shell open command (from HKCU)
    msix_package: Optional[str]     # Path to PythonSoftwareFoundation.PythonManager install dir, or None


def diagnose() -> AssocDiagnosis:
    """Read the current Windows file associations for Python extensions."""
    ext_infos: List[ExtensionInfo] = []
    all_prog_ids: set = set()

    for ext in EXTENSIONS:
        prog_id_hkcu = read_value(HKCU, f"Software\\Classes\\{ext}")
        prog_id_hklm = read_value(HKLM, f"SOFTWARE\\Classes\\{ext}")
        prog_id_effective = read_value(HKCR, ext)
        user_choice = read_value(
            HKCU,
            f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\{ext}\\UserChoice",
            value_name="ProgId",
        )

        ext_infos.append(ExtensionInfo(
            extension=ext,
            prog_id_hkcu=prog_id_hkcu,
            prog_id_hklm=prog_id_hklm,
            prog_id_effective=prog_id_effective,
            user_choice=user_choice,
        ))

        for pid in (prog_id_hkcu, prog_id_hklm, prog_id_effective):
            if pid:
                all_prog_ids.add(pid)

    prog_id_infos: Dict[str, ProgIdInfo] = {}
    for prog_id in sorted(all_prog_ids):
        cmd_subkey = f"{prog_id}\\shell\\open\\command"
        prog_id_infos[prog_id] = ProgIdInfo(
            prog_id=prog_id,
            command_hkcu=read_value(HKCU, f"Software\\Classes\\{cmd_subkey}"),
            command_hklm=read_value(HKLM, f"SOFTWARE\\Classes\\{cmd_subkey}"),
            command_effective=read_value(HKCR, cmd_subkey),
        )

    return AssocDiagnosis(
        extensions=ext_infos,
        prog_ids=prog_id_infos,
        msix_handlers=find_python_appx_prog_ids(),
        msix_package=find_msix_python_package(),
    )


def _is_app_execution_alias(path: str) -> bool:
    """Return True if the path is a Windows App Execution Alias stub (not a real exe).

    Windows 10/11 creates lightweight stub executables under
    C:\\Users\\<user>\\AppData\\Local\\Microsoft\\WindowsApps\\ for apps installed
    via the Microsoft Store or MSIX packages (including modern Python installs).

    These stubs work fine when invoked interactively (e.g. typing "py" in a terminal),
    but FAIL SILENTLY when Windows invokes them from an ftype/shell\\open\\command
    registry entry. Explorer uses a different execution context that does not
    activate the App Execution Alias infrastructure.

    Concretely: shutil.which("py") may return the WindowsApps stub, but writing
    that path into the registry ftype command results in a no-op when double-clicking
    a .py file -- the script runs via a fallback mechanism that bypasses pydblclick.
    """
    return "\\WindowsApps\\" in path


def find_py_exe() -> Optional[str]:
    """Return a usable Python executable for ftype/registry shell commands.

    Tries, in order:
      1. py.exe launcher via PATH -- but only if it is a real executable,
         not a Windows App Execution Alias stub (see _is_app_execution_alias).
      2. C:\\Windows\\py.exe -- the classic location from the Python installer.
      3. sys.executable -- the interpreter currently running this code, which
         is always a real python.exe (never an alias stub).

    The returned path is safe to embed in a registry shell\\open\\command string.
    """
    # Try the py launcher first, but skip App Execution Aliases.
    found = shutil.which("py")
    if found and not _is_app_execution_alias(found):
        return found

    # Known real location from classic Python installer.
    default = r"C:\Windows\py.exe"
    if os.path.isfile(default):
        return default

    # Fall back to the current interpreter (always a real python.exe).
    import sys
    if os.path.isfile(sys.executable) and not _is_app_execution_alias(sys.executable):
        return sys.executable

    return None


def find_msix_python_package() -> Optional[str]:
    """Return the install directory of the MSIX Python Manager package, or None.

    Detects the presence of PythonSoftwareFoundation.PythonManager by looking
    for its directory under C:\\Program Files\\WindowsApps\\. This is a more
    robust signal than the AppX ProgID heuristic in find_python_appx_prog_ids(),
    because it does not rely on the 'AppX' naming convention that Windows uses
    internally and could theoretically change in future OS versions.

    # KNOWN COMPATIBILITY RISK: python/pymanager (https://github.com/python/pymanager)
    # ---------------------------------------------------------------------------------
    # The PythonSoftwareFoundation.PythonManager MSIX package intercepts .py/.pyw
    # double-clicks through Windows App Model activation (declared in appxmanifest.xml,
    # Application Id="Python.Exe", Category="windows.fileTypeAssociation"). This
    # mechanism reads AppxManifest.xml directly and bypasses ALL registry-based
    # ftype/assoc/shell\\open\\command settings, making winpyfiles' set_command()
    # effectively a no-op for double-click scenarios.
    #
    # Future evolutions of python/pymanager to watch:
    #   - New file type associations (.py3, etc.) added to appxmanifest.xml
    #   - Changes to AppX ProgID naming that would break find_python_appx_prog_ids()
    #   - Removal/rename of the PythonSoftwareFoundation.PythonManager package
    #     (would require updating the glob pattern below)
    #
    # If winpyfiles stops detecting MSIX correctly and diagnose() no longer warns
    # about the MSIX block, check this function first.
    """
    # Try filesystem glob first (fast, but C:\Program Files\WindowsApps is
    # protected and unreadable without admin rights -- glob silently returns []).
    import glob
    pattern = R"C:\Program Files\WindowsApps\PythonSoftwareFoundation.PythonManager*"
    matches = glob.glob(pattern)
    if matches:
        return matches[0]

    # Fallback: query via PowerShell Get-AppxPackage (works without admin rights).
    try:
        import subprocess
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "(Get-AppxPackage -Name 'PythonSoftwareFoundation.PythonManager').InstallLocation",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        location = result.stdout.strip()
        if location:
            return location
    except Exception:
        pass

    return None


def find_python_appx_prog_ids() -> Dict[str, str]:
    """Return AppX ProgIDs in HKCU\\Software\\Classes that handle Python files.

    On Windows 10/11, when the Python Launcher (or Python Manager) is installed
    via the Microsoft Store or as an MSIX package, it registers file type handlers
    under ProgIDs named AppX<hash> in HKCU\\Software\\Classes. These handlers
    take priority over the traditional HKLM\\SOFTWARE\\Classes\\Python.File
    ftype mechanism -- Windows uses the AppX handler directly for double-clicks,
    completely bypassing any ftype/assoc registry settings.

    This function enumerates HKCU\\Software\\Classes for AppX ProgIDs whose
    shell\\open\\command references a Python executable, so callers can modify
    or inspect them.

    Returns a dict mapping ProgID -> current shell open command string.
    """
    result: Dict[str, str] = {}
    try:
        with winreg.OpenKey(HKCU, "Software\\Classes") as classes_key:
            i = 0
            while True:
                try:
                    prog_id = winreg.EnumKey(classes_key, i)
                    if prog_id.startswith("AppX"):
                        cmd = read_value(HKCU, f"Software\\Classes\\{prog_id}\\shell\\open\\command")
                        if cmd and "python" in cmd.lower():
                            result[prog_id] = cmd
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return result


def set_command(prog_id: str, command: str, hive: int = HKLM) -> None:
    """Write the shell open command for a ProgID into the given registry hive.

    Requires administrator rights when hive is HKLM (the default).
    Notifies Explorer of the change so it drops its cached association.
    """
    prefix = "SOFTWARE\\Classes" if hive == HKLM else "Software\\Classes"
    write_value(hive, f"{prefix}\\{prog_id}\\shell\\open\\command", command)
    notify_shell_assoc_changed()


def set_prog_id(extension: str, prog_id: str, hive: int = HKLM) -> None:
    """Map a file extension to a ProgID in the given registry hive.

    Requires administrator rights when hive is HKLM (the default).
    Notifies Explorer of the change so it drops its cached association.
    """
    prefix = "SOFTWARE\\Classes" if hive == HKLM else "Software\\Classes"
    write_value(hive, f"{prefix}\\{extension}", prog_id)
    notify_shell_assoc_changed()
