"""Translates a mapped-network-drive path (e.g. S:\\...) into its real UNC
form (\\\\server\\share\\...) before any filesystem operation touches it.

Confirmed necessary the hard way, not speculative: a Windows Service --
even one configured to run under a real interactive user's own account --
does NOT see that account's mapped drives. Drive mappings are tied to the
INTERACTIVE LOGON SESSION they were created in, not to the account itself.
A background service gets its own separate, non-interactive session where
the mapping simply doesn't exist, regardless of which account runs it --
this would happen just the same under a dedicated service account, so this
is the actual fix, not a stopgap tied to today's account choice. UNC paths
have no such dependency: they work identically for any account/session
that has the right share + NTFS permissions.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_mapped_drive(path: str | Path) -> Path:
    """Return path with a leading mapped-drive-letter prefix rewritten to
    its real UNC form, per a MAPPED_DRIVE_<LETTER>_UNC environment
    variable (e.g. MAPPED_DRIVE_S_UNC=\\\\LAB-SERVER\\LabShare).

    Returns path unchanged if it has no drive letter, or if no mapping is
    configured for that letter -- a safe no-op anywhere this translation
    isn't needed (local dev, sqlite-backed tests, a real UNC path already)."""
    path = Path(path)
    drive = path.drive  # e.g. "S:" for "S:\Testing_Requests\..."; "" for a relative or already-UNC path
    if not drive or not drive.endswith(":"):
        return path
    letter = drive.rstrip(":").upper()
    unc_prefix = os.environ.get(f"MAPPED_DRIVE_{letter}_UNC")
    if not unc_prefix:
        return path
    relative_parts = path.parts[1:]  # parts[0] is the drive root itself, e.g. "S:\\"
    return Path(unc_prefix, *relative_parts)
