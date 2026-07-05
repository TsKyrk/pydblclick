"""winpyfiles -- Windows Python file association manager."""
from ._assoc import (
    diagnose,
    find_py_exe,
    find_python_appx_prog_ids,
    set_command,
    set_prog_id,
    AssocDiagnosis,
    ExtensionInfo,
    ProgIdInfo,
)

__all__ = [
    "diagnose",
    "find_py_exe",
    "find_python_appx_prog_ids",
    "set_command",
    "set_prog_id",
    "AssocDiagnosis",
    "ExtensionInfo",
    "ProgIdInfo",
]
