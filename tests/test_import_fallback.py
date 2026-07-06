"""Tests for the `import pydblclick` one-line directive (library fallback mode).

Importing pydblclick from a double-clicked script that is NOT wrapped by
pydblclick activates a minimal pause/readable-errors fallback. In every other
situation the import must do strictly nothing.
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

MINIMAL_MARKER = "[pydblclick] minimal mode"


def _run_plain(script_path, doubleclick, stdin_input="\n"):
    """Run a script with PLAIN python (not python -m pydblclick)."""
    env = {**os.environ, "PYTHONPATH": REPO_ROOT}
    if doubleclick:
        env["pydblclick_simulate_doubleclick"] = "1"
        env.pop("PROMPT", None)
    else:
        env["PROMPT"] = ">"
        env.pop("pydblclick_simulate_doubleclick", None)
        env.pop("pyexewrap_simulate_doubleclick", None)
    result = subprocess.run(
        [sys.executable, str(script_path)],
        input=stdin_input,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def test_fallback_active_on_bare_doubleclick(tmp_path):
    """Double-clicked without pydblclick: pause + hint about register."""
    script = tmp_path / "directive_ok.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    out, _, code = _run_plain(script, doubleclick=True)

    assert "script ran fine" in out
    assert MINIMAL_MARKER in out
    assert "pydblclick register" in out
    assert "Press <Enter>" in out
    assert code == 0


def test_fallback_shows_traceback_on_crash(tmp_path):
    """Uncaught exception: readable traceback, then a single pause."""
    script = tmp_path / "directive_crash.py"
    script.write_text(SCRIPT_CRASH, encoding="utf-8")

    out, err, code = _run_plain(script, doubleclick=True)

    assert "before crash" in out
    assert "ValueError" in err  # traceback on stderr, as plain Python does
    assert out.count(MINIMAL_MARKER) == 1  # excepthook pause, atexit unregistered
    assert code != 0


def test_import_silent_in_console(tmp_path):
    """Console context (PROMPT set): the import must do strictly nothing."""
    script = tmp_path / "directive_console.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    out, _, code = _run_plain(script, doubleclick=False)

    assert "script ran fine" in out
    assert MINIMAL_MARKER not in out
    assert "Press <Enter>" not in out
    assert code == 0


def test_import_silent_when_not_a_tty(tmp_path):
    """No PROMPT but piped stdin (CI-like): stays silent instead of pausing."""
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


def test_import_inert_under_pydblclick(tmp_path):
    """Wrapped by pydblclick: the directive is inert, the full menu shows."""
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
    assert "Press <Enter> to Quit." in result.stdout  # the real pydblclick menu


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
