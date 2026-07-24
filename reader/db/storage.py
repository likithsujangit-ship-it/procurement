import hashlib
import os
from pathlib import Path
from db.db import get_session
from sqlalchemy import text

# Resolve blob root relative to reader/files/
READER_DIR = Path(__file__).parent.parent.resolve()
BLOB_ROOT = os.environ.get("BLOB_ROOT", str(READER_DIR / "files" / "blobs"))


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_path_for_hash(sha256: str, ext: str) -> str:
    # bucket into subfolders so no single directory holds thousands of files
    sub = os.path.join(BLOB_ROOT, sha256[0:2], sha256[2:4])
    os.makedirs(sub, exist_ok=True)
    return os.path.join(sub, f"{sha256}{ext}")


def save_attachment(raw_bytes: bytes, original_filename: str, sender_email: str,
                     mime_type: str = None) -> dict:
    """
    Returns {"sha256": ..., "is_duplicate": bool, "document_id": int, "path": str}
    Call this instead of writing straight to reader/files/<sender>/<timestamp>/.
    """
    sha256 = hash_bytes(raw_bytes)
    session = get_session()
    try:
        existing = session.execute(
            text("SELECT id, file_path FROM documents WHERE sha256 = :h"),
            {"h": sha256},
        ).fetchone()
        if existing:
            return {"sha256": sha256, "is_duplicate": True,
                     "document_id": existing[0], "path": existing[1]}

        ext = os.path.splitext(original_filename)[1]
        path = blob_path_for_hash(sha256, ext)
        with open(path, "wb") as f:
            f.write(raw_bytes)

        # Convert backslashes to forward slashes for cross-platform DB compatibility
        clean_path = Path(path).as_posix()

        result = session.execute(
            text("""INSERT INTO documents
                     (sha256, original_filename, mime_type, sender_email, file_path)
                     VALUES (:h, :fn, :mt, :se, :p)"""),
            {"h": sha256, "fn": original_filename, "mt": mime_type,
             "se": sender_email, "p": clean_path},
        )
        session.commit()
        return {"sha256": sha256, "is_duplicate": False,
                 "document_id": result.lastrowid, "path": clean_path}
    finally:
        session.close()
