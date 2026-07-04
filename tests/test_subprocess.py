"""Subprocess integration tests for pyexewrap.

These tests invoke pyexewrap as a real subprocess (python -m pyexewrap script.py),
testing the full invocation chain: entry point, double-click detection, output,
pause prompt, and error handling.

Unlike test_pyexewrap.py (which calls run_script() directly in-process), these
tests catch issues in __main__.py's entry point, argument parsing, and process
setup that in-process tests cannot detect.

Double-click is simulated via the pyexewrap_simulate_doubleclick env var.
The pause prompt is dismissed by sending '\\n' to stdin.
"""
import os
import sys
import subprocess
import pytest


def _run(script_path, stdin_input="\n", extra_env=None):
    """Invoke pyexewrap as a subprocess simulating a double-click.

    Returns (stdout, stderr, returncode).
    """
    env = {**os.environ, "pyexewrap_simulate_doubleclick": "1"}
    env.pop("PROMPT", None)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-m", "pyexewrap", str(script_path)],
        input=stdin_input,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------

def test_subprocess_output_and_pause_prompt(tmp_path):
    """Script output appears and the pause prompt is shown on double-click."""
    script = tmp_path / "hello.py"
    script.write_text('print("hello world")', encoding="utf-8")

    out, _, code = _run(script)

    assert "hello world" in out
    assert "Press <Enter>" in out
    assert code == 0


def test_subprocess_no_pause_in_cli_mode(tmp_path):
    """No pause prompt when invoked from a console (PROMPT env var set)."""
    script = tmp_path / "hello.py"
    script.write_text('print("hello world")', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pyexewrap", str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "PROMPT": ">"},
    )

    assert "hello world" in result.stdout
    assert "Press <Enter>" not in result.stdout
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------

def test_subprocess_exception_shows_traceback(tmp_path):
    """An uncaught exception prints the traceback and then shows the pause prompt."""
    script = tmp_path / "boom.py"
    script.write_text("raise ValueError('subprocess test')", encoding="utf-8")

    out, _, _ = _run(script)

    assert "ValueError" in out
    assert "subprocess test" in out
    assert "Press <Enter>" in out


def test_subprocess_no_pyexewrap_frame_in_traceback(tmp_path):
    """The traceback does not include pyexewrap's internal exec() frame."""
    script = tmp_path / "boom.py"
    script.write_text("raise RuntimeError('clean traceback')", encoding="utf-8")

    out, _, _ = _run(script)

    assert str(script) in out
    assert "exec(compiled_code" not in out


# ---------------------------------------------------------------------------
# Customization
# ---------------------------------------------------------------------------

def test_subprocess_must_pause_false_suppresses_prompt(tmp_path):
    """Setting must_pause_in_console=False suppresses the pause prompt."""
    script = tmp_path / "no_pause.py"
    script.write_text(
        "pyexewrap_customizations['must_pause_in_console'] = False\n"
        'print("done")\n',
        encoding="utf-8",
    )

    out, _, code = _run(script)

    assert "done" in out
    assert "Press <Enter>" not in out
    assert code == 0


def test_subprocess_exception_forces_pause_despite_customization(tmp_path):
    """An uncaught exception overrides must_pause_in_console=False."""
    script = tmp_path / "forced.py"
    script.write_text(
        "pyexewrap_customizations['must_pause_in_console'] = False\n"
        "raise RuntimeError('forced pause')\n",
        encoding="utf-8",
    )

    out, _, _ = _run(script)

    assert "RuntimeError" in out
    assert "Press <Enter>" in out


# ---------------------------------------------------------------------------
# Parent supervisor — fallback pause when the child cannot pause itself
# ---------------------------------------------------------------------------

def test_subprocess_exit_closing_stdin_still_pauses(tmp_path):
    """exit() closes stdin in the child; the parent supervisor pauses instead."""
    script = tmp_path / "stdin_killer.py"
    script.write_text('print("about to exit")\nexit(0)\n', encoding="utf-8")

    out, _, code = _run(script)

    assert "about to exit" in out
    assert "Press <Enter>" in out  # fallback pause displayed by the parent
    assert code == 0


def test_subprocess_hard_crash_still_pauses(tmp_path):
    """os._exit() kills the child instantly; the parent supervisor pauses."""
    script = tmp_path / "hard_crash.py"
    # flush=True because os._exit() skips stdio buffer flushing (plain Python behavior)
    script.write_text('print("dying hard", flush=True)\nimport os\nos._exit(7)\n', encoding="utf-8")

    out, _, code = _run(script)

    assert "dying hard" in out
    assert "Press <Enter>" in out  # fallback pause displayed by the parent
    assert code == 7


def test_subprocess_no_fallback_pause_in_cli_mode(tmp_path):
    """A hard crash in CLI mode must not trigger the fallback pause."""
    script = tmp_path / "hard_crash.py"
    script.write_text("import os\nos._exit(7)\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pyexewrap", str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "PROMPT": ">"},
    )

    assert "Press <Enter>" not in result.stdout
    assert result.returncode == 7


# ---------------------------------------------------------------------------
# Exit code and argv fidelity (CLI/batch callers)
# ---------------------------------------------------------------------------

def test_subprocess_exit_code_propagated_in_cli_mode(tmp_path):
    """sys.exit(3) in the script surfaces as pyexewrap's own exit code."""
    script = tmp_path / "exit3.py"
    script.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pyexewrap", str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "PROMPT": ">"},
    )

    assert result.returncode == 3


def test_subprocess_script_args_forwarded(tmp_path):
    """Arguments after the script path are forwarded as the script's sys.argv."""
    script = tmp_path / "args.py"
    script.write_text("import sys\nprint('|'.join(sys.argv[1:]))\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pyexewrap", str(script), "alpha", "beta gamma"],
        capture_output=True,
        text=True,
        env={**os.environ, "PROMPT": ">"},
    )

    assert result.stdout.strip() == "alpha|beta gamma"


# ---------------------------------------------------------------------------
# Opt-out directive — pyexewrap steps aside
# ---------------------------------------------------------------------------

def test_subprocess_opt_out_no_pause(tmp_path):
    """A '# pyexewrap: off' script runs unwrapped: no pause even on double-click."""
    script = tmp_path / "opted_out.py"
    script.write_text('# pyexewrap: off\nprint("plain run")\n', encoding="utf-8")

    out, _, code = _run(script)

    assert "plain run" in out
    assert "Press <Enter>" not in out
    assert code == 0


def test_subprocess_opt_out_propagates_exit_code(tmp_path):
    """Opt-out keeps plain-Python behavior including the exit code."""
    script = tmp_path / "opted_out_exit.py"
    script.write_text("# pyexewrap: off\nimport sys\nsys.exit(5)\n", encoding="utf-8")

    _, _, code = _run(script)

    assert code == 5


# ---------------------------------------------------------------------------
# PEP 723 — dependency-aware execution through uv
# ---------------------------------------------------------------------------

PEP723_SCRIPT = (
    "# /// script\n"
    "# dependencies = []\n"
    "# ///\n"
    "import sys\n"
    "print('ran with', sys.version_info[0])\n"
)


def _uv_available():
    import shutil
    return os.environ.get("PYEXEWRAP_UV") or shutil.which("uv")


def test_subprocess_pep723_without_uv_falls_back(tmp_path):
    """Without uv on PATH, a PEP 723 script still runs (plain) with a clear message."""
    if _uv_available():
        pytest.skip("uv is available on this machine; fallback path not reachable")

    script = tmp_path / "needs_deps.py"
    script.write_text(PEP723_SCRIPT, encoding="utf-8")

    out, _, code = _run(script)

    assert "uv" in out and "not found" in out  # clear fallback message
    assert "ran with" in out  # script still executed
    assert "Press <Enter>" in out  # normal wrapped UX preserved
    assert code == 0


def test_subprocess_pep723_runs_through_uv(tmp_path):
    """With uv available, a PEP 723 script runs in an ephemeral env, UX preserved."""
    if not _uv_available():
        pytest.skip("uv not available (install uv or set PYEXEWRAP_UV)")

    script = tmp_path / "with_deps.py"
    script.write_text(PEP723_SCRIPT, encoding="utf-8")

    out, _, code = _run(script)

    assert "ran with" in out
    assert "Press <Enter>" in out  # pyexewrap UX preserved inside the uv env
    assert code == 0
