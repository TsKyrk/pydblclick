"""pydblclick — Python scripts pleasant to run by double-click on Windows.

Importing this package from a script is an optional, one-line directive for
distributable scripts:

    import pydblclick  # optional: pip install pydblclick -- or delete this line

Keep it on the FIRST line of the script. If the script was double-clicked but is
NOT already being run through pydblclick (pip-installed but not registered, or
UserChoice taken over by another app), the import **re-launches the script
through the real pydblclick** (`python -m pydblclick <script>`) and exits with
its code. The recipient gets the full experience — pause menu, restart, clean
tracebacks, PEP 723 dependency resolution — with no registry changes. This works
for `.pyw` too: a double-clicked `.pyw` (detected by its Explorer launcher, since
pythonw has no console/stdin) is relaunched windowless, and a console appears
only if the script raises.

Double-click detection requires the process to descend from explorer.exe with
only known launcher hops in between (py.exe, python.exe, pythonw.exe, the MSIX
Python Manager) -- for `.py` this is checked in addition to the interactive-tty
signal, so `python script.py` run from a shell (including PowerShell, which
unlike cmd.exe does not set `PROMPT`) is never mistaken for a double-click.

If that relaunch cannot even start, a minimal in-process fallback takes over
instead (readable errors + a pause, with a hint about `pydblclick register`).

In every other situation the import does strictly nothing:
- run from a console / a batch file (plain-Python behavior preserved),
- already wrapped by pydblclick (the full experience takes over),
- imported by pydblclick's own processes,
- non-Windows platforms.
"""


def _signed32(code):
    """Convert a Windows exit code to the signed 32-bit range for SystemExit.

    Mirrors pydblclick._child.signed32; inlined so this module stays free of
    pydblclick submodule imports on the common (inert) import path.
    """
    if isinstance(code, int) and code >= 2 ** 31:
        return code - 2 ** 32
    return code


def _install_minimal_fallback():
    """Last-resort, in-process fallback: readable errors + a pause on exit.

    Used only when the bootstrap relaunch is disabled or cannot start.
    """
    import atexit
    import sys
    import traceback

    def _pause():
        print("\n[pydblclick] minimal mode -- this script was double-clicked but not launched")
        print("             through pydblclick. For the full experience (pause menu,")
        print("             PEP 723 dependencies): pydblclick register")
        try:
            input("Press <Enter> to close...")
        except Exception:
            pass

    def _fallback_excepthook(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb)
        atexit.unregister(_pause)
        _pause()

    sys.excepthook = _fallback_excepthook
    atexit.register(_pause)
    return True


def _walk_ancestry_for_explorer(pid, parent_of, name_of, max_depth=8):
    """Pure ancestry walk used by `_launched_by_explorer`: True if `pid`'s
    ancestry reaches explorer.exe before any non-launcher process, tolerating
    only known launcher hops (see LAUNCHERS in `_launched_by_explorer`).
    Factored out of the ctypes snapshot code so it is testable with plain
    dicts, no real process table required."""
    for _ in range(max_depth):
        parent = parent_of.get(pid)
        if not parent or parent == pid:
            break
        pname = name_of.get(parent, "")
        if pname == "explorer.exe":
            return True
        if pname not in LAUNCHERS:
            return False
        pid = parent
    return False


LAUNCHERS = {
    "py.exe", "pyw.exe", "python.exe", "pythonw.exe", "python3.exe",
    # MSIX Python Manager (https://github.com/python/pymanager) hops: its own
    # launcher shims and per-install venv launchers. See
    # pydblclick/winpyfiles/_assoc.py::find_msix_python_package() for the
    # matching registry/package detection -- update both if pymanager renames
    # its executables.
    "pymanager.exe", "pymanager-gui.exe", "venvlauncher.exe", "venvwlauncher.exe",
}


def _launched_by_explorer(max_depth=8):
    """True if this process was started by a GUI double-click: walking up the
    ancestry we reach explorer.exe *before* any non-launcher process. Only
    known launcher hops (LAUNCHERS: py.exe, python.exe, pythonw.exe, the MSIX
    Python Manager) are stepped over; any other ancestor -- a shell/terminal
    (cmd, powershell, pwsh, conhost, Windows Terminal, an IDE's run button, an
    unknown GUI launcher) -- means False. This is an allowlist, not a
    blocklist: an unrecognized parent is treated as NOT a double-click, which
    keeps the feature out of `.pyw` runs from a terminal (whose window is
    itself an Explorer descendant) and out of GUI apps that merely happen to
    have Explorer further up their ancestry. The tradeoff is that launching
    from an unlisted GUI tool (e.g. an IDE's "Run" button) no longer counts as
    a double-click either -- inertness is the safe default there, since it
    just falls back to plain Python behavior. Automation (services, scheduled
    tasks) has svchost/taskeng ancestry and reaches neither marker -> False.
    Used to detect a `.pyw` double-click, which has no console/stdin to key
    on. Best-effort: any failure returns False (stay inert)."""
    import os
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        k32.Process32First.restype = wintypes.BOOL
        k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        k32.Process32Next.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL

        snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == INVALID_HANDLE:
            return False
        parent_of = {}
        name_of = {}
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if not k32.Process32First(snapshot, ctypes.byref(entry)):
                return False
            while True:
                pid = entry.th32ProcessID
                parent_of[pid] = entry.th32ParentProcessID
                name_of[pid] = entry.szExeFile.decode("ascii", "replace").lower()
                if not k32.Process32Next(snapshot, ctypes.byref(entry)):
                    break
        finally:
            k32.CloseHandle(snapshot)
    except Exception:
        return False

    return _walk_ancestry_for_explorer(os.getpid(), parent_of, name_of, max_depth)


def _bootstrap_through_pydblclick(script, script_args):
    """Re-run the script through `python -m pydblclick`; return its exit code.

    The current interpreter is reused: for a `.py` double-click that is
    python.exe (console); for a `.pyw` double-click it is pythonw.exe, so the
    relaunched supervisor is windowless and its child creates a console only if
    the script raises. Raises if the subprocess cannot even be started (caller
    falls back to the minimal in-process hooks).
    """
    import signal
    import subprocess
    import sys

    cmd = [sys.executable, "-m", "pydblclick", script, *script_args]

    # Ctrl+C is delivered to every process on the console. The child chain must
    # own it (KeyboardInterrupt in the script, then the pause menu); this
    # bootstrap process must survive to propagate the exit code. Same reasoning
    # as the supervisor in pydblclick/__main__.py.
    previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        result = subprocess.run(cmd)
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    return _signed32(result.returncode)


def _maybe_enable_import_fallback():
    import os
    import sys

    if os.name != "nt":
        return False

    # Already wrapped by the pydblclick child engine
    import builtins
    if hasattr(builtins, "pydblclick_customizations"):
        return False

    # Double-click detection (same heuristic as the engine)
    simulated = ("pydblclick_simulate_doubleclick" in os.environ
                 or "pyexewrap_simulate_doubleclick" in os.environ)
    if "PROMPT" in os.environ and not simulated:
        return False  # console / batch context
    if not simulated:
        # A real .py double-click gives the process an interactive console
        # (stdin is a tty) -- but so does `python script.py` run interactively
        # from PowerShell (pwsh/powershell.exe do not set PROMPT either, and
        # their stdin is a tty too), so a tty check alone false-positives
        # there. Requiring _launched_by_explorer() too closes that gap. A .pyw
        # runs under pythonw with no console/stdin at all, so for .pyw the
        # double-click is detected by its launcher ancestry exclusively.
        # Everything else -- piped/CI, pythonw automation -- stays inert.
        script_ext = os.path.splitext(sys.argv[0])[1].lower() if sys.argv else ""
        try:
            stdin_is_tty = sys.stdin is not None and sys.stdin.isatty()
        except Exception:
            stdin_is_tty = False
        if script_ext == ".pyw":
            if not _launched_by_explorer():
                return False
        else:
            if not (stdin_is_tty and _launched_by_explorer()):
                return False

    # Only activate when a *user file* imported us. During pydblclick's own
    # startup (python -m pydblclick / -m pydblclick._child) the import stack
    # contains nothing but interpreter machinery (frozen importlib, runpy).
    package_dir = os.path.dirname(os.path.abspath(__file__))
    frame = sys._getframe()
    imported_by_user_file = False
    while frame is not None:
        filename = frame.f_code.co_filename
        if (not filename.startswith("<")
                and not filename.endswith("runpy.py")
                and not os.path.abspath(filename).startswith(package_dir)):
            imported_by_user_file = True
            break
        frame = frame.f_back
    if not imported_by_user_file:
        return False

    # Conditions met: a double-clicked, unregistered, user-imported script.
    script = sys.argv[0] if sys.argv else ""

    # Respect the per-script opt-out (`# pydblclick: off`): pydblclick steps
    # aside entirely -- the script keeps running as plain Python in this very
    # process (the pre-pydblclick experience). This is also what stops an
    # infinite relaunch: the opt-out path runs the script with plain Python,
    # which re-imports pydblclick with no `builtins` marker to break re-entry.
    if script and os.path.isfile(script):
        try:
            from pydblclick import _script_meta
            if _script_meta.has_opt_out(_script_meta.read_script_text(script)):
                return False
        except Exception:
            pass

    # Escape hatch / last resort: honor an explicit opt-out of the relaunch,
    # or a missing/invalid script path.
    forced_minimal = os.environ.get("PYDBLCLICK_NO_BOOTSTRAP", "") not in ("", "0")
    if forced_minimal or not script or not os.path.isfile(script):
        return _install_minimal_fallback()

    # Bootstrap: re-run the script through the real pydblclick and exit with
    # its code. Because the directive is on the first line, nothing else in
    # this original process has run yet, so raising SystemExit here is clean.
    try:
        exit_code = _bootstrap_through_pydblclick(script, sys.argv[1:])
    except Exception:
        return _install_minimal_fallback()
    raise SystemExit(exit_code)


_maybe_enable_import_fallback()
