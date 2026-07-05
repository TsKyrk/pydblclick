"""System-level environment checks for pydblclick double-click invocation.

Unlike the unit tests in test_pydblclick.py (which call run_script() directly
and always pass regardless of Windows file associations), these tests verify
that the *Windows environment* is correctly configured to actually invoke
pydblclick when a .py file is double-clicked.

These tests can fail due to external system state (MSIX packages, missing
file associations) rather than code bugs. A failure here means pydblclick
will not be invoked on double-click, even if the unit tests pass.

MSIX Python Manager compatibility:
  Only the ProgID + UserChoice registration ('pydblclick register') works with
  MSIX; the shebang approach does not. See MSIX_COMPATIBILITY.md for the matrix.
"""
import pytest

try:
    from pydblclick.winpyfiles._assoc import diagnose, find_msix_python_package, find_python_appx_prog_ids
    HAS_WINPYFILES = True
except ImportError:
    HAS_WINPYFILES = False

_winpyfiles = pytest.mark.skipif(
    not HAS_WINPYFILES,
    reason="winpyfiles not importable (add repo root to PYTHONPATH)"
)


@_winpyfiles
def test_py_ftype_command_references_pydblclick():
    """The Windows ftype command for .py/.pyw files must reference pydblclick.

    This test is automatically skipped when the MSIX Python Manager is
    detected (since in that case the ftype command is bypassed anyway --
    see test_no_msix_python_manager for the root cause).
    """
    if find_msix_python_package() or find_python_appx_prog_ids():
        pytest.skip(
            "MSIX Python Manager detected -- ftype command is bypassed by "
            "App Model activation. See test_no_msix_python_manager."
        )

    d = diagnose()
    for ext_info in d.extensions:
        pid = ext_info.user_choice or ext_info.prog_id_effective
        if not pid:
            pytest.fail(
                f"{ext_info.extension}: no ProgID configured -- extension is unmapped.\n"
                f"Run 'pydblclick diagnose' then 'pydblclick register'."
            )
        info = d.prog_ids.get(pid)
        cmd = info.command_effective if info else None
        assert cmd and "pydblclick" in cmd.lower(), (
            f"{ext_info.extension}: pydblclick not found in the ftype command.\n"
            f"  ProgID  : {pid}\n"
            f"  Command : {cmd!r}\n\n"
            f"Run 'pydblclick diagnose' for full details, then\n"
            f"'pydblclick register' to configure."
        )
