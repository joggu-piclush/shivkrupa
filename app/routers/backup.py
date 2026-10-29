"""
Backup download.

The whole business lives in one SQLite file, so a backup is simply a copy of that file.
GET /backup/download makes a consistent copy of it (SQLite's own online-backup call, safe even
while someone is saving an entry) and hands it to the logged-in owner as a download.

Rules:
  - Only a logged-in admin can ask for it (same gate as every other screen: ID + password + code).
  - The copy is made in a temporary file that is deleted as soon as it has been sent.
  - Temporary one-time login codes are left out of the copy (they are useless for a restore).
  - Nothing about the contents is ever printed in the server log, only who asked and how big it was.
"""
import os
import sqlite3
import tempfile
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .. import models
from ..database import engine
from ..deps import get_current_user

router = APIRouter(prefix="/backup", tags=["backup"])


def _sqlite_file():
    """Path of the live database file, or None if the app is not running on a SQLite file."""
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return url.database


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


@router.get("/download")
def download_backup(user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the owner can download a backup.")
    source_path = _sqlite_file()
    if not source_path or not os.path.exists(source_path):
        raise HTTPException(status_code=501, detail="Backups from the app only work with the built-in database.")

    fd, tmp_path = tempfile.mkstemp(prefix="shivkrupa-backup-", suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(source_path, timeout=30)
        dst = sqlite3.connect(tmp_path)
        try:
            src.backup(dst)  # consistent snapshot, even if a save happens at the same moment
            has_codes = dst.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='otp_codes'"
            ).fetchone()
            if has_codes:
                dst.execute("DELETE FROM otp_codes")
                dst.commit()
        finally:
            dst.close()
            src.close()
        size = os.path.getsize(tmp_path)
    except Exception:
        _remove(tmp_path)
        raise HTTPException(status_code=500, detail="Could not make the backup right now. Please try again.")

    print(f"[backup] Login {user.username!r} downloaded a backup ({size} bytes).")
    return FileResponse(
        tmp_path,
        media_type="application/octet-stream",
        filename="shivkrupa-backup.db",
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(_remove, tmp_path),
    )
