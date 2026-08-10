"""File-attachment storage helpers for the 'file' field type (no AI, local disk).

Uploaded files live under DATA_DIR/uploads/<pid>/<record>/<event>/ and the
stored filename is saved as the field's value in data_values. The stored name
has the form  <field>__<random>__<original>  so multiple file fields can share
one folder and the original filename can be recovered for display/download.
"""
import os
import re
import secrets
from flask import current_app
from werkzeug.utils import secure_filename

# Extensions accepted for upload (images + common documents). No executables.
ALLOWED_EXT = {
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "heic",
    "pdf", "doc", "docx", "rtf", "odt", "txt",
    "csv", "xls", "xlsx", "ods",
}

# Expected leading "magic" bytes per extension, so a file's contents must match
# its claimed type (blocks e.g. an HTML/script payload renamed to .png).
_MAGIC = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "bmp": (b"BM",),
    "pdf": (b"%PDF",),
    "rtf": (b"{\\rtf",),
    "docx": (b"PK\x03\x04",), "xlsx": (b"PK\x03\x04",),
    "odt": (b"PK\x03\x04",), "ods": (b"PK\x03\x04",),
    "doc": (b"\xd0\xcf\x11\xe0",), "xls": (b"\xd0\xcf\x11\xe0",),
}
# Plain-text formats have no reliable signature — accepted on extension alone.
_MAGIC_SKIP = {"txt", "csv"}


def content_matches(ext, head):
    """True if the leading bytes are consistent with the claimed extension."""
    ext = (ext or "").lower()
    if ext in _MAGIC_SKIP:
        return True
    if ext in ("tif", "tiff"):
        return head[:4] in (b"II*\x00", b"MM\x00*")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == "heic":
        return head[4:8] == b"ftyp"
    sigs = _MAGIC.get(ext)
    if not sigs:
        return True
    return any(head.startswith(s) for s in sigs)

MAX_FILE_BYTES = 32 * 1024 * 1024  # matches MAX_CONTENT_LENGTH


def _safe_component(text):
    """Filesystem-safe folder component for a record name / event id."""
    s = re.sub(r"[^A-Za-z0-9_.\-]+", "_", str(text)).strip("._")
    return s or "_"


def _uploads_root(data_dir=None):
    base = data_dir or current_app.config["DATA_DIR"]
    return os.path.join(base, "uploads")


def event_dir(pid, record_name, event_id, data_dir=None):
    return os.path.join(_uploads_root(data_dir), str(int(pid)),
                        _safe_component(record_name), str(int(event_id)))


def original_name(stored):
    """<field>__<rand>__<original>  ->  <original>."""
    parts = (stored or "").split("__", 2)
    return parts[2] if len(parts) == 3 else (stored or "")


def allowed(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXT


def save_upload(pid, record_name, event_id, field_name, storage, data_dir=None):
    """Save an uploaded file. Returns (stored_name, error).
    On success error is None; on failure stored_name is None."""
    original = secure_filename(storage.filename or "")
    if not original:
        return None, "The uploaded file has no valid name."
    if not allowed(original):
        return None, ("File type not allowed. Use an image, PDF, Word, text, "
                      "or spreadsheet file.")
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    try:
        head = storage.stream.read(32)
        storage.stream.seek(0)
    except (OSError, ValueError):
        head = b""
    if not content_matches(ext, head):
        return None, ("The file's contents don't match its extension. Please "
                      "upload a genuine image, PDF, or document.")
    directory = event_dir(pid, record_name, event_id, data_dir)
    os.makedirs(directory, exist_ok=True)
    stored = f"{_safe_component(field_name)}__{secrets.token_hex(4)}__{original}"
    path = os.path.join(directory, stored)
    storage.save(path)
    if os.path.getsize(path) > MAX_FILE_BYTES:
        os.remove(path)
        return None, "File is too large (max 32 MB)."
    return stored, None


def delete_stored(pid, record_name, event_id, stored_name, data_dir=None):
    if not stored_name:
        return
    path = os.path.join(event_dir(pid, record_name, event_id, data_dir),
                        os.path.basename(stored_name))
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def delete_record_files(pid, record_name, data_dir=None):
    """Remove all uploaded files for a record (used when a record is deleted)."""
    import shutil
    directory = os.path.join(_uploads_root(data_dir), str(int(pid)),
                             _safe_component(record_name))
    shutil.rmtree(directory, ignore_errors=True)


def delete_project_files(pid, data_dir=None):
    """Remove every uploaded file for a project (used when a project is deleted)."""
    import shutil
    directory = os.path.join(_uploads_root(data_dir), str(int(pid)))
    shutil.rmtree(directory, ignore_errors=True)
