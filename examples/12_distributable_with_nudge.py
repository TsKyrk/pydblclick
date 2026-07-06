# --- pydblclick nudge (optional block, delete freely) ----------------------
# Double-clicked without pydblclick? Keep the window open (readable errors)
# and suggest installing it. Silent in a console or when pydblclick runs us.
import builtins as _b, os as _os, sys as _sys
if _os.name == "nt" and "PROMPT" not in _os.environ and not hasattr(_b, "pydblclick_customizations"):
    import atexit as _atexit, traceback as _tb
    def _pause():
        print("\n" + "-" * 64
              + "\nTip: install pydblclick for a friendlier double-click experience"
              + "\n(readable errors, pause menu, automatic dependencies):"
              + "\n    pip install pydblclick"
              + "\n    pydblclick register"
              + "\nhttps://pypi.org/project/pydblclick/\n" + "-" * 64)
        try:
            input("Press <Enter> to close...")
        except Exception:
            pass
    def _hook(t, v, tb):
        _tb.print_exception(t, v, tb)
        _atexit.unregister(_pause)
        _pause()
    _sys.excepthook = _hook
    _atexit.register(_pause)
# ----------------------------------------------------------------------------

# Your script starts here. It works everywhere:
# - in a console / called by a batch: the block above is silent
# - double-clicked WITH pydblclick installed: the block is inert,
#   pydblclick provides its full experience (menu, PEP 723 deps...)
# - double-clicked WITHOUT pydblclick: degraded but working -- the window
#   stays open, errors are readable, and the user learns about pydblclick
print("hello from a distributable one-filer")
