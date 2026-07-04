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

Before launching, the parent inspects the script's source (pyexewrap/_script_meta.py):
- `# pyexewrap: off` -> run with plain Python, no wrapping at all;
- PEP 723 `# /// script` block -> run the child through `uv run` so the
  declared dependencies are resolved in an ephemeral environment.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile

from pyexewrap import _script_meta
from pyexewrap._child import STATUS_HANDLED, User32, ensure_console, have_console

UV_INSTALL_URL = "https://docs.astral.sh/uv/getting-started/installation/"


def _console_python():
    """The console interpreter (python.exe) even when running under pythonw.exe.

    The parent of a windowless .pyw launch is pythonw.exe, but the child engine
    needs a standard interpreter with working standard streams.
    """
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        candidate = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(candidate):
            return candidate
    return exe


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
    if sys.stdout is None or sys.stdin is None:
        # Windowless parent (pythonw.exe): no usable stdio at all -- create a
        # console on the spot so the failure is visible.
        if not ensure_console(title="pyexewrap"):
            return
    elif have_console():
        # The console may still be hidden if a .pyw script crashed hard
        User32.show_window(User32.Const.SW_SHOWDEFAULT)
    if returncode != 0:
        print("\nThe script ended (exit code " + str(returncode) + ") without pyexewrap being able to pause.")
    try:
        input("Press <Enter> to Quit.\n")
    except (EOFError, ValueError, KeyboardInterrupt):
        pass  # stdin unusable in the parent too: nothing more we can do


def _plain_python_for(script):
    """The interpreter for unwrapped execution (pythonw for .pyw when available)."""
    if os.path.splitext(script)[1].lower() == ".pyw":
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            return pythonw
    return sys.executable


def _find_uv():
    """Locate the uv executable (PYEXEWRAP_UV overrides PATH, for tests)."""
    return os.environ.get("PYEXEWRAP_UV") or shutil.which("uv")


def _build_child_command(script, script_args, env):
    """Build the child command line, delegating to `uv run` for PEP 723 scripts."""
    default_cmd = [_console_python(), "-m", "pyexewrap._child", script] + script_args

    meta = _script_meta.parse_pep723(_script_meta.read_script_text(script))
    if meta is None:
        return default_cmd

    uv = _find_uv()
    if not uv:
        print("[pyexewrap] This script declares PEP 723 dependencies, but 'uv' was not found on PATH.")
        print("            Install uv to run it with its dependencies resolved automatically:")
        print("            " + UV_INSTALL_URL)
        print("            Running with plain Python instead...\n")
        return default_cmd

    cmd = [uv, "run", "--no-project"]
    if meta["requires-python"]:
        cmd += ["--python", meta["requires-python"]]
    for dep in meta["dependencies"]:
        cmd += ["--with", dep]
    cmd += ["python", "-m", "pyexewrap._child", script] + script_args

    # pyexewrap itself must be importable inside uv's ephemeral environment
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = package_parent + (os.pathsep + existing if existing else "")
    return cmd


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

    script, script_args = sys.argv[1], sys.argv[2:]

    # Per-script opt-out: run with plain Python, no wrapping, no pause
    if _script_meta.has_opt_out(_script_meta.read_script_text(script)):
        result = subprocess.run([_plain_python_for(script), script] + script_args)
        return result.returncode

    # The status file is how the child tells us "I already paused (or decided
    # a pause was not needed)". It survives any way the child may die.
    fd, status_file = tempfile.mkstemp(prefix="pyexewrap_status_")
    os.close(fd)
    env = dict(os.environ)
    env["PYEXEWRAP_STATUS_FILE"] = status_file

    cmd = _build_child_command(script, script_args, env)

    # Windowless mode: a double-clicked .pyw arrives here through pythonw.exe,
    # so this parent has no console. The child runs fully detached (no console
    # either), its output captured in a log file. Only if an exception occurs
    # does the child create a console (AllocConsole) and replay the log there.
    windowless = os.path.splitext(script)[1].lower() == ".pyw" and not have_console()
    run_kwargs = {}
    log_file = None
    log_handle = None
    if windowless:
        fd, log_file = tempfile.mkstemp(prefix="pyexewrap_pyw_", suffix=".log")
        log_handle = os.fdopen(fd, "w", encoding="utf-8", errors="replace")
        env["PYEXEWRAP_PYW_LOG"] = log_file
        run_kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "creationflags": subprocess.DETACHED_PROCESS,
        }

    # Ctrl+C is sent to every process attached to the console. The child is
    # the one that must handle it (KeyboardInterrupt in the script, then its
    # pause menu); the parent must survive to display the fallback pause.
    previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        result = subprocess.run(cmd, env=env, **run_kwargs)
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        if log_handle:
            log_handle.close()

    child_handled = _read_status(status_file) == STATUS_HANDLED
    for temp_file in (status_file, log_file):
        if temp_file:
            try:
                os.remove(temp_file)
            except OSError:
                pass

    if not child_handled and _script_is_doubleclicked():
        _fallback_pause(result.returncode)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
