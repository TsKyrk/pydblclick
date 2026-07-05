"""Backup and restore of Windows Python file associations."""
import dataclasses
import json
import os
from datetime import datetime
from typing import Optional

from ._assoc import AssocDiagnosis, ExtensionInfo, ProgIdInfo, diagnose
from ._registry import HKCU, HKLM, write_value, delete_value

_BACKUP_VERSION = 1


def _default_backup_path() -> str:
    # A fixed per-user location: 'pydblclick register' can be run from any
    # directory without littering it with backup files.
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    backup_dir = os.path.join(base, "pydblclick", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(backup_dir, f"winpyfiles_backup_{timestamp}.json")


def backup(path: Optional[str] = None) -> str:
    """Snapshot current associations to a JSON file. Returns the path written."""
    if path is None:
        path = _default_backup_path()

    d = diagnose()
    payload = {
        "version": _BACKUP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "extensions": [dataclasses.asdict(e) for e in d.extensions],
        "prog_ids": {k: dataclasses.asdict(v) for k, v in d.prog_ids.items()},
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return path


def _set_or_delete(hive: int, key_path: str, value: Optional[str]) -> None:
    if value is not None:
        write_value(hive, key_path, value)
    else:
        delete_value(hive, key_path)


def restore(path: str) -> None:
    """Write back the associations saved in a backup file. Requires admin rights."""
    d = load_backup(path)

    # Restore extension -> ProgID mappings
    for ext in d.extensions:
        _set_or_delete(HKCU, f"Software\\Classes\\{ext.extension}", ext.prog_id_hkcu)
        _set_or_delete(HKLM, f"SOFTWARE\\Classes\\{ext.extension}", ext.prog_id_hklm)

    # Restore ProgID -> Command mappings
    for prog_id, info in d.prog_ids.items():
        hkcu_key = f"Software\\Classes\\{prog_id}\\shell\\open\\command"
        hklm_key = f"SOFTWARE\\Classes\\{prog_id}\\shell\\open\\command"
        _set_or_delete(HKCU, hkcu_key, info.command_hkcu)
        _set_or_delete(HKLM, hklm_key, info.command_hklm)


def load_backup(path: str) -> AssocDiagnosis:
    """Deserialize a backup file into an AssocDiagnosis."""
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    if payload.get("version") != _BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {payload.get('version')}")

    extensions = [ExtensionInfo(**e) for e in payload["extensions"]]
    prog_ids = {k: ProgIdInfo(**v) for k, v in payload["prog_ids"].items()}
    return AssocDiagnosis(extensions=extensions, prog_ids=prog_ids)
