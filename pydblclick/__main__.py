"""pydblclick — parent supervisor process.

Entry point: python -m pydblclick <script.py> [args...]

The actual script execution happens in a child process (pydblclick/_child.py)
launched with the same interpreter. The child runs the script with plain-Python
semantics, shows tracebacks and displays the pause prompt/menu itself.

The parent's only job is to guarantee that the console window never flashes
away, even when the child cannot pause by itself:
- the script closed stdin with exit()/quit() (input() becomes impossible),
- the interpreter died hard (os._exit, native crash, MemoryError...),
- the script was Ctrl+C'd to death.

Child -> parent protocol: the child writes "handled" to the file pointed to
by the PYDBLCLICK_STATUS_FILE env var once it has fulfilled its pause-or-no-pause
duty. If the marker is missing after the child exits, the parent pauses.

Before launching, the parent inspects the script's source (pydblclick/_script_meta.py):
- `# pydblclick: off` -> run with plain Python, no wrapping at all;
- PEP 723 `# /// script` block -> run the child through `uv run` so the
  declared dependencies are resolved in an ephemeral environment.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile

from pydblclick import _script_meta
from pydblclick._child import STATUS_HANDLED, User32, ensure_console, have_console, signed32

UV_INSTALL_URL = "https://docs.astral.sh/uv/getting-started/installation/"

# Exit code of a process killed because its console window was closed (or by a
# hard Ctrl+C/Ctrl+Break). Closing the window is a deliberate user action:
# the fallback pause must not fire for it.
STATUS_CONTROL_C_EXIT = 0xC000013A  # 3221225786


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
    return (('PROMPT' not in os.environ)
            or ('pydblclick_simulate_doubleclick' in os.environ)
            or ('pyexewrap_simulate_doubleclick' in os.environ))  # legacy name


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
        if not ensure_console(title="pydblclick"):
            return
    elif have_console():
        # The console may still be hidden if a .pyw script crashed hard
        User32.show_window(User32.Const.SW_SHOWDEFAULT)
    if returncode != 0:
        print("\nThe script ended (exit code " + str(returncode) + ") without pydblclick being able to pause.")
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
    """Locate uv, returning the command (a list of args) to invoke it, or None.

    Order:
      1. the PYDBLCLICK_UV override
      2. PATH (shutil.which)
      3. the Scripts directory of the running interpreter -- where
         `pip install uv` lands. Matters under the MSIX Python Manager, which
         does not put pip Scripts dirs on PATH, so an otherwise-installed uv
         is invisible to shutil.which().
      4. `python -m uv` -- the uv PyPI package is runnable as a module (its
         __main__.py execs the embedded binary), so this covers any
         pip-installed uv without probing paths at all.

    A command is a list (e.g. [sys.executable, "-m", "uv"]) rather than a bare
    path so case 4 can be expressed; callers must prepend/extend, not assume
    a single executable path.
    """
    override = os.environ.get("PYDBLCLICK_UV")
    if override:
        return [override]
    found = shutil.which("uv")
    if found:
        return [found]

    import sysconfig
    exe = "uv.exe" if os.name == "nt" else "uv"
    user_scheme = "nt_user" if os.name == "nt" else "posix_user"
    scripts_dirs = []
    for args in ((), (user_scheme,)):  # this interpreter's Scripts, then --user
        try:
            scripts_dirs.append(sysconfig.get_path("scripts", *args))
        except Exception:
            pass
    for scripts in scripts_dirs:
        if scripts:
            candidate = os.path.join(scripts, exe)
            if os.path.isfile(candidate):
                return [candidate]

    import importlib.util
    try:
        has_uv_module = importlib.util.find_spec("uv") is not None
    except Exception:
        has_uv_module = False
    if has_uv_module:
        return [sys.executable, "-m", "uv"]

    return None


def _pydblclick_version():
    """The installed pydblclick version, or None if it cannot be resolved (a
    dev checkout run off PYTHONPATH with no installed distribution)."""
    import importlib.metadata
    try:
        return importlib.metadata.version("pydblclick")
    except importlib.metadata.PackageNotFoundError:
        return None


def _isolated_pydblclick_copy():
    """Copy just the pydblclick package into a fresh temp directory and return
    that directory (to be put on PYTHONPATH). Isolated so PYTHONPATH shadows
    nothing else from the host's site-packages -- see the PYTHONPATH-shadowing
    comment in _build_child_command(). Caller must remove the returned
    directory once the subprocess using it has finished."""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    staging = tempfile.mkdtemp(prefix="pydblclick_uv_pythonpath_")
    shutil.copytree(package_dir, os.path.join(staging, "pydblclick"))
    return staging


def _build_child_command(script, script_args, env):
    """Build the child command line, delegating to `uv run` for PEP 723 scripts.

    Returns (cmd, cleanup_dir): cleanup_dir is a temp directory the caller must
    remove after the subprocess exits, or None if there is nothing to clean up.
    """
    default_cmd = [_console_python(), "-m", "pydblclick._child", script] + script_args

    meta = _script_meta.parse_pep723(_script_meta.read_script_text(script))
    if meta is None:
        return default_cmd, None

    uv_cmd = _find_uv()
    if not uv_cmd:
        print("[pydblclick] This script declares PEP 723 dependencies, but 'uv' was not found.")
        print("            Install uv to run it with its dependencies resolved automatically:")
        print("            " + UV_INSTALL_URL)
        print("            Running with plain Python instead...\n")
        return default_cmd, None

    cmd = uv_cmd + ["run", "--no-project"]
    if meta["requires-python"]:
        cmd += ["--python", meta["requires-python"]]
    for dep in meta["dependencies"]:
        cmd += ["--with", dep]

    # pydblclick itself must be importable inside uv's ephemeral environment (so
    # the script's own `import pydblclick` directive, if present, is inert
    # rather than a ModuleNotFoundError). Preferred: let uv resolve the exact
    # installed version like any other dependency -- unlike PYTHONPATH, this
    # does not sit ahead of the ephemeral env's site-packages in sys.path, so
    # it cannot shadow a PEP 723-pinned version of a package the host also
    # happens to have installed (e.g. script pins requests==2.32, host has
    # 2.28: PYTHONPATH would have silently served the host's 2.28).
    cleanup_dir = None
    version = _pydblclick_version()
    if version is not None:
        cmd += ["--with", "pydblclick==" + version]
    else:
        # Dev checkout with no installed distribution to resolve a version
        # from: fall back to PYTHONPATH, but isolated to a throwaway copy of
        # just the pydblclick package -- not the whole host site-packages,
        # which is what would shadow pinned dependencies above.
        cleanup_dir = _isolated_pydblclick_copy()
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = cleanup_dir + (os.pathsep + existing if existing else "")

    cmd += ["python", "-m", "pydblclick._child", script] + script_args
    return cmd, cleanup_dir


def main():
    if len(sys.argv) < 2:
        print("Usage: pydblclick <script.py> [args...]")
        print("       pydblclick register    (set pydblclick as the .py/.pyw double-click handler)")
        print("       pydblclick unregister  (restore plain Python on double-click)")
        print("       pydblclick diagnose    (inspect the Windows file association chain)")
        return 2

    # Management subcommands (a real script file named e.g. 'register' still wins)
    from pydblclick._cli import COMMANDS
    if sys.argv[1] in COMMANDS and not os.path.exists(sys.argv[1]):
        from pydblclick import _cli
        return _cli.main(sys.argv[1:])

    script, script_args = sys.argv[1], sys.argv[2:]

    # Per-script opt-out: run with plain Python, no wrapping, no pause
    if _script_meta.has_opt_out(_script_meta.read_script_text(script)):
        result = subprocess.run([_plain_python_for(script), script] + script_args)
        return signed32(result.returncode)

    # The status file is how the child tells us "I already paused (or decided
    # a pause was not needed)". It survives any way the child may die.
    fd, status_file = tempfile.mkstemp(prefix="pydblclick_status_")
    os.close(fd)
    env = dict(os.environ)
    env["PYDBLCLICK_STATUS_FILE"] = status_file

    cmd, cleanup_dir = _build_child_command(script, script_args, env)

    # Windowless mode: a double-clicked .pyw arrives here through pythonw.exe,
    # so this parent has no console. The child runs fully detached (no console
    # either), its output captured in a log file. Only if an exception occurs
    # does the child create a console (AllocConsole) and replay the log there.
    windowless = os.path.splitext(script)[1].lower() == ".pyw" and not have_console()
    run_kwargs = {}
    log_file = None
    log_handle = None
    if windowless:
        fd, log_file = tempfile.mkstemp(prefix="pydblclick_pyw_", suffix=".log")
        log_handle = os.fdopen(fd, "w", encoding="utf-8", errors="replace")
        env["PYDBLCLICK_PYW_LOG"] = log_file
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
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)

    child_handled = _read_status(status_file) == STATUS_HANDLED
    for temp_file in (status_file, log_file):
        if temp_file:
            try:
                os.remove(temp_file)
            except OSError:
                pass

    user_closed_console = result.returncode == STATUS_CONTROL_C_EXIT
    if not child_handled and not user_closed_console and _script_is_doubleclicked():
        _fallback_pause(result.returncode)

    return signed32(result.returncode)


if __name__ == "__main__":
    sys.exit(signed32(main()))
