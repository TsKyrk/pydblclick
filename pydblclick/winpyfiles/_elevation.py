"""UAC elevation helper for Windows."""
import ctypes
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_and_rerun() -> None:
    """Re-launch the current script with admin rights via UAC, then exit."""
    args = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
    sys.exit(0)


def require_admin() -> None:
    """Abort with a clear message if not running as admin."""
    if not is_admin():
        print("[!] This operation requires administrator rights.")
        print("    Re-run as admin or use: py -m pydblclick.winpyfiles <command> --elevate")
        sys.exit(1)
