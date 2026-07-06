"""pydblclick — Python scripts pleasant to run by double-click on Windows.

Importing this package from a script is an optional, one-line directive for
distributable scripts:

    import pydblclick  # optional: pip install pydblclick -- or delete this line

If the script was double-clicked but is NOT being run through pydblclick
(pip-installed but not registered, or UserChoice taken over by another app),
the import activates a minimal fallback: uncaught exceptions stay readable
and the console pauses before closing, with a hint about `pydblclick register`.

In every other situation the import does strictly nothing:
- run from a console / a batch file (plain-Python behavior preserved),
- already wrapped by pydblclick (the full experience takes over),
- imported by pydblclick's own processes,
- non-Windows platforms.
"""


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

    # Minimal fallback: readable errors + pause, and a hint at the real thing
    import atexit
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


_maybe_enable_import_fallback()
