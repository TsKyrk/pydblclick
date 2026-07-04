"""pyexewrap — parent supervisor process.

Entry point: python -m pyexewrap <script.py> [args...]

The actual script execution happens in a child process (pyexewrap/_child.py)
launched with the same interpreter. The child runs the script with plain-Python
semantics, shows tracebacks and displays the pause prompt/menu itself.

The parent's only job is to guarantee that the console window never flashes
away, even when the child cannot pause by itself:
- the script closed stdin with exit()/quit() (input() becomes impossible),
- the interpreter died hard (os._exit, native crash, MemoryError...),
- the script was Ctrl+C'd to death.

Child -> parent protocol: the child writes "handled" to the file pointed to
by the PYEXEWRAP_STATUS_FILE env var once it has fulfilled its pause-or-no-pause
duty. If the marker is missing after the child exits, the parent pauses.
"""
import os
import signal
import subprocess
import sys
import tempfile

from pyexewrap._child import STATUS_HANDLED, User32


def _script_is_doubleclicked():
    return ('PROMPT' not in os.environ) or ('pyexewrap_simulate_doubleclick' in os.environ)


def _read_status(status_file):
    try:
        with open(status_file, encoding="UTF-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _fallback_pause(returncode):
    """Last-resort pause when the child could not display its own prompt."""
    # The console may still be hidden if a .pyw script crashed hard
    User32.show_window(User32.Const.SW_SHOWDEFAULT)
    if returncode != 0:
        print("\nThe script ended (exit code " + str(returncode) + ") without pyexewrap being able to pause.")
    try:
        input("Press <Enter> to Quit.\n")
    except (EOFError, ValueError, KeyboardInterrupt):
        pass  # stdin unusable in the parent too: nothing more we can do


def main():
    if len(sys.argv) < 2:
        print("Usage: pyexewrap <script.py> [args...]")
        print("       pyexewrap register    (set pyexewrap as the .py/.pyw double-click handler)")
        print("       pyexewrap unregister  (restore plain Python on double-click)")
        print("       pyexewrap diagnose    (inspect the Windows file association chain)")
        return 2

    # Management subcommands (a real script file named e.g. 'register' still wins)
    from pyexewrap._cli import COMMANDS
    if sys.argv[1] in COMMANDS and not os.path.exists(sys.argv[1]):
        from pyexewrap import _cli
        return _cli.main(sys.argv[1:])

    # The status file is how the child tells us "I already paused (or decided
    # a pause was not needed)". It survives any way the child may die.
    fd, status_file = tempfile.mkstemp(prefix="pyexewrap_status_")
    os.close(fd)
    env = dict(os.environ)
    env["PYEXEWRAP_STATUS_FILE"] = status_file

    cmd = [sys.executable, "-m", "pyexewrap._child"] + sys.argv[1:]

    # Ctrl+C is sent to every process attached to the console. The child is
    # the one that must handle it (KeyboardInterrupt in the script, then its
    # pause menu); the parent must survive to display the fallback pause.
    previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        result = subprocess.run(cmd, env=env)
    finally:
        signal.signal(signal.SIGINT, previous_handler)

    child_handled = _read_status(status_file) == STATUS_HANDLED
    try:
        os.remove(status_file)
    except OSError:
        pass

    if not child_handled and _script_is_doubleclicked():
        _fallback_pause(result.returncode)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
