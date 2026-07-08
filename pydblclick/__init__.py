"""pydblclick — Python scripts pleasant to run by double-click on Windows.

Importing this package from a script is an optional, one-line directive for
distributable scripts:

    import pydblclick  # optional: pip install pydblclick -- or delete this line

Keep it on the FIRST line of the script. If the script was double-clicked but is
NOT already being run through pydblclick (pip-installed but not registered, or
UserChoice taken over by another app), the import **re-launches the script
through the real pydblclick** (`python -m pydblclick <script>`) and exits with
its code. The recipient gets the full experience — pause menu, restart, clean
tracebacks, PEP 723 dependency resolution — with no registry changes.

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


def _bootstrap_through_pydblclick(script, script_args):
    """Re-run the script through `python -m pydblclick`; return its exit code.

    Raises if the subprocess cannot even be started (caller falls back to the
    minimal in-process hooks).
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
        # A real double-click gives the process an interactive console; this
        # also keeps the fallback out of pythonw and piped/CI contexts.
        try:
            if sys.stdin is None or not sys.stdin.isatty():
                return False
        except Exception:
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
