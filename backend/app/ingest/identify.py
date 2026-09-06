"""File identification by magic bytes with extension fallback."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

IMAGE_MAGIC = {
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF8": "image/gif",
    b"BM": "image/bmp",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
    b"RIFF": "image/webp",
}

EXT_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@dataclass
class FileIdentity:
    file_type: str  # pdf | image | unknown
    mime_type: str


def identify_file(path: Path, filename: str | None = None) -> FileIdentity:
    with path.open("rb") as f:
        head = f.read(16)
    if head.startswith(b"%PDF"):
        return FileIdentity("pdf", "application/pdf")
    for magic, mime in IMAGE_MAGIC.items():
        if head.startswith(magic):
            if mime == "image/webp" and head[8:12] != b"WEBP":
                continue
            return FileIdentity("image", mime)
    ext = Path(filename or path.name).suffix.lower()
    mime = EXT_MIME.get(ext)
    if mime == "application/pdf":
        return FileIdentity("pdf", mime)
    if mime:
        return FileIdentity("image", mime)
    return FileIdentity("unknown", "application/octet-stream")
