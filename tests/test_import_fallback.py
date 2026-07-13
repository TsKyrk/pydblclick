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

import pytest

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


def test_walk_ancestry_for_explorer_allows_only_known_launchers():
    """Pure ancestry-walk logic behind `_launched_by_explorer`: reaching
    explorer.exe through launcher hops only (py.exe, pythonw.exe, ...) returns
    True; hitting a shell or any other unrecognized process first returns
    False. This is the allowlist inversion (ROADMAP_HARDENING.md item 2):
    unlike a shell blocklist, an unknown intervening process is NOT tolerated."""
    from pydblclick import _walk_ancestry_for_explorer

    # explorer -> py.exe -> pythonw.exe -> pid (double-click via launcher hops)
    parent_of = {1: None, 2: 1, 3: 2, 4: 3}
    name_of = {1: "explorer.exe", 2: "py.exe", 3: "pythonw.exe", 4: "script.exe"}
    assert _walk_ancestry_for_explorer(4, parent_of, name_of) is True

    # explorer -> pwsh.exe -> pid (launched from a terminal, itself an
    # Explorer descendant -- must NOT false-positive)
    parent_of_shell = {1: None, 2: 1, 3: 2}
    name_of_shell = {1: "explorer.exe", 2: "pwsh.exe", 3: "script.exe"}
    assert _walk_ancestry_for_explorer(3, parent_of_shell, name_of_shell) is False

    # explorer -> some_unknown_gui.exe -> pid (unrecognized launcher: an
    # allowlist rejects this, where the old blocklist would have tolerated it)
    parent_of_unknown = {1: None, 2: 1, 3: 2}
    name_of_unknown = {1: "explorer.exe", 2: "some_unknown_gui.exe", 3: "script.exe"}
    assert _walk_ancestry_for_explorer(3, parent_of_unknown, name_of_unknown) is False

    # explorer -> pymanager.exe -> pid (MSIX Python Manager hop is allowlisted)
    parent_of_msix = {1: None, 2: 1, 3: 2}
    name_of_msix = {1: "explorer.exe", 2: "pymanager.exe", 3: "script.exe"}
    assert _walk_ancestry_for_explorer(3, parent_of_msix, name_of_msix) is True


def test_pyw_directive_inert_without_explorer(tmp_path):
    """A `.pyw` with the directive, run WITHOUT an Explorer double-click (here a
    test runner, i.e. a shell ancestry) stays inert: `.pyw` double-click
    detection keys on an Explorer launcher, which is absent, so pydblclick does
    not activate and the script runs as plain Python."""
    script = tmp_path / "directive.pyw"
    script.write_text(
        "import pydblclick  # optional directive\n"
        'print("pyw plain")\n',
        encoding="utf-8",
    )

    env = {**os.environ, "PYTHONPATH": REPO_ROOT}
    env.pop("PROMPT", None)
    env.pop("pydblclick_simulate_doubleclick", None)
    env.pop("pyexewrap_simulate_doubleclick", None)
    result = subprocess.run(
        [sys.executable, str(script)],
        input="", capture_output=True, text=True, env=env, timeout=30,
    )

    assert "pyw plain" in result.stdout
    assert MINIMAL_MARKER not in result.stdout
    assert FULL_MENU_MARKER not in result.stdout
    assert result.returncode == 0


def test_pyw_directive_relaunches_windowless_on_crash(tmp_path):
    """A double-clicked `.pyw` with the directive that crashes must relaunch
    through pydblclick and block at the pause menu on a freshly created console.

    Pops a real console window, so gated behind PYDBLCLICK_UI_TESTS. Simulated
    double-click bypasses the Explorer check; the interpreter is pythonw so the
    relaunch goes windowless (a console appears only because of the exception).
    TimeoutExpired proves the relaunched child is alive, waiting at the menu."""
    if not os.environ.get("PYDBLCLICK_UI_TESTS"):
        pytest.skip("UI test (pops a console window); set PYDBLCLICK_UI_TESTS=1 to run")

    script = tmp_path / "directive_crash.pyw"
    script.write_text(
        "import pydblclick  # optional directive\n"
        'print("before crash")\n'
        "raise ValueError('pyw directive crash')\n",
        encoding="utf-8",
    )

    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    assert os.path.exists(pythonw), "pythonw.exe not found next to python.exe"
    env = {**os.environ, "PYTHONPATH": REPO_ROOT,
           "pydblclick_simulate_doubleclick": "1"}
    env.pop("PROMPT", None)
    proc = subprocess.Popen(
        [pythonw, str(script)],
        env=env,
        creationflags=subprocess.DETACHED_PROCESS,
    )
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=15)  # still alive -> it relaunched and is at the menu
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True)


def test_py_tty_without_explorer_ancestry_stays_inert(monkeypatch):
    """The PowerShell false-positive this closes: pwsh/powershell.exe set no
    PROMPT and give the process an interactive tty, which used to be enough to
    trigger the bootstrap. Now `.py` also requires `_launched_by_explorer()`.

    A real subprocess can't easily get a genuine tty stdin here (capture_output
    always pipes it), so this exercises `_maybe_enable_import_fallback()`
    in-process with stdin.isatty() faked True and `_launched_by_explorer()`
    stubbed to return False (the PowerShell shape: a shell ancestor, no
    Explorer) -- proving tty alone is no longer sufficient."""
    import pydblclick

    monkeypatch.delenv("PROMPT", raising=False)
    monkeypatch.delenv("pydblclick_simulate_doubleclick", raising=False)
    monkeypatch.delenv("pyexewrap_simulate_doubleclick", raising=False)
    monkeypatch.setattr(sys, "argv", ["script.py"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)

    explorer_calls = []
    monkeypatch.setattr(
        pydblclick, "_launched_by_explorer",
        lambda: explorer_calls.append(1) or False,
    )

    assert pydblclick._maybe_enable_import_fallback() is False
    assert explorer_calls == [1]  # the explorer check was actually consulted


def test_py_directive_inert_without_explorer(tmp_path):
    """A `.py` with the directive, run in a subprocess WITHOUT the simulation
    env var and WITHOUT PROMPT, stays inert: the test runner's own ancestry is
    a shell, not Explorer. Mirrors test_pyw_directive_inert_without_explorer;
    stdin here is piped (non-tty) so this also covers the ordinary CI/piped
    case, unaffected by the explorer-ancestry requirement."""
    script = tmp_path / "directive_no_explorer.py"
    script.write_text(SCRIPT_OK, encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": REPO_ROOT}
    env.pop("PROMPT", None)
    env.pop("pydblclick_simulate_doubleclick", None)
    env.pop("pyexewrap_simulate_doubleclick", None)
    result = subprocess.run(
        [sys.executable, str(script)],
        input="", capture_output=True, text=True, env=env, timeout=30,
    )

    assert "script ran fine" in result.stdout
    assert MINIMAL_MARKER not in result.stdout
    assert FULL_MENU_MARKER not in result.stdout
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
