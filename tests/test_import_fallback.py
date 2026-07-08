"""Tests for the `import pydblclick` one-line directive.

Importing pydblclick from a double-clicked script that is NOT already wrapped by
pydblclick re-launches the script through the real pydblclick (`python -m
pydblclick <script>`), so the recipient gets the full experience from a single
import line. If that relaunch cannot start, a minimal in-process pause/readable-
errors fallback takes over. In every other situation the import does nothing.
"""
import os
import pathlib
import subprocess
import sys

REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)

SCRIPT_OK = (
    "import pydblclick  # optional directive\n"
    'print("script ran fine")\n'
)
SCRIPT_CRASH = (
    "import pydblclick  # optional directive\n"
    'print("before crash")\n'
    "raise ValueError('fallback crash')\n"
)
SCRIPT_OPTOUT = (
    "import pydblclick  # optional directive\n"
    "# pydblclick: off\n"
    'print("plain optout")\n'
)

MINIMAL_MARKER = "[pydblclick] minimal mode"
FULL_MENU_MARKER = "Press <Enter> to Quit."  # the real pydblclick pause menu


def _run_plain(script_path, doubleclick, stdin_input="\n", extra_env=None):
    """Run a script with PLAIN python (not python -m pydblclick)."""
    env = {**os.environ, "PYTHONPATH": REPO_ROOT}
    if doubleclick:
        env["pydblclick_simulate_doubleclick"] = "1"
        env.pop("PROMPT", None)
    else:
        env["PROMPT"] = ">"
        env.pop("pydblclick_simulate_doubleclick", None)
        env.pop("pyexewrap_simulate_doubleclick", None)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, str(script_path)],
        input=stdin_input,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def test_bootstrap_relaunches_through_pydblclick(tmp_path):
    """Double-clicked without pydblclick: the FULL pydblclick menu appears."""
    script = tmp_path / "directive_ok.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    out, _, code = _run_plain(script, doubleclick=True)

    assert "script ran fine" in out
    assert FULL_MENU_MARKER in out          # the real menu, not the minimal pause
    assert MINIMAL_MARKER not in out
    assert code == 0


def test_bootstrap_shows_traceback_on_crash(tmp_path):
    """Uncaught exception: pydblclick shows a readable traceback + its menu."""
    script = tmp_path / "directive_crash.py"
    script.write_text(SCRIPT_CRASH, encoding="utf-8")

    out, err, code = _run_plain(script, doubleclick=True)

    assert "before crash" in out
    assert "ValueError" in (out + err)
    assert FULL_MENU_MARKER in out
    assert MINIMAL_MARKER not in out
    assert code != 0


def test_bootstrap_no_double_execution(tmp_path):
    """The original process stops at the import: the script body runs once,
    in the relaunched child only (no re-run, no infinite relaunch loop)."""
    script = tmp_path / "directive_once.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    out, _, code = _run_plain(script, doubleclick=True)

    assert out.count("script ran fine") == 1
    assert code == 0


def test_optout_directive_steps_aside_no_relaunch(tmp_path):
    """`# pydblclick: off` alongside the import must make pydblclick step aside:
    the script runs as plain Python in-process, with NO relaunch (which would
    loop forever, since the opt-out path re-runs the script with plain Python).
    Bounded by a timeout so a regression fails loudly instead of fork-bombing."""
    script = tmp_path / "directive_optout.py"
    script.write_text(SCRIPT_OPTOUT, encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": REPO_ROOT,
           "pydblclick_simulate_doubleclick": "1"}
    env.pop("PROMPT", None)
    result = subprocess.run(
        [sys.executable, str(script)],
        input="\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=30,  # a relaunch loop would hang; fail fast instead
    )

    assert result.stdout.count("plain optout") == 1
    assert MINIMAL_MARKER not in result.stdout
    assert FULL_MENU_MARKER not in result.stdout  # stepped aside: no pause menu
    assert result.returncode == 0


def test_no_bootstrap_env_forces_minimal(tmp_path):
    """PYDBLCLICK_NO_BOOTSTRAP disables the relaunch: the minimal fallback runs
    in-process (readable errors + pause + hint about register)."""
    script = tmp_path / "directive_minimal.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    out, _, code = _run_plain(
        script, doubleclick=True, extra_env={"PYDBLCLICK_NO_BOOTSTRAP": "1"}
    )

    assert "script ran fine" in out
    assert MINIMAL_MARKER in out
    assert "pydblclick register" in out
    assert "Press <Enter> to close..." in out
    assert code == 0


def test_import_silent_in_console(tmp_path):
    """Console context (PROMPT set): the import must do strictly nothing."""
    script = tmp_path / "directive_console.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    out, _, code = _run_plain(script, doubleclick=False)

    assert "script ran fine" in out
    assert MINIMAL_MARKER not in out
    assert FULL_MENU_MARKER not in out
    assert code == 0


def test_import_silent_when_not_a_tty(tmp_path):
    """No PROMPT but piped stdin (CI-like): stays silent instead of relaunching."""
    script = tmp_path / "directive_ci.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": REPO_ROOT}
    env.pop("PROMPT", None)
    env.pop("pydblclick_simulate_doubleclick", None)
    env.pop("pyexewrap_simulate_doubleclick", None)
    result = subprocess.run(
        [sys.executable, str(script)],
        input="",
        capture_output=True,
        text=True,
        env=env,
    )

    assert "script ran fine" in result.stdout
    assert MINIMAL_MARKER not in result.stdout
    assert FULL_MENU_MARKER not in result.stdout


def test_import_inert_under_pydblclick(tmp_path):
    """Wrapped by pydblclick: the directive is inert, the full menu shows once."""
    script = tmp_path / "directive_wrapped.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": REPO_ROOT,
           "pydblclick_simulate_doubleclick": "1"}
    env.pop("PROMPT", None)
    result = subprocess.run(
        [sys.executable, "-m", "pydblclick", str(script)],
        input="\n",
        capture_output=True,
        text=True,
        env=env,
    )

    assert "script ran fine" in result.stdout
    assert MINIMAL_MARKER not in result.stdout
    assert result.stdout.count(FULL_MENU_MARKER) == 1  # the real menu, exactly once


def test_own_processes_never_activate_fallback(tmp_path):
    """pydblclick's parent/child own startup must not trigger the fallback,
    even in double-click conditions (script without the directive)."""
    script = tmp_path / "no_directive.py"
    script.write_text('print("plain script")\n', encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": REPO_ROOT,
           "pydblclick_simulate_doubleclick": "1"}
    env.pop("PROMPT", None)
    result = subprocess.run(
        [sys.executable, "-m", "pydblclick", str(script)],
        input="\n",
        capture_output=True,
        text=True,
        env=env,
    )

    assert MINIMAL_MARKER not in result.stdout
