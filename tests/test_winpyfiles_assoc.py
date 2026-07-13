"""Tests for the missing-interpreter detection added in ROADMAP_HARDENING.md
item 6: `pydblclick register` writes a ProgID command pointing at the Python
interpreter that installed it (sys.executable). If that interpreter is later
uninstalled or moved, double-click breaks silently. These tests cover the
pure command-parsing/missing-executable logic and its wiring into `diagnose`
and `register`, all without touching the real Windows registry.
"""
import os

import pytest

try:
    from pydblclick.winpyfiles._assoc import extract_command_exe, is_command_exe_missing
    HAS_WINPYFILES = True
except ImportError:
    HAS_WINPYFILES = False

pytestmark = pytest.mark.skipif(
    not HAS_WINPYFILES,
    reason="winpyfiles not importable (add repo root to PYTHONPATH)",
)


# ---------------------------------------------------------------------------
# extract_command_exe -- pure string parsing
# ---------------------------------------------------------------------------

def test_extract_command_exe_quoted_with_args():
    cmd = '"C:\\Python312\\python.exe" -m pydblclick "%1" %*'
    assert extract_command_exe(cmd) == "C:\\Python312\\python.exe"


def test_extract_command_exe_unquoted_with_args():
    cmd = "C:\\Python312\\python.exe \"%1\" %*"
    assert extract_command_exe(cmd) == "C:\\Python312\\python.exe"


def test_extract_command_exe_quoted_no_args():
    assert extract_command_exe('"C:\\Python312\\python.exe"') == "C:\\Python312\\python.exe"


def test_extract_command_exe_unterminated_quote_best_effort():
    # Malformed command (missing closing quote): return the rest, don't crash.
    assert extract_command_exe('"C:\\Python312\\python.exe') == "C:\\Python312\\python.exe"


def test_extract_command_exe_empty_or_none():
    assert extract_command_exe(None) is None
    assert extract_command_exe("") is None


# ---------------------------------------------------------------------------
# is_command_exe_missing
# ---------------------------------------------------------------------------

def test_is_command_exe_missing_true_for_uninstalled_interpreter(tmp_path):
    gone = tmp_path / "python.exe"  # never created
    cmd = f'"{gone}" -m pydblclick "%1" %*'
    assert is_command_exe_missing(cmd) is True


def test_is_command_exe_missing_false_for_existing_interpreter():
    import sys
    cmd = f'"{sys.executable}" -m pydblclick "%1" %*'
    assert is_command_exe_missing(cmd) is False


def test_is_command_exe_missing_false_for_unconfigured_command():
    # "not configured" is a different condition from "configured but missing"
    assert is_command_exe_missing(None) is False
    assert is_command_exe_missing("") is False


# ---------------------------------------------------------------------------
# Wiring: `pydblclick register` reports when it repairs a stale registration
# ---------------------------------------------------------------------------

class _FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _stub_registry_writes(monkeypatch, cli, previous_command):
    """Replace every registry-writing call in pydblclick._cli with no-ops, and
    make the "read the existing command before overwriting" call return
    `previous_command` -- isolates _register_prog_ids()'s repair-detection
    logic from the real registry."""
    monkeypatch.setattr(cli, "read_value", lambda *a, **k: previous_command)
    monkeypatch.setattr(cli, "write_value", lambda *a, **k: None)
    monkeypatch.setattr(cli, "notify_shell_assoc_changed", lambda: None)
    monkeypatch.setattr(cli.winreg, "CreateKeyEx", lambda *a, **k: _FakeKey())
    monkeypatch.setattr(cli.winreg, "SetValueEx", lambda *a, **k: None)


def test_register_reports_repair_when_previous_interpreter_missing(monkeypatch, capsys):
    import pydblclick._cli as cli

    _stub_registry_writes(
        monkeypatch, cli,
        previous_command='"C:\\this\\python.exe\\does\\not\\exist.exe" -m pydblclick "%1" %*',
    )

    cli._register_prog_ids()

    out = capsys.readouterr().out
    assert "previous registration pointed to a missing interpreter, repaired" in out


def test_register_silent_when_no_previous_registration(monkeypatch, capsys):
    import pydblclick._cli as cli

    _stub_registry_writes(monkeypatch, cli, previous_command=None)

    cli._register_prog_ids()

    out = capsys.readouterr().out
    assert "repaired" not in out


# ---------------------------------------------------------------------------
# Wiring: `pydblclick diagnose` warns about a missing registered interpreter
# ---------------------------------------------------------------------------

def _fake_diagnosis(prog_id_command):
    """A minimal AssocDiagnosis with one pydblclick ProgID whose effective
    command is `prog_id_command` -- enough to drive cmd_diagnose()'s checks."""
    from pydblclick.winpyfiles._assoc import AssocDiagnosis, ExtensionInfo, ProgIdInfo

    return AssocDiagnosis(
        extensions=[
            ExtensionInfo(
                extension=".py",
                prog_id_hkcu="pydblclick.PyFile",
                prog_id_hklm=None,
                prog_id_effective="pydblclick.PyFile",
                user_choice=None,
            ),
        ],
        prog_ids={
            "pydblclick.PyFile": ProgIdInfo(
                prog_id="pydblclick.PyFile",
                command_hkcu=prog_id_command,
                command_hklm=None,
                command_effective=prog_id_command,
            ),
        },
        msix_handlers={},
        msix_package=None,
    )


def test_diagnose_warns_when_registered_interpreter_missing(monkeypatch, capsys, tmp_path):
    import pydblclick.winpyfiles.__main__ as winmain

    gone = tmp_path / "python.exe"
    monkeypatch.setattr(
        winmain, "diagnose",
        lambda: _fake_diagnosis(f'"{gone}" -m pydblclick "%1" %*'),
    )

    winmain.cmd_diagnose()

    out = capsys.readouterr().out
    assert "Registered interpreter check" in out
    assert "no longer exists" in out
    assert "pydblclick register" in out


def test_diagnose_silent_when_registered_interpreter_present(monkeypatch, capsys):
    import sys
    import pydblclick.winpyfiles.__main__ as winmain

    monkeypatch.setattr(
        winmain, "diagnose",
        lambda: _fake_diagnosis(f'"{sys.executable}" -m pydblclick "%1" %*'),
    )

    winmain.cmd_diagnose()

    out = capsys.readouterr().out
    assert "Registered interpreter check" not in out
    assert "no longer exists" not in out
