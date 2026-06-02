"""V1 storage helper — base64 → disk for screenshot uploads.
Files live under UPLOAD_DIR and are served via /api/files/{filename}.
"""
from __future__ import annotations

import base64
import os
import re
import uuid
from pathlib import Path
from typing import Optional, Tuple

ALLOWED_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_BYTES = 4 * 1024 * 1024  # 4MB

_DATA_URI_RE = re.compile(r"^data:(?P<mime>[\w./+\-]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)$")


def _upload_dir() -> Path:
    p = Path(os.environ.get("UPLOAD_DIR", "/app/backend/uploads"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_data_uri(data_uri: str, namespace: str = "img") -> str:
    """Decode a data: URI and save to disk. Returns the public URL path.
    Raises ValueError on malformed input or unsupported mime / oversize.
    """
    m = _DATA_URI_RE.match(data_uri.strip() if data_uri else "")
    if not m:
        raise ValueError("invalid_data_uri")
    mime = m.group("mime").lower()
    ext = ALLOWED_MIME.get(mime)
    if not ext:
        raise ValueError(f"unsupported_mime:{mime}")
    raw = base64.b64decode(m.group("data"), validate=True)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"file_too_large:{len(raw)}_bytes")
    name = f"{namespace}_{uuid.uuid4().hex}.{ext}"
    out = _upload_dir() / name
    out.write_bytes(raw)
    return f"/api/files/{name}"


def get_file_path(name: str) -> Optional[Path]:
    safe = Path(name).name
    p = _upload_dir() / safe
    return p if p.is_file() else None
