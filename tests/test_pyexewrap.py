"""Automated regression tests for pyexewrap.

These tests verify the core behavior of the tool and protect against regressions.
They call run_script() from pyexewrap._child directly (in-process).
For interactive ergonomic tests demonstrating the tool's UX, see unit_tests/.
"""
import os
import pytest
from pyexewrap._child import run_script


@pytest.fixture(autouse=True)
def cli_mode(monkeypatch):
    """Simulate CLI execution (not double-click) for all tests.

    This prevents the caller from blocking on input() at the pause prompt.
    Tests that need to simulate a double-click override this fixture.
    """
    monkeypatch.setenv("PROMPT", ">")
    monkeypatch.delenv("pyexewrap_simulate_doubleclick", raising=False)


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------

def test_simple_script_runs(tmp_path, capsys):
    """A basic script executes and produces the expected output."""
    script = tmp_path / "hello.py"
    script.write_text('print("hello world")', encoding="utf-8")

    pause, code = run_script(str(script))

    assert capsys.readouterr().out.strip() == "hello world"
    assert pause is False  # no pause in CLI mode
    assert code == 0


def test_no_pause_in_cli_mode(tmp_path):
    """run_script() returns pause=False when executed from a console."""
    script = tmp_path / "noop.py"
    script.write_text("x = 1", encoding="utf-8")

    pause, _ = run_script(str(script))
    assert pause is False


def test_pause_in_doubleclick_mode(tmp_path, monkeypatch):
    """run_script() returns pause=True when double-clicked."""
    script = tmp_path / "noop.py"
    script.write_text("x = 1", encoding="utf-8")

    monkeypatch.delenv("PROMPT", raising=False)
    monkeypatch.setenv("pyexewrap_simulate_doubleclick", "1")

    pause, _ = run_script(str(script))
    assert pause is True


# ---------------------------------------------------------------------------
# E001 — imports accessible inside functions
# ---------------------------------------------------------------------------

def test_import_accessible_inside_function(tmp_path, capsys):
    """Module-level imports are visible inside functions (E001 regression).

    Historically, exec() used different global/local scopes so imports
    made at module level were invisible from within a called function.
    runpy.run_path() gives plain-Python module semantics.
    """
    script = tmp_path / "e001.py"
    script.write_text(
        "import os\n"
        "def get_sep():\n"
        "    return os.sep\n"
        "print(get_sep())\n",
        encoding="utf-8",
    )

    run_script(str(script))

    assert capsys.readouterr().out.strip() == os.sep


# ---------------------------------------------------------------------------
# E002 — clean exception traceback (no pyexewrap frame)
# ---------------------------------------------------------------------------

def test_exception_shows_traceback(tmp_path, capsys):
    """An uncaught exception prints the traceback to stdout (E002 regression)."""
    script = tmp_path / "e002.py"
    script.write_text("raise ValueError('oops')", encoding="utf-8")

    _, code = run_script(str(script))

    out = capsys.readouterr().out
    assert "ValueError" in out
    assert "oops" in out
    assert code != 0


def test_traceback_excludes_pyexewrap_frame(tmp_path, capsys):
    """The traceback does not expose pyexewrap's internal frames (E002 regression).

    The traceback must start at the user's script, not at pyexewrap's
    run_script()/runpy internals.
    """
    script = tmp_path / "e002_clean.py"
    script.write_text("raise RuntimeError('boom')", encoding="utf-8")

    run_script(str(script))

    out = capsys.readouterr().out
    # The traceback must point to the user's script, not to pyexewrap internals
    assert str(script) in out
    assert "runpy" not in out
    assert "_child.py" not in out


def test_syntax_error_shows_location(tmp_path, capsys):
    """A SyntaxError (no frame in the script) still shows file and line."""
    script = tmp_path / "e002_syntax.py"
    script.write_text("def broken(:\n", encoding="utf-8")

    _, code = run_script(str(script))

    out = capsys.readouterr().out
    assert "SyntaxError" in out
    assert str(script) in out
    assert code != 0


# ---------------------------------------------------------------------------
# E003 — exit() / quit() / SystemExit handled gracefully
# ---------------------------------------------------------------------------

def test_exit_does_not_crash_pyexewrap(tmp_path):
    """exit() in a script is handled gracefully (E003 regression)."""
    script = tmp_path / "e003_exit.py"
    script.write_text("exit(0)", encoding="utf-8")

    _, code = run_script(str(script))  # must not raise
    assert code == 0


def test_quit_does_not_crash_pyexewrap(tmp_path):
    """quit() in a script is handled gracefully (E003 regression)."""
    script = tmp_path / "e003_quit.py"
    script.write_text("quit(0)", encoding="utf-8")

    _, code = run_script(str(script))  # must not raise
    assert code == 0


def test_systemexit_does_not_crash_pyexewrap(tmp_path):
    """raise SystemExit() in a script is handled gracefully (E003 regression)."""
    script = tmp_path / "e003_systemexit.py"
    script.write_text("raise SystemExit(0)", encoding="utf-8")

    _, code = run_script(str(script))  # must not raise
    assert code == 0


def test_systemexit_code_is_propagated(tmp_path):
    """sys.exit(3) in the script is propagated as exit code 3 (CLI/batch callers)."""
    script = tmp_path / "e003_code.py"
    script.write_text("import sys\nsys.exit(3)", encoding="utf-8")

    _, code = run_script(str(script))
    assert code == 3


# ---------------------------------------------------------------------------
# E004 — __file__ points to the user's script
# ---------------------------------------------------------------------------

def test_dunder_file_points_to_script(tmp_path, capsys):
    """__file__ inside the executed script is the script's own path (E004 regression)."""
    script = tmp_path / "e004.py"
    script.write_text("print(__file__)", encoding="utf-8")

    run_script(str(script))

    assert capsys.readouterr().out.strip() == str(script)


def test_dunder_name_is_main(tmp_path, capsys):
    """The script runs with __name__ == '__main__', like plain python."""
    script = tmp_path / "name.py"
    script.write_text("print(__name__)", encoding="utf-8")

    run_script(str(script))

    assert capsys.readouterr().out.strip() == "__main__"


def test_sibling_import_works(tmp_path, capsys):
    """The script's directory is on sys.path, like `python script.py`."""
    (tmp_path / "sibling.py").write_text("VALUE = 'from sibling'", encoding="utf-8")
    script = tmp_path / "importer.py"
    script.write_text("import sibling\nprint(sibling.VALUE)", encoding="utf-8")

    run_script(str(script))

    assert capsys.readouterr().out.strip() == "from sibling"


# ---------------------------------------------------------------------------
# Customization — must_pause_in_console
# ---------------------------------------------------------------------------

def test_must_pause_false_suppresses_pause(tmp_path, monkeypatch):
    """Setting must_pause_in_console=False prevents the pause even in double-click mode."""
    script = tmp_path / "no_pause.py"
    script.write_text(
        "pyexewrap_customizations['must_pause_in_console'] = False\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("PROMPT", raising=False)
    monkeypatch.setenv("pyexewrap_simulate_doubleclick", "1")

    pause, _ = run_script(str(script))
    assert pause is False


def test_exception_forces_pause_despite_customization(tmp_path, monkeypatch, capsys):
    """An uncaught exception overrides must_pause_in_console=False and forces a pause."""
    script = tmp_path / "forced_pause.py"
    script.write_text(
        "pyexewrap_customizations['must_pause_in_console'] = False\n"
        "raise RuntimeError('forced')\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("PROMPT", raising=False)
    monkeypatch.setenv("pyexewrap_simulate_doubleclick", "1")

    pause, _ = run_script(str(script))
    assert pause is True
